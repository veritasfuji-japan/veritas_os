#!/usr/bin/env python3
"""Deterministic, test-ID-complete plan for *future* heavy-module case sharding.

This module does not change pytest selection or GitHub Actions. It establishes
one bounded design invariant before any CI integration: every collected case
from the two pinned modules has exactly one planned owner, regardless of
collection order. Runtime execution and JUnit proof are out of scope.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Mapping

HEAVY_MODULES = (
    "veritas_os/tests/test_canonical_promotion_live_adapter_dry_run_bind_authorization_gate_review.py",
    "veritas_os/tests/test_canonical_promotion_live_adapter_dry_run_final_bind_authorization_readiness.py",
)

# Exact-main PR #2351 JUnit (run 38005996954). Conservative minima, not a
# claim that pytest collection on another SHA is automatically identical.
BASELINE_MINIMUM = {
    HEAVY_MODULES[0]: 89,
    HEAVY_MODULES[1]: 76,
}


def _normalized_universe(
    nodeids: Iterable[str],
    *,
    modules: tuple[str, ...],
    minimums: Mapping[str, int],
) -> tuple[list[str], dict[str, list[str]]]:
    if not modules or len(set(modules)) != len(modules):
        raise ValueError("expected distinct, nonempty target module names")
    provided = list(nodeids)
    if not provided or any(not isinstance(n, str) or "::" not in n for n in provided):
        raise ValueError("case node IDs must be nonempty pytest nodeids")
    if len(set(provided)) != len(provided):
        raise ValueError("duplicate pytest case ID in complete collection")
    group: dict[str, list[str]] = {module: [] for module in modules}
    for nodeid in provided:
        module, _, name = nodeid.partition("::")
        if module not in group or not name:
            raise ValueError(f"out-of-scope or invalid test case: {nodeid}")
        group[module].append(nodeid)
    if set(minimums) != set(group):
        raise ValueError("minimums must explicitly cover every target module")
    for module, cases in group.items():
        floor = minimums[module]
        if isinstance(floor, bool) or not isinstance(floor, int) or floor < 1:
            raise ValueError("minimums must be positive integers")
        if len(cases) < floor:
            raise ValueError(
                f"selected cases for {module} fell below pinned floor "
                f"{floor}: found {len(cases)}"
            )
        group[module] = sorted(cases)
    return sorted(provided), group


def make_case_shard_manifests(
    nodeids: Iterable[str],
    *,
    shard_count: int = 8,
    modules: tuple[str, ...] = HEAVY_MODULES,
    minimums: Mapping[str, int] | None = None,
) -> list[dict]:
    """Return deterministic manifests; never silently omit a test case."""
    if isinstance(shard_count, bool) or not isinstance(shard_count, int) or shard_count < 2:
        raise ValueError("shard_count must be an integer >= 2")
    if minimums is None:
        minimums = BASELINE_MINIMUM
    universe, grouped = _normalized_universe(nodeids, modules=modules, minimums=minimums)
    fingerprint = hashlib.sha256(
        json.dumps(universe, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    selected: list[list[str]] = [[] for _ in range(shard_count)]
    # Per-module round robin is stable under different collection input orders
    # and avoids assigning an entire heavyweight module to one shard.
    for module in modules:
        for offset, nodeid in enumerate(grouped[module]):
            selected[offset % shard_count].append(nodeid)
    manifests = [
        {
            "schema_version": 1,
            "shard_index": index + 1,
            "shard_count": shard_count,
            "modules": list(modules),
            # Copy the universe so mutation of one manifest cannot affect peers.
            "full_nodeids": list(universe),
            "selected_nodeids": sorted(cases),
            "universe_sha256": fingerprint,
        }
        for index, cases in enumerate(selected)
    ]
    verify_case_shard_manifests(manifests)
    return manifests


def verify_case_shard_manifests(manifests: Iterable[Mapping]) -> int:
    """Validate mutually consistent manifests for complete disjoint ownership."""
    plans = list(manifests)
    if not plans:
        raise ValueError("case shard manifests are missing")
    count = plans[0].get("shard_count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 2:
        raise ValueError("invalid case shard count")
    if len(plans) != count:
        raise ValueError("missing or extra case shard manifest")
    expected_index = set(range(1, count + 1))
    indices = [m.get("shard_index") for m in plans]
    if any(isinstance(i, bool) or not isinstance(i, int) for i in indices):
        raise ValueError("invalid case shard index")
    if set(indices) != expected_index or len(set(indices)) != count:
        raise ValueError("case shard indices are not distinct and complete")

    anchor = plans[0]
    full = anchor.get("full_nodeids")
    if not isinstance(full, list) or not full or any(not isinstance(n, str) for n in full):
        raise ValueError("case universe missing or malformed")
    if len(set(full)) != len(full):
        raise ValueError("case universe contains duplicates")
    fingerprint = hashlib.sha256(
        json.dumps(sorted(full), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    owners: Counter[str] = Counter()
    for plan in plans:
        if plan.get("schema_version") != 1 or plan.get("shard_count") != count:
            raise ValueError("inconsistent shard schema/count")
        if plan.get("full_nodeids") != full or plan.get("modules") != anchor.get("modules"):
            raise ValueError("different full collections between shards")
        if plan.get("universe_sha256") != fingerprint:
            raise ValueError("case universe fingerprint mismatch")
        part = plan.get("selected_nodeids")
        if not isinstance(part, list) or not part or any(not isinstance(n, str) for n in part):
            raise ValueError("empty or malformed case selection")
        owners.update(part)
    if set(owners) != set(full) or any(v != 1 for v in owners.values()):
        raise ValueError("missing or duplicate case ownership")
    return len(full)
