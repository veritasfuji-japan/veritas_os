"""Static checker for Planner / Kernel / Fuji / MemoryOS import boundaries.

This script enforces directional dependency constraints between core modules.
It is intended for CI use and returns non-zero when violations are detected.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class BoundaryRule:
    """A dependency rule for one source module against forbidden imports."""

    source_module: str
    forbidden_imports: frozenset[str]


DEFAULT_RULES: tuple[BoundaryRule, ...] = (
    BoundaryRule(
        source_module="planner",
        forbidden_imports=frozenset({"kernel", "fuji"}),
    ),
    BoundaryRule(
        source_module="fuji",
        forbidden_imports=frozenset({"kernel", "planner"}),
    ),
    BoundaryRule(
        source_module="memory",
        forbidden_imports=frozenset({"kernel", "planner", "fuji"}),
    ),
)


def _normalize_module_name(module_name: str) -> str:
    """Normalize import paths to the core module leaf name."""
    return module_name.rsplit(".", maxsplit=1)[-1]


def _collect_imported_names(tree: ast.Module) -> set[str]:
    """Collect imported module names from a module AST."""
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(_normalize_module_name(alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(_normalize_module_name(node.module))
            else:
                for alias in node.names:
                    imported.add(_normalize_module_name(alias.name))
    return imported


def _check_rule(core_dir: Path, rule: BoundaryRule) -> list[str]:
    """Check one rule and return violation messages, one per forbidden import found."""
    path = core_dir / f"{rule.source_module}.py"
    try:
        source = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [f"Boundary check error: '{rule.source_module}' not found at {path}"]
    tree = ast.parse(source, filename=str(path))
    imported = _collect_imported_names(tree)
    violations = sorted(imported & rule.forbidden_imports)

    return [
        f"Boundary violation: '{rule.source_module}' imports forbidden module '{v}' ({path})"
        for v in violations
    ]


def check_boundaries(core_dir: Path, rules: Iterable[BoundaryRule] = DEFAULT_RULES) -> list[str]:
    """Run all boundary rules and return all violation messages."""
    issues: list[str] = []
    for rule in rules:
        issues.extend(_check_rule(core_dir=core_dir, rule=rule))
    return issues


def _build_parser() -> argparse.ArgumentParser:
    """Build command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--core-dir",
        type=Path,
        default=Path("veritas_os/core"),
        help="Path to the core module directory (default: veritas_os/core).",
    )
    return parser


def main() -> int:
    """CLI entrypoint for CI execution."""
    parser = _build_parser()
    args = parser.parse_args()
    issues = check_boundaries(core_dir=args.core_dir)

    if issues:
        for issue in issues:
            print(issue)
        return 1

    print("Responsibility boundary check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
