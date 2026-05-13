"""Runtime-safe TrustLog production posture validation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from os import environ
from typing import Mapping

_TRUE_VALUES = {"1", "true", "yes", "on"}
PRODUCTION_ENV_ALIASES = {"prod", "production"}


@dataclass(frozen=True)
class TrustLogPostureResult:
    """Result payload for TrustLog production posture checks."""

    passed: bool
    failures: tuple[str, ...]
    warnings: tuple[str, ...]


def _env_true(value: str | None) -> bool:
    """Return True when the provided environment value is explicitly truthy."""
    if value is None:
        return False
    return value.strip().lower() in _TRUE_VALUES


def _normalized(env: Mapping[str, str], key: str) -> str:
    """Return normalized environment value for robust comparisons."""
    return (env.get(key, "") or "").strip().lower()


def _is_production_mode(env: Mapping[str, str]) -> bool:
    """Return True when strict production posture must be enforced."""
    return (
        _normalized(env, "VERITAS_ENV") in PRODUCTION_ENV_ALIASES
        or _env_true(env.get("VERITAS_REQUIRE_PRODUCTION_TRUSTLOG_POSTURE"))
    )


def is_trustlog_production_posture_enforced(
    env: Mapping[str, str] | None = None,
) -> bool:
    """Return True when TrustLog production posture enforcement is active."""
    current_env = env if env is not None else environ
    return _is_production_mode(current_env)


def check_trustlog_production_posture(
    env: Mapping[str, str] | None = None,
) -> TrustLogPostureResult:
    """Validate TrustLog posture using production defaults and required controls."""
    current_env = env if env is not None else environ
    failures: list[str] = []
    warnings: list[str] = []

    if not _is_production_mode(current_env):
        return TrustLogPostureResult(True, tuple(failures), tuple(warnings))

    if _normalized(current_env, "VERITAS_TRUSTLOG_BACKEND") != "postgresql":
        failures.append("production TrustLog backend must be postgresql")

    has_database_url = bool((current_env.get("VERITAS_DATABASE_URL", "") or "").strip())
    has_fallback_database_url = bool((current_env.get("DATABASE_URL", "") or "").strip())
    if not (has_database_url or has_fallback_database_url):
        failures.append(
            "production TrustLog PostgreSQL backend requires VERITAS_DATABASE_URL or DATABASE_URL"
        )

    if not (current_env.get("VERITAS_ENCRYPTION_KEY", "") or "").strip():
        failures.append("production TrustLog encryption requires VERITAS_ENCRYPTION_KEY")

    if _normalized(current_env, "VERITAS_TRUSTLOG_SIGNER_BACKEND") != "aws_kms":
        failures.append("production TrustLog signer backend must be aws_kms")

    if not (current_env.get("VERITAS_TRUSTLOG_KMS_KEY_ID", "") or "").strip():
        failures.append(
            "production TrustLog aws_kms signer requires VERITAS_TRUSTLOG_KMS_KEY_ID"
        )

    if not (current_env.get("VERITAS_TRUSTLOG_WORM_MIRROR_PATH", "") or "").strip():
        warnings.append("production TrustLog WORM mirror path is not configured")

    if not _env_true(current_env.get("VERITAS_TRUSTLOG_TRANSPARENCY_REQUIRED")):
        warnings.append("production TrustLog transparency anchoring is not required")

    if not (current_env.get("VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH", "") or "").strip():
        warnings.append("production TrustLog transparency log path is not configured")

    if _normalized(current_env, "VERITAS_TRUSTLOG_ANCHOR_BACKEND") == "noop":
        warnings.append("production TrustLog anchor backend is noop")

    return TrustLogPostureResult(not failures, tuple(failures), tuple(warnings))
