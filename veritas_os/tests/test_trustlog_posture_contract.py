"""Contract tests for TrustLog posture alignment between checker and core."""

from __future__ import annotations

import os

import pytest

from veritas_os.core.posture import PostureLevel, derive_defaults, resolve_posture, validate_posture_startup
from veritas_os.security.trustlog_production_posture import check_trustlog_production_posture


def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    keys = [
        "VERITAS_ENV",
        "VERITAS_POSTURE",
        "VERITAS_REQUIRE_PRODUCTION_TRUSTLOG_POSTURE",
        "VERITAS_TRUSTLOG_BACKEND",
        "VERITAS_DATABASE_URL",
        "DATABASE_URL",
        "VERITAS_ENCRYPTION_KEY",
        "VERITAS_TRUSTLOG_SIGNER_BACKEND",
        "VERITAS_TRUSTLOG_KMS_KEY_ID",
        "VERITAS_TRUSTLOG_ALLOW_INSECURE_SIGNER_IN_PROD",
        "VERITAS_TRUSTLOG_MIRROR_BACKEND",
        "VERITAS_TRUSTLOG_WORM_MIRROR_PATH",
        "VERITAS_TRUSTLOG_S3_BUCKET",
        "VERITAS_TRUSTLOG_S3_PREFIX",
        "VERITAS_TRUSTLOG_ANCHOR_BACKEND",
        "VERITAS_TRUSTLOG_TRANSPARENCY_REQUIRED",
        "VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH",
        "VERITAS_SECRET_PROVIDER",
        "VERITAS_API_SECRET_REF",
        "VERITAS_POSTURE_OVERRIDE_POLICY_ENFORCE",
        "VERITAS_POSTURE_OVERRIDE_EXTERNAL_SECRET_MGR",
        "VERITAS_POSTURE_OVERRIDE_TRUSTLOG_TRANSPARENCY",
        "VERITAS_POSTURE_OVERRIDE_TRUSTLOG_WORM",
        "VERITAS_POSTURE_OVERRIDE_REPLAY_STRICT",
    ]
    for key in keys:
        monkeypatch.delenv(key, raising=False)


def _checker_full_env() -> dict[str, str]:
    return {
        "VERITAS_ENV": "production",
        "VERITAS_TRUSTLOG_BACKEND": "postgresql",
        "VERITAS_DATABASE_URL": "postgresql://example",
        "VERITAS_ENCRYPTION_KEY": "dummy",
        "VERITAS_TRUSTLOG_SIGNER_BACKEND": "aws_kms",
        "VERITAS_TRUSTLOG_KMS_KEY_ID": "dummy-kms-key",
        "VERITAS_TRUSTLOG_MIRROR_BACKEND": "s3_object_lock",
        "VERITAS_TRUSTLOG_S3_BUCKET": "bucket",
        "VERITAS_TRUSTLOG_S3_PREFIX": "prefix",
        "VERITAS_TRUSTLOG_ANCHOR_BACKEND": "local",
        "VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH": "/tmp/transparency.jsonl",
    }


def _core_full_env() -> dict[str, str]:
    return {
        **_checker_full_env(),
        "VERITAS_SECRET_PROVIDER": "vault",
        "VERITAS_API_SECRET_REF": "secret/ref",
    }


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _clean_env(monkeypatch)


