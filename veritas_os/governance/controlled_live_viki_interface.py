"""Local disabled-by-default runtime interface for controlled live V.I.K.I.

This module intentionally provides only an in-process fail-closed interface.
It does not implement endpoint, network, credential, replay cache, logging,
telemetry, or live V.I.K.I. integration behavior.
"""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping

from veritas_os.governance.controlled_live_viki_rsa_handoff import (
    build_controlled_live_viki_rsa_handoff_decision,
)
from veritas_os.governance.controlled_live_viki_schema_adapter import (
    ADAPTER_VALID,
    build_controlled_live_viki_schema_fail_closed_decision,
    classify_controlled_live_viki_schema_input,
    controlled_live_viki_reason_code_for_classification,
)

CONTROLLED_LIVE_VIKI_FEATURE_FLAG = "VERITAS_CONTROLLED_LIVE_VIKI_ENABLE"

_DISABLED_REASON_CODE = "CONTROLLED_LIVE_DISABLED"
_REQUIRED_NEXT_ACTION = "REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE"
_DEFAULT_REQUEST_ID = "req_viki_disabled_001"
_DEFAULT_CORRELATION_ID = "corr_viki_veritas_disabled_001"
_DEFAULT_SCHEMA_VERSION = "v1alpha1"


def is_controlled_live_viki_enabled(value: str | None) -> bool:
    """Return True only when the feature flag value is exactly ``"true"``."""
    return value == "true"


def _extract_string_field(
    payload: object,
    field_name: str,
    default_value: str,
) -> str:
    if not isinstance(payload, Mapping):
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
    payload: object = None,
    *,
    feature_flag_value: str | None = None,
    seen_request_ids: MutableMapping[str, str] | None = None,
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

    classification = classify_controlled_live_viki_schema_input(
        payload,
        seen_request_ids=seen_request_ids,
    )
    if classification != ADAPTER_VALID:
        reason_code = controlled_live_viki_reason_code_for_classification(classification)
        if reason_code is None:
            reason_code = "CONTROLLED_LIVE_INVALID_JSON_OBJECT"
        return build_controlled_live_viki_schema_fail_closed_decision(
            reason_code,
            request_id=request_id,
            correlation_id=correlation_id,
            schema_version=schema_version,
        )

    if not isinstance(payload, Mapping):
        return build_controlled_live_viki_schema_fail_closed_decision(
            "CONTROLLED_LIVE_INVALID_JSON_OBJECT",
            request_id=request_id,
            correlation_id=correlation_id,
            schema_version=schema_version,
        )

    return build_controlled_live_viki_rsa_handoff_decision(payload)
