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
    - `VERITAS_AUTH_STORE_FAILURE_MODE=open` must also be surfaced explicitly so
      operators can see the effective fail-open request during startup.
    - Auth fail-open is only supported for local/test-style profiles. Shared
      staging profiles (`stg`/`staging`) are treated as protected pre-production
      environments and must fail closed when fail-open is requested.
    - `NEXT_PUBLIC_VERITAS_API_BASE_URL` must never be present in production
      because it can leak internal routing details and triggers BFF fail-closed.
    - `VERITAS_ENABLE_DIRECT_FUJI_API=true` must never be present in production
      because it bypasses `/v1/decide` pipeline controls and expands attack
      surface to direct FUJI policy probing.
    - `NODE_ENV=production` without `VERITAS_ENV=production` must emit a warning
      because frontend strict CSP defaults will not activate automatically.
    """
    is_production = should_fail_fast_startup()
    is_node_production = _is_node_env_production()
    profile = (os.getenv("VERITAS_ENV") or "").strip().lower()
    auth_fail_open_enabled = _is_truthy_env("VERITAS_AUTH_ALLOW_FAIL_OPEN")
    auth_store_failure_mode = (
        (os.getenv("VERITAS_AUTH_STORE_FAILURE_MODE") or "closed").strip().lower()
    )
    auth_fail_open_requested = auth_store_failure_mode == "open"
    direct_fuji_enabled = _is_truthy_env("VERITAS_ENABLE_DIRECT_FUJI_API")
    public_api_base_url = (os.getenv("NEXT_PUBLIC_VERITAS_API_BASE_URL") or "").strip()

    if is_node_production and not is_production:
        logger.warning(
            "[SECURITY] NODE_ENV=production is set without VERITAS_ENV=production. "
            "Frontend strict CSP defaults remain warning-only in this profile, so "
            "deployments must explicitly set VERITAS_ENV=production before release."
        )

    if auth_fail_open_enabled or auth_fail_open_requested:
        configured_flags = []
        if auth_fail_open_enabled:
            configured_flags.append("VERITAS_AUTH_ALLOW_FAIL_OPEN=true")
        if auth_fail_open_requested:
            configured_flags.append("VERITAS_AUTH_STORE_FAILURE_MODE=open")
        configured_flags_text = " + ".join(configured_flags)
        message = (
            f"[SECURITY] {configured_flags_text} is enabled. "
            "This weakens auth-store failure protections and must stay limited "
            "to controlled non-production testing."
        )
        if is_production:
            raise RuntimeError(f"{message} Refusing startup in production.")
        if profile in {"stg", "staging"}:
            raise RuntimeError(
                f"{message} Refusing startup for protected staging profile "
                f"VERITAS_ENV={profile}."
            )
        logger.warning("%s", message)
        if profile not in {"dev", "development", "local", "test"}:
            logger.warning(
                "[SECURITY] Auth fail-open request (%s) is unsupported for "
                "VERITAS_ENV=%s and will be ignored by auth store fallback logic.",
                configured_flags_text,
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

    if direct_fuji_enabled:
        message = (
            "[SECURITY] VERITAS_ENABLE_DIRECT_FUJI_API=true is enabled. "
            "Direct FUJI endpoints bypass `/v1/decide` orchestration controls, "
            "so this flag must remain disabled in production."
        )
        if is_production:
            raise RuntimeError(f"{message} Refusing startup in production.")
        logger.warning("%s", message)


def check_runtime_feature_health(
    *,
    logger: logging.Logger,
    has_sanitize: bool,
    has_atomic_io: bool,
) -> None:
    """Surface degraded runtime features with production fail-closed handling.

    Security policy:
    - Missing sanitize support is warning-only in non-production profiles so
      local recovery work can continue.
    - Missing sanitize support is fatal in production because running without
      PII masking can leak sensitive data into logs.
    - Missing atomic I/O is also fatal in production because trust-log writes
      lose crash-safe guarantees and audit durability degrades silently.
    """
    if not has_sanitize:
        message = (
            "[SECURITY] PII masking is DISABLED (sanitize module failed to "
            "load). Sensitive data may appear in shadow logs. Fix the import "
            "error and restart to restore full protection."
        )
        if should_fail_fast_startup():
            raise RuntimeError(f"{message} Refusing startup in production.")
        logger.warning("%s", message)
    if not has_atomic_io:
        message = (
            "[SECURITY] Atomic I/O is DISABLED (atomic_io module failed to load). "
            "Trust-log and shadow-log writes are no longer crash-safe, so audit "
            "durability is degraded. Fix the import error and restart to restore "
            "full protection."
        )
        if should_fail_fast_startup():
            raise RuntimeError(f"{message} Refusing startup in production.")
        logger.warning("%s", message)