def _apply_env(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> None:
    for key, value in env.items():
        monkeypatch.setenv(key, value)


def test_prod_full_trustlog_config_passes_checker_and_core_posture(monkeypatch: pytest.MonkeyPatch) -> None:
    _apply_env(monkeypatch, _core_full_env())

    checker_result = check_trustlog_production_posture(dict(os.environ))
    assert checker_result.passed is True
    assert checker_result.failures == ()

    defaults = derive_defaults(PostureLevel.PROD)
    assert validate_posture_startup(defaults) == []


def test_aws_kms_ed25519_alias_passes_checker_and_core_posture(monkeypatch: pytest.MonkeyPatch) -> None:
    env = _core_full_env()
    env["VERITAS_TRUSTLOG_SIGNER_BACKEND"] = "aws_kms_ed25519"
    _apply_env(monkeypatch, env)

    checker_result = check_trustlog_production_posture(dict(os.environ))
    assert checker_result.passed is True
    assert checker_result.failures == ()

    defaults = derive_defaults(PostureLevel.PROD)
    assert validate_posture_startup(defaults) == []


def test_file_ed25519_alias_fails_checker_and_core_posture(monkeypatch: pytest.MonkeyPatch) -> None:
    env = _core_full_env()
    env["VERITAS_TRUSTLOG_SIGNER_BACKEND"] = "file_ed25519"
    _apply_env(monkeypatch, env)

    checker_result = check_trustlog_production_posture(dict(os.environ))
    assert any("signer backend must be aws_kms" in item for item in checker_result.failures)

    defaults = derive_defaults(PostureLevel.PROD)
    errors = validate_posture_startup(defaults)
    assert any("managed_signing" in item for item in errors)


def test_s3_mirror_alias_passes_checker_and_core_posture(monkeypatch: pytest.MonkeyPatch) -> None:
    env = _core_full_env()
    env["VERITAS_TRUSTLOG_MIRROR_BACKEND"] = "s3"
    _apply_env(monkeypatch, env)

    checker_result = check_trustlog_production_posture(dict(os.environ))
    assert checker_result.passed is True
    assert not any("s3_object_lock mirror requires" in item for item in checker_result.warnings)

    defaults = derive_defaults(PostureLevel.PROD)
    assert validate_posture_startup(defaults) == []


def test_local_mirror_is_warning_in_checker_but_error_in_core_strict_posture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Intentional divergence: checker warns/non-critical, core strict posture hard-fails."""
    env = _core_full_env()
    env["VERITAS_TRUSTLOG_MIRROR_BACKEND"] = "filesystem"
    env["VERITAS_TRUSTLOG_WORM_MIRROR_PATH"] = "/tmp/worm"
    _apply_env(monkeypatch, env)

    checker_result = check_trustlog_production_posture(dict(os.environ))
    assert checker_result.passed is True
    assert checker_result.failures == ()

    defaults = derive_defaults(PostureLevel.PROD)
    errors = validate_posture_startup(defaults)
    assert any("immutable_retention" in item for item in errors)


def test_noop_anchor_is_warning_in_checker_but_error_in_core_when_transparency_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Intentional divergence: checker warning-only vs core capability hard-fail."""
    env = _core_full_env()
    env["VERITAS_TRUSTLOG_ANCHOR_BACKEND"] = "none"
    _apply_env(monkeypatch, env)

    checker_result = check_trustlog_production_posture(dict(os.environ))
    assert checker_result.passed is True
    assert checker_result.failures == ()
    assert any("anchor backend is noop" in item for item in checker_result.warnings)

    defaults = derive_defaults(PostureLevel.PROD)
    errors = validate_posture_startup(defaults)
    assert any("transparency_anchoring" in item for item in errors)


@pytest.mark.parametrize(
    "alias, expected",
    [
        ("production", PostureLevel.PROD),
        ("prod", PostureLevel.PROD),
        ("secure", PostureLevel.SECURE),
        ("hardened", PostureLevel.SECURE),
    ],
)
def test_strict_env_aliases_enforce_checker_and_core_fail_fast_semantics(
    monkeypatch: pytest.MonkeyPatch,
    alias: str,
    expected: PostureLevel,
) -> None:
    monkeypatch.setenv("VERITAS_ENV", alias)
    result = check_trustlog_production_posture(dict(os.environ))
    assert result.passed is False
    assert any("backend must be postgresql" in item for item in result.failures)
    assert resolve_posture(env_fallback=alias) == expected


@pytest.mark.parametrize(
    "alias, expected",
    [
        ("production", PostureLevel.PROD),
        ("prod", PostureLevel.PROD),
        ("secure", PostureLevel.SECURE),
        ("hardened", PostureLevel.SECURE),
    ],
)
def test_strict_veritas_posture_aliases_enforce_checker_and_core(
    monkeypatch: pytest.MonkeyPatch,
    alias: str,
    expected: PostureLevel,
) -> None:
    monkeypatch.setenv("VERITAS_POSTURE", alias)
    result = check_trustlog_production_posture(dict(os.environ))
    assert result.passed is False
    assert any("backend must be postgresql" in item for item in result.failures)
    assert resolve_posture() == expected


@pytest.mark.parametrize("alias", ["dev", "development", "local", "test", "staging", "stg"])
def test_non_strict_env_aliases_do_not_enforce_checker_or_core_strict_posture(
    monkeypatch: pytest.MonkeyPatch,
    alias: str,
) -> None:
    monkeypatch.setenv("VERITAS_ENV", alias)

    checker_result = check_trustlog_production_posture(dict(os.environ))
    assert checker_result.passed is True
    assert checker_result.failures == ()

    resolved = resolve_posture()
    if alias in {"staging", "stg"}:
        assert resolved == PostureLevel.STAGING
    else:
        assert resolved == PostureLevel.DEV

    defaults = derive_defaults(resolved)
    assert defaults.is_strict is False
