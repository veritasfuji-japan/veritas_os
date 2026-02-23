# veritas_os/api/governance.py
"""
Governance Policy API — GET / PUT /v1/governance/policy

Storage: file-based (governance.json) with an interface that can be
swapped to a DB backend later by replacing `_load` / `_save`.
"""
from __future__ import annotations

import json
import logging
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------- storage path ----------
_DEFAULT_POLICY_PATH = Path(__file__).resolve().parent / "governance.json"

# Thread-safe lock for file I/O
_policy_lock = threading.Lock()

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
    audit_level: str = "full"
    include_fields: list[str] = Field(
        default_factory=lambda: ["status", "risk", "reasons", "violations", "categories"]
    )
    redact_before_log: bool = True
    max_log_size: int = Field(default=10000, ge=100, le=1_000_000)


class GovernancePolicy(BaseModel):
    version: str = "governance_v1"
    fuji_rules: FujiRules = Field(default_factory=FujiRules)
    risk_thresholds: RiskThresholds = Field(default_factory=RiskThresholds)
    auto_stop: AutoStop = Field(default_factory=AutoStop)
    log_retention: LogRetention = Field(default_factory=LogRetention)
    updated_at: str = ""
    updated_by: str = "system"


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
    """Save governance policy to JSON file."""
    path = _policy_path()
    with _policy_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")


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


def update_policy(patch: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge *patch* into the current governance policy and persist.

    Returns the full updated policy.
    """
    current = _load()

    # Deep-merge: only update keys that are present in patch
    for key in ("fuji_rules", "risk_thresholds", "auto_stop", "log_retention"):
        if key in patch and isinstance(patch[key], dict):
            if key not in current or not isinstance(current[key], dict):
                current[key] = {}
            current[key].update(patch[key])

    # Scalar overrides
    for key in ("version",):
        if key in patch:
            current[key] = patch[key]

    # Metadata
    current["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    # ★ セキュリティ修正: updated_by フィールドのサイズ制限（DoS対策）
    current["updated_by"] = str(patch.get("updated_by", "api"))[:200]

    # Validate through pydantic
    validated = GovernancePolicy.model_validate(current)
    result = validated.model_dump()

    _save(result)
    return result


def get_value_drift(telos_baseline: float = DEFAULT_TELOS_BASELINE) -> Dict[str, Any]:
    """Build ValueCore drift metrics relative to the configured Telos baseline."""
    baseline = max(0.0, min(1.0, float(telos_baseline)))
    history = _load_value_history()
    latest_ema = history[-1]["ema"] if history else baseline

    if baseline <= 0:
        drift_percent = 0.0
    else:
        drift_percent = ((latest_ema - baseline) / baseline) * 100.0

    return {
        "baseline": baseline,
        "latest_ema": latest_ema,
        "drift_percent": round(drift_percent, 2),
        "history": history,
        "status": "ok" if history else "no_data",
    }
