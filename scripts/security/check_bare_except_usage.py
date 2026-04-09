#!/usr/bin/env python3
"""Detect bare ``except:`` usage in production Python code.

Bare ``except:`` blocks catch ``BaseException`` (including ``KeyboardInterrupt``
and ``SystemExit``), which can hide operational failures and interfere with safe
shutdown behavior. This checker enforces a gradual-remediation policy by failing
CI when new bare ``except:`` handlers appear in runtime code.
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
    """Represents one bare ``except:`` violation."""

    path: Path
    line: int
    message: str


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command-line options."""
    parser = argparse.ArgumentParser(
        description="Check Python source for bare except handlers."
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


def _scan_file(path: Path) -> list[Violation]:
    """Scan one Python file and return bare ``except:`` violations."""
    source = path.read_text(encoding="utf-8", errors="ignore")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    violations: list[Violation] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            violations.append(
                Violation(
                    path=path,
                    line=node.lineno,
                    message=(
                        "bare except is forbidden; catch explicit exception types "
                        "to avoid masking operational failures"
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
        print("No bare except usage detected.")
        return 0

    print("Bare except usage detected:")
    for item in sorted(violations, key=lambda it: (str(it.path), it.line, it.message)):
        try:
            relative = item.path.relative_to(REPO_ROOT)
        except ValueError:
            relative = item.path
        print(f"- {relative}:{item.line}: {item.message}")

    print(
        "\nSecurity remediation: replace bare except with explicit exception "
        "classes and keep fail-closed behavior for unexpected errors."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
