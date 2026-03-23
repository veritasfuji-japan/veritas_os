#!/usr/bin/env python3
"""Enforce structural complexity budgets for Planner and Kernel.

The 2026-03-23 reassessment identified structural complexity re-growth in
`planner.py` and `kernel.py` as the next major operational risk after the P1
operational documentation fixes. This checker provides a lightweight CI guard
that alerts maintainers before new logic quietly re-inflates those modules.
"""

from __future__ import annotations

import ast
import json
from dataclasses import asdict, dataclass
from pathlib import Path
import sys
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
CORE_DIR = REPO_ROOT / "veritas_os" / "core"


@dataclass(frozen=True)
class ComplexityBudget:
    """Budget thresholds for a guarded core module."""

    module: str
    max_lines: int
    max_public_functions: int
    max_compat_wrappers: int
    max_core_imports: int


@dataclass(frozen=True)
class ComplexityMetrics:
    """Measured complexity indicators for a guarded core module."""

    module: str
    path: str
    line_count: int
    public_function_count: int
    compat_wrapper_count: int
    core_import_count: int
    public_functions: tuple[str, ...]
    compat_wrappers: tuple[str, ...]
    core_imports: tuple[str, ...]


DEFAULT_BUDGETS: dict[str, ComplexityBudget] = {
    "planner": ComplexityBudget(
        module="planner",
        max_lines=980,
        max_public_functions=4,
        max_compat_wrappers=4,
        max_core_imports=8,
    ),
    "kernel": ComplexityBudget(
        module="kernel",
        max_lines=1140,
        max_public_functions=3,
        max_compat_wrappers=3,
        max_core_imports=10,
    ),
}

COMPATIBILITY_MARKERS = (
    "compat",
    "compatibility",
    "wrapper",
    "legacy alias",
    "backward-compatible",
)


def _iter_module_functions(
    tree: ast.Module,
) -> Iterable[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Yield top-level functions from a module AST."""
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def _normalize_core_import(node: ast.ImportFrom | ast.Import) -> set[str]:
    """Normalize direct imports that target sibling core modules."""
    normalized: set[str] = set()
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name.startswith("veritas_os.core."):
                normalized.add(alias.name)
        return normalized

    if node.module and node.module.startswith("veritas_os.core."):
        normalized.add(node.module)
        return normalized

    if node.level >= 1 and node.module:
        normalized.add(f"veritas_os.core.{node.module}")
    return normalized


def _collect_core_imports(tree: ast.Module) -> tuple[str, ...]:
    """Collect unique imports that target sibling `veritas_os.core.*` modules."""
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imports.update(_normalize_core_import(node))
    return tuple(sorted(imports))


def _is_compatibility_wrapper(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    source: str,
) -> bool:
    """Return whether a function is explicitly marked as a compatibility wrapper."""
    docstring = (ast.get_docstring(func) or "").lower()
    source_segment = (ast.get_source_segment(source, func) or "").lower()
    return any(
        marker in docstring or marker in source_segment
        for marker in COMPATIBILITY_MARKERS
    )


def collect_metrics(module_path: Path) -> ComplexityMetrics:
    """Collect structural complexity metrics from a module source file."""
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(module_path))
    resolved_path = module_path.resolve()
    try:
        display_path = str(resolved_path.relative_to(REPO_ROOT))
    except ValueError:
        display_path = str(resolved_path)
    functions = tuple(_iter_module_functions(tree))
    public_functions = tuple(
        function.name for function in functions if not function.name.startswith("_")
    )
    compat_wrappers = tuple(
        function.name
        for function in functions
        if _is_compatibility_wrapper(function, source)
    )
    core_imports = _collect_core_imports(tree)
    return ComplexityMetrics(
        module=module_path.stem,
        path=display_path,
        line_count=len(source.splitlines()),
        public_function_count=len(public_functions),
        compat_wrapper_count=len(compat_wrappers),
        core_import_count=len(core_imports),
        public_functions=public_functions,
        compat_wrappers=compat_wrappers,
        core_imports=core_imports,
    )


def find_budget_violations(
    metrics: ComplexityMetrics,
    budget: ComplexityBudget,
) -> list[str]:
    """Return human-readable budget violations for a module."""
    violations: list[str] = []
    checks = (
        (metrics.line_count, budget.max_lines, "line_count"),
        (
            metrics.public_function_count,
            budget.max_public_functions,
            "public_function_count",
        ),
        (
            metrics.compat_wrapper_count,
            budget.max_compat_wrappers,
            "compat_wrapper_count",
        ),
        (metrics.core_import_count, budget.max_core_imports, "core_import_count"),
    )
    for actual, allowed, label in checks:
        if actual > allowed:
            violations.append(
                f"{metrics.module}: {label} budget exceeded "
                f"(actual={actual}, allowed={allowed})"
            )
    return violations


def build_report(
    core_dir: Path = CORE_DIR,
    budgets: dict[str, ComplexityBudget] | None = None,
) -> dict[str, object]:
    """Build the machine-readable complexity report for guarded modules."""
    active_budgets = budgets or DEFAULT_BUDGETS
    modules = []
    violations: list[str] = []
    for module_name, budget in active_budgets.items():
        module_path = core_dir / f"{module_name}.py"
        metrics = collect_metrics(module_path)
        modules.append(
            {
                "budget": asdict(budget),
                "metrics": asdict(metrics),
            }
        )
        violations.extend(find_budget_violations(metrics, budget))
    return {
        "modules": modules,
        "violations": violations,
    }


def main() -> int:
    """Run the core complexity budget checker."""
    report = build_report()
    if report["violations"]:
        print("[ARCH] Core complexity budget check failed.")
        for violation in report["violations"]:
            print(f"- {violation}")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    print("Core complexity budget checks passed.")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
