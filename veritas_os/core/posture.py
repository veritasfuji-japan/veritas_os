# veritas_os/core/posture.py
"""
Runtime posture model for VERITAS OS.

Provides a single, deterministic deployment posture that controls
governance-critical defaults.  The posture is resolved once at import
time from ``VERITAS_POSTURE`` (or inferred from ``VERITAS_ENV``) and
remains immutable for the process lifetime.

Posture levels
--------------
- **dev**     – local development; relaxed defaults, no mandatory integrations.
- **staging** – pre-production; warnings for missing integrations, no hard fail.
- **secure**  – hardened non-production; same defaults as *prod* but allows
                documented escape hatches via ``VERITAS_POSTURE_OVERRIDE_*``.
- **prod**    – production; all governance controls are on, startup refuses
                to proceed when required integrations are missing.
"""
from __future__ import annotations

import enum
import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

_logger = logging.getLogger(__name__)

# ── Boolean parsing (mirrors config._parse_bool but self-contained) ─────

_TRUTHY = frozenset({"1", "true", "yes", "on"})
_FALSY = frozenset({"0", "false", "no", "off", ""})


def _env_bool(key: str, default: bool) -> bool:
    """Read a boolean from the environment."""
    raw = os.getenv(key)
    if raw is None:
        return default
    normalised = raw.strip().lower()
    if normalised in _TRUTHY:
        return True
    if normalised in _FALSY:
        return False
    return default


# ── Posture enum ────────────────────────────────────────────────────────

class PostureLevel(str, enum.Enum):
    """Runtime posture levels ordered by strictness."""

    DEV = "dev"
    STAGING = "staging"
    SECURE = "secure"
    PROD = "prod"


_POSTURE_ALIASES: Dict[str, PostureLevel] = {
    "dev": PostureLevel.DEV,
    "development": PostureLevel.DEV,
    "local": PostureLevel.DEV,
    "test": PostureLevel.DEV,
    "testing": PostureLevel.DEV,
    "stg": PostureLevel.STAGING,
    "staging": PostureLevel.STAGING,
    "stage": PostureLevel.STAGING,
    "secure": PostureLevel.SECURE,
    "hardened": PostureLevel.SECURE,
    "prod": PostureLevel.PROD,
    "production": PostureLevel.PROD,
}


def resolve_posture(
    *,
    explicit: Optional[str] = None,
    env_fallback: Optional[str] = None,
) -> PostureLevel:
    """Resolve the active posture from environment or explicit override.

    Resolution order:
    1. *explicit* parameter (used by tests).
    2. ``VERITAS_POSTURE`` environment variable.
    3. ``VERITAS_ENV`` environment variable (legacy compat).
    4. Default → ``dev``.
    """
    raw = explicit
    if raw is None:
        raw = (os.getenv("VERITAS_POSTURE") or "").strip().lower()
    if not raw:
        raw = (
            env_fallback
            if env_fallback is not None
            else (os.getenv("VERITAS_ENV") or "").strip().lower()
        )
    if not raw:
        return PostureLevel.DEV

    level = _POSTURE_ALIASES.get(raw)
    if level is None:
        _logger.warning(
            "Unknown VERITAS_POSTURE value %r; falling back to 'dev'.",
            raw,
        )
        return PostureLevel.DEV
    return level


# ── Posture-derived defaults ────────────────────────────────────────────

@dataclass(frozen=True)
class PostureDefaults:
    """Governance-critical defaults derived from the active posture.

    In *secure* / *prod* posture every control is **on** by default.
    Operators may disable individual controls only in *secure* posture
    via narrow ``VERITAS_POSTURE_OVERRIDE_<CONTROL>=0`` escape hatches
    (these are ignored in *prod*).
    """

    posture: PostureLevel

    policy_runtime_enforce: bool = False
    external_secret_manager_required: bool = False
    trustlog_transparency_required: bool = False
    trustlog_worm_hard_fail: bool = False
    replay_strict: bool = False

    @property
    def is_strict(self) -> bool:
        """Return True when the posture is secure or prod."""
        return self.posture in {PostureLevel.SECURE, PostureLevel.PROD}


