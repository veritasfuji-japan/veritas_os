"""Tests for scripts.architecture.check_core_complexity_budget."""

from __future__ import annotations

from pathlib import Path

from scripts.architecture import check_core_complexity_budget as checker


def _write_module(path: Path, source: str) -> None:
    """Write UTF-8 module source to a temporary file."""
    path.write_text(source, encoding="utf-8")


def test_collect_metrics_counts_public_functions_wrappers_and_imports(
    tmp_path: Path,
) -> None:
    """Metrics should capture top-level shape signals used by the budget gate."""
    module_path = tmp_path / "planner.py"
    _write_module(
        module_path,
        (
            '"""planner test module"""\n'
            "from .planner_helpers import normalize_step\n"
            "from .planner_json import rescue_json\n\n"
            "def public_api() -> None:\n"
            '    """Normal public entry point."""\n'
            "    return None\n\n"
            "def generate_plan() -> None:\n"
            '    """Compatibility wrapper for legacy callers."""\n'
            "    return None\n\n"
            "def _private_helper() -> None:\n"
            "    return None\n"
        ),
    )

    metrics = checker.collect_metrics(module_path)

    assert metrics.module == "planner"
    assert metrics.public_function_count == 2
    assert metrics.compat_wrapper_count == 1
    assert metrics.core_import_count == 2
    assert metrics.public_functions == ("public_api", "generate_plan")
    assert metrics.compat_wrappers == ("generate_plan",)
    assert metrics.core_imports == (
        "veritas_os.core.planner_helpers",
        "veritas_os.core.planner_json",
    )


def test_find_budget_violations_reports_each_exceeded_metric() -> None:
    """Each budget category should produce a stable violation message."""
    metrics = checker.ComplexityMetrics(
        module="kernel",
        path="veritas_os/core/kernel.py",
        line_count=12,
        public_function_count=5,
        compat_wrapper_count=4,
        core_import_count=7,
        public_functions=("a", "b", "c", "d", "e"),
        compat_wrappers=("a", "b", "c", "d"),
        core_imports=tuple(f"veritas_os.core.m{i}" for i in range(7)),
    )
    budget = checker.ComplexityBudget(
        module="kernel",
        max_lines=10,
        max_public_functions=3,
        max_compat_wrappers=2,
        max_core_imports=4,
    )

    violations = checker.find_budget_violations(metrics, budget)

    assert "kernel: line_count budget exceeded (actual=12, allowed=10)" in violations
    assert (
        "kernel: public_function_count budget exceeded (actual=5, allowed=3)"
        in violations
    )
    assert (
        "kernel: compat_wrapper_count budget exceeded (actual=4, allowed=2)"
        in violations
    )
    assert "kernel: core_import_count budget exceeded (actual=7, allowed=4)" in violations


def test_build_report_returns_clean_result_for_current_repository() -> None:
    """Current Planner/Kernel files should fit within the agreed complexity budgets."""
    report = checker.build_report()

    assert report["violations"] == []
    modules = {entry["metrics"]["module"]: entry for entry in report["modules"]}
    assert set(modules) == {"planner", "kernel"}
    assert modules["planner"]["metrics"]["line_count"] <= checker.DEFAULT_BUDGETS[
        "planner"
    ].max_lines
    assert modules["kernel"]["metrics"]["line_count"] <= checker.DEFAULT_BUDGETS[
        "kernel"
    ].max_lines


def test_main_returns_success_for_current_repository(capsys) -> None:
    """CLI should exit successfully when the current repository respects the budget."""
    exit_code = checker.main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Core complexity budget checks passed." in output
