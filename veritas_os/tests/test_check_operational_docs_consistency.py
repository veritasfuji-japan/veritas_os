"""Tests for scripts.quality.check_operational_docs_consistency."""

from __future__ import annotations

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


def test_main_returns_success_for_current_repository_docs(capsys) -> None:
    """Repository docs should satisfy the operational consistency check."""
    exit_code = checker.main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Operational documentation consistency checks passed." in output
