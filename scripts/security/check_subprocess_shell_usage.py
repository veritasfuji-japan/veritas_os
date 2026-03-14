#!/usr/bin/env python3
"""Detect dangerous subprocess usage patterns.

This checker enforces two guardrails:
1. ``shell=True`` is always rejected.
2. String commands are rejected unless a module-level allow comment exists.

String commands are often coupled with shell parsing and increase command
injection risk when future refactors accidentally involve user-controlled
inputs. The preferred style is ``subprocess.run(["cmd", "arg"])``.
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
SUBPROCESS_CALL_NAMES = {"run", "check_call", "check_output", "Popen", "call"}
ALLOW_STRING_COMMAND_MARKER = "allow-subprocess-string-command"


@dataclass(frozen=True)
class Violation:
    """Represents one detected subprocess security violation."""

    path: Path
    line: int
    message: str


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command-line options."""
    parser = argparse.ArgumentParser(
        description=(
            "Check Python source for risky subprocess usage "
            "(shell=True, or string command arguments)."
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
            if any(part in SKIP_PATH_PARTS for part in path.parts):
                continue
            files.append(path)
    return files


def _is_subprocess_call(call: ast.Call) -> bool:
    """Return True when AST call matches common subprocess execution APIs."""
    if isinstance(call.func, ast.Attribute):
        return call.func.attr in SUBPROCESS_CALL_NAMES
    return False


def _allows_string_command(source: str) -> bool:
    """Return True when source explicitly documents string-command exception."""
    return ALLOW_STRING_COMMAND_MARKER in source


def _is_string_command_arg(node: ast.AST | None) -> bool:
    """Return True when subprocess command argument is likely a string command."""
    if node is None:
        return False
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str)
    return isinstance(node, ast.JoinedStr)


def _find_command_arg(call: ast.Call) -> ast.AST | None:
    """Resolve the command argument from positional/keyword form."""
    if call.args:
        return call.args[0]

    for keyword in call.keywords:
        if keyword.arg in {"args", "cmd", "command"}:
            return keyword.value
    return None


def _scan_file(path: Path) -> list[Violation]:
    """Scan one Python file and return detected violations."""
    source = path.read_text(encoding="utf-8", errors="ignore")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    allow_string = _allows_string_command(source)
    violations: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not _is_subprocess_call(node):
            continue

        for keyword in node.keywords:
            if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant):
                if keyword.value.value is True:
                    violations.append(
                        Violation(
                            path=path,
                            line=keyword.value.lineno,
                            message="subprocess call with shell=True is forbidden",
                        )
                    )

        command_arg = _find_command_arg(node)
        if not allow_string and _is_string_command_arg(command_arg):
            violations.append(
                Violation(
                    path=path,
                    line=command_arg.lineno,
                    message=(
                        "subprocess string command detected; use argument list "
                        "(or document exception with "
                        f"'{ALLOW_STRING_COMMAND_MARKER}')"
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
        print("No risky subprocess usage detected.")
        return 0

    print("Risky subprocess usage detected:")
    for item in sorted(violations, key=lambda it: (str(it.path), it.line, it.message)):
        try:
            relative = item.path.relative_to(REPO_ROOT)
        except ValueError:
            relative = item.path
        print(f"- {relative}:{item.line}: {item.message}")

    print(
        "\nSecurity remediation: avoid shell=True, pass commands as lists, "
        "and never concatenate external input into command strings."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
