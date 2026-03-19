"""Startup validation and runtime feature health helpers for API server."""

from __future__ import annotations

import logging
import os
from typing import Callable, Optional


def _is_truthy_env(var_name: str) -> bool:
    """Return True when the named environment variable is explicitly truthy."""
    value = (os.getenv(var_name) or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _is_node_env_production() -> bool:
    """Return True when NODE_ENV indicates a production runtime."""
    node_env = (os.getenv("NODE_ENV") or "").strip().lower()
    return node_env == "production"


def should_fail_fast_startup(profile: Optional[str] = None) -> bool:
    """Return whether startup validation failures should stop app boot."""
    resolved_profile = profile if profile is not None else os.getenv("VERITAS_ENV", "")
    normalized_profile = resolved_profile.strip().lower()
    return normalized_profile in {"prod", "production"}


def run_startup_config_validation(
    *,
    logger: logging.Logger,
    should_fail_fast: Callable[[Optional[str]], bool] = should_fail_fast_startup,
    validator: Optional[Callable[[], None]] = None,
) -> None:
    """Validate startup configuration with environment-specific strictness."""
    try:
        validate_startup_security_flags(logger=logger)
        effective_validator = validator
        if effective_validator is None:
            from veritas_os.core.config import validate_startup_config as effective_validator

        effective_validator()
    except Exception:
        fail_fast = should_fail_fast(None)
        logger.warning(
            "startup config validation failed (fail_fast=%s)",
            fail_fast,
            exc_info=True,
        )
        if fail_fast:
            raise


def validate_startup_security_flags(*, logger: logging.Logger) -> None:
    """Validate high-risk startup flags so dangerous configs are never silent.

    Security policy:
    - `VERITAS_AUTH_ALLOW_FAIL_OPEN=true` must never be present in production.
    - Auth fail-open is only supported for local/test-style profiles and must
      not remain enabled in shared staging environments.
    - `NEXT_PUBLIC_VERITAS_API_BASE_URL` must never be present in production
      because it can leak internal routing details and triggers BFF fail-closed.
    - `NODE_ENV=production` without `VERITAS_ENV=production` must emit a warning
      because frontend strict CSP defaults will not activate automatically.
    """
    is_production = should_fail_fast_startup()
    is_node_production = _is_node_env_production()
    profile = (os.getenv("VERITAS_ENV") or "").strip().lower()
    auth_fail_open_enabled = _is_truthy_env("VERITAS_AUTH_ALLOW_FAIL_OPEN")
    public_api_base_url = (os.getenv("NEXT_PUBLIC_VERITAS_API_BASE_URL") or "").strip()

    if is_node_production and not is_production:
        logger.warning(
            "[SECURITY] NODE_ENV=production is set without VERITAS_ENV=production. "
            "Frontend strict CSP defaults remain warning-only in this profile, so "
            "deployments must explicitly set VERITAS_ENV=production before release."
        )

    if auth_fail_open_enabled:
        message = (
            "[SECURITY] VERITAS_AUTH_ALLOW_FAIL_OPEN=true is enabled. "
            "This weakens auth-store failure protections and must stay limited "
            "to controlled non-production testing."
        )
        if is_production:
            raise RuntimeError(
                f"{message} Refusing startup in production."
            )
        logger.warning("%s", message)
        if profile not in {"dev", "development", "local", "test"}:
            logger.warning(
                "[SECURITY] VERITAS_AUTH_ALLOW_FAIL_OPEN=true is unsupported for "
                "VERITAS_ENV=%s and will be ignored by auth store fallback logic.",
                profile or "unset",
            )

    if public_api_base_url:
        message = (
            "[SECURITY] NEXT_PUBLIC_VERITAS_API_BASE_URL is set. "
            "Public API base URLs must not be exposed in deployment "
            "configuration because BFF routing is intended to stay server-only."
        )
        if is_production:
            raise RuntimeError(
                f"{message} Refusing startup in production."
            )
        logger.warning("%s", message)


def check_runtime_feature_health(
    *,
    logger: logging.Logger,
    has_sanitize: bool,
    has_atomic_io: bool,
) -> None:
    """Warn about degraded runtime features so operators are never silently misled."""
    if not has_sanitize:
        logger.warning(
            "[SECURITY] PII masking is DISABLED (sanitize module failed to load). "
            "Sensitive data may appear in shadow logs. "
            "Fix the import error and restart to restore full protection."
        )
    if not has_atomic_io:
        logger.warning(
            "[RELIABILITY] Atomic I/O is DISABLED (atomic_io module failed to load). "
            "Trust log writes are less crash-safe (using direct file I/O). "
            "Fix the import error and restart to restore full protection."
        )
