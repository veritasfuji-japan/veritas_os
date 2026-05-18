"""Tests for TrustLog production posture security checker."""

from __future__ import annotations

import pytest

from scripts.security.check_trustlog_production_posture import main
from veritas_os.security.trustlog_production_posture import check_trustlog_production_posture


def _production_base_env() -> dict[str, str]:
    return {
        "VERITAS_ENV": "production",
        "VERITAS_TRUSTLOG_BACKEND": "postgresql",
        "VERITAS_DATABASE_URL": "postgresql://example",
        "VERITAS_ENCRYPTION_KEY": "dummy",
        "VERITAS_TRUSTLOG_SIGNER_BACKEND": "aws_kms",
        "VERITAS_TRUSTLOG_KMS_KEY_ID": "dummy-kms-key",
    }


def test_development_env_passes() -> None:
    result = check_trustlog_production_posture({})
    assert result.passed is True
    assert result.failures == ()


def test_development_insecure_defaults_do_not_fail() -> None:
    env = {
        "VERITAS_TRUSTLOG_BACKEND": "jsonl",
        "VERITAS_TRUSTLOG_SIGNER_BACKEND": "file",
    }
    result = check_trustlog_production_posture(env)
    assert result.passed is True


def test_production_missing_backend_fails() -> None:
    result = check_trustlog_production_posture({"VERITAS_ENV": "production"})
    assert any("backend must be postgresql" in item for item in result.failures)


def test_production_jsonl_backend_fails() -> None:
    result = check_trustlog_production_posture(
        {"VERITAS_ENV": "production", "VERITAS_TRUSTLOG_BACKEND": "jsonl"}
    )
    assert any("backend must be postgresql" in item for item in result.failures)


def test_prod_alias_enforces_production_posture() -> None:
    result = check_trustlog_production_posture({"VERITAS_ENV": "prod"})
    assert result.passed is False
    assert any("backend must be postgresql" in item for item in result.failures)


def test_secure_env_alias_enforces_production_posture() -> None:
    result = check_trustlog_production_posture({"VERITAS_ENV": "secure"})
    assert result.passed is False
    assert any("backend must be postgresql" in item for item in result.failures)


def test_hardened_env_alias_enforces_production_posture() -> None:
    result = check_trustlog_production_posture({"VERITAS_ENV": "hardened"})
    assert result.passed is False
    assert any("backend must be postgresql" in item for item in result.failures)


def test_local_env_alias_does_not_enforce_production_posture() -> None:
    result = check_trustlog_production_posture({"VERITAS_ENV": "local"})
    assert result.passed is True
    assert result.failures == ()


def test_production_postgresql_without_database_url_fails() -> None:
    result = check_trustlog_production_posture(
        {"VERITAS_ENV": "production", "VERITAS_TRUSTLOG_BACKEND": "postgresql"}
    )
    assert any("requires VERITAS_DATABASE_URL or DATABASE_URL" in item for item in result.failures)


def test_production_missing_encryption_key_fails() -> None:
    env = {
        "VERITAS_ENV": "production",
        "VERITAS_TRUSTLOG_BACKEND": "postgresql",
        "VERITAS_DATABASE_URL": "postgresql://example",
        "VERITAS_TRUSTLOG_SIGNER_BACKEND": "aws_kms",
        "VERITAS_TRUSTLOG_KMS_KEY_ID": "dummy-kms-key",
    }
    result = check_trustlog_production_posture(env)
    assert any("VERITAS_ENCRYPTION_KEY" in item for item in result.failures)


def test_production_file_signer_fails_even_with_override() -> None:
    env = {
        "VERITAS_ENV": "production",
        "VERITAS_TRUSTLOG_BACKEND": "postgresql",
        "VERITAS_DATABASE_URL": "postgresql://example",
        "VERITAS_ENCRYPTION_KEY": "dummy",
        "VERITAS_TRUSTLOG_SIGNER_BACKEND": "file",
        "VERITAS_TRUSTLOG_ALLOW_INSECURE_SIGNER_IN_PROD": "1",
    }
    result = check_trustlog_production_posture(env)
    assert any("signer backend must be aws_kms" in item for item in result.failures)
    assert not any("KMS_KEY_ID" in item for item in result.failures)


