# veritas_os/api/governance.py
"""
Governance Policy API — GET / PUT /v1/governance/policy

Storage: file-based (governance.json) with an interface that can be
swapped to a DB backend later by replacing `_load` / `_save`.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal

from pydantic import BaseModel, Field

try:
    from veritas_os.core.atomic_io import atomic_write_json as _atomic_write_json
    _HAS_ATOMIC_IO = True
except Exception:  # pragma: no cover
    _HAS_ATOMIC_IO = False

logger = logging.getLogger(__name__)

# ---------- storage path ----------
_DEFAULT_POLICY_PATH = Path(__file__).resolve().parent / "governance.json"
_POLICY_HISTORY_PATH = Path(__file__).resolve().parent / "governance_history.jsonl"

# Maximum number of policy change records kept in the history file
_POLICY_HISTORY_MAX = 500

# Thread-safe lock for file I/O
_policy_lock = threading.Lock()

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


class GovernancePolicy(BaseModel):
    version: str = "governance_v1"
    fuji_rules: FujiRules = Field(default_factory=FujiRules)
    risk_thresholds: RiskThresholds = Field(default_factory=RiskThresholds)
    auto_stop: AutoStop = Field(default_factory=AutoStop)
    log_retention: LogRetention = Field(default_factory=LogRetention)
    rollout_controls: RolloutControls = Field(default_factory=RolloutControls)
    approval_workflow: ApprovalWorkflowConfig = Field(default_factory=ApprovalWorkflowConfig)
    updated_at: str = ""
    updated_by: str = "system"


_NESTED_POLICY_MODELS = {
    "fuji_rules": FujiRules,
    "risk_thresholds": RiskThresholds,
    "auto_stop": AutoStop,
    "log_retention": LogRetention,
    "rollout_controls": RolloutControls,
    "approval_workflow": ApprovalWorkflowConfig,
}


# ---------- storage helpers ----------

def _policy_path() -> Path:
    return _DEFAULT_POLICY_PATH


def _load() -> Dict[str, Any]:
    """Load governance policy from JSON file."""
    path = _policy_path()
    with _policy_lock:
        if not path.exists():
            # Return defaults
            default = GovernancePolicy()
            return default.model_dump()
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Failed to load governance policy: %s", e)
            return GovernancePolicy().model_dump()


def _save(data: Dict[str, Any]) -> None:
    """Save governance policy to JSON file atomically (crash-safe)."""
    path = _policy_path()
    with _policy_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        if _HAS_ATOMIC_IO:
            _atomic_write_json(path, data, indent=2)
        else:
            # Fallback: write to temp file then rename for best-effort atomicity
            tmp = path.with_suffix(".tmp")
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                    f.write("\n")
                    f.flush()
                    import os as _os
                    _os.fsync(f.fileno())
                tmp.replace(path)
            except Exception:
                try:
                    tmp.unlink(missing_ok=True)
                except OSError:
                    pass
                raise


def _append_policy_history(previous: Dict[str, Any], updated: Dict[str, Any]) -> None:
    """Append a policy change record to the audit history JSONL (best-effort)."""
    record = {
        "changed_at": updated.get("updated_at", datetime.now(timezone.utc).isoformat()),
        "changed_by": updated.get("updated_by", "unknown"),
        "previous_version": previous.get("version"),
        "new_version": updated.get("version"),
        "previous_policy": previous,
        "new_policy": updated,
    }
    line = json.dumps(record, ensure_ascii=False)
    try:
        _POLICY_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _policy_lock:
            with open(_POLICY_HISTORY_PATH, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            _trim_policy_history()
    except Exception as e:
        logger.warning("Failed to append governance policy history: %s", e)


def _trim_policy_history() -> None:
    """Keep only the most recent _POLICY_HISTORY_MAX records in the history file."""
    try:
        if not _POLICY_HISTORY_PATH.exists():
            return
        lines = _POLICY_HISTORY_PATH.read_text(encoding="utf-8").splitlines(keepends=True)
        if len(lines) > _POLICY_HISTORY_MAX:
            trimmed = "".join(lines[-_POLICY_HISTORY_MAX:])
            tmp = _POLICY_HISTORY_PATH.with_suffix(".tmp")
            tmp.write_text(trimmed, encoding="utf-8")
            tmp.replace(_POLICY_HISTORY_PATH)
    except Exception as e:
        logger.warning("Failed to trim governance policy history: %s", e)


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
        except Exception as e:
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
    import re
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

    _save(result)

    # Record what changed for compliance audit trail
    _append_policy_history(previous, result)

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
    limit = max(1, min(limit, _POLICY_HISTORY_MAX))
    with _policy_lock:
        if not _POLICY_HISTORY_PATH.exists():
            return []
        try:
            lines = _POLICY_HISTORY_PATH.read_text(encoding="utf-8").splitlines()
        except Exception as e:
            logger.warning("Failed to read governance policy history: %s", e)
            return []
    records: List[Dict[str, Any]] = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
        if len(records) >= limit:
            break
    return records


def get_value_drift(telos_baseline: float = DEFAULT_TELOS_BASELINE) -> Dict[str, Any]:
    """Build ValueCore drift metrics relative to the configured Telos baseline."""
    baseline = max(0.0, min(1.0, float(telos_baseline)))
    history = _load_value_history()
    latest_ema = history[-1]["ema"] if history else baseline

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
