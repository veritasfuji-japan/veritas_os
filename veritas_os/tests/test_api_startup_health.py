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


def test_should_fail_fast_startup_honors_trustlog_posture_enforcement_flag(monkeypatch):
    """Explicit TrustLog enforcement flag should force fail-fast startup behavior."""
    monkeypatch.delenv("VERITAS_ENV", raising=False)
    monkeypatch.delenv("VERITAS_POSTURE", raising=False)
    monkeypatch.setenv("VERITAS_REQUIRE_PRODUCTION_TRUSTLOG_POSTURE", "1")
    assert startup_health.should_fail_fast_startup() is True


def test_should_fail_fast_startup_explicit_profile_is_deterministic(monkeypatch):
    """Explicit profile should not be overridden by ambient strict env flags."""
    monkeypatch.setenv("VERITAS_ENV", "production")
    monkeypatch.setenv("VERITAS_POSTURE", "secure")
    monkeypatch.setenv("VERITAS_REQUIRE_PRODUCTION_TRUSTLOG_POSTURE", "1")
    assert startup_health.should_fail_fast_startup("staging") is False


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
    monkeypatch.setenv("VERITAS_ENV", "local")
    monkeypatch.setenv("VERITAS_AUTH_ALLOW_FAIL_OPEN", "true")

    with caplog.at_level(logging.WARNING):
        startup_health.validate_startup_security_flags(
            logger=logging.getLogger("test.startup_health")
        )

    assert "VERITAS_AUTH_ALLOW_FAIL_OPEN=true is enabled" in caplog.text


def test_validate_startup_security_flags_warns_non_production_requested_open_mode(
    monkeypatch,
    caplog,
):
    """Requesting open auth-store fallback should also emit a security warning."""
    monkeypatch.setenv("VERITAS_ENV", "local")
    monkeypatch.setenv("VERITAS_AUTH_STORE_FAILURE_MODE", "open")

    with caplog.at_level(logging.WARNING):
        startup_health.validate_startup_security_flags(
            logger=logging.getLogger("test.startup_health")
        )

    assert "VERITAS_AUTH_STORE_FAILURE_MODE=open is enabled" in caplog.text


def test_validate_startup_security_flags_rejects_fail_open_in_staging(
    monkeypatch,
):
    """Staging must fail closed when auth fail-open flags are requested."""
    monkeypatch.setenv("VERITAS_ENV", "staging")
    monkeypatch.setenv("VERITAS_AUTH_ALLOW_FAIL_OPEN", "true")

    with pytest.raises(RuntimeError, match="VERITAS_ENV=staging"):
        startup_health.validate_startup_security_flags(
            logger=logging.getLogger("test.startup_health")
        )


def test_validate_startup_security_flags_rejects_open_mode_in_staging(
    monkeypatch,
):
    """Staging must reject open auth-store fallback mode requests."""
    monkeypatch.setenv("VERITAS_ENV", "stg")
    monkeypatch.setenv("VERITAS_AUTH_STORE_FAILURE_MODE", "open")

    with pytest.raises(RuntimeError, match="VERITAS_ENV=stg"):
        startup_health.validate_startup_security_flags(
            logger=logging.getLogger("test.startup_health")
        )


def test_validate_startup_security_flags_warns_fail_open_when_profile_unset(
    monkeypatch,
    caplog,
):
    """Unset deployment profiles must also warn that fail-open will be ignored."""
    monkeypatch.delenv("VERITAS_ENV", raising=False)
    monkeypatch.setenv("VERITAS_AUTH_ALLOW_FAIL_OPEN", "true")

    with caplog.at_level(logging.WARNING):
        startup_health.validate_startup_security_flags(
            logger=logging.getLogger("test.startup_health")
        )

    assert "VERITAS_ENV=unset" in caplog.text
    assert "will be ignored by auth store fallback logic" in caplog.text


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


def test_validate_startup_security_flags_rejects_production_open_failure_mode(
    monkeypatch,
):
    """Production must fail fast when auth-store fallback is requested open."""
    monkeypatch.setenv("VERITAS_ENV", "production")
    monkeypatch.setenv("VERITAS_AUTH_STORE_FAILURE_MODE", "open")

    with pytest.raises(RuntimeError, match="VERITAS_AUTH_STORE_FAILURE_MODE=open"):
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


