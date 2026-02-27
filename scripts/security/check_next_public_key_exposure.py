#!/usr/bin/env python3
"""Fail CI when public Next.js environment variables look like secrets.

This script checks source files for `NEXT_PUBLIC_...` variable names that include
sensitive suffixes (for example, `KEY`, `TOKEN`, or `SECRET`). Such variables are
embedded into browser bundles by design and must not store confidential values.
"""

from __future__ import annotations

import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

CHECK_EXTENSIONS = {
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".json",
    ".env",
    ".example",
}

SKIP_DIRS = {
    ".git",
    "node_modules",
    ".next",
    "dist",
    "build",
    "coverage",
}

TARGET_DIRS = [
    REPO_ROOT / "frontend",
    REPO_ROOT / ".github",
]

DISALLOWED_PATTERN = re.compile(
    r"NEXT_PUBLIC_[A-Z0-9_]*(KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*"
)


def _iter_files() -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for target in TARGET_DIRS:
        if not target.exists():
            continue

        for path in target.rglob("*"):
            if not path.is_file():
                continue
            if any(part in SKIP_DIRS for part in path.parts):
                continue

            suffix = path.suffix.lower()
            if suffix in CHECK_EXTENSIONS or path.name.startswith(".env"):
                files.append(path)
    return files


def _scan_file(path: pathlib.Path) -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = []
    content = path.read_text(encoding="utf-8", errors="ignore")
    for line_number, line in enumerate(content.splitlines(), start=1):
        if "NEXT_PUBLIC_" not in line:
            continue
        if DISALLOWED_PATTERN.search(line):
            findings.append((line_number, line.strip()))
    return findings


def main() -> int:
    violations: list[tuple[pathlib.Path, int, str]] = []
    for file_path in _iter_files():
        for line_number, line in _scan_file(file_path):
            violations.append((file_path, line_number, line))

    if not violations:
        print("No disallowed NEXT_PUBLIC secret-like variable names found.")
        return 0

    print("Disallowed NEXT_PUBLIC secret-like variable names detected:")
    for file_path, line_number, line in violations:
        relative = file_path.relative_to(REPO_ROOT)
        print(f"- {relative}:{line_number}: {line}")

    print(
        "\nUse server-side environment variables (without NEXT_PUBLIC_) for "
        "sensitive values."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
