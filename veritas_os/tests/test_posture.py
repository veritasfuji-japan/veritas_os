# veritas_os/tests/test_posture.py
# -*- coding: utf-8 -*-
"""Unit tests for veritas_os.core.posture — runtime posture model.

Covers:
- posture resolution from VERITAS_POSTURE / VERITAS_ENV
- posture-derived governance defaults
- escape hatch behaviour (secure vs prod)
- startup validation and fail-closed semantics
- startup banner output
- singleton lifecycle
"""
from __future__ import annotations

import logging
import os
from unittest.mock import patch

import pytest

from veritas_os.core.posture import (
    PostureDefaults,
    PostureLevel,
    PostureStartupError,
    derive_defaults,
    get_active_posture,
    init_posture,
    log_posture_banner,
    reset_active_posture,
    resolve_posture,
    set_active_posture,
    validate_posture_startup,
)


# ── Helpers ──────────────────────────────────────────────────────────────

def _clean_env(monkeypatch):
    """Remove all posture-related env vars to guarantee a clean slate."""
    keys = [
        "VERITAS_POSTURE",
        "VERITAS_ENV",
        "VERITAS_POLICY_RUNTIME_ENFORCE",
        "VERITAS_ENFORCE_EXTERNAL_SECRET_MANAGER",
        "VERITAS_TRUSTLOG_TRANSPARENCY_REQUIRED",
        "VERITAS_TRUSTLOG_WORM_HARD_FAIL",
        "VERITAS_REPLAY_STRICT",
        "VERITAS_POSTURE_OVERRIDE_POLICY_ENFORCE",
        "VERITAS_POSTURE_OVERRIDE_EXTERNAL_SECRET_MGR",
        "VERITAS_POSTURE_OVERRIDE_TRUSTLOG_TRANSPARENCY",
        "VERITAS_POSTURE_OVERRIDE_TRUSTLOG_WORM",
        "VERITAS_POSTURE_OVERRIDE_REPLAY_STRICT",
        "VERITAS_SECRET_PROVIDER",
        "VERITAS_API_SECRET_REF",
        "VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH",
        "VERITAS_TRUSTLOG_WORM_MIRROR_PATH",
        "VERITAS_TRUSTLOG_MIRROR_BACKEND",
        "VERITAS_TRUSTLOG_S3_BUCKET",
        "VERITAS_TRUSTLOG_S3_PREFIX",
        "VERITAS_TRUSTLOG_ANCHOR_BACKEND",
        "VERITAS_TRUSTLOG_SIGNER_BACKEND",
        "VERITAS_TRUSTLOG_KMS_KEY_ID",
        "VERITAS_TRUSTLOG_ALLOW_INSECURE_SIGNER_IN_PROD",
    ]
    for k in keys:
        monkeypatch.delenv(k, raising=False)
    reset_active_posture()


def _set_minimum_strict_integrations(monkeypatch) -> None:
    """Set non-signer strict integrations so signer tests stay focused."""
    monkeypatch.setenv("VERITAS_SECRET_PROVIDER", "vault")
    monkeypatch.setenv("VERITAS_API_SECRET_REF", "secret/ref")
    monkeypatch.setenv("VERITAS_TRUSTLOG_MIRROR_BACKEND", "s3_object_lock")
    monkeypatch.setenv("VERITAS_TRUSTLOG_S3_BUCKET", "trustlog-prod")
    monkeypatch.setenv("VERITAS_TRUSTLOG_S3_PREFIX", "audit/worm")
    monkeypatch.setenv("VERITAS_TRUSTLOG_ANCHOR_BACKEND", "local")
    monkeypatch.setenv("VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH", "/var/transparency")


# ============================================================
# resolve_posture
# ============================================================

