# veritas_os/api/governance.py
"""Governance Policy API — GET / PUT /v1/governance/policy."""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from veritas_os.governance import file_repository as _file_repo_mod
from veritas_os.governance.config import get_governance_backend
from veritas_os.governance.factory import create_governance_repository
from veritas_os.governance.file_repository import FileGovernanceRepository
from veritas_os.governance.models import GovernancePolicyEventRecord
from veritas_os.governance.repository import GovernanceRepository

logger = logging.getLogger(__name__)

# ---------- storage path ----------
_DEFAULT_POLICY_PATH = Path(__file__).resolve().parent / "governance.json"
_POLICY_HISTORY_PATH = Path(__file__).resolve().parent / "governance_history.jsonl"

# Maximum number of policy change records kept in the history file
_POLICY_HISTORY_MAX = 500
_HAS_ATOMIC_IO = _file_repo_mod._HAS_ATOMIC_IO

# Thread-safe lock for file I/O
_policy_lock = threading.Lock()

# Repository provider; override in tests if needed.
_governance_repository_factory: Callable[[], GovernanceRepository] | None = None

# Callbacks invoked after each successful policy update (e.g. for FUJI hot-reload).
# Each callable receives the full updated policy dict.
_policy_update_callbacks: List[Callable[[Dict[str, Any]], None]] = []
_callbacks_lock = threading.Lock()

_VALUE_HISTORY_PATHS = (
    Path(__file__).resolve().parents[1] / ".veritas" / "value_stats.json",
    Path(__file__).resolve().parents[2] / "data" / "value_stats.json",
)

DEFAULT_TELOS_BASELINE = 0.5


# ---------- Pydantic schemas ----------

class FujiRules(BaseModel):
    pii_check: bool = True
    self_harm_block: bool = True
    illicit_block: bool = True
    violence_review: bool = True
    minors_review: bool = True
    keyword_hard_block: bool = True
    keyword_soft_flag: bool = True
    llm_safety_head: bool = True


class RiskThresholds(BaseModel):
    allow_upper: float = Field(default=0.40, ge=0.0, le=1.0)
    warn_upper: float = Field(default=0.65, ge=0.0, le=1.0)
    human_review_upper: float = Field(default=0.85, ge=0.0, le=1.0)
    deny_upper: float = Field(default=1.00, ge=0.0, le=1.0)


class AutoStop(BaseModel):
    enabled: bool = True
    max_risk_score: float = Field(default=0.85, ge=0.0, le=1.0)
    max_consecutive_rejects: int = Field(default=5, ge=1, le=1000)
    max_requests_per_minute: int = Field(default=60, ge=1, le=10000)


class LogRetention(BaseModel):
    retention_days: int = Field(default=90, ge=1, le=3650)
    audit_level: Literal["none", "minimal", "summary", "standard", "full", "strict"] = "full"
    include_fields: list[str] = Field(
        default_factory=lambda: ["status", "risk", "reasons", "violations", "categories"]
    )
    redact_before_log: bool = True
    max_log_size: int = Field(default=10000, ge=100, le=1_000_000)


class RolloutControls(BaseModel):
    """Progressive enforcement controls for governance policy rollout."""

    strategy: Literal["disabled", "canary", "staged", "full"] = "disabled"
    canary_percent: int = Field(default=0, ge=0, le=100)
    stage: int = Field(default=0, ge=0, le=10)
    staged_enforcement: bool = False


class ApprovalWorkflowConfig(BaseModel):
    """Human review + approver identity binding metadata."""

    human_review_ticket: str = ""
    human_review_required: bool = False
    approver_identity_binding: bool = True
    approver_identities: list[str] = Field(default_factory=list)


