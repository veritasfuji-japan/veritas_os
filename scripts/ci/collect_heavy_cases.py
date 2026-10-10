"""Capture a bounded, collection-only proof from real pytest items.

This plugin never deselects, executes, or moves tests. Invoke explicitly via
python -m pytest --collect-only -m 'not slow' -p scripts.ci.collect_heavy_cases
with exactly the two heavy modules as positional paths.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ci.partition_heavy_pytest_cases import (
    HEAVY_MODULES,
    make_case_shard_manifests,
    verify_case_shard_manifests,
)

SCHEMA_VERSION = 1


def make_collection_proof(nodeids: list[str], *, source_sha: str) -> dict:
    """Build a complete plan from collected nodeids, never from a canned fixture."""
    if not isinstance(source_sha, str) or len(source_sha) != 40:
        raise ValueError("source SHA must be a 40-character exact commit ID")
    if any(char not in "0123456789abcdef" for char in source_sha):
        raise ValueError("source SHA must be lowercase hexadecimal")
    manifests = make_case_shard_manifests(nodeids, shard_count=8)
    count = verify_case_shard_manifests(manifests)
    return {
        "schema_version": SCHEMA_VERSION,
        "proof_kind": "PYTEST_COLLECTION_ONLY",
        "source_sha": source_sha,
        "markexpr": "not slow",
        "modules": list(HEAVY_MODULES),
        "selected_case_count": count,
        "module_case_counts": {
            module: sum(n.startswith(module + "::") for n in nodeids)
            for module in HEAVY_MODULES
        },
        "manifests": manifests,
    }


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("heavy-case-collection-proof")
    group.addoption(
        "--heavy-case-proof-output",
        type=Path,
        default=None,
        help="Write fail-closed collection-only proof to this JSON file.",
    )
    group.addoption(
        "--heavy-case-source-sha",
        default=None,
        help="Exact checkout SHA to pin the collection proof.",
    )


def pytest_collection_finish(session: pytest.Session) -> None:
    config = session.config
    path = config.getoption("heavy_case_proof_output")
    if path is None:
        return
    if not config.getoption("collectonly"):
        raise pytest.UsageError("heavy-case proof requires --collect-only")
    if config.getoption("markexpr").strip() != "not slow":
        raise pytest.UsageError("heavy-case proof requires exact '-m not slow'")
    if list(config.args) != list(HEAVY_MODULES):
        raise pytest.UsageError("heavy-case proof requires exactly the two pinned modules")
    try:
        proof = make_collection_proof(
            [item.nodeid for item in session.items],
            source_sha=config.getoption("heavy_case_source_sha"),
        )
    except (ValueError, TypeError) as exc:
        raise pytest.UsageError(f"heavy-case collection proof failed: {exc}") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(proof, sort_keys=True, indent=2) + "\n", encoding="utf-8")