class TestResolvePosture:
    """Tests for posture resolution logic."""

    def test_default_is_dev(self, monkeypatch):
        _clean_env(monkeypatch)
        assert resolve_posture() == PostureLevel.DEV

    def test_explicit_parameter_wins(self, monkeypatch):
        _clean_env(monkeypatch)
        monkeypatch.setenv("VERITAS_POSTURE", "prod")
        assert resolve_posture(explicit="dev") == PostureLevel.DEV

    def test_veritas_posture_env(self, monkeypatch):
        _clean_env(monkeypatch)
        monkeypatch.setenv("VERITAS_POSTURE", "prod")
        assert resolve_posture() == PostureLevel.PROD

    def test_veritas_env_fallback(self, monkeypatch):
        _clean_env(monkeypatch)
        monkeypatch.setenv("VERITAS_ENV", "production")
        assert resolve_posture() == PostureLevel.PROD

    def test_veritas_posture_overrides_veritas_env(self, monkeypatch):
        _clean_env(monkeypatch)
        monkeypatch.setenv("VERITAS_POSTURE", "staging")
        monkeypatch.setenv("VERITAS_ENV", "production")
        assert resolve_posture() == PostureLevel.STAGING

    @pytest.mark.parametrize(
        "alias, expected",
        [
            ("dev", PostureLevel.DEV),
            ("development", PostureLevel.DEV),
            ("local", PostureLevel.DEV),
            ("test", PostureLevel.DEV),
            ("testing", PostureLevel.DEV),
            ("stg", PostureLevel.STAGING),
            ("staging", PostureLevel.STAGING),
            ("stage", PostureLevel.STAGING),
            ("secure", PostureLevel.SECURE),
            ("hardened", PostureLevel.SECURE),
            ("prod", PostureLevel.PROD),
            ("production", PostureLevel.PROD),
        ],
    )
    def test_alias_mapping(self, monkeypatch, alias, expected):
        _clean_env(monkeypatch)
        monkeypatch.setenv("VERITAS_POSTURE", alias)
        assert resolve_posture() == expected

    def test_unknown_value_falls_back_to_dev(self, monkeypatch, caplog):
        _clean_env(monkeypatch)
        monkeypatch.setenv("VERITAS_POSTURE", "totally_unknown_value")
        caplog.set_level(logging.WARNING)
        assert resolve_posture() == PostureLevel.DEV
        assert "Unknown VERITAS_POSTURE" in caplog.text

    def test_case_insensitive(self, monkeypatch):
        _clean_env(monkeypatch)
        monkeypatch.setenv("VERITAS_POSTURE", "PROD")
        assert resolve_posture() == PostureLevel.PROD

    def test_whitespace_stripped(self, monkeypatch):
        _clean_env(monkeypatch)
        monkeypatch.setenv("VERITAS_POSTURE", "  secure  ")
        assert resolve_posture() == PostureLevel.SECURE

    def test_empty_string_is_dev(self, monkeypatch):
        _clean_env(monkeypatch)
        monkeypatch.setenv("VERITAS_POSTURE", "")
        assert resolve_posture() == PostureLevel.DEV


# ============================================================
# derive_defaults — dev/staging
# ============================================================

class TestDeriveDefaultsDev:
    """Defaults for dev and staging postures."""

    def test_dev_all_off_by_default(self, monkeypatch):
        _clean_env(monkeypatch)
        d = derive_defaults(PostureLevel.DEV)
        assert d.posture == PostureLevel.DEV
        assert d.policy_runtime_enforce is False
        assert d.external_secret_manager_required is False
        assert d.trustlog_transparency_required is False
        assert d.trustlog_worm_hard_fail is False
        assert d.replay_strict is False
        assert d.is_strict is False

    def test_staging_all_off_by_default(self, monkeypatch):
        _clean_env(monkeypatch)
        d = derive_defaults(PostureLevel.STAGING)
        assert d.is_strict is False
        assert d.policy_runtime_enforce is False

    def test_dev_honours_explicit_env_on(self, monkeypatch):
        _clean_env(monkeypatch)
        monkeypatch.setenv("VERITAS_POLICY_RUNTIME_ENFORCE", "1")
        monkeypatch.setenv("VERITAS_REPLAY_STRICT", "true")
        d = derive_defaults(PostureLevel.DEV)
        assert d.policy_runtime_enforce is True
        assert d.replay_strict is True
        # Others still off
        assert d.external_secret_manager_required is False


# ============================================================
# derive_defaults — secure/prod
# ============================================================

class TestDeriveDefaultsStrict:
    """Defaults for secure and prod postures (all on)."""

    def test_prod_all_on(self, monkeypatch):
        _clean_env(monkeypatch)
        d = derive_defaults(PostureLevel.PROD)
        assert d.posture == PostureLevel.PROD
        assert d.policy_runtime_enforce is True
        assert d.external_secret_manager_required is True
        assert d.trustlog_transparency_required is True
        assert d.trustlog_worm_hard_fail is True
        assert d.replay_strict is True
        assert d.is_strict is True

    def test_secure_all_on_by_default(self, monkeypatch):
        _clean_env(monkeypatch)
        d = derive_defaults(PostureLevel.SECURE)
        assert d.policy_runtime_enforce is True
        assert d.is_strict is True

    def test_prod_ignores_escape_hatch(self, monkeypatch):
        _clean_env(monkeypatch)
        monkeypatch.setenv("VERITAS_POSTURE_OVERRIDE_POLICY_ENFORCE", "0")
        d = derive_defaults(PostureLevel.PROD)
        assert d.policy_runtime_enforce is True  # override ignored

    def test_secure_escape_hatch_disables_control(self, monkeypatch, caplog):
        _clean_env(monkeypatch)
        monkeypatch.setenv("VERITAS_POSTURE_OVERRIDE_POLICY_ENFORCE", "0")
        caplog.set_level(logging.WARNING)
        d = derive_defaults(PostureLevel.SECURE)
        assert d.policy_runtime_enforce is False
        assert "Escape hatch" in caplog.text

    def test_secure_escape_hatch_worm(self, monkeypatch):
        _clean_env(monkeypatch)
        monkeypatch.setenv("VERITAS_POSTURE_OVERRIDE_TRUSTLOG_WORM", "0")
        d = derive_defaults(PostureLevel.SECURE)
        assert d.trustlog_worm_hard_fail is False
        # Others still on
        assert d.policy_runtime_enforce is True
        assert d.replay_strict is True

    def test_secure_escape_hatch_all_off(self, monkeypatch):
        _clean_env(monkeypatch)
        monkeypatch.setenv("VERITAS_POSTURE_OVERRIDE_POLICY_ENFORCE", "0")
        monkeypatch.setenv("VERITAS_POSTURE_OVERRIDE_EXTERNAL_SECRET_MGR", "0")
        monkeypatch.setenv("VERITAS_POSTURE_OVERRIDE_TRUSTLOG_TRANSPARENCY", "0")
        monkeypatch.setenv("VERITAS_POSTURE_OVERRIDE_TRUSTLOG_WORM", "0")
        monkeypatch.setenv("VERITAS_POSTURE_OVERRIDE_REPLAY_STRICT", "0")
        d = derive_defaults(PostureLevel.SECURE)
        assert d.policy_runtime_enforce is False
        assert d.external_secret_manager_required is False
        assert d.trustlog_transparency_required is False
        assert d.trustlog_worm_hard_fail is False
        assert d.replay_strict is False


