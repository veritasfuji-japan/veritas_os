"""Tests for TrustLog secure-by-default posture gate."""

from __future__ import annotations

import pytest

from veritas_os.security.trustlog_posture import (
    get_trustlog_security_posture,
    validate_trustlog_secure_defaults,
)


@pytest.mark.parametrize("posture", ["dev", "staging"])
def test_non_strict_posture_jsonl_without_key_degrades(monkeypatch: pytest.MonkeyPatch, posture: str) -> None:
    """dev/staging should not fail closed for file-based TrustLog without key."""
    monkeypatch.setenv("VERITAS_POSTURE", posture)
    monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "jsonl")
    monkeypatch.delenv("VERITAS_DATABASE_URL", raising=False)
    monkeypatch.delenv("VERITAS_ENCRYPTION_KEY", raising=False)

    result = get_trustlog_security_posture()

    assert result["posture"] == posture
    assert result["trustlog_backend"] == "jsonl"
    assert result["status"] == "degraded"
    assert result["reasons"]
    assert result["remediation"]
    validate_trustlog_secure_defaults()


@pytest.mark.parametrize("posture", ["secure", "prod"])
def test_strict_posture_jsonl_without_key_is_blocked(monkeypatch: pytest.MonkeyPatch, posture: str) -> None:
    """secure/prod must fail closed for insecure TrustLog defaults."""
    monkeypatch.setenv("VERITAS_POSTURE", posture)
    monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "jsonl")
    monkeypatch.delenv("VERITAS_DATABASE_URL", raising=False)
    monkeypatch.delenv("VERITAS_ENCRYPTION_KEY", raising=False)

    result = get_trustlog_security_posture()

    assert result["status"] == "blocked"
    with pytest.raises(RuntimeError, match="TrustLog secure posture violation"):
        validate_trustlog_secure_defaults()


def test_prod_posture_postgresql_with_db_and_key_is_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """prod should pass when PostgreSQL and encryption key are configured."""
    monkeypatch.setenv("VERITAS_POSTURE", "prod")
    monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "postgresql")
    monkeypatch.setenv("VERITAS_DATABASE_URL", "postgresql://user:pass@localhost:5432/veritas")
    monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")

    result = get_trustlog_security_posture()

    assert result == {
        "status": "ok",
        "posture": "prod",
        "trustlog_backend": "postgresql",
        "encryption_enabled": True,
        "key_configured": True,
        "secure_by_default": True,
        "reasons": [],
        "remediation": [],
    }
    validate_trustlog_secure_defaults()


def test_secure_posture_missing_database_url_is_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """strict posture should block when DB URL is missing for PostgreSQL TrustLog."""
    monkeypatch.setenv("VERITAS_POSTURE", "secure")
    monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "postgresql")
    monkeypatch.delenv("VERITAS_DATABASE_URL", raising=False)
    monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")

    result = get_trustlog_security_posture()

    assert result["status"] == "blocked"
    assert any("VERITAS_DATABASE_URL" in reason for reason in result["reasons"])


def test_security_posture_snapshot_includes_trustlog_secure_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """health/status security_posture snapshot should include trustlog gate diagnostics."""
    monkeypatch.setenv("VERITAS_POSTURE", "dev")
    monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "jsonl")
    monkeypatch.delenv("VERITAS_ENCRYPTION_KEY", raising=False)

    from veritas_os.api.routes_system import _security_posture_snapshot

    snapshot = _security_posture_snapshot()
    trustlog = snapshot["trustlog_secure_default"]
    assert trustlog["posture"] == "dev"
    assert trustlog["status"] == "degraded"
    assert isinstance(trustlog["reasons"], list)
    assert isinstance(trustlog["remediation"], list)


def test_get_trustlog_security_posture_uses_provided_encryption_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provided encryption status should bypass internal get_encryption_status call."""
    monkeypatch.setenv("VERITAS_POSTURE", "prod")
    monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "postgresql")
    monkeypatch.setenv("VERITAS_DATABASE_URL", "postgresql://user:pass@localhost:5432/veritas")

    import veritas_os.security.trustlog_posture as posture_module

    def _raise_if_called() -> dict[str, bool]:
        raise AssertionError("get_encryption_status should not be called")

    monkeypatch.setattr(posture_module, "get_encryption_status", _raise_if_called)

    result = posture_module.get_trustlog_security_posture(
        encryption_status={
            "encryption_enabled": True,
            "key_configured": True,
            "secure_by_default": True,
        }
    )
    assert result["status"] == "ok"


def test_security_posture_snapshot_reuses_encryption_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Security snapshot should call encryption status once and reuse the value."""
    monkeypatch.setenv("VERITAS_POSTURE", "dev")
    monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "jsonl")

    import veritas_os.api.routes_system as routes_system
    import veritas_os.security.trustlog_posture as posture_module

    call_counter = {"count": 0}

    def _fake_get_encryption_status() -> dict[str, bool]:
        call_counter["count"] += 1
        return {
            "encryption_enabled": False,
            "key_configured": False,
            "secure_by_default": True,
        }

    monkeypatch.setattr(routes_system, "get_encryption_status", _fake_get_encryption_status)
    monkeypatch.setattr(posture_module, "get_encryption_status", _fake_get_encryption_status)

    snapshot = routes_system._security_posture_snapshot()

    assert call_counter["count"] == 1
    assert snapshot["trustlog_secure_default"]["status"] == "degraded"


def test_get_trustlog_security_posture_uses_explicit_posture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit posture input should avoid resolve_posture fallback logic."""
    monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "postgresql")
    monkeypatch.setenv("VERITAS_DATABASE_URL", "postgresql://user:pass@localhost:5432/veritas")

    import veritas_os.security.trustlog_posture as posture_module

    def _raise_if_called() -> None:
        raise AssertionError("resolve_posture should not be called")

    monkeypatch.setattr(posture_module, "resolve_posture", _raise_if_called)

    result = posture_module.get_trustlog_security_posture(
        posture="prod",
        encryption_status={
            "encryption_enabled": True,
            "key_configured": True,
            "secure_by_default": True,
        },
    )
    assert result["posture"] == "prod"
    assert result["status"] == "ok"
