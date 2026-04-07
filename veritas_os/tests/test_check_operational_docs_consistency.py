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


def test_collect_missing_tokens_reports_secondary_readme_scope_gaps() -> None:
    """Checker should preserve the secondary README scope disclaimer."""
    missing = checker.collect_missing_tokens(
        "Beta%20Governance%20Platform\n",
        checker.README_REQUIRED_TOKENS,
    )

    assert "**Document Scope**: バックエンド配下の補助リファレンス" in missing
    assert "**記述スコープの注意**" in missing


def test_collect_missing_any_tokens_accepts_legacy_or_new_runbook_token() -> None:
    """Runbook token checks should allow legacy and new path variants."""
    missing_new = checker.collect_missing_any_tokens(
        "docs/ja/operations/enterprise_slo_sli_runbook_ja.md",
        (("docs/ja/operations/enterprise_slo_sli_runbook_ja.md",
          "docs/operations/ENTERPRISE_SLO_SLI_RUNBOOK_JP.md"),),
    )
    missing_legacy = checker.collect_missing_any_tokens(
        "docs/operations/ENTERPRISE_SLO_SLI_RUNBOOK_JP.md",
        (("docs/ja/operations/enterprise_slo_sli_runbook_ja.md",
          "docs/operations/ENTERPRISE_SLO_SLI_RUNBOOK_JP.md"),),
    )

    assert missing_new == []
    assert missing_legacy == []


def test_main_returns_success_for_current_repository_docs(capsys) -> None:
    """Repository docs should satisfy the operational consistency check."""
    exit_code = checker.main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Operational documentation consistency checks passed." in output


def test_ci_workflow_runs_operational_and_memory_config_guards() -> None:
    """CI lint workflow should execute the reassessment guard scripts."""
    workflow = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "main.yml"
    content = workflow.read_text(encoding="utf-8")

    assert "python scripts/architecture/check_core_complexity_budget.py" in content
    assert "python scripts/quality/check_operational_docs_consistency.py" in content
    assert "python scripts/security/check_memory_dir_allowlist.py" in content


def test_makefile_quality_checks_target_includes_reassessment_guards() -> None:
    """Local quality target should mirror the key reassessment gates."""
    makefile = Path(__file__).resolve().parents[2] / "Makefile"
    content = makefile.read_text(encoding="utf-8")

    assert "quality-checks:" in content
    assert "python scripts/architecture/check_core_complexity_budget.py" in content
    assert "python scripts/quality/check_operational_docs_consistency.py" in content
    assert "python scripts/security/check_memory_dir_allowlist.py" in content