# ============================================================
# validate_posture_startup
# ============================================================

class TestValidatePostureStartup:
    """Startup validation for missing integrations."""

    def test_dev_no_errors(self, monkeypatch):
        _clean_env(monkeypatch)
        d = derive_defaults(PostureLevel.DEV)
        assert validate_posture_startup(d) == []

    def test_prod_missing_all_integrations(self, monkeypatch):
        _clean_env(monkeypatch)
        d = derive_defaults(PostureLevel.PROD)
        errors = validate_posture_startup(d)
        # 6 errors: strict integrations + backend requirements.
        assert len(errors) == 6
        assert any("VERITAS_SECRET_PROVIDER" in e for e in errors)
        assert any("VERITAS_API_SECRET_REF" in e for e in errors)
        assert any("immutable_retention" in e for e in errors)
        assert any("VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH" in e for e in errors)
        assert any(
            "managed_signing" in e
            for e in errors
        )

    def test_prod_all_integrations_present(self, monkeypatch):
        _clean_env(monkeypatch)
        monkeypatch.setenv("VERITAS_SECRET_PROVIDER", "vault")
        monkeypatch.setenv("VERITAS_API_SECRET_REF", "my/secret")
        monkeypatch.setenv("VERITAS_TRUSTLOG_MIRROR_BACKEND", "s3_object_lock")
        monkeypatch.setenv("VERITAS_TRUSTLOG_S3_BUCKET", "prod-bucket")
        monkeypatch.setenv("VERITAS_TRUSTLOG_S3_PREFIX", "audit/worm")
        monkeypatch.setenv("VERITAS_TRUSTLOG_ANCHOR_BACKEND", "local")
        monkeypatch.setenv(
            "VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH",
            "/var/transparency",
        )
        monkeypatch.setenv("VERITAS_TRUSTLOG_SIGNER_BACKEND", "aws_kms")
        monkeypatch.setenv(
            "VERITAS_TRUSTLOG_KMS_KEY_ID",
            "arn:aws:kms:us-east-1:111:key/prod",
        )
        d = derive_defaults(PostureLevel.PROD)
        assert validate_posture_startup(d) == []

    def test_secure_missing_integration_returns_errors(self, monkeypatch):
        _clean_env(monkeypatch)
        d = derive_defaults(PostureLevel.SECURE)
        errors = validate_posture_startup(d)
        assert len(errors) >= 1

    def test_secure_missing_kms_config_has_actionable_error(self, monkeypatch):
        """Secure posture requires KMS key when aws_kms signer is selected."""
        _clean_env(monkeypatch)
        _set_minimum_strict_integrations(monkeypatch)
        monkeypatch.setenv("VERITAS_TRUSTLOG_SIGNER_BACKEND", "aws_kms")
        monkeypatch.delenv("VERITAS_TRUSTLOG_KMS_KEY_ID", raising=False)
        defaults = derive_defaults(PostureLevel.SECURE)

        errors = validate_posture_startup(defaults)

        assert any(
            "VERITAS_TRUSTLOG_KMS_KEY_ID" in err and "aws_kms" in err
            for err in errors
        )

    def test_secure_missing_s3_config_has_actionable_errors(self, monkeypatch):
        """Secure posture requires S3 bucket and prefix for mirror backend."""
        _clean_env(monkeypatch)
        _set_minimum_strict_integrations(monkeypatch)
        monkeypatch.setenv("VERITAS_TRUSTLOG_SIGNER_BACKEND", "aws_kms")
        monkeypatch.setenv("VERITAS_TRUSTLOG_KMS_KEY_ID", "arn:aws:kms:us-east-1:1:key/a")
        monkeypatch.delenv("VERITAS_TRUSTLOG_S3_BUCKET", raising=False)
        monkeypatch.delenv("VERITAS_TRUSTLOG_S3_PREFIX", raising=False)
        defaults = derive_defaults(PostureLevel.SECURE)

        errors = validate_posture_startup(defaults)

        assert any("VERITAS_TRUSTLOG_S3_BUCKET" in err for err in errors)
        assert any("VERITAS_TRUSTLOG_S3_PREFIX" in err for err in errors)

    def test_secure_rejects_invalid_backend_combination(self, monkeypatch):
        """Secure posture rejects local mirror backend even with path set."""
        _clean_env(monkeypatch)
        _set_minimum_strict_integrations(monkeypatch)
        monkeypatch.setenv("VERITAS_TRUSTLOG_SIGNER_BACKEND", "aws_kms")
        monkeypatch.setenv("VERITAS_TRUSTLOG_KMS_KEY_ID", "arn:aws:kms:us-east-1:1:key/a")
        monkeypatch.setenv("VERITAS_TRUSTLOG_MIRROR_BACKEND", "local")
        monkeypatch.setenv("VERITAS_TRUSTLOG_WORM_MIRROR_PATH", "/var/worm")
        defaults = derive_defaults(PostureLevel.SECURE)

        errors = validate_posture_startup(defaults)

        assert any("immutable_retention" in err for err in errors)

    def test_dev_with_enforcement_on_missing_integration(self, monkeypatch):
        _clean_env(monkeypatch)
        monkeypatch.setenv("VERITAS_ENFORCE_EXTERNAL_SECRET_MANAGER", "1")
        d = derive_defaults(PostureLevel.DEV)
        errors = validate_posture_startup(d)
        assert any("VERITAS_SECRET_PROVIDER" in e for e in errors)

    def test_dev_with_file_trustlog_signer_succeeds(self, monkeypatch):
        """Dev posture keeps local file signer workflow available."""
        _clean_env(monkeypatch)
        monkeypatch.setenv("VERITAS_TRUSTLOG_MIRROR_BACKEND", "local")
        monkeypatch.setenv("VERITAS_TRUSTLOG_ANCHOR_BACKEND", "noop")
        monkeypatch.setenv("VERITAS_TRUSTLOG_SIGNER_BACKEND", "file")
        defaults = derive_defaults(PostureLevel.DEV)

        assert validate_posture_startup(defaults) == []

    def test_prod_with_file_trustlog_signer_fails(self, monkeypatch):
        """Prod posture must reject local file-based TrustLog signing."""
        _clean_env(monkeypatch)
        _set_minimum_strict_integrations(monkeypatch)
        monkeypatch.setenv("VERITAS_TRUSTLOG_SIGNER_BACKEND", "file")
        defaults = derive_defaults(PostureLevel.PROD)
        errors = validate_posture_startup(defaults)

        assert any(
            "managed_signing" in err
            for err in errors
        )

    def test_prod_with_aws_kms_trustlog_signer_succeeds(self, monkeypatch):
        """Prod posture accepts AWS KMS-backed TrustLog signer."""
        _clean_env(monkeypatch)
        _set_minimum_strict_integrations(monkeypatch)
        monkeypatch.setenv("VERITAS_TRUSTLOG_SIGNER_BACKEND", "aws_kms")
        monkeypatch.setenv(
            "VERITAS_TRUSTLOG_KMS_KEY_ID",
            "arn:aws:kms:us-east-1:111122223333:key/example-ed25519",
        )
        defaults = derive_defaults(PostureLevel.PROD)

        assert validate_posture_startup(defaults) == []

    def test_prod_with_file_signer_override_succeeds_with_warning(
        self,
        monkeypatch,
        caplog,
    ):
        """Break-glass override allows startup but emits unsupported warning."""
        _clean_env(monkeypatch)
        _set_minimum_strict_integrations(monkeypatch)
        monkeypatch.setenv("VERITAS_TRUSTLOG_SIGNER_BACKEND", "file")
        monkeypatch.setenv("VERITAS_TRUSTLOG_ALLOW_INSECURE_SIGNER_IN_PROD", "1")
        defaults = derive_defaults(PostureLevel.PROD)

        with caplog.at_level(logging.WARNING):
            errors = validate_posture_startup(defaults)

        assert errors == []
        assert (
            "VERITAS_TRUSTLOG_ALLOW_INSECURE_SIGNER_IN_PROD=1 is active"
            in caplog.text
        )
        assert "NOT enterprise supported" in caplog.text


