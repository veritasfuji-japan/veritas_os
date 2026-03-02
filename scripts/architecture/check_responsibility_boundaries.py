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


@dataclass(frozen=True)
class ViolationDetail:
    """Structured details for a single responsibility-boundary violation."""

    source_module: str
    forbidden_module: str
    path: Path


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


ALLOWED_DEPENDENCY_GUIDE: dict[str, tuple[str, ...]] = {
    "planner": (
        "veritas_os.core.memory",
        "veritas_os.core.world_model",
        "veritas_os.core.strategy",
    ),
    "kernel": (
        "veritas_os.core.planner",
        "veritas_os.core.fuji",
        "veritas_os.core.memory",
    ),
    "fuji": (
        "veritas_os.core.fuji_codes",
        "veritas_os.core.sanitize",
    ),
    "memory": (
        "veritas_os.utils.atomic_io",
        "veritas_os.core.memory_vector",
    ),
}


REMEDIATION_LINK = "docs/review/SYSTEM_SCORECARD_2026_03_02.md#実装方針責務境界を越えない範囲"


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
            # Include imported symbols to detect patterns like:
            #   from veritas_os.core import kernel
            # This is a forbidden dependency equivalent to
            #   import veritas_os.core.kernel
            for alias in node.names:
                imported.add(_normalize_module_name(alias.name))
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


def _collect_violations(
    core_dir: Path,
    rules: Iterable[BoundaryRule] = DEFAULT_RULES,
) -> list[ViolationDetail]:
    """Collect structured violation details for remediation guidance output."""
    violation_details: list[ViolationDetail] = []
    for rule in rules:
        path = core_dir / f"{rule.source_module}.py"
        try:
            source = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            continue
        tree = ast.parse(source, filename=str(path))
        imported = _collect_imported_names(tree)
        violations = sorted(imported & rule.forbidden_imports)
        for forbidden_module in violations:
            violation_details.append(
                ViolationDetail(
                    source_module=rule.source_module,
                    forbidden_module=forbidden_module,
                    path=path,
                )
            )
    return violation_details


def build_remediation_guide(
    violations: Iterable[ViolationDetail],
    remediation_link: str = REMEDIATION_LINK,
) -> str:
    """Build a CI-friendly remediation guide for boundary violations."""
    rows: list[str] = []
    for violation in violations:
        alternatives = ", ".join(ALLOWED_DEPENDENCY_GUIDE.get(violation.source_module, ("N/A",)))
        rows.append(
            " | ".join(
                (
                    f"{violation.source_module} -> {violation.forbidden_module}",
                    alternatives,
                    remediation_link,
                )
            )
        )

    if not rows:
        return ""

    header = (
        "\n=== Responsibility Boundary Remediation Guide ===\n"
        "禁止依存 | 代替実装先（許可依存） | 修正例リンク\n"
    )
    return header + "\n".join(rows)


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
        violations = _collect_violations(core_dir=args.core_dir)
        for issue in issues:
            print(issue)
        remediation_guide = build_remediation_guide(violations)
        if remediation_guide:
            print(remediation_guide)
        return 1

    print("Responsibility boundary check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
