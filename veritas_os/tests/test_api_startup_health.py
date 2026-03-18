"""Tests for API startup health helpers."""

import logging

import pytest

from veritas_os.api import startup_health


def test_should_fail_fast_startup_profile_detection(monkeypatch):
    """Production profiles should enable fail-fast startup behavior."""
    monkeypatch.delenv("VERITAS_ENV", raising=False)

    assert startup_health.should_fail_fast_startup("production") is True
    assert startup_health.should_fail_fast_startup("prod") is True
    assert startup_health.should_fail_fast_startup("staging") is False


def test_should_fail_fast_startup_reads_env(monkeypatch):
    """VERITAS_ENV should control fail-fast behavior when profile is omitted."""
    monkeypatch.setenv("VERITAS_ENV", "production")
    assert startup_health.should_fail_fast_startup() is True


def test_run_startup_config_validation_warn_only(caplog):
    """Validation errors should be logged and not raised when fail-fast is false."""

    def _validator():
        raise RuntimeError("boom")

    with caplog.at_level(logging.WARNING):
        startup_health.run_startup_config_validation(
            logger=logging.getLogger("test.startup_health"),
            should_fail_fast=lambda _: False,
            validator=_validator,
        )

    assert "startup config validation failed (fail_fast=False)" in caplog.text


def test_run_startup_config_validation_raises_when_fail_fast():
    """Validation errors should be re-raised when fail-fast is enabled."""

    def _validator():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        startup_health.run_startup_config_validation(
            logger=logging.getLogger("test.startup_health"),
            should_fail_fast=lambda _: True,
            validator=_validator,
        )


def test_validate_startup_security_flags_warns_non_production_fail_open(
    monkeypatch,
    caplog,
):
    """Non-production fail-open must still emit a security warning."""
    monkeypatch.setenv("VERITAS_ENV", "staging")
    monkeypatch.setenv("VERITAS_AUTH_ALLOW_FAIL_OPEN", "true")

    with caplog.at_level(logging.WARNING):
        startup_health.validate_startup_security_flags(
            logger=logging.getLogger("test.startup_health")
        )

    assert "VERITAS_AUTH_ALLOW_FAIL_OPEN=true is enabled" in caplog.text


def test_validate_startup_security_flags_rejects_production_fail_open(
    monkeypatch,
):
    """Production must fail fast when auth fail-open is explicitly enabled."""
    monkeypatch.setenv("VERITAS_ENV", "production")
    monkeypatch.setenv("VERITAS_AUTH_ALLOW_FAIL_OPEN", "true")

    with pytest.raises(RuntimeError, match="VERITAS_AUTH_ALLOW_FAIL_OPEN=true"):
        startup_health.validate_startup_security_flags(
            logger=logging.getLogger("test.startup_health")
        )


def test_validate_startup_security_flags_rejects_public_api_base_url_in_production(
    monkeypatch,
):
    """Production must reject leaked public API base URL configuration."""
    monkeypatch.setenv("VERITAS_ENV", "production")
    monkeypatch.setenv(
        "NEXT_PUBLIC_VERITAS_API_BASE_URL",
        "https://internal-api.example.test",
    )

    with pytest.raises(RuntimeError, match="NEXT_PUBLIC_VERITAS_API_BASE_URL"):
        startup_health.validate_startup_security_flags(
            logger=logging.getLogger("test.startup_health")
        )


def test_validate_startup_security_flags_warns_node_env_production_without_veritas_env(
    monkeypatch,
    caplog,
):
    """NODE_ENV-only production must warn because strict CSP defaults stay off."""
    monkeypatch.delenv("VERITAS_ENV", raising=False)
    monkeypatch.setenv("NODE_ENV", "production")

    with caplog.at_level(logging.WARNING):
        startup_health.validate_startup_security_flags(
            logger=logging.getLogger("test.startup_health")
        )

    assert "NODE_ENV=production is set without VERITAS_ENV=production" in caplog.text


def test_check_runtime_feature_health_logs_security_warning(caplog):
    """Security warning must be emitted when sanitization is unavailable."""
    with caplog.at_level(logging.WARNING):
        startup_health.check_runtime_feature_health(
            logger=logging.getLogger("test.startup_health"),
            has_sanitize=False,
            has_atomic_io=True,
        )

    assert "[SECURITY] PII masking is DISABLED" in caplog.text