# ============================================================
# init_posture — full startup flow
# ============================================================

class TestInitPosture:
    """End-to-end posture initialisation."""

    def test_dev_succeeds_without_integrations(self, monkeypatch):
        _clean_env(monkeypatch)
        d = init_posture(explicit="dev")
        assert d.posture == PostureLevel.DEV
        assert d.is_strict is False

    def test_prod_fails_without_integrations(self, monkeypatch):
        _clean_env(monkeypatch)
        with pytest.raises(PostureStartupError, match="missing required integrations"):
            init_posture(explicit="prod")

    def test_prod_succeeds_with_all_integrations(self, monkeypatch):
        _clean_env(monkeypatch)
        monkeypatch.setenv("VERITAS_SECRET_PROVIDER", "vault")
        monkeypatch.setenv("VERITAS_API_SECRET_REF", "path/to/secret")
        monkeypatch.setenv("VERITAS_TRUSTLOG_MIRROR_BACKEND", "s3_object_lock")
        monkeypatch.setenv("VERITAS_TRUSTLOG_S3_BUCKET", "prod-bucket")
        monkeypatch.setenv("VERITAS_TRUSTLOG_S3_PREFIX", "audit/worm")
        monkeypatch.setenv("VERITAS_TRUSTLOG_ANCHOR_BACKEND", "local")
        monkeypatch.setenv("VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH", "/var/t")
        monkeypatch.setenv("VERITAS_TRUSTLOG_SIGNER_BACKEND", "aws_kms")
        monkeypatch.setenv(
            "VERITAS_TRUSTLOG_KMS_KEY_ID",
            "arn:aws:kms:us-east-1:111:key/prod",
        )
        d = init_posture(explicit="prod")
        assert d.posture == PostureLevel.PROD
        assert d.is_strict is True

    def test_secure_fails_without_integrations(self, monkeypatch):
        _clean_env(monkeypatch)
        with pytest.raises(PostureStartupError):
            init_posture(explicit="secure")

    def test_secure_succeeds_with_escape_hatch(self, monkeypatch):
        _clean_env(monkeypatch)
        # Disable all strict controls via escape hatches
        monkeypatch.setenv("VERITAS_POSTURE_OVERRIDE_POLICY_ENFORCE", "0")
        monkeypatch.setenv("VERITAS_POSTURE_OVERRIDE_EXTERNAL_SECRET_MGR", "0")
        monkeypatch.setenv("VERITAS_POSTURE_OVERRIDE_TRUSTLOG_TRANSPARENCY", "0")
        monkeypatch.setenv("VERITAS_POSTURE_OVERRIDE_TRUSTLOG_WORM", "0")
        monkeypatch.setenv("VERITAS_POSTURE_OVERRIDE_REPLAY_STRICT", "0")
        monkeypatch.setenv("VERITAS_TRUSTLOG_SIGNER_BACKEND", "aws_kms")
        monkeypatch.setenv(
            "VERITAS_TRUSTLOG_KMS_KEY_ID",
            "arn:aws:kms:us-east-1:111:key/secure",
        )
        monkeypatch.setenv("VERITAS_TRUSTLOG_MIRROR_BACKEND", "s3_object_lock")
        monkeypatch.setenv("VERITAS_TRUSTLOG_S3_BUCKET", "secure-bucket")
        monkeypatch.setenv("VERITAS_TRUSTLOG_S3_PREFIX", "audit/worm")
        d = init_posture(explicit="secure")
        assert d.posture == PostureLevel.SECURE
        assert d.policy_runtime_enforce is False

    def test_fail_on_error_false_returns_defaults_anyway(self, monkeypatch):
        _clean_env(monkeypatch)
        d = init_posture(explicit="prod", fail_on_error=False)
        assert d.posture == PostureLevel.PROD
        # No exception raised even though integrations are missing


