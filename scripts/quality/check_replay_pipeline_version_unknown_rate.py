#!/usr/bin/env python3
"""Check unknown pipeline version rate in replay reports.

This script enforces an operational guardrail recommended by the code review:
monitor the rate of ``meta.pipeline_version == 'unknown'`` in replay reports.
High unknown rates reduce audit traceability during incident response.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORTS_DIR = REPO_ROOT / "audit" / "replay_reports"
UNKNOWN_VALUE = "unknown"


@dataclass(frozen=True)
class VersionRateResult:
    """Computed replay version quality metrics."""

    total_reports: int
    unknown_reports: int

    @property
    def unknown_rate(self) -> float:
        """Return unknown version ratio in [0, 1]."""
        if self.total_reports <= 0:
            return 0.0
        return self.unknown_reports / self.total_reports


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command-line options."""
    parser = argparse.ArgumentParser(
        description=(
            "Check unknown pipeline version rate in replay reports and fail "
            "when the rate exceeds a configured threshold."
        )
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=DEFAULT_REPORTS_DIR,
        help="Directory that stores replay_*.json reports.",
    )
    parser.add_argument(
        "--max-unknown-rate",
        type=float,
        default=0.0,
        help="Maximum allowed unknown ratio (0.0 - 1.0).",
    )
    return parser.parse_args(argv)


def _extract_pipeline_version(payload: dict[str, object]) -> str:
    """Extract normalized pipeline version from replay payload."""
    meta = payload.get("meta")
    if not isinstance(meta, dict):
        return UNKNOWN_VALUE

    version = meta.get("pipeline_version")
    if isinstance(version, str) and version.strip():
        return version.strip()
    return UNKNOWN_VALUE


def _load_json(path: Path) -> dict[str, object] | None:
    """Load one replay report and return dict payload, or None on parse issues."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(raw, dict):
        return None
    return raw


def _compute_version_rate(reports_dir: Path) -> VersionRateResult:
    """Compute unknown pipeline version rate for replay reports."""
    total = 0
    unknown = 0

    for path in sorted(reports_dir.glob("replay_*.json")):
        payload = _load_json(path)
        if payload is None:
            continue
        total += 1
        if _extract_pipeline_version(payload) == UNKNOWN_VALUE:
            unknown += 1

    return VersionRateResult(total_reports=total, unknown_reports=unknown)


def _validate_rate_threshold(max_unknown_rate: float) -> None:
    """Validate threshold range and raise ``ValueError`` when invalid."""
    if 0.0 <= max_unknown_rate <= 1.0:
        return
    raise ValueError("--max-unknown-rate must be between 0.0 and 1.0")


def main(argv: list[str] | None = None) -> int:
    """Run unknown-rate check and return process exit code."""
    parsed = _parse_args(argv or sys.argv[1:])

    try:
        _validate_rate_threshold(parsed.max_unknown_rate)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2

    reports_dir = parsed.reports_dir.resolve(strict=False)
    if not reports_dir.exists():
        print(f"WARNING: replay reports directory does not exist: {reports_dir}")
        return 0

    result = _compute_version_rate(reports_dir)
    if result.total_reports == 0:
        print(f"WARNING: no replay reports found under {reports_dir}")
        return 0

    rate = result.unknown_rate
    print(
        "Replay pipeline version metrics: "
        f"unknown={result.unknown_reports}/{result.total_reports} "
        f"({rate:.2%})"
    )

    if rate > parsed.max_unknown_rate:
        print(
            "SECURITY WARNING: unknown pipeline version rate exceeded threshold; "
            "audit traceability is degraded. Ensure CI injects "
            "VERITAS_PIPELINE_VERSION and investigate missing Git metadata."
        )
        return 1

    print("OK: unknown pipeline version rate is within threshold.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