class WatConfig(BaseModel):
    """Witness attestation token (WAT) issuance controls."""

    enabled: bool = False
    issuance_mode: Literal["shadow_only", "disabled"] = "shadow_only"
    require_observable_digest: bool = True
    default_ttl_seconds: int = Field(default=300, ge=1, le=86_400)
    signer_backend: str = "existing_signer"
    wat_metadata_retention_ttl_seconds: int = Field(
        default=7_776_000,
        ge=60,
        le=315_360_000,
        description="Retention TTL for lean WAT metadata in the primary audit path.",
    )
    wat_event_pointer_retention_ttl_seconds: int = Field(
        default=7_776_000,
        ge=60,
        le=315_360_000,
        description="Retention TTL for event-pointer records in the primary audit path.",
    )
    observable_digest_retention_ttl_seconds: int = Field(
        default=31_536_000,
        ge=60,
        le=315_360_000,
        description="Retention TTL for full observable digests in a separate store.",
    )
    observable_digest_access_class: Literal["restricted", "privileged"] = Field(
        default="restricted",
        description="Access class for full observable digest store linkage.",
    )
    observable_digest_ref: str = Field(
        default="separate_store://wat_observables",
        max_length=500,
        description=(
            "Reference/locator prefix for separate-store observable digest material; "
            "never an inline digest payload."
        ),
    )
    retention_policy_version: str = Field(
        default="wat_retention_v1",
        min_length=1,
        max_length=120,
        description=(
            "Immutable once retention_enforced_at_write=true; identifies retention"
            " boundary policy revision used at write time."
        ),
    )
    retention_enforced_at_write: bool = Field(
        default=True,
        description=(
            "When true, write-time retention guards are active and "
            "retention_policy_version becomes immutable."
        ),
    )


class PsidConfig(BaseModel):
    """Policy-scoped identifier display and enforcement settings."""

    enforcement_mode: Literal["full_digest_only"] = "full_digest_only"
    display_length: int = Field(default=12, ge=4, le=128)


class ShadowValidationConfig(BaseModel):
    """Shadow validation behavior for non-disruptive rollout checks."""

    enabled: bool = True
    partial_validation_default: Literal["non_admissible"] = "non_admissible"
    warning_only_until: str = ""
    timestamp_skew_tolerance_seconds: int = Field(default=5, ge=0, le=3600)
    replay_binding_required: bool = False
    replay_binding_escalation_threshold: int = Field(default=4, ge=1, le=16)
    partial_validation_requires_confirmation: bool = True


class RevocationConfig(BaseModel):
    """Revocation consistency targets and degraded-mode posture."""

    enabled: bool = True
    mode: Literal["bounded_eventual_consistency"] = "bounded_eventual_consistency"
    alert_target_seconds: int = Field(default=30, ge=1, le=86_400)
    convergence_target_p95_seconds: int = Field(default=60, ge=1, le=86_400)
    degrade_on_pending: bool = True
    revocation_confirmation_required: bool = True
    auto_escalate_confirmed_revocations: bool = False


class DriftScoringConfig(BaseModel):
    """Weights and thresholds used for drift scoring telemetry."""

    policy_weight: float = Field(default=0.4, ge=0.0, le=1.0)
    signature_weight: float = Field(default=0.3, ge=0.0, le=1.0)
    observable_weight: float = Field(default=0.2, ge=0.0, le=1.0)
    temporal_weight: float = Field(default=0.1, ge=0.0, le=1.0)
    healthy_threshold: float = Field(default=0.2, ge=0.0, le=1.0)
    critical_threshold: float = Field(default=0.5, ge=0.0, le=1.0)


class BindAdjudicationPolicyConfig(BaseModel):
    """Runtime bind-adjudication controls used by bind core/adapters."""

    missing_signal_default: Literal["block", "escalate"] = "block"
    drift_required: bool = True
    ttl_required: bool = False
    approval_freshness_required: bool = False
    rollback_on_apply_failure: bool = False


