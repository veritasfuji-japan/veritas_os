"""Tests for deployment environment template smoke checks."""

from __future__ import annotations

from pathlib import Path

from scripts.quality import check_deployment_env_defaults as deployment_defaults


def test_iter_env_assignments_normalizes_export_and_quotes() -> None:
    """Shell-style env syntax should still be parsed into normalized pairs."""
    content = """
    # comment
    export VERITAS_AUTH_ALLOW_FAIL_OPEN = 'TRUE'
    VERITAS_ENV=production
    """

    assignments = list(deployment_defaults._iter_env_assignments(content))

    assert assignments == [
        ("VERITAS_AUTH_ALLOW_FAIL_OPEN", "TRUE"),
        ("VERITAS_ENV", "production"),
    ]


def test_validate_rule_flags_fail_open_with_export_spacing(tmp_path: Path) -> None:
    """Fail-open defaults must be caught even when template formatting varies."""
    template = tmp_path / "setup.sh"
    template.write_text(
        """
        export VERITAS_API_BASE_URL=http://localhost:8000
        VERITAS_ENV=production
        export VERITAS_AUTH_ALLOW_FAIL_OPEN = \"TrUe\"
        """,
        encoding="utf-8",
    )
    rule = deployment_defaults.TemplateRule(
        relative_path=str(template.relative_to(tmp_path)),
        required_tokens=(
            "VERITAS_API_BASE_URL=http://localhost:8000",
            "VERITAS_ENV=production",
        ),
        forbidden_env_assignments=(("VERITAS_AUTH_ALLOW_FAIL_OPEN", "true"),),
    )

    original_root = deployment_defaults.REPO_ROOT
    deployment_defaults.REPO_ROOT = tmp_path
    try:
        violations = deployment_defaults._validate_rule(rule)
    finally:
        deployment_defaults.REPO_ROOT = original_root

    assert violations == [
        "setup.sh: forbidden env assignment VERITAS_AUTH_ALLOW_FAIL_OPEN=true"
    ]


def test_validate_rule_flags_auth_store_open_mode(tmp_path: Path) -> None:
    """Open auth-store failure mode must be rejected in deployment templates."""
    template = tmp_path / ".env.example"
    template.write_text(
        """
        VERITAS_API_BASE_URL=http://localhost:8000
        VERITAS_ENV=production
        export VERITAS_AUTH_STORE_FAILURE_MODE = "OPEN"
        """,
        encoding="utf-8",
    )
    rule = deployment_defaults.TemplateRule(
        relative_path=str(template.relative_to(tmp_path)),
        required_tokens=("VERITAS_API_BASE_URL", "VERITAS_ENV=production"),
        forbidden_env_assignments=(
            ("VERITAS_AUTH_STORE_FAILURE_MODE", "open"),
        ),
    )

    original_root = deployment_defaults.REPO_ROOT
    deployment_defaults.REPO_ROOT = tmp_path
    try:
        violations = deployment_defaults._validate_rule(rule)
    finally:
        deployment_defaults.REPO_ROOT = original_root

    assert violations == [
        ".env.example: forbidden env assignment "
        "VERITAS_AUTH_STORE_FAILURE_MODE=open"
    ]


def test_validate_rule_passes_without_forbidden_defaults(tmp_path: Path) -> None:
    """Safe templates should continue to pass the smoke check."""
    template = tmp_path / ".env.example"
    template.write_text(
        """
        VERITAS_API_BASE_URL=http://localhost:8000
        VERITAS_ENV=production
        """,
        encoding="utf-8",
    )
    rule = deployment_defaults.TemplateRule(
        relative_path=str(template.relative_to(tmp_path)),
        required_tokens=("VERITAS_API_BASE_URL", "VERITAS_ENV=production"),
        forbidden_tokens=("NEXT_PUBLIC_VERITAS_API_BASE_URL",),
        forbidden_env_assignments=(
            ("VERITAS_AUTH_ALLOW_FAIL_OPEN", "true"),
            ("VERITAS_AUTH_STORE_FAILURE_MODE", "open"),
        ),
    )

    original_root = deployment_defaults.REPO_ROOT
    deployment_defaults.REPO_ROOT = tmp_path
    try:
        violations = deployment_defaults._validate_rule(rule)
    finally:
        deployment_defaults.REPO_ROOT = original_root

    assert violations == []


def test_validate_rule_flags_direct_fuji_api_key_presence(tmp_path: Path) -> None:
    """Direct FUJI API flag must not appear in operator env templates."""
    template = tmp_path / ".env.example"
    template.write_text(
        """
        VERITAS_API_BASE_URL=http://localhost:8000
        VERITAS_ENV=production
        VERITAS_ENABLE_DIRECT_FUJI_API=0
        """,
        encoding="utf-8",
    )
    rule = deployment_defaults.TemplateRule(
        relative_path=str(template.relative_to(tmp_path)),
        required_tokens=("VERITAS_API_BASE_URL", "VERITAS_ENV=production"),
        forbidden_env_keys=("VERITAS_ENABLE_DIRECT_FUJI_API",),
    )

    original_root = deployment_defaults.REPO_ROOT
    deployment_defaults.REPO_ROOT = tmp_path
    try:
        violations = deployment_defaults._validate_rule(rule)
    finally:
        deployment_defaults.REPO_ROOT = original_root

    assert violations == [
        ".env.example: forbidden env key present VERITAS_ENABLE_DIRECT_FUJI_API"
    ]
