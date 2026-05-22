"""Local-only V.I.K.I. mock receiver for deterministic sandbox fixture ingestion.

This module is intentionally test-only guarded. It does not expose a
production endpoint, does not perform network calls, and does not integrate
with live V.I.K.I. middleware.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Final, Mapping

from veritas_os.governance.rsa_sandbox_receiver import (
    RSASandboxPayload,
    evaluate_rsa_sandbox_signal,
)

_TRUTHY_ENV_VALUES: Final[set[str]] = {"1", "true", "yes", "on"}
_REQUIRED_FIELDS: Final[tuple[str, ...]] = ("rsa_status", "trigger_source", "timestamp")
_OPTIONAL_TEXT_FIELDS: Final[tuple[str, ...]] = (
    "original_llm_intent",
    "rsa_action_taken",
)
_UNSPECIFIED_PLACEHOLDER: Final[str] = "[UNSPECIFIED]"
_MAX_CLOCK_SKEW_SECONDS: Final[int] = 300
UPSTREAM_MOCK_PAYLOAD_INVALID: Final[str] = "UPSTREAM_MOCK_PAYLOAD_INVALID"
UPSTREAM_MIDDLEWARE_OFFLINE: Final[str] = "UPSTREAM_MIDDLEWARE_OFFLINE"


def _require_local_mock_receiver_enabled() -> None:
    """Require explicit opt-in before local mock receiver functions can run."""
    enabled = os.getenv("VERITAS_LOCAL_VIKI_MOCK_RECEIVER_ENABLE", "").strip().lower()
    if enabled not in _TRUTHY_ENV_VALUES:
        raise RuntimeError(
            "Local V.I.K.I. mock receiver is disabled. "
            "Set VERITAS_LOCAL_VIKI_MOCK_RECEIVER_ENABLE=1 to enable test-only ingestion."
        )


def _receiver_timestamp(receiver_now: datetime | None) -> str:
    now = receiver_now if receiver_now is not None else datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("receiver_now must be timezone-aware")
    return now.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _failed_closed_invalid_payload(*, timestamp: str) -> dict[str, dict[str, str]]:
    return {
        "veritas_decision": {
            "continuation_decision": "PAUSE_FOR_HUMAN_REVIEW",
            "reason_code": UPSTREAM_MOCK_PAYLOAD_INVALID,
            "authority_evidence_status": "INSUFFICIENT",
            "sandbox_bind_boundary_state": "NOT_EVALUATED_PENDING_AUTHORITY_EVIDENCE",
            "sandbox_commit_state": "SUSPENDED_NOT_COMMITTED",
            "required_next_action": "REQUEST_VALID_SYNTHETIC_PAYLOAD_OR_HUMAN_REVIEW",
        },
        "audit_entry": {
            "upstream_signal_source": "RSA",
            "rsa_status": "INVALID_OR_UNAVAILABLE",
            "trigger_source": "LOCAL_VIKI_MOCK_RECEIVER",
            "original_llm_intent": "[REDACTED]",
            "rsa_action_taken": "[REDACTED]",
            "veritas_reason": (
                "local mock payload failed validation and VERITAS failed closed"
            ),
            "timestamp": timestamp,
            "veritas_continuation_decision": "PAUSE_FOR_HUMAN_REVIEW",
            "veritas_sandbox_commit_state": "SUSPENDED_NOT_COMMITTED",
        },
    }


def build_local_viki_mock_unreachable_decision(
    *, receiver_now: datetime | None = None
) -> dict[str, dict[str, str]]:
    """Return deterministic fail-closed output for unavailable local mock generator."""
    _require_local_mock_receiver_enabled()
    timestamp = _receiver_timestamp(receiver_now)
    return {
        "veritas_decision": {
            "continuation_decision": "PAUSE_FOR_HUMAN_REVIEW",
            "reason_code": UPSTREAM_MIDDLEWARE_OFFLINE,
            "authority_evidence_status": "INSUFFICIENT",
            "sandbox_bind_boundary_state": "NOT_EVALUATED_PENDING_AUTHORITY_EVIDENCE",
            "sandbox_commit_state": "SUSPENDED_NOT_COMMITTED",
            "required_next_action": (
                "REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE"
            ),
        },
        "audit_entry": {
            "upstream_signal_source": "RSA",
            "rsa_status": "INVALID_OR_UNAVAILABLE",
            "trigger_source": "LOCAL_VIKI_MOCK_RECEIVER",
            "original_llm_intent": "[REDACTED]",
            "rsa_action_taken": "[REDACTED]",
            "veritas_reason": (
                "local V.I.K.I. mock generator unavailable and VERITAS failed closed"
            ),
            "timestamp": timestamp,
            "veritas_continuation_decision": "PAUSE_FOR_HUMAN_REVIEW",
            "veritas_sandbox_commit_state": "SUSPENDED_NOT_COMMITTED",
        },
    }


def _parse_raw_payload(raw_payload: str | Mapping[str, object]) -> Mapping[str, object]:
    if isinstance(raw_payload, str):
        decoded = json.loads(raw_payload)
        if not isinstance(decoded, dict):
            raise ValueError("Local V.I.K.I. mock payload must decode to a JSON object")
        return decoded
    if isinstance(raw_payload, Mapping):
        return raw_payload
    raise ValueError("Local V.I.K.I. mock payload must be a JSON string or mapping")


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp must be a non-empty string")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware ISO-8601")
    return parsed


def ingest_local_viki_mock_payload(
    raw_payload: str | Mapping[str, object],
    *,
    receiver_now: datetime | None = None,
) -> dict[str, dict[str, str]]:
    """Ingest synthetic local V.I.K.I. mock payload and map via RSA sandbox evaluator."""
    _require_local_mock_receiver_enabled()
    now = receiver_now if receiver_now is not None else datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("receiver_now must be timezone-aware")

    try:
        parsed = _parse_raw_payload(raw_payload)
        for field in _REQUIRED_FIELDS:
            value = parsed.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field} must be a non-empty string")

        parsed_timestamp = _parse_timestamp(parsed["timestamp"])
        skew_seconds = abs((now - parsed_timestamp).total_seconds())
        if skew_seconds > _MAX_CLOCK_SKEW_SECONDS:
            raise ValueError("timestamp clock skew exceeded")

        optional_values: dict[str, str] = {}
        # Optional fields: if present, must be a non-empty string.
        # A present-but-invalid value (None, non-string, empty) is rejected
        # as UPSTREAM_MOCK_PAYLOAD_INVALID rather than silently redacted,
        # because an invalid value indicates a malformed payload, not a
        # legitimate field that should be suppressed.
        for field in _OPTIONAL_TEXT_FIELDS:
            value = parsed.get(field, _UNSPECIFIED_PLACEHOLDER)
            if value == _UNSPECIFIED_PLACEHOLDER:
                optional_values[field] = _UNSPECIFIED_PLACEHOLDER
                continue
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field} must be a non-empty string when provided")
            optional_values[field] = value

        payload = RSASandboxPayload(
            rsa_status=str(parsed["rsa_status"]),
            trigger_source=str(parsed["trigger_source"]),
            original_llm_intent=optional_values["original_llm_intent"],
            rsa_action_taken=optional_values["rsa_action_taken"],
            timestamp=str(parsed["timestamp"]),
        )
        return evaluate_rsa_sandbox_signal(payload)
    except (ValueError, TypeError, json.JSONDecodeError):
        return _failed_closed_invalid_payload(timestamp=_receiver_timestamp(now))
