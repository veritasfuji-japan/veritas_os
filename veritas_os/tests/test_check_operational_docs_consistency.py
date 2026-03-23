"""Tests for scripts.quality.check_operational_docs_consistency."""

from __future__ import annotations

from pathlib import Path

from scripts.quality import check_operational_docs_consistency as checker


def test_collect_missing_tokens_reports_readme_and_runbook_gaps() -> None:
    """Checker should report missing P1 operational doc markers."""
    missing = checker.collect_missing_tokens(
        "### 4.3 degraded 判定のアラートポリシー（P1固定）\n",
        checker.RUNBOOK_REQUIRED_TOKENS,
    )

    assert "runtime_features.sanitize=degraded" in missing
    assert "checks.auth_store=degraded" in missing
    assert "### 4.4 `/health` / `/status` の運用判定" in missing


def test_collect_missing_tokens_reports_primary_readme_gaps() -> None:
    """Checker should keep the top-level README source-of-truth markers."""
    missing = checker.collect_missing_tokens(
        "**Release Status**: ベータ版\n",
        checker.PRIMARY_README_REQUIRED_TOKENS,
    )

    assert "**ベータ品質のガバナンス基盤**" in missing
    assert "### 拡張時に重要な責務境界" in missing
    assert "| **Planner** |" in missing


def test_main_returns_success_for_current_repository_docs(capsys) -> None:
    """Repository docs should satisfy the operational consistency check."""
    exit_code = checker.main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Operational documentation consistency checks passed." in output


def test_ci_workflow_runs_operational_doc_and_complexity_guards() -> None:
    """CI lint workflow should execute the reassessment guard scripts."""
    workflow = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "main.yml"
    content = workflow.read_text(encoding="utf-8")

    assert "python scripts/architecture/check_core_complexity_budget.py" in content
    assert "python scripts/quality/check_operational_docs_consistency.py" in content


def test_makefile_quality_checks_target_includes_reassessment_guards() -> None:
    """Local quality target should mirror the key reassessment gates."""
    makefile = Path(__file__).resolve().parents[2] / "Makefile"
    content = makefile.read_text(encoding="utf-8")

    assert "quality-checks:" in content
    assert "python scripts/architecture/check_core_complexity_budget.py" in content
    assert "python scripts/quality/check_operational_docs_consistency.py" in content