def test_production_file_ed25519_signer_fails() -> None:
    env = {
        "VERITAS_ENV": "production",
        "VERITAS_TRUSTLOG_BACKEND": "postgresql",
        "VERITAS_DATABASE_URL": "postgresql://example",
        "VERITAS_ENCRYPTION_KEY": "dummy",
        "VERITAS_TRUSTLOG_SIGNER_BACKEND": "file_ed25519",
        "VERITAS_TRUSTLOG_KMS_KEY_ID": "dummy-kms-key",
    }
    result = check_trustlog_production_posture(env)
    assert any("signer backend must be aws_kms" in item for item in result.failures)


def test_production_aws_kms_without_kms_key_fails() -> None:
    env = {
        "VERITAS_ENV": "production",
        "VERITAS_TRUSTLOG_BACKEND": "postgresql",
        "VERITAS_DATABASE_URL": "postgresql://example",
        "VERITAS_ENCRYPTION_KEY": "dummy",
        "VERITAS_TRUSTLOG_SIGNER_BACKEND": "aws_kms",
    }
    result = check_trustlog_production_posture(env)
    assert any("KMS_KEY_ID" in item for item in result.failures)


def test_production_aws_kms_ed25519_without_kms_key_fails() -> None:
    env = {
        "VERITAS_ENV": "production",
        "VERITAS_TRUSTLOG_BACKEND": "postgresql",
        "VERITAS_DATABASE_URL": "postgresql://example",
        "VERITAS_ENCRYPTION_KEY": "dummy",
        "VERITAS_TRUSTLOG_SIGNER_BACKEND": "aws_kms_ed25519",
    }
    result = check_trustlog_production_posture(env)
    assert any("KMS_KEY_ID" in item for item in result.failures)


def test_production_fully_configured_passes() -> None:
    env = {
        **_production_base_env(),
        "VERITAS_TRUSTLOG_WORM_MIRROR_PATH": "/tmp/worm",
        "VERITAS_TRUSTLOG_TRANSPARENCY_REQUIRED": "1",
        "VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH": "/tmp/transparency.jsonl",
    }
    result = check_trustlog_production_posture(env)
    assert result.passed is True
    assert result.failures == ()


def test_secure_env_fully_configured_passes() -> None:
    env = {
        **_production_base_env(),
        "VERITAS_ENV": "secure",
        "VERITAS_TRUSTLOG_WORM_MIRROR_PATH": "/tmp/worm",
        "VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH": "/tmp/transparency.jsonl",
    }
    result = check_trustlog_production_posture(env)
    assert result.passed is True
    assert result.failures == ()


def test_production_aws_kms_ed25519_signer_passes() -> None:
    env = {
        **_production_base_env(),
        "VERITAS_TRUSTLOG_SIGNER_BACKEND": "aws_kms_ed25519",
        "VERITAS_TRUSTLOG_WORM_MIRROR_PATH": "/tmp/worm",
        "VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH": "/tmp/transparency.jsonl",
    }
    result = check_trustlog_production_posture(env)
    assert result.passed is True
    assert result.failures == ()


def test_production_local_mirror_without_worm_emits_warning() -> None:
    env = {
        **_production_base_env(),
        "VERITAS_TRUSTLOG_TRANSPARENCY_REQUIRED": "1",
        "VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH": "/tmp/transparency.jsonl",
    }
    result = check_trustlog_production_posture(env)
    assert result.passed is True
    assert any("local WORM mirror path" in item for item in result.warnings)


def test_production_s3_object_lock_without_worm_path_no_local_warning() -> None:
    env = {
        **_production_base_env(),
        "VERITAS_TRUSTLOG_MIRROR_BACKEND": "s3_object_lock",
        "VERITAS_TRUSTLOG_S3_BUCKET": "bucket",
        "VERITAS_TRUSTLOG_S3_PREFIX": "prefix",
        "VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH": "/tmp/transparency.jsonl",
    }
    result = check_trustlog_production_posture(env)
    assert not any("local WORM mirror path" in item for item in result.warnings)


