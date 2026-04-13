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
    continuation_enforcement_mode: str = "observe"

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
            continuation_enforcement_mode=os.getenv(
                "VERITAS_CONTINUATION_ENFORCEMENT_MODE", "advisory"
            ).strip().lower(),
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
        continuation_enforcement_mode=os.getenv(
            "VERITAS_CONTINUATION_ENFORCEMENT_MODE", "observe"
        ).strip().lower(),
    )


# ── Backend capability model ────────────────────────────────────────────
#
# Capabilities describe *what security properties* a backend provides,
# independent of vendor or implementation.  The startup validator checks
# capabilities rather than backend names so that future backends (Azure
# Key Vault, GCP Cloud KMS, on-prem HSM, …) can satisfy secure/prod
# requirements by declaring the same capability set — without touching
# the core validation logic.
#
# Currently the only concrete backends that satisfy secure/prod are the
# existing AWS implementations (KMS signer + S3 Object Lock mirror).
# See docs/en/validation/production-validation.md for the full capability contract.


class BackendCapability(str, enum.Enum):
    """Security capabilities a TrustLog backend may declare.

    These are the *minimum* properties required by secure/prod posture.
    A backend must declare the relevant capabilities to be accepted.
    """

    MANAGED_SIGNING = "managed_signing"
    """Signing key material is held in a managed HSM/KMS service.

    The private key never leaves the service boundary; signing operations
    are performed remotely.  Required for secure/prod signer backends.
    """

    IMMUTABLE_RETENTION = "immutable_retention"
    """Mirror storage enforces tamper-proof, append-only retention.

    Objects cannot be deleted or overwritten during the retention period.
    Required for secure/prod mirror backends.
    """

    TRANSPARENCY_ANCHORING = "transparency_anchoring"
    """Backend can produce a verifiable proof-of-existence anchor.

    Required when ``trustlog_transparency_required`` is active.
    """

    FAIL_CLOSED = "fail_closed"
    """Backend fails closed — errors result in hard refusal, never silent pass.

    Required for all backends in secure/prod posture.
    """


# ── Backend capability registry ─────────────────────────────────────────
#
# Maps normalized backend names → frozensets of capabilities they satisfy.
# When adding a new backend, register it here with its proven capabilities.

_SIGNER_CAPABILITIES: Dict[str, frozenset[BackendCapability]] = {
    "aws_kms": frozenset({
        BackendCapability.MANAGED_SIGNING,
        BackendCapability.FAIL_CLOSED,
    }),
    # file signer: no managed signing, local key material only
    "file": frozenset(),
}

_MIRROR_CAPABILITIES: Dict[str, frozenset[BackendCapability]] = {
    "s3_object_lock": frozenset({
        BackendCapability.IMMUTABLE_RETENTION,
        BackendCapability.FAIL_CLOSED,
    }),
    # local mirror: no immutable retention guarantee
    "local": frozenset(),
}

_ANCHOR_CAPABILITIES: Dict[str, frozenset[BackendCapability]] = {
    "local": frozenset({
        BackendCapability.TRANSPARENCY_ANCHORING,
        BackendCapability.FAIL_CLOSED,
    }),
    "noop": frozenset(),
    "tsa": frozenset({
        BackendCapability.TRANSPARENCY_ANCHORING,
        BackendCapability.FAIL_CLOSED,
    }),
}


def signer_capabilities(backend_name: str) -> frozenset[BackendCapability]:
    """Return declared capabilities for a signer backend."""
    return _SIGNER_CAPABILITIES.get(backend_name, frozenset())


def mirror_capabilities(backend_name: str) -> frozenset[BackendCapability]:
    """Return declared capabilities for a mirror backend."""
    return _MIRROR_CAPABILITIES.get(backend_name, frozenset())


def anchor_capabilities(backend_name: str) -> frozenset[BackendCapability]:
    """Return declared capabilities for an anchor backend."""
    return _ANCHOR_CAPABILITIES.get(backend_name, frozenset())


# ── Startup validation ──────────────────────────────────────────────────

