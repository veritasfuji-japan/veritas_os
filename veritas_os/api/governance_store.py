from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from fastapi import HTTPException

from veritas_os.core.atomic_io import atomic_write_json


_ALLOWED_AUDIT_INTENSITY = {"low", "standard", "high"}


@dataclass
class GovernancePolicyStore:
    """File-backed storage for governance policy with DB-friendly interface."""

    path: Path

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _default_policy(self) -> Dict[str, Any]:
        """Return the default governance policy payload."""
        return {
            "fuji_enabled": True,
            "risk_threshold": 0.6,
            "auto_stop_conditions": [
                "policy_violation_detected",
                "risk_threshold_exceeded",
            ],
            "log_retention_days": 90,
            "audit_intensity": "standard",
            "updated_at": _utc_now_iso(),
            "version": 1,
        }

    def get_policy(self) -> Dict[str, Any]:
        """Load governance policy from disk. Initialize defaults when file is absent."""
        if not self.path.exists():
            policy = self._default_policy()
            atomic_write_json(self.path, policy)
            return policy

        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=500, detail="governance policy file is corrupted") from exc

        if not isinstance(loaded, dict):
            raise HTTPException(status_code=500, detail="governance policy file must be object")

        normalized = self._validate_and_normalize(loaded)
        if normalized != loaded:
            atomic_write_json(self.path, normalized)
        return normalized

    def save_policy(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and persist governance policy payload."""
        normalized = self._validate_and_normalize(payload)
        current = self.get_policy()
        normalized["version"] = int(current.get("version", 0)) + 1
        normalized["updated_at"] = _utc_now_iso()
        atomic_write_json(self.path, normalized)
        return normalized

    def _validate_and_normalize(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Validate payload and return normalized policy object."""
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="policy payload must be object")

        fuji_enabled = payload.get("fuji_enabled")
        if not isinstance(fuji_enabled, bool):
            raise HTTPException(status_code=400, detail="fuji_enabled must be boolean")

        risk_raw = payload.get("risk_threshold")
        try:
            risk_threshold = float(risk_raw)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="risk_threshold must be number") from exc
        if not 0.0 <= risk_threshold <= 1.0:
            raise HTTPException(status_code=400, detail="risk_threshold must be between 0.0 and 1.0")

        conditions_raw = payload.get("auto_stop_conditions")
        if not isinstance(conditions_raw, list):
            raise HTTPException(status_code=400, detail="auto_stop_conditions must be array")
        auto_stop_conditions: List[str] = []
        for item in conditions_raw:
            if not isinstance(item, str) or not item.strip():
                raise HTTPException(
                    status_code=400,
                    detail="auto_stop_conditions must contain non-empty strings",
                )
            auto_stop_conditions.append(item.strip())

        retention_raw = payload.get("log_retention_days")
        if not isinstance(retention_raw, int):
            raise HTTPException(status_code=400, detail="log_retention_days must be integer")
        if not 1 <= retention_raw <= 3650:
            raise HTTPException(status_code=400, detail="log_retention_days must be between 1 and 3650")

        audit_intensity = payload.get("audit_intensity")
        if audit_intensity not in _ALLOWED_AUDIT_INTENSITY:
            raise HTTPException(
                status_code=400,
                detail="audit_intensity must be one of: low, standard, high",
            )

        return {
            "fuji_enabled": fuji_enabled,
            "risk_threshold": round(risk_threshold, 4),
            "auto_stop_conditions": auto_stop_conditions,
            "log_retention_days": retention_raw,
            "audit_intensity": audit_intensity,
            "updated_at": payload.get("updated_at") or _utc_now_iso(),
            "version": int(payload.get("version", 1)),
        }


def _utc_now_iso() -> str:
    """Return UTC ISO-8601 timestamp with Z suffix."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
