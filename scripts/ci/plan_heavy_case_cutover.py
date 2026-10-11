#!/usr/bin/env python3
"""Plan-only, fail-closed handoff from Python 3.12 file shards to heavy case shards.

No pytest tests are deselected or executed here, and no existing CI job is
modified. The prospective handoff is accepted only when every discoverable
test *file* has one owner: ordinary 8-way file-sharding, or the two frozen
heavy modules represented by their complete pytest collection node IDs.
Python 3.11 and slow suites are explicitly outside this proposed cutover.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Mapping, Sequence

from scripts.ci.partition_heavy_pytest_cases import HEAVY_MODULES
from scripts.ci.select_pytest_shard import (
    DEFAULT_ROOTS,
    discover_test_files,
    load_historical_durations,
    partition_test_files,
)
from scripts.ci.validate_heavy_case_collection import verify_collection_proof

PY312_DURATION_SEED = Path("scripts/ci/pytest-file-durations-py312.json")
SHARD_COUNT = 8
SCHEMA_VERSION = 1
KIND = "PY312_FILE_TO_CASE_CUTOVER_PREFLIGHT_ONLY"


def _digest(names: list[str]) -> str:
    return hashlib.sha256(
        json.dumps(names, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _compose(
    files: Sequence[Path],
    collection_proof: dict,
    *,
    expected_sha: str,
    historical: Mapping[str, float],
) -> dict:
    if verify_collection_proof(collection_proof, expected_sha=expected_sha) < 165:
        raise ValueError("heavy-case collection unexpectedly shrank")
    if (
        not files
        or any(not isinstance(path, Path) for path in files)
        or any(path.is_absolute() or ".." in path.parts for path in files)
    ):
        raise ValueError("file universe must contain relative repository paths")

    all_names = sorted(path.as_posix() for path in files)
    if len(set(all_names)) != len(all_names):
        raise ValueError("duplicate file in complete discovered test universe")
    if any(all_names.count(module) != 1 for module in HEAVY_MODULES):
        raise ValueError("both heavy modules must occur exactly once in file discovery")

    ordinary_files = [
        path for path in files if path.as_posix() not in HEAVY_MODULES
    ]
    if len(ordinary_files) < SHARD_COUNT:
        raise ValueError("insufficient ordinary files for a complete 8-way plan")

    assigned = partition_test_files(
        ordinary_files, shard_count=SHARD_COUNT, historical=historical,
        avoid_duplicate_test_basenames=True,
    )
    normal: list[dict] = []
    owners: Counter[str] = Counter()
    for shard_index, shard in enumerate(assigned, start=1):
        if not shard:
            raise ValueError("empty normal file shard")
        filenames = sorted(path.as_posix() for path in shard)
        if len({path.name for path in shard}) != len(shard):
            raise ValueError("same-basename collection collision within shard")
        if set(filenames).intersection(HEAVY_MODULES):
            raise ValueError("heavy module leaked into normal Python 3.12 file shard")
        owners.update(filenames)
        normal.append({"shard_index": shard_index, "selected_files": filenames})

    expected_normal = set(all_names) - set(HEAVY_MODULES)
    if set(owners) != expected_normal or any(v != 1 for v in owners.values()):
        raise ValueError("ordinary file ownership missing, duplicated or out of scope")

    plans = collection_proof["manifests"]
    case_owners: Counter[str] = Counter()
    handoff: list[dict] = []
    for index, plan in enumerate(plans, start=1):
        if plan.get("shard_index") != index:
            raise ValueError("heavy-case shard index not canonical")
        selected = plan["selected_nodeids"]
        if not selected:
            raise ValueError("empty prospective heavy-case shard")
        case_owners.update(selected)
        handoff.append({
            "shard_index": index,
            "selected_nodeids": list(selected),
            "universe_sha256": plan["universe_sha256"],
        })

    expected_cases = set(plans[0]["full_nodeids"])
    if (
        set(case_owners) != expected_cases
        or any(v != 1 for v in case_owners.values())
    ):
        raise ValueError("heavy-case handoff has missing or duplicate ownership")
    if any(
        not any(nodeid.startswith(module + "::") for module in HEAVY_MODULES)
        for nodeid in expected_cases
    ):
        raise ValueError("heavy-case ownership escaped pinned modules")

    return {
        "schema_version": SCHEMA_VERSION,
        "plan_kind": KIND,
        "source_sha": expected_sha,
        "markexpr": "not slow",
        "scope": "python3.12_only",
        "normal_shard_count": SHARD_COUNT,
        "heavy_shard_count": SHARD_COUNT,
        "heavy_modules": list(HEAVY_MODULES),
        "full_test_files": all_names,
        "full_file_sha256": _digest(all_names),
        "ordinary_file_shards": normal,
        "heavy_case_shards": handoff,
        "heavy_case_count": len(expected_cases),
    }


def build_cutover_plan(
    files: Sequence[Path],
    collection_proof: dict,
    *,
    expected_sha: str,
    historical: Mapping[str, float],
) -> dict:
    """Build a prospective, exact-checkout file-to-case ownership preflight."""
    return _compose(
        files, collection_proof, expected_sha=expected_sha, historical=historical
    )


def verify_cutover_plan(
    proposal: object,
    files: Sequence[Path],
    collection_proof: dict,
    *,
    expected_sha: str,
    historical: Mapping[str, float],
) -> tuple[int, int]:
    """Reject proposed ownership if it differs from a new deterministic plan."""
    if not isinstance(proposal, dict):
        raise ValueError("cutover preflight plan must be a JSON object")
    expected = _compose(
        files, collection_proof, expected_sha=expected_sha, historical=historical
    )
    if proposal != expected:
        raise ValueError("cutover plan differs from actual file/case discovery")
    return len(expected["full_test_files"]), expected["heavy_case_count"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("collection_proof", type=Path)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        proof = json.loads(args.collection_proof.read_text(encoding="utf-8"))
        actual_files = discover_test_files(DEFAULT_ROOTS)
        historical = load_historical_durations(PY312_DURATION_SEED)
        plan = build_cutover_plan(
            actual_files, proof, expected_sha=args.expected_sha, historical=historical
        )
        count_files, count_cases = verify_cutover_plan(
            plan, actual_files, proof, expected_sha=args.expected_sha,
            historical=historical,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        parser.exit(1, f"FAIL file-to-case cutover preflight: {exc}\n")
    print(
        f"PASS file-to-case cutover preflight: {count_files} discovered files, "
        f"{count_cases} heavy test IDs, 8+8 prospective owner shards; "
        "existing CI execution unchanged"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
