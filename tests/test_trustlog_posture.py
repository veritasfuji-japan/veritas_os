"""Tests for TrustLog secure-by-default posture gate."""

from __future__ import annotations

import json

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
    result = get_trustlog_security_posture(
        encryption_status={
            "encryption_enabled": True,
            "key_configured": True,
            "secure_by_default": True,
            "backend_available": True,
            "backend_required": True,
            "backend_acceptable": True,
        }
    )

    assert result["status"] == "ok"
    assert result["posture"] == "prod"
    assert result["trustlog_backend"] == "postgresql"
    assert result["encryption_enabled"] is True
    assert result["key_configured"] is True
    assert result["backend_available"] is True
    assert result["backend_required"] is True
    assert result["backend_acceptable"] is True
    assert result["secure_by_default"] is True
    assert result["reasons"] == []
    assert result["remediation"] == []


def test_secure_posture_blocks_when_encryption_backend_unacceptable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Strict posture must block when backend_acceptable is false."""
    monkeypatch.setenv("VERITAS_POSTURE", "secure")
    monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "postgresql")
    monkeypatch.setenv("VERITAS_DATABASE_URL", "postgresql://user:pass@localhost:5432/veritas")

    import veritas_os.security.trustlog_posture as posture_module

    monkeypatch.setattr(
        posture_module,
        "get_encryption_status",
        lambda: {
            "encryption_enabled": True,
            "key_configured": True,
            "secure_by_default": True,
            "backend_available": False,
            "backend_required": True,
            "backend_acceptable": False,
        },
    )

    result = posture_module.get_trustlog_security_posture()
    assert result["status"] == "blocked"
    assert result["backend_acceptable"] is False
    assert any("backend" in reason.lower() for reason in result["reasons"])

    with pytest.raises(RuntimeError, match="TrustLog secure posture violation"):
        posture_module.validate_trustlog_secure_defaults()


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


@pytest.mark.parametrize("posture", ["dev", "staging"])
def test_encryption_status_error_is_sanitized_non_strict(
    monkeypatch: pytest.MonkeyPatch,
    posture: str,
) -> None:
    """Non-strict postures should degrade without leaking raw provider error text."""
    monkeypatch.setenv("VERITAS_POSTURE", posture)
    monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "jsonl")
    monkeypatch.setenv("VERITAS_ENCRYPTION_KEY_PROVIDER", "env")
    monkeypatch.delenv("VERITAS_DATABASE_URL", raising=False)

    import veritas_os.security.trustlog_posture as posture_module

    def _raise_provider_error() -> dict[str, bool]:
        raise RuntimeError("secret path /prod/foo token abc")

    monkeypatch.setattr(posture_module, "get_encryption_status", _raise_provider_error)

    result = posture_module.get_trustlog_security_posture()

    assert result["status"] == "degraded"
    combined = " ".join(result["reasons"])
    assert "RuntimeError" in combined
    assert "secret path" not in combined
    assert "/prod/foo" not in combined
    assert "token abc" not in combined


@pytest.mark.parametrize("posture", ["secure", "prod"])
def test_encryption_status_error_is_sanitized_strict(
    monkeypatch: pytest.MonkeyPatch,
    posture: str,
) -> None:
    """Strict postures should block and raise sanitized startup error messages."""
    monkeypatch.setenv("VERITAS_POSTURE", posture)
    monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "postgresql")
    monkeypatch.setenv("VERITAS_DATABASE_URL", "postgresql://user:pass@localhost:5432/veritas")
    monkeypatch.setenv("VERITAS_ENCRYPTION_KEY_PROVIDER", "env")

    import veritas_os.security.trustlog_posture as posture_module

    def _raise_provider_error() -> dict[str, bool]:
        raise RuntimeError("secret path /prod/foo token abc")

    monkeypatch.setattr(posture_module, "get_encryption_status", _raise_provider_error)

    result = posture_module.get_trustlog_security_posture()
    assert result["status"] == "blocked"
    assert any("RuntimeError" in reason for reason in result["reasons"])

    with pytest.raises(RuntimeError) as excinfo:
        posture_module.validate_trustlog_secure_defaults()
    message = str(excinfo.value)
    assert "RuntimeError" in message
    assert "secret path" not in message
    assert "/prod/foo" not in message
    assert "token abc" not in message


def test_security_posture_snapshot_sanitizes_encryption_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Snapshot should stay stable and sanitized when encryption status lookup fails."""
    monkeypatch.setenv("VERITAS_POSTURE", "staging")
    monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "jsonl")

    import veritas_os.api.routes_system as routes_system

    def _raise_provider_error() -> dict[str, bool]:
        raise RuntimeError("secret path /prod/foo token abc")

    monkeypatch.setattr(routes_system, "get_encryption_status", _raise_provider_error)

    snapshot = routes_system._security_posture_snapshot()

    assert snapshot["encryption"]["error_type"] == "RuntimeError"
    assert "secret path" not in json.dumps(snapshot["encryption"], sort_keys=True)
    assert "trustlog_secure_default" in snapshot

    rendered_snapshot = json.dumps(snapshot, sort_keys=True)
    assert "secret path" not in rendered_snapshot
    assert "/prod/foo" not in rendered_snapshot
    assert "token abc" not in rendered_snapshot