def test_validate_startup_security_flags_warns_direct_fuji_non_production(
    monkeypatch,
    caplog,
):
    """Direct FUJI env key presence must warn even when disabled."""
    monkeypatch.setenv("VERITAS_ENV", "local")
    monkeypatch.setenv("VERITAS_ENABLE_DIRECT_FUJI_API", "0")

    with caplog.at_level(logging.WARNING):
        startup_health.validate_startup_security_flags(
            logger=logging.getLogger("test.startup_health")
        )

    assert "VERITAS_ENABLE_DIRECT_FUJI_API is present" in caplog.text
    assert "removed from shared env templates" in caplog.text


def test_validate_startup_security_flags_rejects_direct_fuji_in_production(
    monkeypatch,
):
    """Production must reject direct FUJI env drift before startup."""
    monkeypatch.setenv("VERITAS_ENV", "production")
    monkeypatch.setenv("VERITAS_ENABLE_DIRECT_FUJI_API", "false")

    with pytest.raises(RuntimeError, match="VERITAS_ENABLE_DIRECT_FUJI_API is present"):
        startup_health.validate_startup_security_flags(
            logger=logging.getLogger("test.startup_health")
        )


def test_check_runtime_feature_health_logs_security_warning(caplog):
    """Security warning must be emitted when sanitization is unavailable."""
    with caplog.at_level(logging.WARNING):
        startup_health.check_runtime_feature_health(
            logger=logging.getLogger("test.startup_health"),
            has_sanitize=False,
            has_atomic_io=True,
        )

    assert "[SECURITY] PII masking is DISABLED" in caplog.text


def test_check_runtime_feature_health_rejects_missing_sanitize_in_production(
    monkeypatch,
):
    """Production must fail closed when sanitize support is unavailable."""
    monkeypatch.setenv("VERITAS_ENV", "production")

    with pytest.raises(RuntimeError, match="PII masking is DISABLED"):
        startup_health.check_runtime_feature_health(
            logger=logging.getLogger("test.startup_health"),
            has_sanitize=False,
            has_atomic_io=True,
        )


def test_check_runtime_feature_health_logs_atomic_io_warning_non_production(
    caplog,
):
    """Non-production should still surface atomic I/O degradation as a warning."""
    with caplog.at_level(logging.WARNING):
        startup_health.check_runtime_feature_health(
            logger=logging.getLogger("test.startup_health"),
            has_sanitize=True,
            has_atomic_io=False,
        )

    assert "Atomic I/O is DISABLED" in caplog.text


def test_check_runtime_feature_health_rejects_missing_atomic_io_in_production(
    monkeypatch,
):
    """Production must fail closed when crash-safe audit writes are unavailable."""
    monkeypatch.setenv("VERITAS_ENV", "production")

    with pytest.raises(RuntimeError, match="Atomic I/O is DISABLED"):
        startup_health.check_runtime_feature_health(
            logger=logging.getLogger("test.startup_health"),
            has_sanitize=True,
            has_atomic_io=False,
        )


def _trustlog_production_env() -> dict[str, str]:
    return {
        "VERITAS_ENV": "production",
        "VERITAS_TRUSTLOG_BACKEND": "postgresql",
        "VERITAS_DATABASE_URL": "postgresql://example",
        "VERITAS_ENCRYPTION_KEY": "dummy",
        "VERITAS_TRUSTLOG_SIGNER_BACKEND": "aws_kms",
        "VERITAS_TRUSTLOG_KMS_KEY_ID": "dummy-kms-key",
    }


def test_validate_startup_security_flags_non_production_trustlog_insecure_does_not_raise(
    monkeypatch,
):
    monkeypatch.delenv("VERITAS_POSTURE", raising=False)
    monkeypatch.delenv("VERITAS_REQUIRE_PRODUCTION_TRUSTLOG_POSTURE", raising=False)
    monkeypatch.setenv("VERITAS_ENV", "local")
    monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "jsonl")

    startup_health.validate_startup_security_flags(
        logger=logging.getLogger("test.startup_health")
    )