def test_production_s3_object_lock_missing_bucket_or_prefix_emits_warning() -> None:
    env = {
        **_production_base_env(),
        "VERITAS_TRUSTLOG_MIRROR_BACKEND": "s3_object_lock",
        "VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH": "/tmp/transparency.jsonl",
    }
    result = check_trustlog_production_posture(env)
    assert any("s3_object_lock mirror requires" in item for item in result.warnings)


def test_production_s3_object_lock_with_bucket_and_prefix_has_no_mirror_warning() -> None:
    env = {
        **_production_base_env(),
        "VERITAS_TRUSTLOG_MIRROR_BACKEND": "s3_object_lock",
        "VERITAS_TRUSTLOG_S3_BUCKET": "bucket",
        "VERITAS_TRUSTLOG_S3_PREFIX": "prefix",
        "VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH": "/tmp/transparency.jsonl",
    }
    result = check_trustlog_production_posture(env)
    assert not any("mirror" in item for item in result.warnings)


def test_unrecognized_mirror_backend_warning_includes_backend_value() -> None:
    env = {
        **_production_base_env(),
        "VERITAS_TRUSTLOG_MIRROR_BACKEND": "unknown_backend",
        "VERITAS_TRUSTLOG_WORM_MIRROR_PATH": "/tmp/worm",
        "VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH": "/tmp/transparency.jsonl",
    }
    result = check_trustlog_production_posture(env)
    assert any("unknown_backend" in item for item in result.warnings)


def test_anchor_noop_emits_warning() -> None:
    env = {
        **_production_base_env(),
        "VERITAS_TRUSTLOG_WORM_MIRROR_PATH": "/tmp/worm",
        "VERITAS_TRUSTLOG_TRANSPARENCY_REQUIRED": "1",
        "VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH": "/tmp/transparency.jsonl",
        "VERITAS_TRUSTLOG_ANCHOR_BACKEND": "noop",
    }
    result = check_trustlog_production_posture(env)
    assert result.passed is True
    assert any("anchor backend is noop" in item for item in result.warnings)


def test_anchor_no_op_emits_warning() -> None:
    env = {
        **_production_base_env(),
        "VERITAS_TRUSTLOG_WORM_MIRROR_PATH": "/tmp/worm",
        "VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH": "/tmp/transparency.jsonl",
        "VERITAS_TRUSTLOG_ANCHOR_BACKEND": "no_op",
    }
    result = check_trustlog_production_posture(env)
    assert any("anchor backend is noop" in item for item in result.warnings)


def test_anchor_none_emits_warning() -> None:
    env = {
        **_production_base_env(),
        "VERITAS_TRUSTLOG_WORM_MIRROR_PATH": "/tmp/worm",
        "VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH": "/tmp/transparency.jsonl",
        "VERITAS_TRUSTLOG_ANCHOR_BACKEND": "none",
    }
    result = check_trustlog_production_posture(env)
    assert any("anchor backend is noop" in item for item in result.warnings)


def test_anchor_default_local_does_not_emit_noop_warning() -> None:
    env = {
        **_production_base_env(),
        "VERITAS_TRUSTLOG_WORM_MIRROR_PATH": "/tmp/worm",
        "VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH": "/tmp/transparency.jsonl",
    }
    result = check_trustlog_production_posture(env)
    assert not any("anchor backend is noop" in item for item in result.warnings)


def test_local_anchor_required_transparency_without_path_emits_local_path_warning() -> None:
    env = {
        **_production_base_env(),
        "VERITAS_TRUSTLOG_WORM_MIRROR_PATH": "/tmp/worm",
    }
    result = check_trustlog_production_posture(env)
    assert any("local transparency log path is not configured" in item for item in result.warnings)