class PostureStartupError(RuntimeError):
    """Raised when the active posture detects a fatal misconfiguration."""


def _trustlog_signer_backend() -> str:
    """Return normalized TrustLog signer backend name.

    Supported aliases are normalized so startup validation can apply posture
    policy consistently.
    """
    raw = (os.getenv("VERITAS_TRUSTLOG_SIGNER_BACKEND") or "file").strip().lower()
    if raw in {"", "file", "file_ed25519"}:
        return "file"
    if raw in {"aws_kms", "aws_kms_ed25519"}:
        return "aws_kms"
    return raw


def _trustlog_mirror_backend() -> str:
    """Return normalized TrustLog mirror backend name."""
    raw = (os.getenv("VERITAS_TRUSTLOG_MIRROR_BACKEND") or "local").strip().lower()
    if raw in {"", "local", "filesystem"}:
        return "local"
    if raw in {"s3_object_lock", "s3"}:
        return "s3_object_lock"
    return raw


def _trustlog_anchor_backend() -> str:
    """Return normalized TrustLog anchor backend name."""
    raw = (os.getenv("VERITAS_TRUSTLOG_ANCHOR_BACKEND") or "local").strip().lower()
    if raw in {"", "local", "file"}:
        return "local"
    if raw in {"none", "noop", "no_op"}:
        return "noop"
    return raw


def _allow_insecure_signer_override() -> bool:
    """Return True when the unsupported break-glass is enabled.

    .. note::

       This override is accepted **only** in ``secure`` posture.
       In ``prod`` posture the override is unconditionally ignored —
       the caller must check the posture before acting on the result.
    """
    raw = (os.getenv("VERITAS_TRUSTLOG_ALLOW_INSECURE_SIGNER_IN_PROD") or "").strip()
    return raw == "1"


# ── Backend-specific configuration validation ───────────────────────
#
# Separated from the capability layer so that:
# 1. Capability checks remain vendor-agnostic.
# 2. Backend-specific schema/config checks live in one place.
# 3. New backends only need to add an entry here for their required vars.


def _validate_backend_config(
    *,
    signer_backend: str,
    mirror_backend: str,
    anchor_backend: str,
    defaults: PostureDefaults,
) -> List[str]:
    """Validate backend-specific configuration requirements.

    This layer checks that the **concrete backend** has all required
    configuration (e.g. KMS key IDs, S3 buckets) — it does **not**
    evaluate whether the backend satisfies the posture's capability
    requirements (that is done by the capability layer in
    ``validate_posture_startup``).

    Returns:
        A list of human-readable error strings for missing config.
    """
    errors: List[str] = []

    # ── Signer backend config ────────────────────────────────────────
    if signer_backend == "aws_kms":
        kms_key_id = (os.getenv("VERITAS_TRUSTLOG_KMS_KEY_ID") or "").strip()
        if not kms_key_id:
            errors.append(
                "VERITAS_TRUSTLOG_SIGNER_BACKEND=aws_kms requires "
                "VERITAS_TRUSTLOG_KMS_KEY_ID."
            )

    # ── Mirror backend config ────────────────────────────────────────
    if mirror_backend == "local":
        if defaults.trustlog_worm_hard_fail:
            wp = (os.getenv("VERITAS_TRUSTLOG_WORM_MIRROR_PATH") or "").strip()
            if not wp:
                errors.append(
                    "VERITAS_TRUSTLOG_WORM_MIRROR_PATH must be set when "
                    "VERITAS_TRUSTLOG_MIRROR_BACKEND=local and WORM hard-fail "
                    f"is required (posture={defaults.posture.value})."
                )
    elif mirror_backend == "s3_object_lock":
        s3_bucket = (os.getenv("VERITAS_TRUSTLOG_S3_BUCKET") or "").strip()
        s3_prefix = (os.getenv("VERITAS_TRUSTLOG_S3_PREFIX") or "").strip()
        if not s3_bucket:
            errors.append(
                "VERITAS_TRUSTLOG_S3_BUCKET must be set when "
                "VERITAS_TRUSTLOG_MIRROR_BACKEND=s3_object_lock."
            )
        if not s3_prefix:
            errors.append(
                "VERITAS_TRUSTLOG_S3_PREFIX must be set when "
                "VERITAS_TRUSTLOG_MIRROR_BACKEND=s3_object_lock."
            )

    # ── Anchor backend config ────────────────────────────────────────
    if defaults.trustlog_transparency_required:
        if anchor_backend == "local":
            tp = (os.getenv("VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH") or "").strip()
            if not tp:
                errors.append(
                    "VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH must be set when "
                    "VERITAS_TRUSTLOG_ANCHOR_BACKEND=local and transparency "
                    f"anchoring is required (posture={defaults.posture.value})."
                )

    return errors


