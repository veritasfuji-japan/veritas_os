#!/usr/bin/env python3
"""Offline, fail-closed contract for planned heavy-case execution evidence.

This validator does NOT execute or repartition pytest. A later, separately
reviewed CI integration must create one manifest and one pytest JUnit XML for
each planned shard. Until then synthetic tests prove only the verifier logic.
"""

from __future__ import annotations

import argparse
import json
import math
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from scripts.ci.partition_heavy_pytest_cases import HEAVY_MODULES
from scripts.ci.validate_heavy_case_collection import verify_collection_proof

SHARD_COUNT = 8
ARTIFACT_PREFIX = "heavy-case-execution-shard-"
ALLOWED_OUTCOMES = frozenset({"passed", "skipped"})


def junit_identity(nodeid: str) -> tuple[str, str]:
    """Expected pytest xunit2 JUnit address for this *two-module* proof domain.

    Nested test classes and custom junit_classname are intentionally outside
    the frozen scope; those require a separate proof-profile revision.
    """
    if not isinstance(nodeid, str) or nodeid.count("::") != 1:
        raise ValueError("unsupported heavy-case pytest node ID")
    module, name = nodeid.split("::")
    if module not in HEAVY_MODULES or not name or not name.startswith("test_"):
        raise ValueError("heavy-case JUnit identity outside frozen proof domain")
    return module.removesuffix(".py").replace("/", "."), name


def _string_set(value: object, *, label: str) -> set[str]:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(n, str) or not n for n in value)
        or len(set(value)) != len(value)
    ):
        raise ValueError(f"empty/duplicate/invalid {label}")
    return set(value)


def _parse_junit(path: Path) -> dict[tuple[str, str], str]:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise ValueError(f"missing or malformed JUnit: {path}") from exc
    if root.tag not in {"testsuite", "testsuites"}:
        raise ValueError("unexpected JUnit root element")
    cases = root.findall(".//testcase")
    if not cases:
        raise ValueError("JUnit evidence contains no testcases")
    outcomes: dict[tuple[str, str], str] = {}
    for case in cases:
        key = case.get("classname", ""), case.get("name", "")
        if not all(key) or key in outcomes:
            raise ValueError("missing or duplicate JUnit testcase identity")
        seconds = case.get("time")
        try:
            duration = float(seconds) if seconds is not None else float("nan")
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid JUnit duration") from exc
        if not math.isfinite(duration) or duration < 0:
            raise ValueError("invalid JUnit duration")
        if case.find("failure") is not None or case.find("error") is not None:
            raise ValueError("JUnit contains a failing or errored test")
        if case.find("rerun") is not None or case.find("flakyFailure") is not None:
            raise ValueError("JUnit contains an unproven retry")
        outcomes[key] = "skipped" if case.find("skipped") is not None else "passed"
    return outcomes


def verify_heavy_execution(
    proof_file: Path, shards_root: Path, *, expected_sha: str
) -> tuple[int, int]:
    """Verify exact JUnit identity/status for every planned node ID, once."""
    proof = json.loads(proof_file.read_text(encoding="utf-8"))
    if verify_collection_proof(proof, expected_sha=expected_sha) < 165:
        raise ValueError("heavy case universe unexpectedly shrank")
    expected_plans = proof["manifests"]
    if len(expected_plans) != SHARD_COUNT:
        raise ValueError("incorrect expected shard count")

    dirs = sorted(shards_root.iterdir()) if shards_root.is_dir() else []
    expected_names = {f"{ARTIFACT_PREFIX}{n}" for n in range(1, SHARD_COUNT + 1)}
    if {x.name for x in dirs} != expected_names or any(not x.is_dir() for x in dirs):
        raise ValueError("missing, extra, or invalid execution shard artifact")

    seen_ids: Counter[str] = Counter()
    all_junit: Counter[tuple[str, str]] = Counter()
    passed = skipped = 0
    for index in range(1, SHARD_COUNT + 1):
        directory = shards_root / f"{ARTIFACT_PREFIX}{index}"
        try:
            manifest = json.loads(
                (directory / "execution-manifest.json").read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"missing/invalid shard execution manifest {index}") from exc
        if not isinstance(manifest, dict):
            raise ValueError("shard manifest must be an object")
        if (
            manifest.get("schema_version") != 1
            or manifest.get("proof_kind") != "PYTEST_EXECUTION_EVIDENCE"
            or manifest.get("source_sha") != expected_sha
            or manifest.get("shard_index") != index
            or manifest.get("shard_count") != SHARD_COUNT
            or manifest.get("universe_sha256")
            != expected_plans[index - 1]["universe_sha256"]
        ):
            raise ValueError(f"wrong exact-checkout shard execution metadata: {index}")

        planned = _string_set(
            expected_plans[index - 1]["selected_nodeids"], label="planned node IDs"
        )
        selected = _string_set(
            manifest.get("selected_nodeids"), label="selected node IDs"
        )
        reported = _string_set(
            manifest.get("reported_nodeids"), label="reported node IDs"
        )
        if selected != planned or reported != planned:
            raise ValueError(f"missing/foreign execution node IDs on shard {index}")

        terminal = manifest.get("terminal_outcomes")
        if (
            not isinstance(terminal, dict)
            or set(terminal) != planned
            or any(outcome not in ALLOWED_OUTCOMES for outcome in terminal.values())
        ):
            raise ValueError(f"invalid/missing terminal outcomes on shard {index}")

        expected_junit = {junit_identity(n): terminal[n] for n in planned}
        if len(expected_junit) != len(planned):
            raise ValueError("colliding JUnit identities for distinct pytest node IDs")
        actual_junit = _parse_junit(directory / "pytest.xml")
        if actual_junit != expected_junit:
            raise ValueError(f"JUnit testcase ID/outcome mismatch on shard {index}")

        seen_ids.update(planned)
        # Counter.update(mapping) adds mapping VALUES (e.g. "passed"), not keys.
        # Count each distinct JUnit identity exactly once instead.
        all_junit.update(actual_junit.keys())
        passed += sum(outcome == "passed" for outcome in actual_junit.values())
        skipped += sum(outcome == "skipped" for outcome in actual_junit.values())

    full = set(expected_plans[0]["full_nodeids"])
    if set(seen_ids) != full or any(v != 1 for v in seen_ids.values()):
        raise ValueError("missing or duplicate executed pytest node IDs")
    if len(all_junit) != len(full) or any(v != 1 for v in all_junit.values()):
        raise ValueError("missing or duplicate global JUnit testcase identity")
    if passed + skipped != len(full):
        raise ValueError("JUnit outcomes do not cover the full case universe")
    return passed, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("collection_proof", type=Path)
    parser.add_argument("execution_artifact_directory", type=Path)
    parser.add_argument("--expected-sha", required=True)
    args = parser.parse_args()
    try:
        passed, skipped = verify_heavy_execution(
            args.collection_proof, args.execution_artifact_directory,
            expected_sha=args.expected_sha,
        )
    except (OSError, ValueError, TypeError, KeyError, ET.ParseError) as exc:
        parser.exit(1, f"FAIL heavy-case JUnit reconciliation: {exc}\n")
    print(
        f"PASS heavy-case JUnit reconciliation: {passed} passed, "
        f"{skipped} skipped, 8 complete disjoint shards"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
