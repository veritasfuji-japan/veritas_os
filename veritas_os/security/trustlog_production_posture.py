"""Runtime-safe TrustLog production posture validation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from os import environ
from typing import Mapping

_TRUE_VALUES = {"1", "true", "yes", "on"}
PRODUCTION_ENV_ALIASES = {"prod", "production"}
STRICT_POSTURE_ALIASES = {"secure", "hardened", "prod", "production"}


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
        or _normalized(env, "VERITAS_POSTURE") in STRICT_POSTURE_ALIASES
        or _env_true(env.get("VERITAS_REQUIRE_PRODUCTION_TRUSTLOG_POSTURE"))
    )


def is_trustlog_production_posture_enforced(env: Mapping[str, str]) -> bool:
    """Return whether TrustLog production posture enforcement is active."""
    return _is_production_mode(env)


def _normalized_signer_backend(env: Mapping[str, str]) -> str:
    """Normalize signer backend aliases to runtime posture canonical values."""
    raw = _normalized(env, "VERITAS_TRUSTLOG_SIGNER_BACKEND")
    if raw in {"", "file", "file_ed25519"}:
        return "file"
    if raw in {"aws_kms", "aws_kms_ed25519"}:
        return "aws_kms"
    return raw


def _normalized_anchor_backend(env: Mapping[str, str]) -> str:
    """Normalize anchor backend aliases to runtime posture canonical values."""
    raw = _normalized(env, "VERITAS_TRUSTLOG_ANCHOR_BACKEND")
    if raw in {"", "local", "file"}:
        return "local"
    if raw in {"none", "noop", "no_op"}:
        return "noop"
    return raw


def _normalized_mirror_backend(env: Mapping[str, str]) -> str:
    """Normalize mirror backend aliases to runtime posture canonical values."""
    raw = _normalized(env, "VERITAS_TRUSTLOG_MIRROR_BACKEND")
    if raw in {"", "local", "filesystem"}:
        return "local"
    if raw in {"s3_object_lock", "s3"}:
        return "s3_object_lock"
    return raw


def _effective_transparency_required(env: Mapping[str, str]) -> bool:
    """Return effective transparency-required state with posture defaults."""
    raw = env.get("VERITAS_TRUSTLOG_TRANSPARENCY_REQUIRED")
    if raw is not None:
        return _env_true(raw)
    return _is_production_mode(env)


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

    has_database_url = bool(
        (current_env.get("VERITAS_DATABASE_URL", "") or "").strip()
    )
    has_fallback_database_url = bool((current_env.get("DATABASE_URL", "") or "").strip())
    if not (has_database_url or has_fallback_database_url):
        failures.append(
            "production TrustLog PostgreSQL backend requires VERITAS_DATABASE_URL or DATABASE_URL"
        )

    if not (current_env.get("VERITAS_ENCRYPTION_KEY", "") or "").strip():
        failures.append("production TrustLog encryption requires VERITAS_ENCRYPTION_KEY")

    if _normalized_signer_backend(current_env) != "aws_kms":
        failures.append("production TrustLog signer backend must be aws_kms")

    if not (current_env.get("VERITAS_TRUSTLOG_KMS_KEY_ID", "") or "").strip():
        failures.append(
            "production TrustLog aws_kms signer requires VERITAS_TRUSTLOG_KMS_KEY_ID"
        )

    mirror_backend = _normalized_mirror_backend(current_env)
    if mirror_backend == "local":
        if not (current_env.get("VERITAS_TRUSTLOG_WORM_MIRROR_PATH", "") or "").strip():
            warnings.append("production TrustLog local WORM mirror path is not configured")
    elif mirror_backend == "s3_object_lock":
        has_bucket = bool((current_env.get("VERITAS_TRUSTLOG_S3_BUCKET", "") or "").strip())
        has_prefix = bool((current_env.get("VERITAS_TRUSTLOG_S3_PREFIX", "") or "").strip())
        if not (has_bucket and has_prefix):
            warnings.append(
                "production TrustLog s3_object_lock mirror requires "
                "VERITAS_TRUSTLOG_S3_BUCKET and VERITAS_TRUSTLOG_S3_PREFIX"
            )
    else:
        warnings.append(
            f"production TrustLog mirror backend {mirror_backend!r} is unrecognized"
        )

    if not _effective_transparency_required(current_env):
        warnings.append("production TrustLog transparency anchoring is not required")

    if not (current_env.get("VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH", "") or "").strip():
        warnings.append("production TrustLog transparency log path is not configured")

    if _normalized_anchor_backend(current_env) == "noop":
        warnings.append("production TrustLog anchor backend is noop")

    return TrustLogPostureResult(not failures, tuple(failures), tuple(warnings))
