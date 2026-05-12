"""Sandbox-only RSA upstream signal receiver for AML/KYC interface contract.

This module is intentionally scoped to deterministic fixture behavior. It does
not implement production AML/KYC compliance workflows and must not be treated
as legal or regulatory certification.
"""

from __future__ import annotations

import os
from datetime import datetime
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Mapping


@dataclass(frozen=True)
class RSAStatusContract:
    """Immutable RSA status contract used by this sandbox fixture."""

    continuation_decision: str
    reason_code: str
    audit_narrative: str


_TIMESTAMP_ERROR_MESSAGE = (
    "RSASandboxPayload.timestamp must be timezone-aware ISO-8601 "
    "with trailing Z or explicit offset"
)


_RSA_STATUS_CONTRACTS: Final[Mapping[str, RSAStatusContract]] = MappingProxyType(
    {
        "SAFE_PROCEED": RSAStatusContract(
            continuation_decision="CONTINUE_TO_BIND_BOUNDARY",
            reason_code="UPSTREAM_SAFE_PROCEED_SIGNAL",
            audit_narrative=(
                "The upstream RSA signal indicates the workflow may continue "
                "toward normal bind-boundary evaluation."
            ),
        ),
        "DENSITY_THROTTLED": RSAStatusContract(
            continuation_decision="CONTINUE_WITH_UPSTREAM_INTERVENTION_LOGGED",
            reason_code="UPSTREAM_INTERVENTION_DENSITY_THROTTLE",
            audit_narrative=(
                "RSA modified the upstream output for cognitive density control; "
                "VERITAS records the intervention without treating it as a "
                "default hard block."
            ),
        ),
        "ALGORITHMIC_HUMILITY_ENGAGED": RSAStatusContract(
            continuation_decision="PAUSE_FOR_HUMAN_REVIEW",
            reason_code="UPSTREAM_INCOMPLETE_KYC_CONTEXT",
            audit_narrative=(
                "The workflow cannot continue toward final commit because "
                "required KYC context is incomplete and authority evidence is "
                "insufficient."
            ),
        ),
        "DEFERRAL_ENGAGED": RSAStatusContract(
            continuation_decision="BLOCK_FINAL_COMMIT",
            reason_code="UPSTREAM_CRITICAL_DEFERRAL_SIGNAL",
            audit_narrative=(
                "RSA reported a critical upstream deferral condition; VERITAS "
                "blocks final commit until human review or policy remediation "
                "occurs."
            ),
        ),
    }
)


@dataclass(frozen=True)
class RSASandboxPayload:
    """External RSA upstream payload consumed by VERITAS sandbox fixtures."""

    rsa_status: str
    trigger_source: str
    original_llm_intent: str
    rsa_action_taken: str
    timestamp: str


@dataclass(frozen=True)
class VeritasSandboxDecision:
    """VERITAS downstream decision fields derived from RSA upstream status."""

    continuation_decision: str
    reason_code: str
    authority_evidence_status: str
    sandbox_bind_boundary_state: str
    sandbox_commit_state: str
    required_next_action: str


def _build_veritas_decision(rsa_status: str) -> VeritasSandboxDecision:
    """Translate a sandbox RSA status into a deterministic VERITAS decision."""
    contract = _RSA_STATUS_CONTRACTS.get(rsa_status)
    if contract is None:
        supported = ", ".join(sorted(_RSA_STATUS_CONTRACTS))
        raise ValueError(
            f"Unknown RSA sandbox status: {rsa_status}. Supported: {supported}"
        )
    is_deferral = rsa_status == "DEFERRAL_ENGAGED"

    return VeritasSandboxDecision(
        continuation_decision=contract.continuation_decision,
        reason_code=contract.reason_code,
        authority_evidence_status="INSUFFICIENT",
        sandbox_bind_boundary_state="NOT_EVALUATED_PENDING_AUTHORITY_EVIDENCE",
        sandbox_commit_state=(
            "BLOCKED_NOT_COMMITTED" if is_deferral else "SUSPENDED_NOT_COMMITTED"
        ),
        required_next_action="REQUEST_ADDITIONAL_KYC_EVIDENCE_OR_HUMAN_REVIEW",
    )


def evaluate_rsa_sandbox_signal(
    payload: RSASandboxPayload,
    include_raw_upstream_fields: bool = False,
) -> dict[str, dict[str, str]]:
    """Evaluate RSA upstream status as an external signal in sandbox mode.

    RSA remains external upstream context. VERITAS owns continuation
    admissibility, sandbox bind-boundary state, sandbox commit state, and audit
    output.

    Security note:
    By default, original_llm_intent and rsa_action_taken are redacted.
    Set include_raw_upstream_fields=True only for sandbox tests that need raw
    fixture values. This masking is limited to those fields and is not
    generalized PII/secret detection. Do not persist raw values outside tests
    unless they pass through the TrustLog redaction/sanitization pipeline.
    """
    for field_name, value in (
        ("rsa_status", payload.rsa_status),
        ("trigger_source", payload.trigger_source),
        ("original_llm_intent", payload.original_llm_intent),
        ("rsa_action_taken", payload.rsa_action_taken),
        ("timestamp", payload.timestamp),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"RSASandboxPayload.{field_name} must be a non-empty string"
            )

    if include_raw_upstream_fields:
        veritas_env = os.getenv("VERITAS_ENV", "").strip().lower()
        if veritas_env in {"prod", "production", "stg", "staging"}:
            raise ValueError(
                "Raw upstream RSA sandbox fields are not allowed in operational environments"
            )
        if os.getenv("VERITAS_RSA_SANDBOX_ALLOW_RAW_UPSTREAM") != "1":
            raise ValueError(
                "Raw upstream RSA sandbox fields require "
                "VERITAS_RSA_SANDBOX_ALLOW_RAW_UPSTREAM=1"
            )

    normalized_timestamp = (
        payload.timestamp[:-1] + "+00:00"
        if payload.timestamp.endswith("Z")
        else payload.timestamp
    )
    try:
        parsed = datetime.fromisoformat(normalized_timestamp)
    except ValueError as exc:
        raise ValueError(_TIMESTAMP_ERROR_MESSAGE) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(_TIMESTAMP_ERROR_MESSAGE)

    contract = _RSA_STATUS_CONTRACTS[payload.rsa_status]
    decision = _build_veritas_decision(payload.rsa_status)
    original_llm_intent = (
        payload.original_llm_intent if include_raw_upstream_fields else "[REDACTED]"
    )
    rsa_action_taken = (
        payload.rsa_action_taken if include_raw_upstream_fields else "[REDACTED]"
    )

    return {
        "veritas_decision": {
            "continuation_decision": decision.continuation_decision,
            "reason_code": decision.reason_code,
            "authority_evidence_status": decision.authority_evidence_status,
            "sandbox_bind_boundary_state": decision.sandbox_bind_boundary_state,
            "sandbox_commit_state": decision.sandbox_commit_state,
            "required_next_action": decision.required_next_action,
        },
        "audit_entry": {
            "upstream_signal_source": "RSA",
            "rsa_status": payload.rsa_status,
            "trigger_source": payload.trigger_source,
            "original_llm_intent": original_llm_intent,
            "rsa_action_taken": rsa_action_taken,
            "veritas_reason": contract.audit_narrative,
            "timestamp": payload.timestamp,
            "veritas_continuation_decision": decision.continuation_decision,
            "veritas_sandbox_commit_state": decision.sandbox_commit_state,
        },
    }