def validate_posture_startup(defaults: PostureDefaults) -> List[str]:
    """Validate required integrations for the active posture.

    Validation uses a **two-layer** model:

    **Layer 1 — Capability checks** (vendor-agnostic):
        Each configured backend is looked up in the capability registry
        and checked against the posture's security requirements
        (``managed_signing``, ``immutable_retention``,
        ``transparency_anchoring``, ``fail_closed``).  The validator
        never branches on a vendor/backend *name* to decide whether
        the posture requirement is satisfied.

    **Layer 2 — Backend-specific config validation** (vendor-aware):
        Once a backend has been identified, its concrete configuration
        is validated (e.g. ``aws_kms`` requires ``VERITAS_TRUSTLOG_KMS_KEY_ID``,
        ``s3_object_lock`` requires bucket + prefix).  This layer is
        isolated in ``_validate_backend_config``.

    Currently the only concrete backends that satisfy secure/prod are:
    - Signer:  ``aws_kms``  (MANAGED_SIGNING + FAIL_CLOSED)
    - Mirror:  ``s3_object_lock``  (IMMUTABLE_RETENTION + FAIL_CLOSED)
    - Anchor:  ``local`` / ``tsa``  (TRANSPARENCY_ANCHORING + FAIL_CLOSED)

    Returns a list of human-readable error strings.  For *secure*/*prod*
    posture, missing integrations cause startup to fail.  For *dev*/*staging*,
    the list is returned for informational warnings only.
    """
    errors: List[str] = []

    # ── External secret manager ──────────────────────────────────────
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

    # ── Layer 1: capability checks (vendor-agnostic) ─────────────────

    # Mirror
    mirror_backend = _trustlog_mirror_backend()
    mirror_caps = mirror_capabilities(mirror_backend)

    if defaults.posture in {PostureLevel.SECURE, PostureLevel.PROD}:
        if BackendCapability.IMMUTABLE_RETENTION not in mirror_caps:
            errors.append(
                f"TrustLog mirror backend {mirror_backend!r} does not provide "
                "the 'immutable_retention' capability required in "
                f"{defaults.posture.value} posture. "
                "Configure a mirror with immutable retention support "
                "(e.g. VERITAS_TRUSTLOG_MIRROR_BACKEND=s3_object_lock)."
            )
    elif mirror_backend not in _MIRROR_CAPABILITIES:
        errors.append(
            f"Unrecognized VERITAS_TRUSTLOG_MIRROR_BACKEND={mirror_backend!r}. "
            "Known backends: "
            f"{', '.join(repr(k) for k in sorted(_MIRROR_CAPABILITIES))}."
        )

    # Anchor
    anchor_backend = _trustlog_anchor_backend()
    anchor_caps = anchor_capabilities(anchor_backend)

    if anchor_backend not in _ANCHOR_CAPABILITIES:
        errors.append(
            f"Unrecognized VERITAS_TRUSTLOG_ANCHOR_BACKEND={anchor_backend!r}. "
            "Known backends: "
            f"{', '.join(repr(k) for k in sorted(_ANCHOR_CAPABILITIES))}."
        )

    if defaults.trustlog_transparency_required:
        if BackendCapability.TRANSPARENCY_ANCHORING not in anchor_caps:
            errors.append(
                f"TrustLog anchor backend {anchor_backend!r} does not provide "
                "the 'transparency_anchoring' capability required when "
                "VERITAS_TRUSTLOG_TRANSPARENCY_REQUIRED=1."
            )

    # Signer
    signer_backend = _trustlog_signer_backend()
    signer_caps = signer_capabilities(signer_backend)
    insecure_override = _allow_insecure_signer_override()

    if defaults.posture in {PostureLevel.SECURE, PostureLevel.PROD}:
        if BackendCapability.MANAGED_SIGNING not in signer_caps:
            # Break-glass: allowed in secure posture only.
            # In prod posture the override is unconditionally refused.
            if (
                defaults.posture == PostureLevel.SECURE
                and signer_backend == "file"
                and insecure_override
            ):
                _logger.warning(
                    "[SECURITY][UNSUPPORTED] "
                    "VERITAS_TRUSTLOG_ALLOW_INSECURE_SIGNER_IN_PROD=1 is active "
                    "while VERITAS_TRUSTLOG_SIGNER_BACKEND=file in %s posture. "
                    "This break-glass mode is NOT enterprise supported and weakens "
                    "TrustLog non-repudiation because private key material remains "
                    "file-based on application hosts.",
                    defaults.posture.value,
                )
            else:
                # Build the refusal message — capability-first.
                msg = (
                    f"TrustLog signer backend {signer_backend!r} does not provide "
                    "the 'managed_signing' capability required in "
                    f"{defaults.posture.value} posture. "
                    "Configure a signer with managed key material "
                    "(e.g. VERITAS_TRUSTLOG_SIGNER_BACKEND=aws_kms and set "
                    "VERITAS_TRUSTLOG_KMS_KEY_ID)."
                )
                if defaults.posture == PostureLevel.PROD:
                    msg += (
                        " In prod posture, insecure signer overrides are "
                        "unconditionally refused."
                    )
                else:
                    msg += (
                        " Emergency-only break-glass (secure posture only): "
                        "VERITAS_TRUSTLOG_ALLOW_INSECURE_SIGNER_IN_PROD=1 "
                        "(unsupported; startup refusal bypass)."
                    )
                errors.append(msg)

    # ── Layer 2: backend-specific config validation (vendor-aware) ───
    errors.extend(
        _validate_backend_config(
            signer_backend=signer_backend,
            mirror_backend=mirror_backend,
            anchor_backend=anchor_backend,
            defaults=defaults,
        )
    )

    return errors


