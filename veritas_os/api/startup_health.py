"""Startup validation and runtime feature health helpers for API server."""

from __future__ import annotations

import logging
import multiprocessing
import os
import sys
from pathlib import Path
from typing import Any, Callable, Optional

from veritas_os.security.trustlog_production_posture import (
    STRICT_PRODUCTION_POSTURE_ALIASES,
    check_trustlog_production_posture,
    is_trustlog_production_posture_enforced,
)


def _is_truthy_env(var_name: str) -> bool:
    """Return True when the named environment variable is explicitly truthy."""
    value = (os.getenv(var_name) or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _is_node_env_production() -> bool:
    """Return True when NODE_ENV indicates a production runtime."""
    node_env = (os.getenv("NODE_ENV") or "").strip().lower()
    return node_env == "production"


def _is_env_key_present(var_name: str) -> bool:
    """Return True when an env key exists, regardless of configured value."""
    return var_name in os.environ


def should_fail_fast_startup(profile: Optional[str] = None) -> bool:
    """Return whether startup validation errors should fail the process.

    When profile is provided, it is authoritative: explicit strict profiles
    (``prod``, ``production``, ``secure``, ``hardened``) enable fail-fast,
    while non-strict explicit profiles are not overridden by ambient
    environment or posture flags. When profile is omitted, fail-fast is
    enabled for strict VERITAS_ENV aliases, strict resolved posture, or a
    truthy VERITAS_REQUIRE_PRODUCTION_TRUSTLOG_POSTURE flag.
    """
    resolved_profile = profile if profile is not None else os.getenv("VERITAS_ENV", "")
    normalized_profile = resolved_profile.strip().lower()
    if normalized_profile in STRICT_PRODUCTION_POSTURE_ALIASES:
        return True
    if profile is not None:
        return False
    if is_trustlog_production_posture_enforced(dict(os.environ)):
        return True

    # Delegate to canonical posture resolution to avoid alias drift.
    try:
        from veritas_os.core.posture import PostureLevel, resolve_posture
        level = resolve_posture()
        if level in {PostureLevel.SECURE, PostureLevel.PROD}:
            return True
    except Exception:
        pass

    return False


def _api_worker_declarations() -> list[tuple[str, str]]:
    """Read environment counts and explicit worker arguments of Uvicorn CLI.

    Spawned Uvicorn CLI workers inherit sys.argv. This does not discover
    programmatic uvicorn.run(), custom launchers, or independent replicas.
    """
    declarations = [
        (name, os.getenv(name) or "")
        for name in ("WEB_CONCURRENCY", "UVICORN_WORKERS")
    ]
    if not sys.argv:
        return declarations
    launcher = Path(sys.argv[0])
    if launcher.name not in {"uvicorn", "uvicorn.exe"} and not (
        launcher.name == "__main__.py" and launcher.parent.name == "uvicorn"
    ):
        return declarations
    args = iter(sys.argv[1:])
    for arg in args:
        if arg == "--":
            break
        if arg == "--workers":
            declarations.append(("uvicorn --workers", next(args, "")))
        elif arg.startswith("--workers="):
            declarations.append(("uvicorn --workers", arg.partition("=")[2]))
    return declarations


def run_startup_config_validation(
    *,
    logger: logging.Logger,
    should_fail_fast: Callable[[Optional[str]], bool] = should_fail_fast_startup,
    validator: Optional[Callable[[], None]] = None,
) -> None:
    """Validate API keys in all profiles and other config according to profile."""
    from veritas_os.api.auth import _parse_api_keys_config

    _parse_api_keys_config()
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


def initialize_system_halt_on_startup() -> None:
    """Require explicit operator resume after each strict API startup.

    This re-arms a process-local stop; it does not restore historical state.
    Preserve a halt already set in this process, including its original reason.
    """
    if not should_fail_fast_startup():
        return
    from veritas_os.core.eu_ai_act_oversight import SystemHaltController

    if not SystemHaltController.is_halted():
        SystemHaltController.halt(
            reason="Strict API startup requires an authenticated operator resume",
            operator="system:startup",
        )


def security_startup_is_complete(app: Any) -> bool:
    """Refuse strict API admission until this app's lifespan has completed setup."""
    if not should_fail_fast_startup():
        return True
    state = getattr(app, "state", None)
    pid = getattr(state, "security_startup_pid", None)
    return (
        getattr(state, "security_startup_complete", False) is True
        and isinstance(pid, int) and not isinstance(pid, bool)
        and pid == os.getpid()
    )


def validate_startup_security_flags(*, logger: logging.Logger) -> None:
    """Validate high-risk startup flags so dangerous configs are never silent.

    Security policy:
    - Declared multiple API workers are refused in production/strict mode
      because emergency halt state is process-local, even with Redis auth.
    - Multiprocessing children and Gunicorn-marked runtimes are refused in
      strict mode when a single API process cannot be established.
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
    direct_fuji_key_present = _is_env_key_present("VERITAS_ENABLE_DIRECT_FUJI_API")
    direct_fuji_enabled = _is_truthy_env("VERITAS_ENABLE_DIRECT_FUJI_API")
    public_api_base_url = (os.getenv("NEXT_PUBLIC_VERITAS_API_BASE_URL") or "").strip()

    # Programmatic Uvicorn workers have no CLI count, but Python exposes their
    # multiprocessing parent. Gunicorn uses os.fork() and marks its workers
    # through SERVER_SOFTWARE instead. Neither signal proves a worker count;
    # refuse these contexts conservatively, including a single managed child.
    managed_runtime = None
    if multiprocessing.parent_process() is not None:
        managed_runtime = "multiprocessing child"
    elif (os.getenv("SERVER_SOFTWARE") or "").strip().lower().startswith("gunicorn/"):
        managed_runtime = "Gunicorn-marked runtime"
    if managed_runtime is not None:
        message = (
            "[SECURITY] The process-local emergency halt cannot establish a "
            f"single API process in a {managed_runtime}. Run the API as one "
            "standalone process until shared halt control is implemented."
        )
        if is_production:
            raise RuntimeError(f"{message} Refusing startup in production/strict mode.")
        logger.warning("%s", message)

    # Redis auth state does not share the emergency halt controller's memory.
    # Inspect each declaration independently: an env value of one must not
    # hide multiple workers explicitly requested through the Uvicorn CLI.
    for worker_var, raw_count in _api_worker_declarations():
        try:
            worker_count = int(raw_count.strip())
        except ValueError:
            continue
        if worker_count <= 1:
            continue
        message = (
            "[SECURITY] The process-local emergency halt is not shared across "
            f"workers ({worker_var}={worker_count}). Redis authentication does "
            "not synchronize halt/resume state. Use one API worker per "
            "deployment until a shared halt boundary is implemented."
        )
        if is_production:
            raise RuntimeError(f"{message} Refusing startup in production/strict mode.")
        logger.warning("%s", message)
        break

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

    if direct_fuji_key_present:
        message = (
            "[SECURITY] VERITAS_ENABLE_DIRECT_FUJI_API is present in environment "
            "configuration. This flag is HIGH risk because direct FUJI endpoints "
            "bypass `/v1/decide` orchestration controls."
        )
        if is_production:
            raise RuntimeError(
                f"{message} Treating this as production drift; remove the key "
                "from environment distribution before startup."
            )
        if direct_fuji_enabled:
            logger.warning(
                "%s It is explicitly enabled and should stay limited to isolated "
                "local testing.",
                message,
            )
        else:
            logger.warning(
                "%s Even disabled values should be removed from shared env "
                "templates to prevent production drift.",
                message,
            )

    validate_trustlog_production_posture_on_startup(logger=logger)


def validate_trustlog_production_posture_on_startup(*, logger: logging.Logger) -> None:
    """Validate TrustLog posture during startup with production fail-fast handling.

    `check_trustlog_production_posture` only returns failures when TrustLog
    production posture enforcement is active, so any failure here is fatal
    during startup. Warning-only findings remain non-fatal.
    """
    current_env = dict(os.environ)
    result = check_trustlog_production_posture(current_env)
    if result.failures:
        failures = "; ".join(result.failures)
        message = f"[SECURITY] TrustLog production posture check failed: {failures}"
        raise RuntimeError(
            f"{message}. Refusing startup because TrustLog production posture is "
            "enforced."
        )

    for warning in result.warnings:
        logger.warning("[SECURITY] TrustLog production posture warning: %s", warning)


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