def test_transparency_disabled_without_path_does_not_emit_local_path_warning() -> None:
    env = {
        **_production_base_env(),
        "VERITAS_TRUSTLOG_WORM_MIRROR_PATH": "/tmp/worm",
        "VERITAS_TRUSTLOG_TRANSPARENCY_REQUIRED": "0",
    }
    result = check_trustlog_production_posture(env)
    assert any("anchoring is not required" in item for item in result.warnings)
    assert not any("local transparency log path is not configured" in item for item in result.warnings)


def test_tsa_anchor_missing_path_does_not_emit_local_path_warning() -> None:
    env = {
        **_production_base_env(),
        "VERITAS_TRUSTLOG_WORM_MIRROR_PATH": "/tmp/worm",
        "VERITAS_TRUSTLOG_ANCHOR_BACKEND": "tsa",
    }
    result = check_trustlog_production_posture(env)
    assert not any("local transparency log path is not configured" in item for item in result.warnings)


def test_noop_anchor_missing_path_does_not_emit_local_path_warning() -> None:
    env = {
        **_production_base_env(),
        "VERITAS_TRUSTLOG_WORM_MIRROR_PATH": "/tmp/worm",
        "VERITAS_TRUSTLOG_ANCHOR_BACKEND": "noop",
    }
    result = check_trustlog_production_posture(env)
    assert any("anchor backend is noop" in item for item in result.warnings)
    assert not any("local transparency log path is not configured" in item for item in result.warnings)


def test_require_production_flag_enforces_check() -> None:
    env = {"VERITAS_REQUIRE_PRODUCTION_TRUSTLOG_POSTURE": "1"}
    result = check_trustlog_production_posture(env)
    assert result.passed is False


def test_require_production_flag_truthy_alias_enforces_check() -> None:
    env = {"VERITAS_REQUIRE_PRODUCTION_TRUSTLOG_POSTURE": "true"}
    result = check_trustlog_production_posture(env)
    assert result.passed is False


def test_production_transparency_unset_does_not_warn_not_required() -> None:
    env = {
        **_production_base_env(),
        "VERITAS_TRUSTLOG_WORM_MIRROR_PATH": "/tmp/worm",
        "VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH": "/tmp/transparency.jsonl",
    }
    result = check_trustlog_production_posture(env)
    assert not any("anchoring is not required" in item for item in result.warnings)


def test_secure_env_transparency_unset_does_not_warn_not_required() -> None:
    env = {
        **_production_base_env(),
        "VERITAS_ENV": "secure",
        "VERITAS_TRUSTLOG_WORM_MIRROR_PATH": "/tmp/worm",
    }
    result = check_trustlog_production_posture(env)
    assert not any("anchoring is not required" in item for item in result.warnings)


def test_production_transparency_explicit_zero_warns_not_required() -> None:
    env = {
        **_production_base_env(),
        "VERITAS_TRUSTLOG_WORM_MIRROR_PATH": "/tmp/worm",
        "VERITAS_TRUSTLOG_TRANSPARENCY_REQUIRED": "0",
        "VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH": "/tmp/transparency.jsonl",
    }
    result = check_trustlog_production_posture(env)
    assert any("anchoring is not required" in item for item in result.warnings)


def test_require_production_flag_with_transparency_unset_does_not_warn_not_required() -> None:
    env = {
        "VERITAS_REQUIRE_PRODUCTION_TRUSTLOG_POSTURE": "1",
        "VERITAS_TRUSTLOG_BACKEND": "postgresql",
        "VERITAS_DATABASE_URL": "postgresql://example",
        "VERITAS_ENCRYPTION_KEY": "dummy",
        "VERITAS_TRUSTLOG_SIGNER_BACKEND": "aws_kms",
        "VERITAS_TRUSTLOG_KMS_KEY_ID": "dummy-kms-key",
        "VERITAS_TRUSTLOG_WORM_MIRROR_PATH": "/tmp/worm",
        "VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH": "/tmp/transparency.jsonl",
    }
    result = check_trustlog_production_posture(env)
    assert not any("anchoring is not required" in item for item in result.warnings)


def test_trustlog_enforcement_flag_truthy_values_enable_production_posture() -> None:
    for value in ("1", "true", "yes", "on"):
        result = check_trustlog_production_posture(
            {"VERITAS_REQUIRE_PRODUCTION_TRUSTLOG_POSTURE": value}
        )
        assert result.passed is False
        assert any("backend must be postgresql" in item for item in result.failures)


