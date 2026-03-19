"""Tests for scripts.quality.check_deployment_env_defaults."""

from __future__ import annotations

from scripts.quality import check_deployment_env_defaults as checker


def test_validate_rule_reports_forbidden_legacy_public_env_token(
    monkeypatch, tmp_path
) -> None:
    """Legacy public API base URL tokens must fail the smoke check."""
    template = tmp_path / "setup.sh"
    template.write_text(
        "NEXT_PUBLIC_API_BASE_URL=http://localhost:8000\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(checker, "REPO_ROOT", tmp_path)

    violations = checker._validate_rule(
        checker.TemplateRule(
            relative_path="setup.sh",
            forbidden_tokens=("NEXT_PUBLIC_API_BASE_URL",),
        )
    )

    assert violations == [
        "setup.sh: forbidden token present 'NEXT_PUBLIC_API_BASE_URL'"
    ]


def test_validate_rule_requires_server_only_api_base_url(
    monkeypatch, tmp_path
) -> None:
    """Operator templates must keep server-only API base URL guidance."""
    template = tmp_path / "setup.sh"
    template.write_text(
        "VERITAS_API_KEY=example\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(checker, "REPO_ROOT", tmp_path)

    violations = checker._validate_rule(
        checker.TemplateRule(
            relative_path="setup.sh",
            required_tokens=("VERITAS_API_BASE_URL=http://localhost:8000",),
        )
    )

    assert violations == [
        "setup.sh: missing required token 'VERITAS_API_BASE_URL=http://localhost:8000'"
    ]


def test_validate_rule_requires_production_profile_guidance(
    monkeypatch, tmp_path
) -> None:
    """Operator templates must document the production hardening profile."""
    template = tmp_path / ".env.example"
    template.write_text(
        "VERITAS_API_BASE_URL=http://backend:8000\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(checker, "REPO_ROOT", tmp_path)

    violations = checker._validate_rule(
        checker.TemplateRule(
            relative_path=".env.example",
            required_tokens=("VERITAS_ENV=production",),
        )
    )

    assert violations == [
        ".env.example: missing required token 'VERITAS_ENV=production'"
    ]


def test_main_returns_success_for_current_repo_templates(capsys) -> None:
    """Current repository templates should pass the deployment smoke check."""
    exit_code = checker.main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Deployment env templates passed smoke checks." in output