# ============================================================
# log_posture_banner
# ============================================================

class TestLogPostureBanner:
    """Startup banner contains posture information."""

    def test_banner_contains_posture_level(self, monkeypatch, caplog):
        _clean_env(monkeypatch)
        d = derive_defaults(PostureLevel.PROD)
        caplog.set_level(logging.INFO)
        banner = log_posture_banner(d)
        assert "Active posture: prod" in banner
        assert "Guarantees ON" in banner
        assert "policy_runtime_enforce" in banner

    def test_banner_dev_shows_off(self, monkeypatch, caplog):
        _clean_env(monkeypatch)
        d = derive_defaults(PostureLevel.DEV)
        caplog.set_level(logging.INFO)
        banner = log_posture_banner(d)
        assert "Active posture: dev" in banner
        assert "Guarantees OFF" in banner

    def test_banner_logged_to_info(self, monkeypatch, caplog):
        _clean_env(monkeypatch)
        d = derive_defaults(PostureLevel.STAGING)
        caplog.set_level(logging.INFO)
        log_posture_banner(d)
        assert "[POSTURE]" in caplog.text


# ============================================================
# Singleton lifecycle
# ============================================================

class TestSingleton:
    """get_active_posture / set_active_posture / reset_active_posture."""

    def test_get_active_posture_lazy_init(self, monkeypatch):
        _clean_env(monkeypatch)
        p = get_active_posture()
        assert isinstance(p, PostureDefaults)
        assert p.posture == PostureLevel.DEV

    def test_set_active_posture(self, monkeypatch):
        _clean_env(monkeypatch)
        prod = derive_defaults(PostureLevel.PROD)
        set_active_posture(prod)
        assert get_active_posture().posture == PostureLevel.PROD
        reset_active_posture()

    def test_reset_active_posture(self, monkeypatch):
        _clean_env(monkeypatch)
        prod = derive_defaults(PostureLevel.PROD)
        set_active_posture(prod)
        reset_active_posture()
        # After reset, lazy init kicks in again → dev
        p = get_active_posture()
        assert p.posture == PostureLevel.DEV


