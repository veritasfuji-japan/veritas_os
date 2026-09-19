#!/usr/bin/env python3
"""Run the required F-01 through F-08 security closure regression gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "security" / "integrated_security_closure_v1.json"
EXPECTED_FINDINGS = {f"F-{index:02d}" for index in range(1, 9)}


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    """Load and validate the integrated security closure manifest."""
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("format_version") != "veritas-integrated-security-closure/v1":
        raise ValueError("unsupported integrated security closure format")
    if manifest.get("status") != "REQUIRED_SECURITY_REGRESSION_GATE":
        raise ValueError("integrated security closure gate is not required")

    findings = manifest.get("findings")
    if not isinstance(findings, dict) or set(findings) != EXPECTED_FINDINGS:
        raise ValueError("integrated security closure must cover exactly F-01 through F-08")

    targets = regression_targets(manifest)
    if not targets or len(targets) != len(set(targets)):
        raise ValueError("integrated security closure targets must be non-empty and unique")

    declared_targets = set(targets)
    for finding, finding_targets in findings.items():
        if not isinstance(finding_targets, list) or not finding_targets:
            raise ValueError(f"{finding} must declare at least one regression target")
        if not set(finding_targets).issubset(declared_targets):
            raise ValueError(f"{finding} references an undeclared regression target")

    for target in targets:
        file_part = target.split("::", maxsplit=1)[0]
        if not (REPO_ROOT / file_part).is_file():
            raise ValueError(f"security closure target does not exist: {file_part}")
    return manifest


def regression_targets(manifest: dict[str, Any]) -> list[str]:
    """Return the ordered pytest targets from the manifest."""
    security_targets = manifest.get("security_regression_targets")
    boundary_targets = manifest.get("preserved_boundary_targets")
    if not isinstance(security_targets, list) or not isinstance(boundary_targets, list):
        raise ValueError("security and boundary targets must be lists")
    return [str(target) for target in (*security_targets, *boundary_targets)]


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the VERITAS integrated security closure regression gate."
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print the ordered pytest targets without running them.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Validate the manifest and run its pytest targets."""
    args = _parse_args(argv or sys.argv[1:])
    try:
        manifest = load_manifest()
        targets = regression_targets(manifest)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Integrated security closure manifest invalid: {exc}", file=sys.stderr)
        return 2

    if args.list:
        for target in targets:
            print(target)
        return 0

    command = [sys.executable, "-m", "pytest", "-q", *targets]
    completed = subprocess.run(command, cwd=REPO_ROOT, check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
