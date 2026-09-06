"""Bind caller-supplied runtime risk review to verified requirement rechecks.

This is a pre-authorization evidence boundary, not a risk sensor or issuer.
External source/policy, metadata, clocks, and expected review remain mandatory.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from veritas_os.governance.action_contracts import ActionClassContract
from veritas_os.policy.human_approval_requirement_resolution import _json, _timestamp
from veritas_os.policy.promotion_requirement_final_rechecks import (
    ABSENT_FIELDS,
    verify_promotion_requirement_final_recheck_packet as verify_rechecks,
)
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_runtime_risk_review import (
    PASS_OUTCOME,
    RuntimeRiskReviewResult,
    _evaluate_runtime_risk_inputs,
    _validate_times,
)
from veritas_os.security.hash import sha256_of_canonical_json


class PromotionRequirementRuntimeRiskError(ValueError):
    """Missing, mismatched, rejected, or expired risk evidence."""


class RequirementRuntimeRiskDecision(BaseModel):
    """Closed caller evidence bound to one exact verified recheck result."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    review_id: str = Field(min_length=1)
    reviewer_id: str = Field(min_length=1)
    risk_reason: str = Field(min_length=1)
    reviewed_at: str
    valid_until: str
    source_final_recheck_id: str
    source_final_recheck_hash: str
    bind_context_hash: str
    action_contract_digest: str
    expected_state_fingerprint: str | None
    observed_state_fingerprint: str | None
    runtime_risk_signal: bool | None
    runtime_risk_evidence_refs: list[str] = Field(min_length=1)
    acknowledged_caller_evidence_only: Literal[True]
    acknowledged_no_authorization: Literal[True]
    acknowledged_bind_time_risk_recheck_required: Literal[True]


