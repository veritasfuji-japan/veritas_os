"""Tests for scripts.quality.check_review_improvements_consistency."""

from __future__ import annotations

from pathlib import Path

from scripts.quality import check_review_improvements_consistency as checker


def test_collect_missing_tokens_reports_integrated_backlog_gaps() -> None:
    """Checker should detect missing consolidation markers."""
    content = "# VERITAS OS 改善点レビュー（2026-03-30）\n"

    missing = checker.collect_missing_tokens(content)

    assert "## 優先度付きテーマ（次アクション）" in missing
    assert "### 2026-03-30 追加追記（改善バックログの統合ビュー運用を追加）" in missing
    assert "- **週次更新ルール（運用固定）**" in missing


def test_main_returns_success_for_current_repository_review(capsys) -> None:
    """Repository review document should satisfy the consistency contract."""
    exit_code = checker.main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Review improvements consistency checks passed." in output


def test_resolve_review_path_prefers_canonical() -> None:
    """Checker should prefer canonical docs path when present."""
    resolved = checker.resolve_review_path()
    assert resolved == checker.CANONICAL_REVIEW_PATH


def test_resolve_review_path_falls_back_to_legacy(monkeypatch, tmp_path) -> None:
    """Checker should fallback to legacy path when canonical is unavailable."""
    canonical = tmp_path / "canonical.md"
    legacy = tmp_path / "legacy.md"
    legacy.write_text("# legacy", encoding="utf-8")
    monkeypatch.setattr(checker, "CANONICAL_REVIEW_PATH", canonical)
    monkeypatch.setattr(checker, "LEGACY_REVIEW_PATH", legacy)

    resolved = checker.resolve_review_path()

    assert resolved == legacy


def test_ci_workflow_runs_review_improvements_consistency_check() -> None:
    """CI lint workflow should execute the review backlog consistency checker."""
    workflow = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "main.yml"
    content = workflow.read_text(encoding="utf-8")

    assert "python scripts/quality/check_review_improvements_consistency.py" in content


def test_makefile_quality_checks_target_includes_review_consistency_guard() -> None:
    """Local quality checks should include review backlog consistency validation."""
    makefile = Path(__file__).resolve().parents[2] / "Makefile"
    content = makefile.read_text(encoding="utf-8")

    assert "quality-checks:" in content
    assert "python scripts/quality/check_review_improvements_consistency.py" in content