class GovernancePolicy(BaseModel):
    version: str = "governance_v1"
    fuji_rules: FujiRules = Field(default_factory=FujiRules)
    risk_thresholds: RiskThresholds = Field(default_factory=RiskThresholds)
    auto_stop: AutoStop = Field(default_factory=AutoStop)
    log_retention: LogRetention = Field(default_factory=LogRetention)
    rollout_controls: RolloutControls = Field(default_factory=RolloutControls)
    approval_workflow: ApprovalWorkflowConfig = Field(default_factory=ApprovalWorkflowConfig)
    wat: WatConfig = Field(default_factory=WatConfig)
    psid: PsidConfig = Field(default_factory=PsidConfig)
    shadow_validation: ShadowValidationConfig = Field(default_factory=ShadowValidationConfig)
    revocation: RevocationConfig = Field(default_factory=RevocationConfig)
    drift_scoring: DriftScoringConfig = Field(default_factory=DriftScoringConfig)
    bind_adjudication: BindAdjudicationPolicyConfig = Field(default_factory=BindAdjudicationPolicyConfig)
    operator_verbosity: Literal["minimal", "expanded"] = "minimal"
    updated_at: str = ""
    updated_by: str = "system"


_NESTED_POLICY_MODELS = {
    "fuji_rules": FujiRules,
    "risk_thresholds": RiskThresholds,
    "auto_stop": AutoStop,
    "log_retention": LogRetention,
    "rollout_controls": RolloutControls,
    "approval_workflow": ApprovalWorkflowConfig,
    "wat": WatConfig,
    "psid": PsidConfig,
    "shadow_validation": ShadowValidationConfig,
    "revocation": RevocationConfig,
    "drift_scoring": DriftScoringConfig,
    "bind_adjudication": BindAdjudicationPolicyConfig,
}


# ---------- storage helpers ----------

def _policy_path() -> Path:
    return _DEFAULT_POLICY_PATH


def _build_default_repository() -> GovernanceRepository:
    """Create governance repository selected by environment backend config."""
    return create_governance_repository(
        policy_path=_DEFAULT_POLICY_PATH,
        history_path=_POLICY_HISTORY_PATH,
        lock=_policy_lock,
        policy_history_max=_POLICY_HISTORY_MAX,
        has_atomic_io=_HAS_ATOMIC_IO,
    )


def set_governance_repository_factory(
    factory: Callable[[], GovernanceRepository] | None,
) -> None:
    """Set repository factory used by governance API persistence helpers."""
    global _governance_repository_factory
    _governance_repository_factory = factory


def _get_repository() -> GovernanceRepository:
    if _governance_repository_factory is None:
        return _build_default_repository()
    return _governance_repository_factory()


def configure_governance_repository_from_env() -> GovernanceRepository:
    """Configure repository DI factory from backend env and fail fast on errors."""
    repository = _build_default_repository()
    set_governance_repository_factory(lambda: repository)
    logger.info("Governance repository configured (backend=%s)", get_governance_backend())
    return repository


def _load() -> Dict[str, Any]:
    """Load governance policy through repository abstraction."""
    return _get_repository().get_current_policy(
        default_factory=lambda: GovernancePolicy().model_dump()
    )


def _save(data: Dict[str, Any]) -> None:
    """Persist governance policy through repository abstraction."""
    _get_repository().save_policy(data)


def _append_policy_history(
    previous: Dict[str, Any],
    updated: Dict[str, Any],
    *,
    proposer: str = "",
    approvers: Optional[List[str]] = None,
    event_type: str = "update",
) -> None:
    """Append policy history through repository abstraction."""
    try:
        from veritas_os.policy.governance_identity import compute_governance_digest

        prev_digest = compute_governance_digest(previous)
        new_digest = compute_governance_digest(updated)
    except Exception:
        prev_digest = ""
        new_digest = ""

    event = GovernancePolicyEventRecord(
        changed_at=updated.get("updated_at", datetime.now(timezone.utc).isoformat()),
        changed_by=updated.get("updated_by", "unknown"),
        proposer=proposer or updated.get("updated_by", "unknown"),
        approvers=approvers or [],
        event_type=event_type,
        previous_version=previous.get("version"),
        new_version=updated.get("version"),
        previous_digest=prev_digest,
        new_digest=new_digest,
        previous_policy=previous,
        new_policy=updated,
    )
    _get_repository().append_policy_event(event)


