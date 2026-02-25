"""Tests for veritas_os/scripts/pr_impact_summary.py."""

from __future__ import annotations

import pytest

from veritas_os.scripts import pr_impact_summary


@pytest.mark.parametrize(
    "file_path,expected_responsibility,expected_risk",
    [
        (
            "veritas_os/core/planner.py",
            "Planner: planning strategy and task generation",
            "high",
        ),
        (
            "veritas_os/core/kernel.py",
            "Kernel: orchestration and execution flow",
            "high",
        ),
        (
            "veritas_os/core/fuji.py",
            "Fuji: policy and risk judgement",
            "high",
        ),
        (
            "veritas_os/core/memory.py",
            "MemoryOS: memory persistence/search behavior",
            "high",
        ),
        (
            "frontend/app/page.tsx",
            "Frontend: UI and client-side behavior",
            "medium",
        ),
    ],
)
def test_infer_impact_core_paths(file_path, expected_responsibility, expected_risk):
    """責務分類とリスク分類が主要パスで想定どおりになること。"""
    row = pr_impact_summary.infer_impact(file_path)

    assert row.responsibility == expected_responsibility
    assert expected_risk in row.risk


def test_infer_impact_api_security_sensitive_path() -> None:
    """Security-sensitive API path should include security warning in risk."""
    row = pr_impact_summary.infer_impact("veritas_os/api/auth/token_guard.py")

    assert "security-sensitive" in row.risk


def test_render_markdown_includes_security_warning() -> None:
    """Security rows should trigger explicit security warning section."""
    rows = [
        pr_impact_summary.ImpactRow(
            file_path="security/policy.md",
            responsibility="Security-related configuration or implementation",
            risk="high (security risk; manual review mandatory)",
            required_tests="Targeted tests + security-focused review",
        )
    ]

    content = pr_impact_summary._render_markdown(rows)

    assert "## 変更影響範囲（自動要約）" in content
    assert "### セキュリティ警告" in content


def test_generate_summary_uses_git_diff(monkeypatch: pytest.MonkeyPatch) -> None:
    """Summary generation should map git changed files to markdown rows."""

    def _mock_run_git_diff_name_only(base_ref: str, head_ref: str) -> list[str]:
        assert base_ref == "origin/main"
        assert head_ref == "HEAD"
        return ["veritas_os/core/planner.py", "frontend/app/page.tsx"]

    monkeypatch.setattr(
        pr_impact_summary,
        "_run_git_diff_name_only",
        _mock_run_git_diff_name_only,
    )

    result = pr_impact_summary.generate_summary(
        base_ref="origin/main",
        head_ref="HEAD",
    )

    assert "`veritas_os/core/planner.py`" in result
    assert "`frontend/app/page.tsx`" in result


def test_run_git_diff_raises_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """git diff failures should be wrapped in RuntimeError."""

    class _CompletedProcess:
        returncode = 1
        stderr = "fatal: bad revision"
        stdout = ""

    def _mock_subprocess_run(*args, **kwargs):
        return _CompletedProcess()

    monkeypatch.setattr(pr_impact_summary.subprocess, "run", _mock_subprocess_run)

    with pytest.raises(RuntimeError):
        pr_impact_summary._run_git_diff_name_only("origin/main", "HEAD")
