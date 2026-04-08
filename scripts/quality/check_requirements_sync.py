#!/usr/bin/env python3
"""Validate dependency name sync between pyproject extras and requirements.txt.

This guard enforces that ``veritas_os/requirements.txt`` stays aligned with the
packages resolved by ``pyproject.toml``'s core dependencies plus the ``full``
extra closure. Version-pinning strategy can differ between files; this checker
intentionally validates normalized package *names* to prevent silent drift.
"""

from __future__ import annotations

import pathlib
import re
import sys
import tomllib
from collections.abc import Mapping

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
REQUIREMENTS_PATH = REPO_ROOT / "veritas_os" / "requirements.txt"

_SELF_PACKAGE = "veritas-os"
_NAME_SPLIT_PATTERN = re.compile(r"[<>=!~;\s]")
_NORMALIZE_PATTERN = re.compile(r"[-_.]+")


def normalize_name(raw_name: str) -> str:
    """Return a canonicalized dependency name suitable for set comparisons."""
    return _NORMALIZE_PATTERN.sub("-", raw_name.strip().lower())


def extract_dependency_name(spec: str) -> str:
    """Extract package name from a dependency specification string."""
    candidate = _NAME_SPLIT_PATTERN.split(spec.strip(), maxsplit=1)[0]
    name_only = candidate.split("[", maxsplit=1)[0]
    return normalize_name(name_only)


def _expand_extra(
    extra: str,
    optional_deps: Mapping[str, list[str]],
    visited: set[str],
) -> set[str]:
    """Recursively expand package names declared by an optional dependency extra."""
    if extra in visited:
        return set()

    visited.add(extra)
    expanded: set[str] = set()

    for spec in optional_deps.get(extra, []):
        dep_name = extract_dependency_name(spec)
        if dep_name != _SELF_PACKAGE:
            expanded.add(dep_name)
            continue

        nested_match = re.search(r"\[(.+?)\]", spec)
        if not nested_match:
            continue
        nested_extras = [token.strip() for token in nested_match.group(1).split(",")]
        for nested_extra in nested_extras:
            expanded.update(_expand_extra(nested_extra, optional_deps, visited))

    return expanded


def expected_dependency_names(pyproject_data: dict[str, object]) -> set[str]:
    """Build expected dependency-name set from core + full extra dependencies."""
    project_table = pyproject_data.get("project")
    if not isinstance(project_table, dict):
        raise ValueError("[project] table is missing in pyproject.toml")

    dependencies = project_table.get("dependencies", [])
    optional_deps = project_table.get("optional-dependencies", {})
    if not isinstance(dependencies, list) or not isinstance(optional_deps, dict):
        raise ValueError("[project] dependency fields are malformed")

    expected = {extract_dependency_name(spec) for spec in dependencies}
    expected.update(_expand_extra("full", optional_deps, visited=set()))
    return expected


def requirements_dependency_names(requirements_content: str) -> set[str]:
    """Parse normalized dependency names from requirements.txt content."""
    names: set[str] = set()
    for raw_line in requirements_content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        names.add(extract_dependency_name(line))
    return names


def main() -> int:
    """Run requirements sync check and print actionable drift diagnostics."""
    if not PYPROJECT_PATH.exists() or not REQUIREMENTS_PATH.exists():
        print("[SYNC] Required dependency manifest file is missing.")
        return 1

    pyproject_data = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    expected = expected_dependency_names(pyproject_data)
    actual = requirements_dependency_names(REQUIREMENTS_PATH.read_text(encoding="utf-8"))

    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)

    if not missing and not unexpected:
        print("Dependency manifests are in sync (name-level).")
        return 0

    print("[SYNC] requirements.txt is out of sync with pyproject full dependency set:")
    for pkg in missing:
        print(f"- missing in requirements.txt: {pkg}")
    for pkg in unexpected:
        print(f"- unexpected in requirements.txt: {pkg}")

    print(
        "Hint: align veritas_os/requirements.txt with pyproject.toml "
        "([project.dependencies] + [project.optional-dependencies].full).",
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