def test_trustlog_enforcement_flag_falsy_values_do_not_enable_production_posture() -> None:
    for value in ("0", "false", "no", "off", ""):
        result = check_trustlog_production_posture(
            {"VERITAS_REQUIRE_PRODUCTION_TRUSTLOG_POSTURE": value}
        )
        assert result.passed is True
        assert result.failures == ()


def test_cli_main_returns_zero_in_development(monkeypatch) -> None:
    monkeypatch.delenv("VERITAS_ENV", raising=False)
    monkeypatch.delenv("VERITAS_REQUIRE_PRODUCTION_TRUSTLOG_POSTURE", raising=False)
    assert main() == 0


def test_cli_main_returns_one_in_production_insecure(monkeypatch) -> None:
    monkeypatch.setenv("VERITAS_ENV", "production")
    monkeypatch.delenv("VERITAS_TRUSTLOG_BACKEND", raising=False)
    monkeypatch.delenv("VERITAS_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("VERITAS_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("VERITAS_TRUSTLOG_SIGNER_BACKEND", raising=False)
    monkeypatch.delenv("VERITAS_TRUSTLOG_KMS_KEY_ID", raising=False)
    assert main() == 1


def test_cli_main_returns_zero_in_production_fully_configured(monkeypatch) -> None:
    monkeypatch.setenv("VERITAS_ENV", "production")
    monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "postgresql")
    monkeypatch.setenv("VERITAS_DATABASE_URL", "postgresql://example")
    monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", "dummy")
    monkeypatch.setenv("VERITAS_TRUSTLOG_SIGNER_BACKEND", "aws_kms")
    monkeypatch.setenv("VERITAS_TRUSTLOG_KMS_KEY_ID", "dummy-kms-key")
    monkeypatch.setenv("VERITAS_TRUSTLOG_WORM_MIRROR_PATH", "/tmp/worm")
    monkeypatch.setenv("VERITAS_TRUSTLOG_TRANSPARENCY_REQUIRED", "1")
    monkeypatch.setenv("VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH", "/tmp/transparency.jsonl")
    assert main() == 0


def test_production_posture_fails_when_encryption_backend_unacceptable(monkeypatch) -> None:
    """Production posture checker must fail when backend_acceptable is false."""
    import veritas_os.security.trustlog_production_posture as posture_module

    monkeypatch.setattr(
        posture_module,
        "get_encryption_status",
        lambda: {
            "encryption_enabled": True,
            "key_configured": True,
            "backend_available": False,
            "backend_required": True,
            "backend_acceptable": False,
        },
    )

    result = posture_module.check_trustlog_production_posture(_production_base_env())
    assert result.passed is False
    assert any("AES-256-GCM" in item for item in result.failures)


def test_startup_validation_fails_when_encryption_backend_unacceptable(monkeypatch) -> None:
    """Startup validation must fail-fast when production backend is unacceptable."""
    import logging

    import veritas_os.api.startup_health as startup_health
    import veritas_os.security.trustlog_production_posture as posture_module

    monkeypatch.setenv("VERITAS_ENV", "production")
    monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "postgresql")
    monkeypatch.setenv("VERITAS_DATABASE_URL", "postgresql://example")
    monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", "dummy")
    monkeypatch.setenv("VERITAS_TRUSTLOG_SIGNER_BACKEND", "aws_kms")
    monkeypatch.setenv("VERITAS_TRUSTLOG_KMS_KEY_ID", "dummy-kms-key")

    monkeypatch.setattr(
        posture_module,
        "get_encryption_status",
        lambda: {
            "encryption_enabled": True,
            "key_configured": True,
            "backend_available": False,
            "backend_required": True,
            "backend_acceptable": False,
        },
    )

    with pytest.raises(RuntimeError, match="AES-256-GCM|backend|cryptography"):
        startup_health.validate_trustlog_production_posture_on_startup(
            logger=logging.getLogger(__name__)
        )
