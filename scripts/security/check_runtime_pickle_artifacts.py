#!/usr/bin/env python3
"""Fail CI when legacy pickle-derived artifacts are found in runtime dirs.

This check enforces the runtime policy that `.pkl` / `.joblib` artifacts must not
be placed in MemoryOS runtime paths because pickle deserialization can lead to
arbitrary code execution (RCE). The runtime already blocks loading; this script
adds CI guardrails so risky files are rejected before deployment.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
LEGACY_EXTENSIONS = frozenset({".pkl", ".joblib", ".pickle"})


def _default_scan_dirs() -> list[Path]:
    """Return runtime directories that must not contain pickle/joblib artifacts.

    Includes the current MemoryOS model directory, the historical memory
    directory used by older deployments, and optional `VERITAS_MEMORY_DIR` when
    configured.
    """
    runtime_dirs = [
        REPO_ROOT / "veritas_os" / "core" / "models",
        REPO_ROOT / "veritas_os" / "memory",
    ]
    configured_memory_dir = os.getenv("VERITAS_MEMORY_DIR", "").strip()
    if configured_memory_dir:
        runtime_dirs.append(Path(configured_memory_dir))
    return runtime_dirs


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments for optional scan root overrides."""
    parser = argparse.ArgumentParser(
        description=(
            "Detect legacy .pkl/.joblib artifacts in MemoryOS runtime "
            "directories "
            "and fail if any are present."
        )
    )
    parser.add_argument(
        "--scan-dir",
        dest="scan_dirs",
        action="append",
        default=[],
        help=(
            "Additional directory to scan. Can be passed multiple times."
        ),
    )
    return parser.parse_args(argv)


def _iter_unique_existing_dirs(
    paths: list[Path],
) -> tuple[list[Path], list[Path]]:
    """Return unique existing dirs and non-existing path inputs.

    Returns:
        tuple[list[Path], list[Path]]: Existing directories in first-seen order
        and paths that do not exist.
    """
    unique_dirs: list[Path] = []
    missing_dirs: list[Path] = []
    seen: set[Path] = set()

    for path in paths:
        resolved = path.resolve(strict=False)
        if resolved in seen:
            continue
        if not resolved.exists():
            missing_dirs.append(resolved)
            seen.add(resolved)
            continue
        if not resolved.is_dir():
            seen.add(resolved)
            continue
        seen.add(resolved)
        unique_dirs.append(resolved)

    return unique_dirs, missing_dirs


def _find_legacy_pickles(scan_dirs: list[Path]) -> tuple[list[Path], list[Path]]:
    """Find `.pkl`/`.joblib` files recursively under each scan directory.

    The scan is case-insensitive (`.pkl` / `.PKL`, `.joblib` / `.JOBLIB`) so
    renamed legacy artifacts cannot bypass detection by filename casing alone.
    """
    findings: list[Path] = []
    missing_dirs: list[Path] = []
    directories, missing = _iter_unique_existing_dirs(scan_dirs)
    missing_dirs.extend(missing)

    for directory in directories:
        findings.extend(
            sorted(
                path
                for path in directory.rglob("*")
                if path.is_file() and path.suffix.lower() in LEGACY_EXTENSIONS
            )
        )
    return findings, missing_dirs


def main(argv: list[str] | None = None) -> int:
    """Run the runtime pickle artifact check and return process exit code."""
    parsed = _parse_args(argv or sys.argv[1:])
    scan_dirs = _default_scan_dirs() + [Path(raw) for raw in parsed.scan_dirs]
    findings, missing_dirs = _find_legacy_pickles(scan_dirs)

    if missing_dirs:
        print("[SECURITY] Scan target not found (check deployment path):")
        for missing in missing_dirs:
            try:
                relative = missing.relative_to(REPO_ROOT)
            except ValueError:
                relative = missing
            print(f"- {relative}")
        print("Proceeding with remaining existing directories.\n")

    if not findings:
        print("No legacy runtime pickle artifacts detected in scanned directories.")
        return 0

    print("[SECURITY] Legacy runtime pickle artifacts detected:")
    for file_path in findings:
        try:
            relative = file_path.relative_to(REPO_ROOT)
        except ValueError:
            relative = file_path
        print(f"- {relative}")

    print(
        "\nRemove these files before deployment. Runtime pickle/joblib loading is "
        "disabled due to RCE risk. See docs/en/operations/memory_pickle_migration.md"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