def test_get_trustlog_security_posture_normalizes_explicit_posture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit posture input should be normalized before strictness checks."""
    monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "jsonl")
    monkeypatch.delenv("VERITAS_DATABASE_URL", raising=False)

    result = get_trustlog_security_posture(
        posture=" Prod ",
        encryption_status={
            "encryption_enabled": True,
            "key_configured": True,
            "secure_by_default": True,
        },
    )
    assert result["posture"] == "prod"
    assert result["status"] == "blocked"


def test_get_trustlog_security_posture_dev_error_type_is_degraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DEV posture must not report ok when sanitized encryption error exists."""
    monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "jsonl")
    monkeypatch.delenv("VERITAS_DATABASE_URL", raising=False)

    result = get_trustlog_security_posture(
        posture=" DEV ",
        encryption_status={
            "encryption_enabled": True,
            "key_configured": True,
            "secure_by_default": True,
            "error_type": "RuntimeError",
        },
    )
    assert result["posture"] == "dev"
    assert result["status"] == "degraded"
    assert result["reasons"]


def test_security_posture_snapshot_fallback_key_provider_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fallback encryption status should expose configured provider safely."""
    monkeypatch.setenv("VERITAS_POSTURE", "staging")
    monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "jsonl")
    monkeypatch.setenv("VERITAS_ENCRYPTION_KEY_PROVIDER", "vault")

    import veritas_os.api.routes_system as routes_system

    def _raise_provider_error() -> dict[str, bool]:
        raise RuntimeError("secret path /prod/foo token abc")

    monkeypatch.setattr(routes_system, "get_encryption_status", _raise_provider_error)

    snapshot = routes_system._security_posture_snapshot()
    assert snapshot["encryption"]["key_provider"] == "vault"


def test_validate_trustlog_secure_defaults_raises_for_blocked_dev_posture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Blocked status must fail closed even when reported posture is dev."""
    import veritas_os.security.trustlog_posture as posture_module

    monkeypatch.setattr(
        posture_module,
        "get_trustlog_security_posture",
        lambda: {
            "status": "blocked",
            "posture": "dev",
            "backend_required": True,
            "backend_acceptable": False,
            "reasons": ["backend unavailable under enforced strict posture"],
        },
    )

    with pytest.raises(RuntimeError, match="backend_required=True"):
        posture_module.validate_trustlog_secure_defaults()


def test_validate_trustlog_secure_defaults_does_not_raise_for_degraded_dev(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Degraded dev diagnostics remain non-fatal for startup validation."""
    import veritas_os.security.trustlog_posture as posture_module

    monkeypatch.setattr(
        posture_module,
        "get_trustlog_security_posture",
        lambda: {
            "status": "degraded",
            "posture": "dev",
            "backend_required": False,
            "backend_acceptable": True,
            "reasons": ["development mode without configured key"],
        },
    )

    posture_module.validate_trustlog_secure_defaults()
    assert snapshot["encryption"]["error_type"] == "RuntimeError"

    rendered_snapshot = json.dumps(snapshot, sort_keys=True)
    assert "secret path" not in rendered_snapshot
    assert "/prod/foo" not in rendered_snapshot
    assert "token abc" not in rendered_snapshot


def test_security_posture_snapshot_fallback_key_provider_default_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fallback provider should default to env when configuration is missing/empty."""
    monkeypatch.setenv("VERITAS_POSTURE", "staging")
    monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "jsonl")
    monkeypatch.setenv("VERITAS_ENCRYPTION_KEY_PROVIDER", " ")

    import veritas_os.api.routes_system as routes_system

    def _raise_provider_error() -> dict[str, bool]:
        raise RuntimeError("secret path /prod/foo token abc")

    monkeypatch.setattr(routes_system, "get_encryption_status", _raise_provider_error)

    snapshot = routes_system._security_posture_snapshot()
    assert snapshot["encryption"]["key_provider"] == "env"
