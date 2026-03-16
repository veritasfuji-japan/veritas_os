"""Startup validation and runtime feature health helpers for API server."""

from __future__ import annotations

import logging
import os
from typing import Callable, Optional


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
