"""Local disabled-by-default runtime interface for controlled live V.I.K.I.

This module intentionally provides only an in-process fail-closed interface.
It does not implement endpoint, network, credential, replay cache, logging,
telemetry, or live V.I.K.I. integration behavior.
"""

from __future__ import annotations

from typing import Mapping

CONTROLLED_LIVE_VIKI_FEATURE_FLAG = "VERITAS_CONTROLLED_LIVE_VIKI_ENABLE"

_DISABLED_REASON_CODE = "CONTROLLED_LIVE_DISABLED"
_NOT_IMPLEMENTED_REASON_CODE = "CONTROLLED_LIVE_RUNTIME_NOT_IMPLEMENTED"
_REQUIRED_NEXT_ACTION = "REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE"
_DEFAULT_REQUEST_ID = "req_viki_disabled_001"
_DEFAULT_CORRELATION_ID = "corr_viki_veritas_disabled_001"
_DEFAULT_SCHEMA_VERSION = "v1alpha1"


def is_controlled_live_viki_enabled(value: str | None) -> bool:
    """Return True only when the feature flag value is exactly ``"true"``."""
    return value == "true"


def _extract_string_field(
    payload: Mapping[str, object] | None,
    field_name: str,
    default_value: str,
) -> str:
    if payload is None:
        return default_value
    raw_value = payload.get(field_name)
    if isinstance(raw_value, str) and raw_value.strip():
        return raw_value
    return default_value


def build_controlled_live_viki_disabled_decision(
    request_id: str = _DEFAULT_REQUEST_ID,
    correlation_id: str = _DEFAULT_CORRELATION_ID,
    schema_version: str = _DEFAULT_SCHEMA_VERSION,
) -> dict[str, object]:
    """Build the deterministic fail-closed decision for disabled state."""
    return {
        "veritas_continuation_decision": "PAUSE_FOR_HUMAN_REVIEW",
        "veritas_sandbox_commit_state": "SUSPENDED_NOT_COMMITTED",
        "final_commit_approved": False,
        "required_next_action": _REQUIRED_NEXT_ACTION,
        "veritas_reason_code": _DISABLED_REASON_CODE,
        "upstream_signal_source": "RSA",
        "request_id": request_id,
        "correlation_id": correlation_id,
        "schema_version": schema_version,
        "decision_source": "controlled_live_viki_disabled_runtime_interface",
    }


def receive_controlled_live_viki_payload(
    payload: Mapping[str, object] | None = None,
    *,
    feature_flag_value: str | None = None,
) -> dict[str, object]:
    """Receive a local payload and return deterministic fail-closed decisions."""
    request_id = _extract_string_field(payload, "request_id", _DEFAULT_REQUEST_ID)
    correlation_id = _extract_string_field(
        payload,
        "correlation_id",
        _DEFAULT_CORRELATION_ID,
    )
    schema_version = _extract_string_field(
        payload,
        "schema_version",
        _DEFAULT_SCHEMA_VERSION,
    )

    decision = build_controlled_live_viki_disabled_decision(
        request_id=request_id,
        correlation_id=correlation_id,
        schema_version=schema_version,
    )
    if not is_controlled_live_viki_enabled(feature_flag_value):
        return decision

    decision["veritas_reason_code"] = _NOT_IMPLEMENTED_REASON_CODE
    decision["decision_source"] = "controlled_live_viki_runtime_interface_not_implemented"
    return decision