# ============================================================
# Integration: startup_health.should_fail_fast_startup
# ============================================================

class TestStartupHealthPostureIntegration:
    """should_fail_fast_startup respects VERITAS_POSTURE."""

    def test_posture_prod_triggers_fail_fast(self, monkeypatch):
        _clean_env(monkeypatch)
        monkeypatch.setenv("VERITAS_POSTURE", "prod")
        from veritas_os.api.startup_health import should_fail_fast_startup
        assert should_fail_fast_startup() is True

    def test_posture_secure_triggers_fail_fast(self, monkeypatch):
        _clean_env(monkeypatch)
        monkeypatch.setenv("VERITAS_POSTURE", "secure")
        from veritas_os.api.startup_health import should_fail_fast_startup
        assert should_fail_fast_startup() is True

    def test_posture_dev_no_fail_fast(self, monkeypatch):
        _clean_env(monkeypatch)
        monkeypatch.setenv("VERITAS_POSTURE", "dev")
        from veritas_os.api.startup_health import should_fail_fast_startup
        assert should_fail_fast_startup() is False

    def test_legacy_veritas_env_still_works(self, monkeypatch):
        _clean_env(monkeypatch)
        monkeypatch.setenv("VERITAS_ENV", "production")
        from veritas_os.api.startup_health import should_fail_fast_startup
        assert should_fail_fast_startup() is True

    def test_no_env_no_fail_fast(self, monkeypatch):
        _clean_env(monkeypatch)
        from veritas_os.api.startup_health import should_fail_fast_startup
        assert should_fail_fast_startup() is False


# ============================================================
# PostureDefaults frozen
# ============================================================

class TestPostureDefaultsImmutable:
    """PostureDefaults is frozen and cannot be mutated."""

    def test_frozen(self, monkeypatch):
        _clean_env(monkeypatch)
        d = derive_defaults(PostureLevel.DEV)
        with pytest.raises(AttributeError):
            d.policy_runtime_enforce = True  # type: ignore[misc]


# ============================================================
# Capability model
# ============================================================

class TestBackendCapabilities:
    """Tests for the capability-aware backend registry."""

    def test_aws_kms_signer_has_managed_signing(self):
        from veritas_os.core.posture import (
            BackendCapability,
            signer_capabilities,
        )
        caps = signer_capabilities("aws_kms")
        assert BackendCapability.MANAGED_SIGNING in caps
        assert BackendCapability.FAIL_CLOSED in caps

    def test_file_signer_lacks_managed_signing(self):
        from veritas_os.core.posture import (
            BackendCapability,
            signer_capabilities,
        )
        caps = signer_capabilities("file")
        assert BackendCapability.MANAGED_SIGNING not in caps

    def test_s3_object_lock_mirror_has_immutable_retention(self):
        from veritas_os.core.posture import (
            BackendCapability,
            mirror_capabilities,
        )
        caps = mirror_capabilities("s3_object_lock")
        assert BackendCapability.IMMUTABLE_RETENTION in caps
        assert BackendCapability.FAIL_CLOSED in caps

    def test_local_mirror_lacks_immutable_retention(self):
        from veritas_os.core.posture import (
            BackendCapability,
            mirror_capabilities,
        )
        caps = mirror_capabilities("local")
        assert BackendCapability.IMMUTABLE_RETENTION not in caps

    def test_local_anchor_has_transparency(self):
        from veritas_os.core.posture import (
            BackendCapability,
            anchor_capabilities,
        )
        caps = anchor_capabilities("local")
        assert BackendCapability.TRANSPARENCY_ANCHORING in caps

    def test_noop_anchor_lacks_transparency(self):
        from veritas_os.core.posture import (
            BackendCapability,
            anchor_capabilities,
        )
        caps = anchor_capabilities("noop")
        assert BackendCapability.TRANSPARENCY_ANCHORING not in caps

    def test_tsa_anchor_has_transparency(self):
        from veritas_os.core.posture import (
            BackendCapability,
            anchor_capabilities,
        )
        caps = anchor_capabilities("tsa")
        assert BackendCapability.TRANSPARENCY_ANCHORING in caps
        assert BackendCapability.FAIL_CLOSED in caps

    def test_unknown_backend_returns_empty(self):
        from veritas_os.core.posture import (
            signer_capabilities,
            mirror_capabilities,
            anchor_capabilities,
        )
        assert signer_capabilities("unknown_vendor") == frozenset()
        assert mirror_capabilities("unknown_vendor") == frozenset()
        assert anchor_capabilities("unknown_vendor") == frozenset()


# ============================================================
# Capability-aware startup validation
# ============================================================