def test_validate_startup_security_flags_rejects_production_insecure_trustlog(monkeypatch):
    monkeypatch.setenv("VERITAS_ENV", "production")
    monkeypatch.delenv("VERITAS_TRUSTLOG_BACKEND", raising=False)
    monkeypatch.delenv("VERITAS_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("VERITAS_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("VERITAS_TRUSTLOG_SIGNER_BACKEND", raising=False)
    monkeypatch.delenv("VERITAS_TRUSTLOG_KMS_KEY_ID", raising=False)

    with pytest.raises(RuntimeError, match="TrustLog production posture check failed"):
        startup_health.validate_startup_security_flags(
            logger=logging.getLogger("test.startup_health")
        )


def test_validate_startup_security_flags_rejects_prod_alias_insecure_trustlog(monkeypatch):
    monkeypatch.setenv("VERITAS_ENV", "prod")
    monkeypatch.delenv("VERITAS_TRUSTLOG_BACKEND", raising=False)
    monkeypatch.delenv("VERITAS_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("VERITAS_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("VERITAS_TRUSTLOG_SIGNER_BACKEND", raising=False)
    monkeypatch.delenv("VERITAS_TRUSTLOG_KMS_KEY_ID", raising=False)

    with pytest.raises(RuntimeError, match="TrustLog production posture check failed"):
        startup_health.validate_startup_security_flags(
            logger=logging.getLogger("test.startup_health")
        )


def test_validate_startup_security_flags_allows_fully_configured_production_trustlog(
    monkeypatch,
):
    for key, value in {
        **_trustlog_production_env(),
        "VERITAS_TRUSTLOG_WORM_MIRROR_PATH": "/tmp/worm",
        "VERITAS_TRUSTLOG_TRANSPARENCY_REQUIRED": "1",
        "VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH": "/tmp/transparency.jsonl",
    }.items():
        monkeypatch.setenv(key, value)

    startup_health.validate_startup_security_flags(
        logger=logging.getLogger("test.startup_health")
    )


def test_validate_startup_security_flags_trustlog_warning_only_does_not_raise(
    monkeypatch,
    caplog,
):
    for key, value in _trustlog_production_env().items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("VERITAS_TRUSTLOG_WORM_MIRROR_PATH", raising=False)
    monkeypatch.delenv("VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH", raising=False)
    monkeypatch.setenv("VERITAS_TRUSTLOG_TRANSPARENCY_REQUIRED", "1")

    with caplog.at_level(logging.WARNING):
        startup_health.validate_startup_security_flags(
            logger=logging.getLogger("test.startup_health")
        )

    assert "TrustLog production posture warning" in caplog.text


def test_validate_startup_security_flags_rejects_production_file_signer_with_break_glass(
    monkeypatch,
):
    for key, value in _trustlog_production_env().items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("VERITAS_TRUSTLOG_SIGNER_BACKEND", "file")
    monkeypatch.setenv("VERITAS_TRUSTLOG_ALLOW_INSECURE_SIGNER_IN_PROD", "1")

    with pytest.raises(RuntimeError, match="signer backend must be aws_kms"):
        startup_health.validate_startup_security_flags(
            logger=logging.getLogger("test.startup_health")
        )


def test_validate_trustlog_production_posture_rejects_secure_posture_insecure_env(
    monkeypatch,
):
    monkeypatch.delenv("VERITAS_ENV", raising=False)
    monkeypatch.delenv("VERITAS_REQUIRE_PRODUCTION_TRUSTLOG_POSTURE", raising=False)
    monkeypatch.setenv("VERITAS_POSTURE", "secure")
    monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "jsonl")
    monkeypatch.delenv("VERITAS_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("VERITAS_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("VERITAS_TRUSTLOG_SIGNER_BACKEND", raising=False)
    monkeypatch.delenv("VERITAS_TRUSTLOG_KMS_KEY_ID", raising=False)

    with pytest.raises(RuntimeError, match="TrustLog production posture check failed"):
        startup_health.validate_trustlog_production_posture_on_startup(
            logger=logging.getLogger("test.startup_health")
        )


def test_run_startup_config_validation_raises_with_trustlog_enforcement_flag(
    monkeypatch,
):
    monkeypatch.delenv("VERITAS_ENV", raising=False)
    monkeypatch.delenv("VERITAS_POSTURE", raising=False)
    monkeypatch.setenv("VERITAS_REQUIRE_PRODUCTION_TRUSTLOG_POSTURE", "1")
    monkeypatch.delenv("VERITAS_TRUSTLOG_BACKEND", raising=False)
    monkeypatch.delenv("VERITAS_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("VERITAS_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("VERITAS_TRUSTLOG_SIGNER_BACKEND", raising=False)
    monkeypatch.delenv("VERITAS_TRUSTLOG_KMS_KEY_ID", raising=False)

    with pytest.raises(RuntimeError, match="TrustLog production posture check failed"):
        startup_health.run_startup_config_validation(
            logger=logging.getLogger("test.startup_health")
        )
