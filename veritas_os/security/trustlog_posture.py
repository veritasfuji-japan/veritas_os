"""TrustLog secure-by-default posture gate helpers."""

from __future__ import annotations

import os
from typing import Any

from veritas_os.core.posture import resolve_posture
from veritas_os.logging.encryption import get_encryption_status
from veritas_os.storage.factory import get_backend_info


def _normalize_posture(posture: str | None) -> str:
    """Return a normalized posture string with env fallback."""
    normalized = str(posture or "").strip().lower()
    if normalized:
        return normalized
    return resolve_posture().value


def get_trustlog_security_posture(
    encryption_status: dict[str, Any] | None = None,
    posture: str | None = None,
) -> dict[str, Any]:
    """Return TrustLog runtime security posture diagnostics.

    The returned schema is intentionally stable for health/status payloads.
    """
    posture_level = _normalize_posture(posture)
    backend = get_backend_info().get("trustlog", "jsonl")
    encryption_error_type: str | None = None
    if encryption_status is not None:
        encryption = encryption_status
    else:
        try:
            encryption = get_encryption_status()
        except Exception as exc:  # noqa: BLE001
            encryption_error_type = exc.__class__.__name__
            encryption = {
                "encryption_enabled": False,
                "key_configured": False,
                "secure_by_default": True,
            }
    if encryption_error_type is None:
        raw_error_type = encryption.get("error_type")
        if isinstance(raw_error_type, str) and raw_error_type.strip():
            encryption_error_type = raw_error_type.strip()
    encryption_enabled = bool(encryption.get("encryption_enabled", False))
    key_configured = bool(encryption.get("key_configured", False))
    backend_acceptable = bool(encryption.get("backend_acceptable", True))
    db_url_configured = bool((os.getenv("VERITAS_DATABASE_URL") or "").strip())

    reasons: list[str] = []
    remediation: list[str] = []
    status = "ok"

    if encryption_error_type is not None:
        reasons.append(
            f"TrustLog encryption status retrieval failed: {encryption_error_type}"
        )
        remediation.append(
            "Check VERITAS_ENCRYPTION_KEY_PROVIDER configuration and required KMS/Vault dependencies."
        )
        remediation.append(
            "Use VERITAS_ENCRYPTION_KEY_PROVIDER=env for local validation, "
            "or configure the selected KMS/Vault provider correctly."
        )

    if posture_level in {"secure", "prod"}:
        if backend != "postgresql":
            reasons.append(
                f"VERITAS_POSTURE={posture_level} requires TrustLog backend=postgresql (current={backend})."
            )
            remediation.append("Set VERITAS_TRUSTLOG_BACKEND=postgresql.")
        if not db_url_configured:
            reasons.append("VERITAS_DATABASE_URL is not configured for PostgreSQL TrustLog.")
            remediation.append("Set VERITAS_DATABASE_URL to a PostgreSQL DSN.")
        if not encryption_enabled or not key_configured:
            reasons.append("TrustLog encryption key is not configured.")
            remediation.append(
                "Set VERITAS_ENCRYPTION_KEY or configure a supported KMS/Vault key provider."
            )
        if not backend_acceptable:
            reasons.append(
                "TrustLog production posture requires cryptography-backed AES-256-GCM."
            )
            remediation.append(
                "Install cryptography so TrustLog can use AES-256-GCM in secure/prod posture."
            )
    elif posture_level == "staging":
        if backend != "postgresql":
            reasons.append("Staging posture should use PostgreSQL TrustLog for production parity.")
            remediation.append("Set VERITAS_TRUSTLOG_BACKEND=postgresql.")
        if not db_url_configured:
            reasons.append("Staging posture should set VERITAS_DATABASE_URL.")
            remediation.append("Set VERITAS_DATABASE_URL to a PostgreSQL DSN.")
        if not encryption_enabled or not key_configured:
            reasons.append("Staging posture should configure TrustLog encryption key.")
            remediation.append(
                "Set VERITAS_ENCRYPTION_KEY or configure a supported KMS/Vault key provider."
            )
    else:
        if not encryption_enabled or not key_configured:
            reasons.append(
                "Development posture allows unencrypted startup, but TrustLog writes will fail without a key."
            )
            remediation.append(
                "Set VERITAS_ENCRYPTION_KEY for encrypted TrustLog writes when validating production posture."
            )

    if posture_level in {"secure", "prod"}:
        status = "blocked" if reasons else "ok"
    else:
        status = "degraded" if reasons else "ok"

    return {
        "status": status,
        "posture": posture_level,
        "trustlog_backend": backend,
        "encryption_enabled": encryption_enabled,
        "key_configured": key_configured,
        "secure_by_default": bool(encryption.get("secure_by_default", True)),
        "backend_available": bool(encryption.get("backend_available", True)),
        "backend_required": bool(encryption.get("backend_required", False)),
        "backend_acceptable": backend_acceptable,
        "reasons": reasons,
        "remediation": remediation,
    }


def validate_trustlog_secure_defaults() -> None:
    """Fail closed when secure/prod posture violates TrustLog hardening baseline."""
    posture_info = get_trustlog_security_posture()
    if posture_info["posture"] in {"secure", "prod"} and posture_info["status"] == "blocked":
        raise RuntimeError(
            "TrustLog secure posture violation: "
            f"VERITAS_POSTURE={posture_info['posture']} requires "
            "VERITAS_TRUSTLOG_BACKEND=postgresql, VERITAS_DATABASE_URL, "
            "and configured encryption key. Set VERITAS_DATABASE_URL and "
            "VERITAS_ENCRYPTION_KEY or a supported KMS/Vault provider. "
            f"Reasons: {'; '.join(posture_info['reasons'])}"
        )
