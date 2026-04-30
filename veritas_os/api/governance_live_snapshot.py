"""Mission Control governance live snapshot builder."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from veritas_os.policy.bind_artifacts import FinalOutcome, find_bind_receipts

_ALLOWED_PARTICIPATION_STATES = {
    "informative",
    "participatory",
    "decision_shaping",
    "unknown",
}
_ALLOWED_PRESERVATION_STATES = {
    "open",
    "degrading",
    "collapsed",
    "unknown",
}
_ALLOWED_INTERVENTION_VIABILITY = {
    "high",
    "medium",
    "minimal",
    "unknown",
}
_ALLOWED_BIND_OUTCOMES = {item.value for item in FinalOutcome} | {"UNKNOWN"}


def _utc_now_iso8601() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _normalize_state(value: Any, *, allowed: set[str]) -> str:
    if not isinstance(value, str):
        return "unknown"
    normalized = value.strip().lower()
    return normalized if normalized in allowed else "unknown"


def _normalize_bind_outcome(value: Any) -> str:
    if not isinstance(value, str):
        return "UNKNOWN"
    normalized = value.strip().upper()
    return normalized if normalized in _ALLOWED_BIND_OUTCOMES else "UNKNOWN"


def build_governance_live_snapshot() -> dict[str, Any]:
    """Build a lightweight governance snapshot for Mission Control.

    Returns a degraded unknown snapshot when recent governance artifacts are
    unavailable or cannot be loaded.
    """
    fallback = {
        "governance_layer_snapshot": {
            "participation_state": "unknown",
            "preservation_state": "unknown",
            "intervention_viability": "unknown",
            "bind_outcome": "UNKNOWN",
            "source": "degraded_no_recent_governance_artifact",
            "updated_at": _utc_now_iso8601(),
        },
    }
    try:
        receipts = find_bind_receipts()
    except Exception:
        return fallback

    if not receipts:
        return fallback

    latest = receipts[-1].to_dict()
    snapshot = {
        "participation_state": _normalize_state(
            latest.get("participation_state"),
            allowed=_ALLOWED_PARTICIPATION_STATES,
        ),
        "preservation_state": _normalize_state(
            latest.get("preservation_state"),
            allowed=_ALLOWED_PRESERVATION_STATES,
        ),
        "intervention_viability": _normalize_state(
            latest.get("intervention_viability"),
            allowed=_ALLOWED_INTERVENTION_VIABILITY,
        ),
        "bind_outcome": _normalize_bind_outcome(latest.get("final_outcome")),
        "source": "backend_live_snapshot",
        "updated_at": latest.get("bind_ts") if isinstance(latest.get("bind_ts"), str) else _utc_now_iso8601(),
    }
    return {"governance_layer_snapshot": snapshot}