class PromotionRequirementRuntimeRiskPacket(BaseModel):
    """Compact evidence requiring the independent complete source to verify."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    format_version: Literal["promotion-requirement-runtime-risk/v1"]
    packet_id: str
    packet_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    recorded_at: str
    source_final_recheck_id: str
    source_final_recheck_hash: str
    bind_context_hash: str
    action_contract_digest: str
    execution_intent_id: str
    execution_intent_hash: str
    required_human_approval: bool
    risk_decision: RequirementRuntimeRiskDecision
    risk_result: RuntimeRiskReviewResult
    future_authorization_requirements: list[str]
    future_invocation_requirements: list[str]
    fail_closed: bool
    ready_for_remaining_authorization_requirements: bool
    bind_time_runtime_risk_recheck_required: Literal[True]
    human_approval_created: Literal[False]
    human_approval_proven: Literal[False]
    authority_evidence_proven: Literal[False]
    execution_authority_created: Literal[False]
    bind_authorization_created: Literal[False]
    bind_invoked: Literal[False]
    bind_receipt_created: Literal[False]
    credential_material_accessed: Literal[False]
    network_used: Literal[False]
    external_effect_occurred: Literal[False]
    ready_for_real_bind: Literal[False]


def _seal(raw: dict[str, Any]) -> dict[str, Any]:
    value = {k: v for k, v in raw.items() if k not in {"packet_id", "packet_hash"}}
    digest = sha256_of_canonical_json(
        {
            "domain": "veritas.promotion-requirement-runtime-risk/v1",
            "value": value,
        }
    )
    return {**value, "packet_hash": digest, "packet_id": f"prrr:v1:sha256:{digest}"}


def _assemble(
    source: Any, decision: Any, recorded_at: datetime
) -> PromotionRequirementRuntimeRiskPacket:
    decision = RequirementRuntimeRiskDecision.model_validate(_json(decision))
    refs = decision.runtime_risk_evidence_refs
    if any(not ref.strip() for ref in refs) or len(set(refs)) != len(refs):
        raise PromotionRequirementRuntimeRiskError("PRRR_EVIDENCE_REFS_INVALID")
    expected = {
        "source_final_recheck_id": source.packet_id,
        "source_final_recheck_hash": source.packet_hash,
        "bind_context_hash": source.bind_context_hash,
        "action_contract_digest": source.exact_bind_context.action_contract_digest,
        "expected_state_fingerprint": source.execution_intent.get(
            "expected_state_fingerprint"
        ),
    }
    if any(getattr(decision, key) != value for key, value in expected.items()):
        raise PromotionRequirementRuntimeRiskError("PRRR_DECISION_BINDING_MISMATCH")
    reviewed, valid_until, recorded = _validate_times(
        source.rechecked_at, decision, recorded_at
    )
    if source.future_authorization_requirements[0:1] != ["runtime_risk_review"]:
        raise PromotionRequirementRuntimeRiskError("PRRR_REQUIREMENT_ORDER")
    result = _evaluate_runtime_risk_inputs(
        source.execution_intent,
        expected=decision.expected_state_fingerprint,
        observed=decision.observed_state_fingerprint,
        signal=decision.runtime_risk_signal,
        reviewed_at=reviewed,
        valid_until=valid_until,
    )
    accepted = result["outcome"] == PASS_OUTCOME
    decision = decision.model_copy(
        update={
            "reviewed_at": reviewed.isoformat(),
            "valid_until": valid_until.isoformat(),
        }
    )
    raw = {
        "format_version": "promotion-requirement-runtime-risk/v1",
        "recorded_at": recorded.isoformat(),
        **{k: v for k, v in expected.items() if k != "expected_state_fingerprint"},
        "execution_intent_id": source.exact_bind_context.execution_intent_id,
        "execution_intent_hash": source.exact_bind_context.execution_intent_hash,
        "required_human_approval": source.required_human_approval,
        "risk_decision": decision.model_dump(mode="json"),
        "risk_result": result,
        "future_authorization_requirements": source.future_authorization_requirements[
            1:
        ]
        if accepted
        else source.future_authorization_requirements,
        "future_invocation_requirements": source.future_invocation_requirements,
        "fail_closed": not accepted,
        "ready_for_remaining_authorization_requirements": accepted,
        "bind_time_runtime_risk_recheck_required": True,
        **{name: getattr(source, name) for name in ABSENT_FIELDS},
    }
    return PromotionRequirementRuntimeRiskPacket.model_validate(_seal(raw))


def build_promotion_requirement_runtime_risk_packet(
    final_recheck: Any,
    risk_decision: Any,
    recorded_at: datetime,
    *,
    expected_source: Any,
    expected_contract: ActionClassContract,
    expected_verified_at: datetime,
    expected_rechecked_at: datetime,
    current_endpoint: Any,
    current_credential_reference: Any,
    required_credential_scope: str,
) -> PromotionRequirementRuntimeRiskPacket:
    """Review only the final recheck rebuilt against the independent inputs."""
    source = verify_rechecks(
        final_recheck,
        expected_source=expected_source,
        expected_contract=expected_contract,
        expected_verified_at=expected_verified_at,
        expected_rechecked_at=expected_rechecked_at,
        current_endpoint=current_endpoint,
        current_credential_reference=current_credential_reference,
        required_credential_scope=required_credential_scope,
    )
    return _assemble(source, risk_decision, recorded_at)


def verify_promotion_requirement_runtime_risk_packet(
    packet: Any,
    final_recheck: Any,
    *,
    expected_risk_decision: Any,
    expected_recorded_at: datetime,
    verification_now: datetime,
    expected_source: Any,
    expected_contract: ActionClassContract,
    expected_verified_at: datetime,
    expected_rechecked_at: datetime,
    current_endpoint: Any,
    current_credential_reference: Any,
    required_credential_scope: str,
) -> PromotionRequirementRuntimeRiskPacket:
    """Rebuild against independent review/source and reject expired consumption."""
    candidate = PromotionRequirementRuntimeRiskPacket.model_validate(_json(packet))
    rebuilt = build_promotion_requirement_runtime_risk_packet(
        final_recheck,
        expected_risk_decision,
        expected_recorded_at,
        expected_source=expected_source,
        expected_contract=expected_contract,
        expected_verified_at=expected_verified_at,
        expected_rechecked_at=expected_rechecked_at,
        current_endpoint=current_endpoint,
        current_credential_reference=current_credential_reference,
        required_credential_scope=required_credential_scope,
    )
    if _json(candidate) != _json(rebuilt):
        raise PromotionRequirementRuntimeRiskError("PRRR_RECONSTRUCTION_MISMATCH")
    now = datetime.fromisoformat(_timestamp(verification_now))
    if not (
        datetime.fromisoformat(rebuilt.recorded_at)
        <= now
        < datetime.fromisoformat(rebuilt.risk_decision.valid_until)
    ):
        raise PromotionRequirementRuntimeRiskError("PRRR_REVIEW_NOT_CURRENT")
    return rebuilt


def require_promotion_requirement_runtime_risk_pass(
    packet: Any,
    final_recheck: Any,
    **verification_inputs: Any,
) -> PromotionRequirementRuntimeRiskPacket:
    """Admission guard: BLOCK and INDETERMINATE cannot enter later composition.

    The verifier enforces all mandatory keyword inputs. This guard grants no
    execution authority and does not replace the independent Bind-time check.
    """
    verified = verify_promotion_requirement_runtime_risk_packet(
        packet, final_recheck, **verification_inputs
    )
    if (
        verified.fail_closed
        or not verified.ready_for_remaining_authorization_requirements
    ):
        raise PromotionRequirementRuntimeRiskError("PRRR_RISK_NOT_ACCEPTABLE")
    return verified