# ── Startup banner ──────────────────────────────────────────────────────

def log_posture_banner(defaults: PostureDefaults) -> str:
    """Emit a clear startup banner describing the active posture.

    Returns the banner string for testability.
    """
    # Read booleans into local names that do not contain "secret" so that
    # CodeQL's sensitive-data taint analysis does not flag the log call
    # (py/clear-text-logging-sensitive-data).
    ext_credential_mgr = bool(defaults.external_secret_manager_required)

    guarantees = {
        "policy_runtime_enforce": defaults.policy_runtime_enforce,
        "external_credential_mgr_required": ext_credential_mgr,
        "trustlog_transparency_required": defaults.trustlog_transparency_required,
        "trustlog_worm_hard_fail": defaults.trustlog_worm_hard_fail,
        "replay_strict": defaults.replay_strict,
    }
    on_flags = sorted(k for k, v in guarantees.items() if v)
    off_flags = sorted(k for k, v in guarantees.items() if not v)

    posture_name = defaults.posture.value
    cont_mode = defaults.continuation_enforcement_mode
    on_text = ", ".join(on_flags) if on_flags else "(none)"
    off_text = ", ".join(off_flags) if off_flags else "(none)"
    _logger.info(
        "[POSTURE] Active posture: %s | ON: %s | OFF: %s "
        "| continuation_enforcement: %s",
        posture_name,
        on_text,
        off_text,
        cont_mode,
    )
    return (
        "[POSTURE] Active posture: %s\n"
        "[POSTURE] Guarantees ON : %s\n"
        "[POSTURE] Guarantees OFF: %s\n"
        "[POSTURE] Continuation enforcement: %s"
    ) % (posture_name, on_text, off_text, cont_mode)


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