class TestCapabilityAwareValidation:
    """Verify startup validator uses capabilities, not vendor names."""

    def test_dev_file_signer_local_mirror_passes(self, monkeypatch):
        """dev/local: file signer + local mirror works as before."""
        _clean_env(monkeypatch)
        monkeypatch.setenv("VERITAS_TRUSTLOG_SIGNER_BACKEND", "file")
        monkeypatch.setenv("VERITAS_TRUSTLOG_MIRROR_BACKEND", "local")
        monkeypatch.setenv("VERITAS_TRUSTLOG_ANCHOR_BACKEND", "noop")
        d = derive_defaults(PostureLevel.DEV)
        assert validate_posture_startup(d) == []

    def test_secure_rejects_incapable_signer(self, monkeypatch):
        """Secure posture rejects signer without managed_signing capability."""
        _clean_env(monkeypatch)
        _set_minimum_strict_integrations(monkeypatch)
        monkeypatch.setenv("VERITAS_TRUSTLOG_SIGNER_BACKEND", "file")
        d = derive_defaults(PostureLevel.SECURE)
        errors = validate_posture_startup(d)
        assert any("managed_signing" in e for e in errors)

    def test_secure_rejects_incapable_mirror(self, monkeypatch):
        """Secure posture rejects mirror without immutable_retention."""
        _clean_env(monkeypatch)
        _set_minimum_strict_integrations(monkeypatch)
        monkeypatch.setenv("VERITAS_TRUSTLOG_SIGNER_BACKEND", "aws_kms")
        monkeypatch.setenv("VERITAS_TRUSTLOG_KMS_KEY_ID", "arn:aws:kms:x:1:key/a")
        monkeypatch.setenv("VERITAS_TRUSTLOG_MIRROR_BACKEND", "local")
        monkeypatch.setenv("VERITAS_TRUSTLOG_WORM_MIRROR_PATH", "/var/worm")
        d = derive_defaults(PostureLevel.SECURE)
        errors = validate_posture_startup(d)
        assert any("immutable_retention" in e for e in errors)

    def test_prod_aws_kms_s3_passes(self, monkeypatch):
        """prod: aws_kms + s3_object_lock passes as before."""
        _clean_env(monkeypatch)
        monkeypatch.setenv("VERITAS_SECRET_PROVIDER", "vault")
        monkeypatch.setenv("VERITAS_API_SECRET_REF", "path/to/secret")
        monkeypatch.setenv("VERITAS_TRUSTLOG_MIRROR_BACKEND", "s3_object_lock")
        monkeypatch.setenv("VERITAS_TRUSTLOG_S3_BUCKET", "prod-bucket")
        monkeypatch.setenv("VERITAS_TRUSTLOG_S3_PREFIX", "audit/worm")
        monkeypatch.setenv("VERITAS_TRUSTLOG_ANCHOR_BACKEND", "local")
        monkeypatch.setenv("VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH", "/var/t")
        monkeypatch.setenv("VERITAS_TRUSTLOG_SIGNER_BACKEND", "aws_kms")
        monkeypatch.setenv("VERITAS_TRUSTLOG_KMS_KEY_ID", "arn:aws:kms:x:1:key/p")
        d = derive_defaults(PostureLevel.PROD)
        assert validate_posture_startup(d) == []

    def test_prod_file_local_rejected(self, monkeypatch):
        """prod: file/local backends are still rejected."""
        _clean_env(monkeypatch)
        _set_minimum_strict_integrations(monkeypatch)
        monkeypatch.setenv("VERITAS_TRUSTLOG_SIGNER_BACKEND", "file")
        monkeypatch.setenv("VERITAS_TRUSTLOG_MIRROR_BACKEND", "local")
        d = derive_defaults(PostureLevel.PROD)
        errors = validate_posture_startup(d)
        assert any("managed_signing" in e for e in errors)
        assert any("immutable_retention" in e for e in errors)

    def test_refusal_messages_are_capability_based(self, monkeypatch):
        """Refusal messages reference capabilities, not just vendor names."""
        _clean_env(monkeypatch)
        _set_minimum_strict_integrations(monkeypatch)
        monkeypatch.setenv("VERITAS_TRUSTLOG_SIGNER_BACKEND", "file")
        monkeypatch.setenv("VERITAS_TRUSTLOG_MIRROR_BACKEND", "local")
        d = derive_defaults(PostureLevel.PROD)
        errors = validate_posture_startup(d)
        # Messages should mention the capability being checked
        signer_err = [e for e in errors if "signer" in e.lower()]
        mirror_err = [e for e in errors if "mirror" in e.lower()]
        assert len(signer_err) >= 1
        assert len(mirror_err) >= 1
        assert any("managed_signing" in e for e in signer_err)
        assert any("immutable_retention" in e for e in mirror_err)

    def test_backward_compat_break_glass_still_works(self, monkeypatch, caplog):
        """Break-glass override for file signer still works in prod."""
        _clean_env(monkeypatch)
        _set_minimum_strict_integrations(monkeypatch)
        monkeypatch.setenv("VERITAS_TRUSTLOG_SIGNER_BACKEND", "file")
        monkeypatch.setenv("VERITAS_TRUSTLOG_ALLOW_INSECURE_SIGNER_IN_PROD", "1")
        d = derive_defaults(PostureLevel.PROD)
        with caplog.at_level(logging.WARNING):
            errors = validate_posture_startup(d)
        # Break-glass allows startup
        signer_errors = [e for e in errors if "signer" in e.lower()]
        assert signer_errors == []
        assert "NOT enterprise supported" in caplog.text


