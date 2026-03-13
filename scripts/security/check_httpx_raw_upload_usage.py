#!/usr/bin/env python3
"""Detect deprecated httpx raw upload call patterns.

httpx warns when raw text/bytes are sent through ``data=``. Projects should use
``content=`` for raw payloads to preserve forward compatibility across httpx
releases. This script scans Python source files and fails when obviously
deprecated usages are found.
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
SKIP_DIR_NAMES = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".venv", "node_modules"}
HTTPX_METHODS = {"post", "put", "patch", "request"}


@dataclass(frozen=True)
class Violation:
    """Represents a deprecated raw upload pattern discovered in source."""

    path: Path
    line: int
    message: str


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command-line options."""
    parser = argparse.ArgumentParser(
        description=(
            "Check Python source for deprecated httpx raw upload usage "
            "(data=<str|bytes>)."
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
    """Return Python files under the provided roots, excluding cache/vendor dirs."""
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
            files.append(path)
    return files


def _looks_like_raw_payload(node: ast.AST) -> bool:
    """Return True when AST node is an obvious raw text/bytes payload literal."""
    if isinstance(node, ast.Constant):
        return isinstance(node.value, (str, bytes))
    return isinstance(node, ast.JoinedStr)


def _is_httpx_call(call: ast.Call) -> bool:
    """Check whether this call targets a common httpx request method."""
    if isinstance(call.func, ast.Attribute):
        return call.func.attr in HTTPX_METHODS
    return False


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
        if not _is_httpx_call(node):
            continue

        for keyword in node.keywords:
            if keyword.arg != "data":
                continue
            if _looks_like_raw_payload(keyword.value):
                violations.append(
                    Violation(
                        path=path,
                        line=keyword.value.lineno,
                        message="httpx raw payload in data= detected; use content= instead",
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
        print("No deprecated httpx raw upload usage detected.")
        return 0

    print("Deprecated httpx raw upload usage detected:")
    for item in sorted(violations, key=lambda it: (str(it.path), it.line)):
        try:
            relative = item.path.relative_to(REPO_ROOT)
        except ValueError:
            relative = item.path
        print(f"- {relative}:{item.line}: {item.message}")

    print("\nReplace data=<str|bytes> with content=<str|bytes> for httpx requests.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
