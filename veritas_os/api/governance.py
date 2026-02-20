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
from typing import Any, Dict

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------- storage path ----------
_DEFAULT_POLICY_PATH = Path(__file__).resolve().parent / "governance.json"

# Thread-safe lock for file I/O
_policy_lock = threading.Lock()


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
    current["updated_by"] = patch.get("updated_by", "api")

    # Validate through pydantic
    validated = GovernancePolicy.model_validate(current)
    result = validated.model_dump()

    _save(result)
    return result
