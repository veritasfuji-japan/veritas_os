#!/usr/bin/env python3
"""Independently verify complete, disjoint slow-suite shards; fail closed."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

if __package__:
    from .validate_pytest_slow_junit import validate_junit
else:
    from validate_pytest_slow_junit import validate_junit


def verify_shards(root: Path, *, shard_count: int, min_cases: int) -> tuple[int, int]:
    if shard_count < 1 or min_cases < 1:
        raise ValueError("shard-count and min-cases must be positive")
    dirs = sorted(path for path in root.iterdir() if path.is_dir()) if root.is_dir() else []
    expected = {f"pytest-slow-py312-shard-{i}" for i in range(1, shard_count + 1)}
    if {path.name for path in dirs} != expected:
        raise ValueError("incomplete or unexpected slow shard artifacts")

    universe: set[str] | None = None
    selected: Counter[str] = Counter()
    junit_ids: Counter[tuple[str, str]] = Counter()
    passed = skipped = 0
    for directory in dirs:
        data = json.loads((directory / "slow-shard-manifest.json").read_text(encoding="utf-8"))
        index = int(directory.name.rsplit("-", 1)[1])
        if data.get("schema_version") != 1 or data.get("shard_index") != index or data.get("shard_count") != shard_count:
            raise ValueError(f"invalid shard metadata: {directory}")
        full = data.get("full_nodeids")
        part = data.get("selected_nodeids")
        observed = data.get("reported_nodeids")
        for group in (full, part, observed):
            if (not isinstance(group, list) or not group
                    or any(not isinstance(n, str) or not n for n in group)
                    or len(set(group)) != len(group)):
                raise ValueError(f"invalid/empty/duplicate test identities: {directory}")
        current = set(full)
        if universe is None:
            universe = current
        elif current != universe:
            raise ValueError("full slow collections differ between shards")
        if set(part) != set(observed) or not set(part) <= current:
            raise ValueError(f"selected vs executed node IDs mismatch: {directory}")
        selected.update(part)

        junit = directory / "pytest-slow.xml"
        executed, skip, _ = validate_junit(junit)
        cases = ET.parse(junit).getroot().findall(".//testcase")
        if len(cases) != len(part) or executed + skip != len(part):
            raise ValueError(f"JUnit testcase count differs from selected IDs: {directory}")
        for case in cases:
            identity = (case.get("classname", ""), case.get("name", ""))
            if not all(identity):
                raise ValueError("JUnit testcase missing classname or name")
            junit_ids[identity] += 1
        passed += executed
        skipped += skip

    assert universe is not None
    if len(universe) < min_cases:
        raise ValueError(f"slow suite fell below minimum {min_cases} cases")
    if set(selected) != universe or any(v != 1 for v in selected.values()):
        raise ValueError("missing or duplicated test node IDs across shards")
    if any(v != 1 for v in junit_ids.values()):
        raise ValueError("duplicated JUnit testcase identities")
    if passed + skipped != len(universe):
        raise ValueError("JUnit totals do not match complete slow collection")
    return passed, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--shard-count", type=int, required=True)
    parser.add_argument("--min-cases", type=int, required=True)
    args = parser.parse_args()
    try:
        passed, skipped = verify_shards(args.root, shard_count=args.shard_count, min_cases=args.min_cases)
    except (OSError, ValueError, TypeError, KeyError, ET.ParseError) as exc:
        parser.exit(1, f"slow shard proof FAILED: {exc}\n")
    print(f"Slow shard proof PASS: {passed} executed, {skipped} skipped; disjoint and complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
