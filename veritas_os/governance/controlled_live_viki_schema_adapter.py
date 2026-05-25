"""Local pure schema adapter for controlled live V.I.K.I. payload validation.

This module is intentionally offline and deterministic. It does not add network,
endpoint, credentials, replay cache infrastructure, logging, telemetry,
observability, or live V.I.K.I. integration behavior.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, MutableMapping
from datetime import datetime, timedelta

CONTROLLED_LIVE_VIKI_SCHEMA_VERSION = "v1alpha1"

ADAPTER_VALID = "ADAPTER_VALID"
ADAPTER_UNSUPPORTED_SCHEMA_VERSION = "ADAPTER_UNSUPPORTED_SCHEMA_VERSION"
ADAPTER_UNKNOWN_RSA_STATUS = "ADAPTER_UNKNOWN_RSA_STATUS"
ADAPTER_MISSING_REQUIRED_FIELD = "ADAPTER_MISSING_REQUIRED_FIELD"
ADAPTER_INVALID_TIMESTAMP = "ADAPTER_INVALID_TIMESTAMP"
ADAPTER_FORBIDDEN_FIELD_PRESENT = "ADAPTER_FORBIDDEN_FIELD_PRESENT"
ADAPTER_SECRET_LIKE_VALUE_PRESENT = "ADAPTER_SECRET_LIKE_VALUE_PRESENT"
ADAPTER_REGULATED_DATA_PRESENT = "ADAPTER_REGULATED_DATA_PRESENT"
ADAPTER_REPLAY_DUPLICATE_REQUEST_ID = "ADAPTER_REPLAY_DUPLICATE_REQUEST_ID"
ADAPTER_INVALID_JSON_OBJECT = "ADAPTER_INVALID_JSON_OBJECT"

ACCEPTED_RSA_STATUSES = {
    "SAFE_PROCEED",
    "DENSITY_THROTTLED",
    "ALGORITHMIC_HUMILITY_ENGAGED",
    "DEFERRAL_ENGAGED",
}
REQUIRED_FIELDS = {
    "schema_version",
    "rsa_status",
    "trigger_source",
    "timestamp",
    "request_id",
    "correlation_id",
    "payload_issued_at",
}
FORBIDDEN_REASONING_FIELDS = {
    "chain_of_thought",
    "hidden_model_state",
    "raw_llm_reasoning",
    "raw_viki_reasoning",
    "raw_llm_text",
}
SECRET_LIKE_FIELDS = {
    "secrets",
    "credentials",
    "api_key",
    "access_token",
    "refresh_token",
    "private_key",
    "webhook_secret",
    "raw_authorization_header",
    "authorization",
    "bearer_token",
}
REGULATED_DATA_FIELDS = {
    "raw_kyc_record",
    "customer_pii",
    "unredacted_regulated_data",
}
RAW_BODY_FIELDS = {
    "raw_payload_body",
    "raw_request_body",
    "raw_response_body",
    "raw_stack_trace_with_secrets",
}

CLASS_TO_REASON_CODE = {
    ADAPTER_UNSUPPORTED_SCHEMA_VERSION: "CONTROLLED_LIVE_UNSUPPORTED_SCHEMA_VERSION",
    ADAPTER_UNKNOWN_RSA_STATUS: "CONTROLLED_LIVE_UNKNOWN_RSA_STATUS",
    ADAPTER_MISSING_REQUIRED_FIELD: "CONTROLLED_LIVE_MISSING_REQUIRED_FIELD",
    ADAPTER_INVALID_TIMESTAMP: "CONTROLLED_LIVE_INVALID_TIMESTAMP",
    ADAPTER_FORBIDDEN_FIELD_PRESENT: "CONTROLLED_LIVE_FORBIDDEN_FIELD_PRESENT",
    ADAPTER_SECRET_LIKE_VALUE_PRESENT: "CONTROLLED_LIVE_SECRET_LIKE_VALUE_PRESENT",
    ADAPTER_REGULATED_DATA_PRESENT: "CONTROLLED_LIVE_REGULATED_DATA_PRESENT",
    ADAPTER_REPLAY_DUPLICATE_REQUEST_ID: "CONTROLLED_LIVE_REPLAY_DUPLICATE_REQUEST_ID",
    ADAPTER_INVALID_JSON_OBJECT: "CONTROLLED_LIVE_INVALID_JSON_OBJECT",
}


def is_timezone_aware_timestamp(value: str) -> bool:
    """Return ``True`` when ``value`` parses as a timezone-aware ISO timestamp."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def has_future_payload_issued_at_skew(
    timestamp_value: str,
    payload_issued_at_value: str,
) -> bool:
    """Return True when payload_issued_at is more than 300s after timestamp."""
    timestamp = datetime.fromisoformat(timestamp_value.replace("Z", "+00:00"))
    payload_issued_at = datetime.fromisoformat(payload_issued_at_value.replace("Z", "+00:00"))
    return payload_issued_at - timestamp > timedelta(seconds=300)


