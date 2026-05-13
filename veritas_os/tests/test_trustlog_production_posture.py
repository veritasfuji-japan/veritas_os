"""Tests for TrustLog production posture security checker."""

from __future__ import annotations

from scripts.security.check_trustlog_production_posture import _env_true
from scripts.security.check_trustlog_production_posture import check_trustlog_production_posture
from scripts.security.check_trustlog_production_posture import main


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


def test_production_without_worm_emits_warning() -> None:
    env = {
        **_production_base_env(),
        "VERITAS_TRUSTLOG_TRANSPARENCY_REQUIRED": "1",
        "VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH": "/tmp/transparency.jsonl",
    }
    result = check_trustlog_production_posture(env)
    assert result.passed is True
    assert any("WORM mirror path" in item for item in result.warnings)


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


def test_require_production_flag_enforces_check() -> None:
    env = {"VERITAS_REQUIRE_PRODUCTION_TRUSTLOG_POSTURE": "1"}
    result = check_trustlog_production_posture(env)
    assert result.passed is False


def test_boolean_parser_accepts_truthy_values() -> None:
    assert _env_true("1")
    assert _env_true("TrUe")
    assert _env_true("YES")
    assert _env_true(" on ")


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
