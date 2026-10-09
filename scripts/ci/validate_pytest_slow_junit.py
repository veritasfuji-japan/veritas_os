#!/usr/bin/env python3
"""Fail closed unless the slow-suite JUnit artifact contains executed tests.

JUnit is evidence for future, strictly coverage-preserving slow-test sharding.
Do not infer pass/fail from a summary alone: the pytest exit status remains
authoritative and this independent check rejects missing, empty or malformed
JUnit evidence even if pytest unexpectedly exits zero.
"""

from __future__ import annotations

import argparse
import math
import xml.etree.ElementTree as ET
from pathlib import Path


def validate_junit(path: Path) -> tuple[int, int, float]:
    """Return (executed, skipped, measured seconds) for a valid JUnit report."""
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise ValueError(f"slow JUnit unreadable: {path}") from exc

    if root.tag not in {"testsuite", "testsuites"}:
        raise ValueError(f"unsupported JUnit root element: {root.tag}")

    cases = root.findall(".//testcase")
    if not cases:
        raise ValueError("slow JUnit contains no testcases")

    skipped = 0
    total_seconds = 0.0
    for case in cases:
        if case.find("failure") is not None or case.find("error") is not None:
            raise ValueError("slow JUnit contains failing or errored testcases")
        raw_seconds = case.get("time")
        try:
            duration = float(raw_seconds) if raw_seconds is not None else float("nan")
        except ValueError as exc:
            raise ValueError("slow JUnit testcase has invalid duration") from exc
        if not math.isfinite(duration) or duration < 0:
            raise ValueError("slow JUnit testcase has non-finite or negative duration")
        total_seconds += duration
        if case.find("skipped") is not None:
            skipped += 1

    executed = len(cases) - skipped
    if executed == 0:
        raise ValueError("slow JUnit contains no executed (non-skipped) tests")
    return executed, skipped, total_seconds


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    try:
        executed, skipped, seconds = validate_junit(args.path)
    except ValueError as exc:
        parser.exit(1, f"{exc}\n")
    print(
        f"Slow suite JUnit: {executed} executed, {skipped} skipped, "
        f"{seconds:.3f}s summed testcase time."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
