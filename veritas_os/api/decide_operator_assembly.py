"""Operator-facing governance assembly helpers for /v1/decide."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from veritas_os.audit.wat_events import format_event_ts_utc

OPERATOR_VERBOSITY_MINIMAL = "minimal"
OPERATOR_VERBOSITY_EXPANDED = "expanded"
DEFAULT_EXPANDED_ROLES: set[str] = {"admin"}


def normalize_wat_drift_vector(raw_vector: Any) -> Dict[str, float]:
    """Normalize WAT drift vector keys for the public DecideResponse contract."""
    if not isinstance(raw_vector, dict):
        raw_vector = {}
    key_map = {
        "policy": "policy",
        "policy_drift": "policy",
        "signature": "signature",
        "signature_drift": "signature",
        "observable": "observable",
        "observable_drift": "observable",
        "temporal": "temporal",
        "temporal_drift": "temporal",
    }
    normalized: Dict[str, float] = {}
    for source_key, target_key in key_map.items():
        if target_key in normalized:
            continue
        value = raw_vector.get(source_key)
        if isinstance(value, (int, float)):
            normalized[target_key] = float(value)
    for key in ("policy", "signature", "observable", "temporal"):
        normalized.setdefault(key, 0.0)
    return normalized


def resolve_operator_verbosity(value: Any) -> str:
    """Resolve canonical operator verbosity with minimal-default safety."""
    verbosity = str(value or OPERATOR_VERBOSITY_MINIMAL)
    if verbosity not in {OPERATOR_VERBOSITY_MINIMAL, OPERATOR_VERBOSITY_EXPANDED}:
        return OPERATOR_VERBOSITY_MINIMAL
    return verbosity


def build_operator_surface(
    *,
    summary: Dict[str, Any],
    detail: Optional[Dict[str, Any]],
    operator_verbosity: str,
    role: str,
    expanded_roles: set[str],
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """Build minimal-default operator surface with role-gated expanded detail."""
    effective_verbosity = (
        OPERATOR_VERBOSITY_EXPANDED
        if operator_verbosity == OPERATOR_VERBOSITY_EXPANDED and role in expanded_roles
        else OPERATOR_VERBOSITY_MINIMAL
    )
    summary["operator_verbosity"] = effective_verbosity
    if effective_verbosity == OPERATOR_VERBOSITY_EXPANDED and isinstance(detail, dict):
        return summary, detail
    return summary, None


def attach_wat_contract_fields(payload: Dict[str, Any], wat_shadow: Dict[str, Any]) -> None:
    """Attach additive canonical WAT fields + operator summary/detail."""
    integrity_state = (
        "healthy" if str(wat_shadow.get("validation_status")) == "valid" else "warning"
    )
    if str(wat_shadow.get("admissibility_state")) in {"non_admissible", "blocked"}:
        integrity_state = "critical"
    payload["wat_integrity"] = {
        "integrity_state": integrity_state,
        "wat_id": wat_shadow.get("wat_id"),
        "psid_display": wat_shadow.get("psid_display"),
        "validation_status": wat_shadow.get("validation_status"),
        "admissibility_state": wat_shadow.get("admissibility_state"),
        "replay_status": wat_shadow.get("replay_status"),
        "revocation_status": wat_shadow.get("revocation_status"),
        "action_summary": "observer_only_validation",
    }
    payload["wat_drift_vector"] = normalize_wat_drift_vector(wat_shadow.get("drift_vector"))
    verifier_output_raw = wat_shadow.get("verifier_output_raw")
    expanded_verifier_output_raw = dict(verifier_output_raw) if isinstance(verifier_output_raw, dict) else {}
    if isinstance(wat_shadow.get("event_lane_details"), dict):
        expanded_verifier_output_raw["event_lane_details"] = dict(
            wat_shadow["event_lane_details"]
        )
    summary, detail = build_operator_surface(
        summary={
            "integrity_severity": integrity_state,
            "affected_lanes": list(wat_shadow.get("affected_lanes") or ["wat_shadow"]),
            "event_ts": format_event_ts_utc(
                wat_shadow.get("event_ts") or wat_shadow.get("ts")
            ),
            "correlation_id": str(
                wat_shadow.get("correlation_id")
                or payload.get("request_id")
                or wat_shadow.get("wat_id")
                or ""
            ),
            "warning_context": str(wat_shadow.get("warning_context") or ""),
            "warning_correlation_id": str(
                wat_shadow.get("warning_correlation_id")
                or wat_shadow.get("correlation_id")
                or payload.get("request_id")
                or wat_shadow.get("wat_id")
                or ""
            ),
        },
        detail={
            "drift_vector": normalize_wat_drift_vector(wat_shadow.get("drift_vector")),
            "verifier_output_raw": expanded_verifier_output_raw,
            "historical_drift_trend": wat_shadow.get("historical_drift_trend"),
        },
        operator_verbosity=resolve_operator_verbosity(wat_shadow.get("operator_verbosity")),
        role="admin",
        expanded_roles=DEFAULT_EXPANDED_ROLES,
    )
    payload["wat_operator_summary"] = summary
    if detail is not None:
        payload["wat_operator_detail"] = detail


def attach_bind_operator_surface(
    *,
    payload: Dict[str, Any],
    policy: Dict[str, Any],
    role: str,
) -> None:
    """Attach reusable minimal/expanded operator surface for bind governance."""
    bind_summary = payload.get("bind_summary")
    if not isinstance(bind_summary, dict):
        return
    operator_verbosity = resolve_operator_verbosity(policy.get("operator_verbosity"))
    bind_outcome = str(payload.get("bind_outcome") or bind_summary.get("outcome") or "")
    summary, detail = build_operator_surface(
        summary={
            "bind_state": bind_outcome.lower() or "unknown",
            "bind_outcome": bind_outcome,
            "bind_reason_code": str(
                payload.get("bind_reason_code") or bind_summary.get("reason_code") or ""
            ),
            "bind_receipt_id": str(
                payload.get("bind_receipt_id") or bind_summary.get("bind_receipt_id") or ""
            ),
            "execution_intent_id": str(
                payload.get("execution_intent_id")
                or bind_summary.get("execution_intent_id")
                or ""
            ),
        },
        detail={
            "authority_check_result": payload.get("authority_check_result"),
            "constraint_check_result": payload.get("constraint_check_result"),
            "drift_check_result": payload.get("drift_check_result"),
            "risk_check_result": payload.get("risk_check_result"),
        },
        operator_verbosity=operator_verbosity,
        role=role,
        expanded_roles=DEFAULT_EXPANDED_ROLES,
    )
    payload["bind_operator_summary"] = summary
    if detail is not None:
        payload["bind_operator_detail"] = detail