# Escape-hatch env vars accepted only in *secure* posture.
_OVERRIDE_KEYS: Dict[str, str] = {
    "policy_runtime_enforce": "VERITAS_POSTURE_OVERRIDE_POLICY_ENFORCE",
    "external_secret_manager_required": "VERITAS_POSTURE_OVERRIDE_EXTERNAL_SECRET_MGR",
    "trustlog_transparency_required": "VERITAS_POSTURE_OVERRIDE_TRUSTLOG_TRANSPARENCY",
    "trustlog_worm_hard_fail": "VERITAS_POSTURE_OVERRIDE_TRUSTLOG_WORM",
    "replay_strict": "VERITAS_POSTURE_OVERRIDE_REPLAY_STRICT",
}


def derive_defaults(posture: PostureLevel) -> PostureDefaults:
    """Compute governance defaults for *posture*.

    For *secure*/*prod* all flags default to True.  In *secure* posture
    individual flags may be overridden to False via documented escape
    hatches.  In *prod* the escape hatches are ignored.

    For *dev*/*staging* flags honour explicit env vars but default to
    False so local development remains frictionless.
    """
    if posture in {PostureLevel.SECURE, PostureLevel.PROD}:
        overrides: Dict[str, bool] = {}
        for attr, env_key in _OVERRIDE_KEYS.items():
            if posture == PostureLevel.SECURE:
                override_raw = os.getenv(env_key)
                if override_raw is not None:
                    normalised = override_raw.strip().lower()
                    # Escape hatch disables the control when set to a falsy
                    # value (0/false/no/off); any other value keeps it on.
                    val = normalised in _TRUTHY
                    overrides[attr] = val
                    _logger.warning(
                        "[Posture] Escape hatch %s active in 'secure' posture "
                        "(control=%s).",
                        env_key,
                        "on" if val else "off",
                    )
            # prod: overrides are silently ignored
        return PostureDefaults(
            posture=posture,
            policy_runtime_enforce=overrides.get("policy_runtime_enforce", True),
            external_secret_manager_required=overrides.get(
                "external_secret_manager_required", True
            ),
            trustlog_transparency_required=overrides.get(
                "trustlog_transparency_required", True
            ),
            trustlog_worm_hard_fail=overrides.get("trustlog_worm_hard_fail", True),
            replay_strict=overrides.get("replay_strict", True),
        )

    # dev / staging: honour explicit env vars, default off
    return PostureDefaults(
        posture=posture,
        policy_runtime_enforce=_env_bool("VERITAS_POLICY_RUNTIME_ENFORCE", False),
        external_secret_manager_required=_env_bool(
            "VERITAS_ENFORCE_EXTERNAL_SECRET_MANAGER", False
        ),
        trustlog_transparency_required=_env_bool(
            "VERITAS_TRUSTLOG_TRANSPARENCY_REQUIRED", False
        ),
        trustlog_worm_hard_fail=_env_bool("VERITAS_TRUSTLOG_WORM_HARD_FAIL", False),
        replay_strict=_env_bool("VERITAS_REPLAY_STRICT", False),
    )


# ── Startup validation ──────────────────────────────────────────────────

class PostureStartupError(RuntimeError):
    """Raised when the active posture detects a fatal misconfiguration."""


def validate_posture_startup(defaults: PostureDefaults) -> List[str]:
    """Validate required integrations for the active posture.

    Returns a list of human-readable error strings.  For *secure*/*prod*
    posture, missing integrations cause startup to fail.  For *dev*/*staging*,
    the list is returned for informational warnings only.
    """
    errors: List[str] = []

    if defaults.external_secret_manager_required:
        provider = (os.getenv("VERITAS_SECRET_PROVIDER") or "").strip()
        ref = (os.getenv("VERITAS_API_SECRET_REF") or "").strip()
        if not provider:
            errors.append(
                "VERITAS_SECRET_PROVIDER must be set when external secret "
                "manager enforcement is active "
                f"(posture={defaults.posture.value})."
            )
        if not ref:
            errors.append(
                "VERITAS_API_SECRET_REF must be set when external secret "
                "manager enforcement is active "
                f"(posture={defaults.posture.value})."
            )

    if defaults.trustlog_transparency_required:
        tp = (os.getenv("VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH") or "").strip()
        if not tp:
            errors.append(
                "VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH must be set when "
                "transparency log anchoring is required "
                f"(posture={defaults.posture.value})."
            )

    if defaults.trustlog_worm_hard_fail:
        wp = (os.getenv("VERITAS_TRUSTLOG_WORM_MIRROR_PATH") or "").strip()
        if not wp:
            errors.append(
                "VERITAS_TRUSTLOG_WORM_MIRROR_PATH must be set when "
                "WORM hard-fail is required "
                f"(posture={defaults.posture.value})."
            )

    return errors


