#!/usr/bin/env python3
"""Fail-closed verification of an exported actual-pytest collection-only proof."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.ci.collect_heavy_cases import SCHEMA_VERSION, make_collection_proof
from scripts.ci.partition_heavy_pytest_cases import HEAVY_MODULES, verify_case_shard_manifests


def verify_collection_proof(data: object, *, expected_sha: str) -> int:
    if not isinstance(data, dict):
        raise ValueError("proof must be a JSON object")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("incorrect proof schema")
    if data.get("proof_kind") != "PYTEST_COLLECTION_ONLY":
        raise ValueError("incorrect proof kind")
    if data.get("source_sha") != expected_sha:
        raise ValueError("proof is not pinned to the exact checkout SHA")
    if data.get("markexpr") != "not slow":
        raise ValueError("proof marker filter mismatch")
    if data.get("modules") != list(HEAVY_MODULES):
        raise ValueError("proof module scope mismatch")
    manifests = data.get("manifests")
    if not isinstance(manifests, list) or len(manifests) != 8:
        raise ValueError("proof requires exactly eight shard manifests")

    observed = verify_case_shard_manifests(manifests)
    full = manifests[0]["full_nodeids"]
    expected = make_collection_proof(full, source_sha=expected_sha)
    if manifests != expected["manifests"]:
        raise ValueError("manifest partition does not match the deterministic plan")
    if data.get("selected_case_count") != observed:
        raise ValueError("case count does not match full collected universe")
    if data.get("module_case_counts") != expected["module_case_counts"]:
        raise ValueError("per-module case counts do not match collection")
    return observed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--expected-sha", required=True)
    options = parser.parse_args()
    try:
        data = json.loads(options.artifact.read_text(encoding="utf-8"))
        count = verify_collection_proof(data, expected_sha=options.expected_sha)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(1, f"FAIL heavy-case collection proof: {exc}\n")
    print(f"PASS heavy-case collection proof: {count} test IDs, 8 disjoint partitions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