def _trim_policy_history() -> None:
    """Keep only the most recent _POLICY_HISTORY_MAX records in history."""
    repository = _get_repository()
    if isinstance(repository, FileGovernanceRepository):
        repository.trim_policy_history()


def _notify_policy_update(policy: Dict[str, Any]) -> None:
    """Call all registered callbacks with the updated policy (best-effort)."""
    with _callbacks_lock:
        callbacks = list(_policy_update_callbacks)
    for cb in callbacks:
        try:
            cb(policy)
        except Exception as e:
            logger.warning("Policy update callback %r raised: %s", cb, e)


def register_policy_update_callback(callback: Callable[[Dict[str, Any]], None]) -> None:
    """Register a callback to be invoked after each successful policy update.

    This enables hot-reload: components like FUJI can register here and
    refresh their cached policy without requiring a process restart.

    Args:
        callback: Callable accepting the full updated policy dict.
    """
    with _callbacks_lock:
        if callback not in _policy_update_callbacks:
            _policy_update_callbacks.append(callback)


def unregister_policy_update_callback(callback: Callable[[Dict[str, Any]], None]) -> None:
    """Remove a previously registered policy update callback."""
    with _callbacks_lock:
        try:
            _policy_update_callbacks.remove(callback)
        except ValueError:
            pass


def _coerce_metric_point(raw: Any, fallback_index: int) -> Dict[str, Any] | None:
    """Normalize a raw history item into a metric point shape."""
    if not isinstance(raw, dict):
        return None

    ema_raw = raw.get("ema")
    if not isinstance(ema_raw, (int, float)):
        return None

    ema = max(0.0, min(1.0, float(ema_raw)))
    ts = raw.get("timestamp") or raw.get("created_at") or raw.get("ts")
    if not isinstance(ts, str):
        ts = f"point-{fallback_index}"

    return {"ema": ema, "timestamp": ts}


def _load_value_history() -> List[Dict[str, Any]]:
    """Load ValueEMA history from known paths, returning a normalized list."""
    for path in _VALUE_HISTORY_PATHS:
        if not path.exists():
            continue

        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError, ValueError, UnicodeDecodeError) as e:
            logger.warning("Failed to load value history from %s: %s", path, e)
            continue

        raw_history: List[Any] = []
        if isinstance(payload, dict) and isinstance(payload.get("history"), list):
            raw_history = payload["history"]
        elif isinstance(payload, list):
            raw_history = payload

        points = [
            point
            for i, item in enumerate(raw_history)
            for point in [_coerce_metric_point(item, i)]
            if point is not None
        ]
        if points:
            return points

    return []


# ---------- public API ----------

def get_policy() -> Dict[str, Any]:
    """Return the current governance policy."""
    return _load()


def _sanitize_updated_by(raw: Any) -> str:
    """Sanitize the ``updated_by`` field for safe persistence and display.

    * Falls back to ``"api"`` for ``None``
    * Coerces to str
    * Strips leading/trailing whitespace and control characters
    * Removes HTML-like tags to mitigate stored-XSS when rendered in dashboards
    * Truncates to 200 characters (DoS protection)
    """
    if raw is None:
        return "api"
    text = str(raw).strip()
    # Strip control characters (U+0000–U+001F, U+007F–U+009F) except common whitespace
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", text)
    # Strip HTML tags to prevent stored-XSS in governance dashboards
    text = re.sub(r"<[^>]*>", "", text)
    return text[:200]