def contains_any_key(payload: Mapping[str, object], keys: Collection[str]) -> bool:
    """Return ``True`` when any key from ``keys`` exists in ``payload``."""
    return any(key in payload for key in keys)


def classify_controlled_live_viki_schema_input(
    payload: object,
    *,
    seen_request_ids: MutableMapping[str, str] | None = None,
) -> str:
    """Classify payload using deterministic, offline, fail-closed adapter rules."""
    if not isinstance(payload, dict):
        return ADAPTER_INVALID_JSON_OBJECT

    if payload.get("schema_version") != CONTROLLED_LIVE_VIKI_SCHEMA_VERSION:
        return ADAPTER_UNSUPPORTED_SCHEMA_VERSION

    if any(field not in payload for field in REQUIRED_FIELDS):
        return ADAPTER_MISSING_REQUIRED_FIELD

    if payload["rsa_status"] not in ACCEPTED_RSA_STATUSES:
        return ADAPTER_UNKNOWN_RSA_STATUS

    if not is_timezone_aware_timestamp(payload["timestamp"]):
        return ADAPTER_INVALID_TIMESTAMP
    if not is_timezone_aware_timestamp(payload["payload_issued_at"]):
        return ADAPTER_INVALID_TIMESTAMP

    if has_future_payload_issued_at_skew(payload["timestamp"], payload["payload_issued_at"]):
        return ADAPTER_INVALID_TIMESTAMP

    if contains_any_key(payload, REGULATED_DATA_FIELDS):
        return ADAPTER_REGULATED_DATA_PRESENT

    if contains_any_key(payload, SECRET_LIKE_FIELDS):
        return ADAPTER_SECRET_LIKE_VALUE_PRESENT

    if contains_any_key(payload, FORBIDDEN_REASONING_FIELDS):
        return ADAPTER_FORBIDDEN_FIELD_PRESENT

    if seen_request_ids is not None:
        request_id = payload["request_id"]
        if request_id in seen_request_ids:
            return ADAPTER_REPLAY_DUPLICATE_REQUEST_ID
        seen_request_ids[request_id] = payload["correlation_id"]

    return ADAPTER_VALID


def controlled_live_viki_reason_code_for_classification(classification: str) -> str | None:
    """Map adapter classification to fail-closed reason code when available."""
    return CLASS_TO_REASON_CODE.get(classification)


def build_controlled_live_viki_schema_fail_closed_decision(
    reason_code: str,
    *,
    request_id: str = "req_viki_schema_adapter_001",
    correlation_id: str = "corr_viki_veritas_schema_adapter_001",
    schema_version: str = CONTROLLED_LIVE_VIKI_SCHEMA_VERSION,
) -> dict[str, object]:
    """Build deterministic fail-closed decision shape for adapter rejections."""
    return {
        "veritas_continuation_decision": "PAUSE_FOR_HUMAN_REVIEW",
        "veritas_sandbox_commit_state": "SUSPENDED_NOT_COMMITTED",
        "final_commit_approved": False,
        "required_next_action": "REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE",
        "upstream_signal_source": "RSA",
        "decision_source": "controlled_live_viki_schema_adapter",
        "reason_code": reason_code,
        "request_id": request_id,
        "correlation_id": correlation_id,
        "schema_version": schema_version,
    }
