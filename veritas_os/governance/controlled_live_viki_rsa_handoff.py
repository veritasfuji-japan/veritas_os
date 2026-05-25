"""Local offline helper for schema-valid controlled live V.I.K.I. RSA handoff.

This helper is deterministic and fail-closed. It does not open endpoints,
perform network I/O, integrate live V.I.K.I., use credentials, implement replay
cache, logging, telemetry, observability runtime, or persistence.
"""

from __future__ import annotations

from collections.abc import Mapping

CONTROLLED_LIVE_RSA_HANDOFF_SAFE_PROCEED_NOT_FINAL = (
    "CONTROLLED_LIVE_RSA_HANDOFF_SAFE_PROCEED_NOT_FINAL"
)
CONTROLLED_LIVE_RSA_HANDOFF_DENSITY_THROTTLED = (
    "CONTROLLED_LIVE_RSA_HANDOFF_DENSITY_THROTTLED"
)
CONTROLLED_LIVE_RSA_HANDOFF_ALGORITHMIC_HUMILITY_ENGAGED = (
    "CONTROLLED_LIVE_RSA_HANDOFF_ALGORITHMIC_HUMILITY_ENGAGED"
)
CONTROLLED_LIVE_RSA_HANDOFF_DEFERRAL_ENGAGED = (
    "CONTROLLED_LIVE_RSA_HANDOFF_DEFERRAL_ENGAGED"
)
CONTROLLED_LIVE_RSA_HANDOFF_UNSUPPORTED_STATUS = (
    "CONTROLLED_LIVE_RSA_HANDOFF_UNSUPPORTED_STATUS"
)
CONTROLLED_LIVE_RSA_HANDOFF_MISSING_REQUIRED_FIELD = (
    "CONTROLLED_LIVE_RSA_HANDOFF_MISSING_REQUIRED_FIELD"
)

RSA_HANDOFF_STATUS_MAP = {
    "SAFE_PROCEED": CONTROLLED_LIVE_RSA_HANDOFF_SAFE_PROCEED_NOT_FINAL,
    "DENSITY_THROTTLED": CONTROLLED_LIVE_RSA_HANDOFF_DENSITY_THROTTLED,
    "ALGORITHMIC_HUMILITY_ENGAGED": (
        CONTROLLED_LIVE_RSA_HANDOFF_ALGORITHMIC_HUMILITY_ENGAGED
    ),
    "DEFERRAL_ENGAGED": CONTROLLED_LIVE_RSA_HANDOFF_DEFERRAL_ENGAGED,
}

_REQUIRED_FIELDS = ("request_id", "correlation_id", "schema_version", "rsa_status")


def is_controlled_live_viki_rsa_handoff_supported_status(rsa_status: object) -> bool:
    """Return True when rsa_status is one of supported RSA-compatible statuses."""
    return isinstance(rsa_status, str) and rsa_status in RSA_HANDOFF_STATUS_MAP


def controlled_live_viki_rsa_handoff_reason_code_for_status(rsa_status: str) -> str | None:
    """Return mapped handoff reason-code for a supported rsa_status."""
    return RSA_HANDOFF_STATUS_MAP.get(rsa_status)


def _extract_string_field(payload: Mapping[str, object], field_name: str, default: str) -> str:
    value = payload.get(field_name)
    if isinstance(value, str) and value.strip():
        return value
    return default


def _base_fail_closed_decision(*, reason_code: str, request_id: str, correlation_id: str, schema_version: str, rsa_status: str) -> dict[str, object]:
    return {
        "reason_code": reason_code,
        "veritas_continuation_decision": "PAUSE_FOR_HUMAN_REVIEW",
        "veritas_sandbox_commit_state": "SUSPENDED_NOT_COMMITTED",
        "final_commit_approved": False,
        "required_next_action": "REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE",
        "upstream_signal_source": "RSA",
        "decision_source": "controlled_live_viki_rsa_handoff",
        "request_id": request_id,
        "correlation_id": correlation_id,
        "schema_version": schema_version,
        "rsa_status": rsa_status,
    }


def build_controlled_live_viki_rsa_handoff_decision(
    payload: Mapping[str, object],
) -> dict[str, object]:
    """Build a deterministic RSA-compatible fail-closed handoff decision."""
    if not isinstance(payload, Mapping):
        payload = {}

    request_id = _extract_string_field(payload, "request_id", "req_viki_rsa_handoff_001")
    correlation_id = _extract_string_field(
        payload,
        "correlation_id",
        "corr_viki_veritas_rsa_handoff_001",
    )
    schema_version = _extract_string_field(payload, "schema_version", "v1alpha1")

    if any(not isinstance(payload.get(field), str) or not payload.get(field, "").strip() for field in _REQUIRED_FIELDS):
        return _base_fail_closed_decision(
            reason_code=CONTROLLED_LIVE_RSA_HANDOFF_MISSING_REQUIRED_FIELD,
            request_id=request_id,
            correlation_id=correlation_id,
            schema_version=schema_version,
            rsa_status=_extract_string_field(payload, "rsa_status", "UNKNOWN"),
        )

    rsa_status = _extract_string_field(payload, "rsa_status", "UNKNOWN")
    reason_code = controlled_live_viki_rsa_handoff_reason_code_for_status(rsa_status)
    if reason_code is None:
        return _base_fail_closed_decision(
            reason_code=CONTROLLED_LIVE_RSA_HANDOFF_UNSUPPORTED_STATUS,
            request_id=request_id,
            correlation_id=correlation_id,
            schema_version=schema_version,
            rsa_status=rsa_status,
        )

    return _base_fail_closed_decision(
        reason_code=reason_code,
        request_id=request_id,
        correlation_id=correlation_id,
        schema_version=schema_version,
        rsa_status=rsa_status,
    )
