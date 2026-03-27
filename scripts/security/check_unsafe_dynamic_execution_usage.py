#!/usr/bin/env python3
"""Detect unsafe dynamic execution and deserialization usage patterns.

This checker rejects high-risk runtime primitives in production code:
- ``eval(...)``
- ``exec(...)``
- ``pickle.loads(...)``
- ``yaml.load(...)``

Security rationale:
    These APIs increase remote code execution risk when data provenance
    assumptions drift over time. The project policy requires safer alternatives
    (for example, ``yaml.safe_load``) and explicit review before any exception.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCAN_ROOTS = (
    REPO_ROOT / "veritas_os",
    REPO_ROOT / "scripts",
)
SKIP_DIR_NAMES = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".venv",
    "node_modules",
}
SKIP_PATH_PARTS = {"tests"}


@dataclass(frozen=True)
class Violation:
    """Represents one detected dynamic-execution security violation."""

    path: Path
    line: int
    message: str


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command-line options."""
    parser = argparse.ArgumentParser(
        description=(
            "Check Python source for unsafe dynamic execution and "
            "deserialization APIs (eval/exec/pickle.loads/yaml.load)."
        )
    )
    parser.add_argument(
        "--scan-root",
        action="append",
        default=[],
        help="Optional directory/file to scan. Can be provided multiple times.",
    )
    return parser.parse_args(argv)


def _iter_python_files(scan_roots: list[Path]) -> list[Path]:
    """Return Python files under roots while skipping cache/vendor/test dirs."""
    files: list[Path] = []
    for root in scan_roots:
        resolved = root.resolve(strict=False)
        if not resolved.exists():
            continue
        if resolved.is_file() and resolved.suffix == ".py":
            files.append(resolved)
            continue

        for path in resolved.rglob("*.py"):
            if any(part in SKIP_DIR_NAMES for part in path.parts):
                continue
            if any(part in SKIP_PATH_PARTS for part in path.parts):
                continue
            files.append(path)
    return files


def _is_name_call(call: ast.Call, func_name: str) -> bool:
    """Return True if ``call`` targets a plain name (e.g., eval(...))."""
    return isinstance(call.func, ast.Name) and call.func.id == func_name


def _is_attr_call(call: ast.Call, module_name: str, attr_name: str) -> bool:
    """Return True if ``call`` targets a module attribute call."""
    return (
        isinstance(call.func, ast.Attribute)
        and call.func.attr == attr_name
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == module_name
    )


def _scan_file(path: Path) -> list[Violation]:
    """Scan one Python file and return detected violations."""
    source = path.read_text(encoding="utf-8", errors="ignore")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    violations: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        if _is_name_call(node, "eval"):
            violations.append(
                Violation(
                    path=path,
                    line=node.lineno,
                    message="eval(...) is forbidden due to code injection risk",
                )
            )
        if _is_name_call(node, "exec"):
            violations.append(
                Violation(
                    path=path,
                    line=node.lineno,
                    message="exec(...) is forbidden due to code injection risk",
                )
            )
        if _is_attr_call(node, "pickle", "loads"):
            violations.append(
                Violation(
                    path=path,
                    line=node.lineno,
                    message=(
                        "pickle.loads(...) is forbidden for untrusted data; "
                        "use a safe serialization format"
                    ),
                )
            )
        if _is_attr_call(node, "yaml", "load"):
            violations.append(
                Violation(
                    path=path,
                    line=node.lineno,
                    message=(
                        "yaml.load(...) is forbidden; use yaml.safe_load(...) "
                        "with trusted schema validation"
                    ),
                )
            )

    return violations


def main(argv: list[str] | None = None) -> int:
    """Run scan and return shell exit code."""
    parsed = _parse_args(argv or sys.argv[1:])
    scan_roots = DEFAULT_SCAN_ROOTS + tuple(Path(p) for p in parsed.scan_root)

    violations: list[Violation] = []
    for file_path in _iter_python_files(list(scan_roots)):
        violations.extend(_scan_file(file_path))

    if not violations:
        print("No unsafe dynamic execution/deserialization usage detected.")
        return 0

    print("Unsafe dynamic execution/deserialization usage detected:")
    for item in sorted(violations, key=lambda it: (str(it.path), it.line, it.message)):
        try:
            relative = item.path.relative_to(REPO_ROOT)
        except ValueError:
            relative = item.path
        print(f"- {relative}:{item.line}: {item.message}")

    print(
        "\nSecurity remediation: remove eval/exec, avoid pickle.loads on runtime "
        "data, and replace yaml.load with yaml.safe_load plus schema checks."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
