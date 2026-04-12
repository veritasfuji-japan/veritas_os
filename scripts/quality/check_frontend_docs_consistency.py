#!/usr/bin/env python3
"""Validate frontend tech-stack versions documented in README.md match package.json.

Detects version drift between the documentation and the actual frontend
dependencies so external reviewers see accurate information.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
README_PATH = REPO_ROOT / "README.md"
PACKAGE_JSON_PATH = REPO_ROOT / "frontend" / "package.json"

# Map of (README label regex) -> (package.json dependency name).
# The regex should capture the *major.minor* version from the README table row.
VERSION_CHECKS: list[tuple[str, str]] = [
    (r"Next\.js\s+(\d+\.\d+)", "next"),
    (r"TypeScript\s+(\d+\.\d+)", "typescript"),
    (r"Tailwind\s+CSS\s+(\d+\.\d+)", "tailwindcss"),
    (r"eslint-config-next\s+(\d+\.\d+)", "eslint-config-next"),
]


def _parse_major_minor(version_str: str) -> str:
    """Extract major.minor from a semver string like '^5.7.2' or '16.1.7'."""
    match = re.search(r"(\d+\.\d+)", version_str)
    return match.group(1) if match else ""


def check_consistency(readme_text: str, pkg: dict) -> list[str]:
    """Return list of mismatch descriptions (empty = all OK)."""
    all_deps: dict[str, str] = {}
    all_deps.update(pkg.get("dependencies", {}))
    all_deps.update(pkg.get("devDependencies", {}))

    problems: list[str] = []
    for pattern, dep_name in VERSION_CHECKS:
        readme_match = re.search(pattern, readme_text)
        if readme_match is None:
            problems.append(f"README.md does not mention {dep_name} version")
            continue

        readme_ver = readme_match.group(1)
        pkg_ver_raw = all_deps.get(dep_name)
        if pkg_ver_raw is None:
            problems.append(
                f"README.md documents {dep_name} {readme_ver} but "
                f"{dep_name} is not in frontend/package.json"
            )
            continue

        pkg_ver = _parse_major_minor(pkg_ver_raw)
        if readme_ver != pkg_ver:
            problems.append(
                f"Version drift: README.md says {dep_name} {readme_ver}, "
                f"package.json has {pkg_ver_raw} (major.minor={pkg_ver})"
            )

    return problems


def main() -> int:
    """Run the frontend documentation consistency check."""
    if not README_PATH.exists():
        print(f"[DOCS] Missing file: {README_PATH}")
        return 1
    if not PACKAGE_JSON_PATH.exists():
        print(f"[DOCS] Missing file: {PACKAGE_JSON_PATH}")
        return 1

    readme_text = README_PATH.read_text(encoding="utf-8")
    pkg = json.loads(PACKAGE_JSON_PATH.read_text(encoding="utf-8"))

    problems = check_consistency(readme_text, pkg)

    if not problems:
        print("Frontend documentation consistency checks passed.")
        return 0

    print("[DOCS] Frontend documentation / package.json version drift detected:")
    for problem in problems:
        print(f"  - {problem}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
