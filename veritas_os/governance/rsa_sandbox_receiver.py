"""Sandbox-only RSA upstream signal receiver for AML/KYC interface contract.

This module is intentionally scoped to deterministic fixture behavior. It does
not implement production AML/KYC compliance workflows and must not be treated
as legal or regulatory certification.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Mapping


RSA_CONTINUATION_DECISIONS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "SAFE_PROCEED": "CONTINUE_TO_BIND_BOUNDARY",
        "DENSITY_THROTTLED": "CONTINUE_WITH_UPSTREAM_INTERVENTION_LOGGED",
        "ALGORITHMIC_HUMILITY_ENGAGED": "PAUSE_FOR_HUMAN_REVIEW",
        "DEFERRAL_ENGAGED": "BLOCK_FINAL_COMMIT",
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
    bind_boundary_result: str
    final_commit_outcome: str
    required_next_action: str


def _reason_code_for_status(rsa_status: str) -> str:
    if rsa_status == "ALGORITHMIC_HUMILITY_ENGAGED":
        return "UPSTREAM_INCOMPLETE_KYC_CONTEXT"
    if rsa_status == "SAFE_PROCEED":
        return "UPSTREAM_SAFE_PROCEED_SIGNAL"
    if rsa_status == "DENSITY_THROTTLED":
        return "UPSTREAM_INTERVENTION_DENSITY_THROTTLE"
    if rsa_status == "DEFERRAL_ENGAGED":
        return "UPSTREAM_CRITICAL_DEFERRAL_SIGNAL"
    return "UPSTREAM_RSA_SIGNAL_RECEIVED"


def _veritas_reason_for_status(rsa_status: str, reason_code: str) -> str:
    """Return status-specific sandbox audit narrative for RSA upstream signals."""
    if rsa_status == "SAFE_PROCEED":
        return (
            "The upstream RSA signal indicates the workflow may continue "
            "toward normal bind-boundary evaluation."
        )
    if rsa_status == "DENSITY_THROTTLED":
        return (
            "RSA modified the upstream output for cognitive density control; "
            "VERITAS records the intervention without treating it as a default "
            "hard block."
        )
    if rsa_status == "DEFERRAL_ENGAGED":
        return (
            "RSA reported a critical upstream deferral condition; VERITAS "
            "blocks final commit until human review or policy remediation occurs."
        )
    if reason_code == "UPSTREAM_INCOMPLETE_KYC_CONTEXT":
        return (
            "The workflow cannot continue toward final commit because required "
            "KYC context is incomplete and authority evidence is insufficient."
        )
    return (
        "VERITAS received an upstream RSA signal and logged the intervention "
        "for bind-boundary and commit evaluation."
    )


def _build_veritas_decision(rsa_status: str) -> VeritasSandboxDecision:
    """Translate a sandbox RSA status into a deterministic VERITAS decision."""
    continuation_decision = RSA_CONTINUATION_DECISIONS.get(
        rsa_status,
        "CONTINUE_WITH_UPSTREAM_INTERVENTION_LOGGED",
    )
    is_deferral = rsa_status == "DEFERRAL_ENGAGED"

    return VeritasSandboxDecision(
        continuation_decision=continuation_decision,
        reason_code=_reason_code_for_status(rsa_status),
        authority_evidence_status="INSUFFICIENT",
        bind_boundary_result="NOT_ADMISSIBLE_PENDING_EVIDENCE",
        final_commit_outcome=(
            "BLOCKED_NOT_COMMITTED" if is_deferral else "SUSPENDED_NOT_COMMITTED"
        ),
        required_next_action="REQUEST_ADDITIONAL_KYC_EVIDENCE_OR_HUMAN_REVIEW",
    )


def evaluate_rsa_sandbox_signal(payload: RSASandboxPayload) -> dict[str, dict[str, str]]:
    """Evaluate RSA upstream status as an external signal in sandbox mode.

    RSA remains external upstream context. VERITAS owns continuation
    admissibility, bind-boundary status, final commit outcome, and audit output.
    """
    decision = _build_veritas_decision(payload.rsa_status)
    veritas_reason = _veritas_reason_for_status(
        payload.rsa_status,
        decision.reason_code,
    )

    return {
        "veritas_decision": {
            "continuation_decision": decision.continuation_decision,
            "reason_code": decision.reason_code,
            "authority_evidence_status": decision.authority_evidence_status,
            "bind_boundary_result": decision.bind_boundary_result,
            "final_commit_outcome": decision.final_commit_outcome,
            "required_next_action": decision.required_next_action,
        },
        "audit_entry": {
            "upstream_signal_source": "RSA",
            "rsa_status": payload.rsa_status,
            "trigger_source": payload.trigger_source,
            "original_llm_intent": payload.original_llm_intent,
            "rsa_action_taken": payload.rsa_action_taken,
            "veritas_reason": veritas_reason,
            "timestamp": payload.timestamp,
            "veritas_continuation_decision": decision.continuation_decision,
            "veritas_final_commit_outcome": decision.final_commit_outcome,
        },
    }