def update_policy(patch: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge *patch* into the current governance policy and persist.

    Changes are written atomically and appended to the audit history log.
    All registered callbacks (e.g. FUJI hot-reload) are notified after save.

    Raises:
        TypeError: If *patch* is not a dict.
        ValueError: If a nested section is not an object or fails validation.

    Returns the full updated policy.
    """
    if not isinstance(patch, dict):
        raise TypeError("policy patch must be a dict")

    previous = _load()
    current = deepcopy(previous)

    previous_wat = current.get("wat") if isinstance(current.get("wat"), dict) else {}

    # Validate and deep-merge nested patches immediately.
    # This prevents silently skipping non-dict payloads and validates each
    # section before it is written into the in-memory aggregate state.
    for key, model_cls in _NESTED_POLICY_MODELS.items():
        if key not in patch:
            continue

        section_patch = patch[key]
        if not isinstance(section_patch, dict):
            raise ValueError(f"{key} must be an object")

        section_current = current.get(key, {})
        if not isinstance(section_current, dict):
            section_current = {}

        merged_section = deepcopy(section_current)
        merged_section.update(section_patch)

        validated_section = model_cls.model_validate(merged_section)
        current[key] = validated_section.model_dump()

    # Retention boundary lock-in:
    # once retention_enforced_at_write=true, retention_policy_version must not
    # change for this persisted policy path.
    current_wat = current.get("wat") if isinstance(current.get("wat"), dict) else {}
    previous_enforced = bool(previous_wat.get("retention_enforced_at_write"))
    if previous_enforced:
        previous_version = str(previous_wat.get("retention_policy_version", "")).strip()
        current_version = str(current_wat.get("retention_policy_version", "")).strip()
        if previous_version and current_version and current_version != previous_version:
            raise ValueError(
                "wat.retention_policy_version is immutable after "
                "retention_enforced_at_write=true"
            )

    # Scalar overrides
    for key in ("version",):
        if key in patch:
            current[key] = patch[key]

    # Metadata
    current["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    current["updated_by"] = _sanitize_updated_by(patch.get("updated_by", "api"))

    # Validate through pydantic
    validated = GovernancePolicy.model_validate(current)
    result = validated.model_dump()

    # Extract provenance metadata from the patch for audit trail.
    approvals = patch.get("approvals")
    approver_ids: List[str] = []
    if isinstance(approvals, list):
        for a in approvals:
            if isinstance(a, dict):
                r = str(a.get("reviewer", "")).strip()
                if r:
                    approver_ids.append(r)
    proposer = _sanitize_updated_by(patch.get("updated_by", "api"))
    event_type = str(patch.get("_event_type", "update"))

    _get_repository().update_policy(
        previous=previous,
        updated=result,
        proposer=proposer,
        approvers=approver_ids,
        event_type=event_type,
        approval_records=approvals if isinstance(approvals, list) else None,
    )

    # Notify subscribers (e.g. FUJI hot-reload) — best-effort, non-blocking
    _notify_policy_update(result)

    return result


def enforce_four_eyes_approval(payload: Dict[str, Any]) -> None:
    """Enforce 4-eyes approval for governance policy updates.

    This control is enabled by default and can be disabled explicitly for
    development with ``VERITAS_GOVERNANCE_REQUIRE_FOUR_EYES=0``.

    Required payload shape:

    - ``approvals``: list of exactly two objects
    - each object must include non-empty ``reviewer`` and ``signature``
    - reviewers and signatures must be distinct
    """
    enforce = os.getenv("VERITAS_GOVERNANCE_REQUIRE_FOUR_EYES", "1").strip().lower()
    if enforce in {"0", "false", "no", "off"}:
        return

    approvals = payload.get("approvals")
    if not isinstance(approvals, list) or len(approvals) != 2:
        raise PermissionError("governance update requires exactly two approvals")

    reviewers: set[str] = set()
    signatures: set[str] = set()
    for approval in approvals:
        if not isinstance(approval, dict):
            raise PermissionError("approval entries must be objects")

        reviewer = str(approval.get("reviewer", "")).strip()
        signature = str(approval.get("signature", "")).strip()
        if not reviewer or not signature:
            raise PermissionError("approval entries require reviewer and signature")

        reviewers.add(reviewer)
        signatures.add(signature)

    if len(reviewers) != 2:
        raise PermissionError("approvals must be from two distinct reviewers")
    if len(signatures) != 2:
        raise PermissionError("approvals must include two distinct signatures")


def get_policy_history(limit: int = 50) -> List[Dict[str, Any]]:
    """Return recent policy change records from the audit history, newest first.

    Args:
        limit: Maximum number of records to return (capped at _POLICY_HISTORY_MAX).
    """
    return _get_repository().list_policy_history(
        limit=limit, max_records=_POLICY_HISTORY_MAX
    )


def get_value_drift(telos_baseline: float = DEFAULT_TELOS_BASELINE) -> Dict[str, Any]:
    """Build ValueCore drift metrics relative to the configured Telos baseline."""
    baseline = max(0.0, min(1.0, float(telos_baseline)))
    history = _load_value_history()
    latest_ema = history[-1].get("ema", baseline) if history else baseline

    if baseline <= 1e-9:
        drift_percent = 0.0
    else:
        drift_percent = ((latest_ema - baseline) / baseline) * 100.0
        # Cap drift to prevent extreme values when baseline is very small
        drift_percent = max(-1000.0, min(1000.0, drift_percent))

    return {
        "baseline": baseline,
        "latest_ema": latest_ema,
        "drift_percent": round(drift_percent, 2),
        "history": history,
        "status": "ok" if history else "no_data",
    }


def rollback_policy(
    target_policy: Dict[str, Any],
    *,
    rolled_back_by: str = "api",
    approvals: Optional[List[Dict[str, Any]]] = None,
    reason: str = "",
) -> Dict[str, Any]:
    """Rollback governance policy to a previous state.

    Rollback is a governed operation: it records the event as ``rollback``
    in the audit trail with full provenance (proposer, approvers, digests).

    When 4-eyes approval is enabled, the *approvals* list must satisfy the
    same constraints as a regular policy update.

    Args:
        target_policy: The full governance policy dict to restore.
        rolled_back_by: Identity of the person/system performing the rollback.
        approvals: List of approval objects for 4-eyes verification.
        reason: Human-readable reason for the rollback.

    Returns:
        The restored policy dict after validation and persistence.

    Raises:
        TypeError: If *target_policy* is not a dict.
        ValueError: If validation fails.
        PermissionError: If 4-eyes approval is required but not satisfied.
    """
    if not isinstance(target_policy, dict):
        raise TypeError(
            f"target_policy must be a dict, got {type(target_policy).__name__}"
        )

    # Enforce 4-eyes approval for rollback (same as update)
    payload_for_approval = {"approvals": approvals or []}
    enforce_four_eyes_approval(payload_for_approval)

    previous = _load()

    # Validate through pydantic
    target_policy["updated_at"] = (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )
    target_policy["updated_by"] = _sanitize_updated_by(rolled_back_by)
    validated = GovernancePolicy.model_validate(target_policy)
    result = validated.model_dump()

    # Extract approver identities
    approver_ids: List[str] = []
    if isinstance(approvals, list):
        for a in approvals:
            if isinstance(a, dict):
                r = str(a.get("reviewer", "")).strip()
                if r:
                    approver_ids.append(r)

    _get_repository().rollback_policy(
        previous=previous,
        restored=result,
        proposer=_sanitize_updated_by(rolled_back_by),
        approvers=approver_ids,
        approval_records=approvals if isinstance(approvals, list) else None,
        reason=reason,
    )

    _notify_policy_update(result)

    logger.info(
        "governance policy rolled back by=%s reason=%s",
        rolled_back_by,
        reason or "(none)",
    )
    return result
