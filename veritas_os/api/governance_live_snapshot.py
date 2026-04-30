"""Mission Control governance live snapshot builder."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from veritas_os.api.bind_summary import (
    build_bind_summary_from_receipt,
    enrich_bind_receipt_payload,
    resolve_bind_reason_code,
)
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


def _build_degraded_snapshot(source: str) -> dict[str, Any]:
    """Return a render-safe degraded snapshot with explicit failure source."""
    return {
        "governance_layer_snapshot": {
            "participation_state": "unknown",
            "preservation_state": "unknown",
            "intervention_viability": "unknown",
            "bind_outcome": "UNKNOWN",
            "source": source,
            "updated_at": _utc_now_iso8601(),
        },
    }


def _select_latest_receipt(receipts: list[Any]) -> Any | None:
    """Select the latest receipt when artifacts exist."""
    if not receipts:
        return None
    return receipts[-1]


def _safe_receipt_payload(receipt: Any) -> dict[str, Any] | None:
    """Safely materialize a receipt payload as a dictionary."""
    try:
        payload = receipt.to_dict()
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _build_enriched_snapshot_from_receipt_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Build enriched live snapshot from a valid receipt payload."""
    try:
        enriched_receipt = enrich_bind_receipt_payload(payload)
        bind_summary = build_bind_summary_from_receipt(enriched_receipt)
        bind_reason_code = resolve_bind_reason_code(enriched_receipt)
    except Exception:
        return None

    snapshot = {
        "participation_state": _normalize_state(
            enriched_receipt.get("participation_state"),
            allowed=_ALLOWED_PARTICIPATION_STATES,
        ),
        "preservation_state": _normalize_state(
            enriched_receipt.get("preservation_state"),
            allowed=_ALLOWED_PRESERVATION_STATES,
        ),
        "intervention_viability": _normalize_state(
            enriched_receipt.get("intervention_viability"),
            allowed=_ALLOWED_INTERVENTION_VIABILITY,
        ),
        "bind_outcome": _normalize_bind_outcome(enriched_receipt.get("final_outcome")),
        "source": "backend_live_snapshot",
        "updated_at": (
            enriched_receipt.get("bind_ts")
            if isinstance(enriched_receipt.get("bind_ts"), str)
            else _utc_now_iso8601()
        ),
        "bind_receipt_id": enriched_receipt.get("bind_receipt_id"),
        "execution_intent_id": enriched_receipt.get("execution_intent_id"),
        "decision_id": enriched_receipt.get("decision_id"),
        "bind_reason_code": bind_reason_code,
        "bind_failure_reason": bind_summary.get("bind_failure_reason"),
        "failure_category": enriched_receipt.get("failure_category"),
        "rollback_status": enriched_receipt.get("rollback_status"),
        "retry_safety": enriched_receipt.get("retry_safety"),
        "target_path": enriched_receipt.get("target_path"),
        "target_type": enriched_receipt.get("target_type"),
        "target_path_type": enriched_receipt.get("target_path_type"),
        "target_label": enriched_receipt.get("target_label"),
        "operator_surface": enriched_receipt.get("operator_surface"),
        "relevant_ui_href": enriched_receipt.get("relevant_ui_href"),
        "authority_check_result": enriched_receipt.get("authority_check_result"),
        "constraint_check_result": enriched_receipt.get("constraint_check_result"),
        "drift_check_result": enriched_receipt.get("drift_check_result"),
        "risk_check_result": enriched_receipt.get("risk_check_result"),
        "bind_summary": bind_summary,
    }
    return {"governance_layer_snapshot": snapshot}


def build_governance_live_snapshot() -> dict[str, Any]:
    """Build a lightweight governance snapshot for Mission Control.

    Returns a degraded unknown snapshot when recent governance artifacts are
    unavailable, malformed, or cannot be enriched safely.
    """
    try:
        receipts = find_bind_receipts()
    except Exception:
        return _build_degraded_snapshot("degraded_artifact_retrieval_failed")

    latest_receipt = _select_latest_receipt(receipts)
    if latest_receipt is None:
        return _build_degraded_snapshot("degraded_no_recent_governance_artifact")

    payload = _safe_receipt_payload(latest_receipt)
    if payload is None:
        return _build_degraded_snapshot("degraded_invalid_latest_bind_receipt")

    snapshot = _build_enriched_snapshot_from_receipt_payload(payload)
    if snapshot is None:
        return _build_degraded_snapshot("degraded_bind_summary_enrichment_failed")

    return snapshot