# ── Startup banner ──────────────────────────────────────────────────────

def log_posture_banner(defaults: PostureDefaults) -> str:
    """Emit a clear startup banner describing the active posture.

    Returns the banner string for testability.
    """
    guarantees = {
        "policy_runtime_enforce": defaults.policy_runtime_enforce,
        "external_secret_manager_required": defaults.external_secret_manager_required,
        "trustlog_transparency_required": defaults.trustlog_transparency_required,
        "trustlog_worm_hard_fail": defaults.trustlog_worm_hard_fail,
        "replay_strict": defaults.replay_strict,
    }
    on_flags = sorted(k for k, v in guarantees.items() if v)
    off_flags = sorted(k for k, v in guarantees.items() if not v)

    lines = [
        f"[POSTURE] Active posture: {defaults.posture.value}",
        f"[POSTURE] Guarantees ON : {', '.join(on_flags) if on_flags else '(none)'}",
        f"[POSTURE] Guarantees OFF: {', '.join(off_flags) if off_flags else '(none)'}",
    ]
    banner = "\n".join(lines)
    _logger.info("%s", banner)
    return banner


# ── Convenience: resolve + derive + validate in one call ────────────────

def init_posture(
    *,
    explicit: Optional[str] = None,
    fail_on_error: bool = True,
) -> PostureDefaults:
    """Resolve, derive, validate, and log the runtime posture.

    This is the single entry-point called during server startup.

    Args:
        explicit: Override posture value (mainly for tests).
        fail_on_error: When True (default), raise ``PostureStartupError``
            for strict postures with missing integrations.

    Returns:
        The resolved ``PostureDefaults``.

    Raises:
        PostureStartupError: When strict posture requirements are not met
            and *fail_on_error* is True.
    """
    level = resolve_posture(explicit=explicit)
    defaults = derive_defaults(level)
    log_posture_banner(defaults)

    errors = validate_posture_startup(defaults)
    if errors and defaults.is_strict:
        msg = (
            f"Posture '{defaults.posture.value}' startup refused — "
            "missing required integrations:\n  • "
            + "\n  • ".join(errors)
        )
        _logger.critical("[POSTURE] %s", msg)
        if fail_on_error:
            raise PostureStartupError(msg)
    elif errors:
        for err in errors:
            _logger.warning("[POSTURE] (non-fatal) %s", err)

    return defaults


# ── Module-level singleton (lazy) ───────────────────────────────────────

_active_posture: Optional[PostureDefaults] = None


def get_active_posture() -> PostureDefaults:
    """Return the active posture defaults (lazy-initialised on first call).

    In production the singleton is set during ``init_posture()`` in the
    server lifespan.  This function provides a safe fallback for code
    paths that run before lifespan (e.g. config module).
    """
    global _active_posture  # noqa: PLW0603 — process-wide posture singleton
    if _active_posture is None:
        _active_posture = derive_defaults(resolve_posture())
    return _active_posture


def set_active_posture(defaults: PostureDefaults) -> None:
    """Set the module-level active posture (called from lifespan)."""
    global _active_posture  # noqa: PLW0603 — set once during server startup
    _active_posture = defaults


def reset_active_posture() -> None:
    """Reset the module-level posture singleton (testing only)."""
    global _active_posture  # noqa: PLW0603 — testing reset only
    _active_posture = None