# ============================================================
# Mock future backend — proves capability-based (not vendor-based)
# ============================================================

class TestMockFutureBackendCapability:
    """Register a hypothetical future backend and verify it passes
    secure/prod validation based on capabilities, not vendor name.

    This confirms the validator is truly capability-aware: an unknown
    backend name can pass validation if it declares the right capabilities.
    """

    def test_future_signer_with_managed_signing_passes_prod(self, monkeypatch):
        """A hypothetical 'azure_keyvault' signer with managed_signing
        capability should pass secure/prod validation."""
        from veritas_os.core.posture import (
            BackendCapability,
            _SIGNER_CAPABILITIES,
        )
        _clean_env(monkeypatch)
        # Register mock future backend
        _SIGNER_CAPABILITIES["azure_keyvault"] = frozenset({
            BackendCapability.MANAGED_SIGNING,
            BackendCapability.FAIL_CLOSED,
        })
        try:
            monkeypatch.setenv("VERITAS_SECRET_PROVIDER", "vault")
            monkeypatch.setenv("VERITAS_API_SECRET_REF", "path/to/s")
            monkeypatch.setenv("VERITAS_TRUSTLOG_MIRROR_BACKEND", "s3_object_lock")
            monkeypatch.setenv("VERITAS_TRUSTLOG_S3_BUCKET", "b")
            monkeypatch.setenv("VERITAS_TRUSTLOG_S3_PREFIX", "p")
            monkeypatch.setenv("VERITAS_TRUSTLOG_ANCHOR_BACKEND", "local")
            monkeypatch.setenv("VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH", "/v")
            monkeypatch.setenv("VERITAS_TRUSTLOG_SIGNER_BACKEND", "azure_keyvault")
            d = derive_defaults(PostureLevel.PROD)
            errors = validate_posture_startup(d)
            # No signer-capability errors (may have kms_key_id error for
            # aws_kms-specific config, but that doesn't apply here)
            assert not any("managed_signing" in e for e in errors)
        finally:
            _SIGNER_CAPABILITIES.pop("azure_keyvault", None)

    def test_future_mirror_with_immutable_retention_passes_prod(self, monkeypatch):
        """A hypothetical 'azure_blob_immutable' mirror with
        immutable_retention should pass secure/prod validation."""
        from veritas_os.core.posture import (
            BackendCapability,
            _MIRROR_CAPABILITIES,
        )
        _clean_env(monkeypatch)
        _MIRROR_CAPABILITIES["azure_blob_immutable"] = frozenset({
            BackendCapability.IMMUTABLE_RETENTION,
            BackendCapability.FAIL_CLOSED,
        })
        try:
            monkeypatch.setenv("VERITAS_SECRET_PROVIDER", "vault")
            monkeypatch.setenv("VERITAS_API_SECRET_REF", "path/to/s")
            monkeypatch.setenv("VERITAS_TRUSTLOG_MIRROR_BACKEND",
                               "azure_blob_immutable")
            monkeypatch.setenv("VERITAS_TRUSTLOG_ANCHOR_BACKEND", "local")
            monkeypatch.setenv("VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH", "/v")
            monkeypatch.setenv("VERITAS_TRUSTLOG_SIGNER_BACKEND", "aws_kms")
            monkeypatch.setenv("VERITAS_TRUSTLOG_KMS_KEY_ID", "arn:key")
            d = derive_defaults(PostureLevel.PROD)
            errors = validate_posture_startup(d)
            assert not any("immutable_retention" in e for e in errors)
        finally:
            _MIRROR_CAPABILITIES.pop("azure_blob_immutable", None)

    def test_future_backend_without_capability_rejected(self, monkeypatch):
        """A future backend without the needed capability is rejected."""
        from veritas_os.core.posture import (
            _SIGNER_CAPABILITIES,
        )
        _clean_env(monkeypatch)
        # Register with empty capabilities — should be rejected
        _SIGNER_CAPABILITIES["weak_signer"] = frozenset()
        try:
            _set_minimum_strict_integrations(monkeypatch)
            monkeypatch.setenv("VERITAS_TRUSTLOG_SIGNER_BACKEND", "weak_signer")
            d = derive_defaults(PostureLevel.PROD)
            errors = validate_posture_startup(d)
            assert any("managed_signing" in e for e in errors)
        finally:
            _SIGNER_CAPABILITIES.pop("weak_signer", None)
