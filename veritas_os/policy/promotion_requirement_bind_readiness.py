"""Policy-bound native final readiness and gate review, without authorization.

Both stages consume rebuilt requirement satisfaction and require independent
source/policy anchors. These formats do not masquerade as linkage-only v1
packets and are not yet inputs to the real authorization issuer.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from veritas_os.governance.action_contracts import ActionClassContract
from veritas_os.policy.human_approval_requirement_resolution import _json, _timestamp
from veritas_os.policy.promotion_human_approval_requirement_satisfaction import (
    PromotionHumanApprovalRequirementSatisfactionPacket,
    verify_promotion_human_approval_requirement_satisfaction_packet as verify_satisfaction,
)
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_bind_authorization_gate_review import (
    AUTHORIZATION_REQUIREMENTS,
    INVOCATION_REQUIREMENTS,
)
from veritas_os.security.hash import sha256_of_canonical_json


class PromotionRequirementBindReviewError(ValueError):
    """Invalid source, review ordering, or reconstructed policy binding."""


class RequirementBindReviewDecision(BaseModel):
    """Explicit local review; no signed human approval is asserted."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    review_id: str = Field(min_length=1)
    reviewer_id: str = Field(min_length=1)
    review_reason: str = Field(min_length=1)
    reviewed_at: str
    accepted: bool
    acknowledged_no_authorization: Literal[True]
    acknowledged_no_human_approval_proof: Literal[True]
    acknowledged_no_authority_evidence_proof: Literal[True]
    acknowledged_no_external_effect: Literal[True]
    acknowledged_independent_policy_binding: Literal[True]


class _ReviewPacket(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    packet_id: str
    packet_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    recorded_at: str
    review_decision: RequirementBindReviewDecision
    source_packet: dict[str, Any]
    source_packet_id: str
    source_packet_hash: str
    source_authority_evidence_linkage_review_id: str
    source_authority_evidence_linkage_review_hash: str
    action_contract_digest: str
    requirement_resolution_hash: str
    required_human_approval: bool
    requirement_state: Literal["REQUIRED", "NOT_REQUIRED_BY_ACTION_CONTRACT"]
    satisfaction_state: Literal[
        "SATISFIED_BY_VERIFIED_HUMAN_APPROVAL_LINKAGE",
        "SATISFIED_AS_NOT_REQUIRED_BY_ACTION_CONTRACT",
    ]
    execution_intent: dict[str, Any]
    execution_intent_id: str
    execution_intent_hash: str
    future_authorization_requirements: list[str]
    future_invocation_requirements: list[str]
    fail_closed: bool
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


class PromotionRequirementFinalReadinessPacket(_ReviewPacket):
    """Final readiness derived from verified native requirement satisfaction."""

    format_version: Literal["promotion-requirement-final-readiness/v1"]
    ready_for_bind_authorization_gate_review: bool


class PromotionRequirementBindGatePacket(_ReviewPacket):
    """Gate review retaining the complete independently verified readiness."""

    format_version: Literal["promotion-requirement-bind-gate/v1"]
    ready_for_fresh_verified_source_gate: bool


def _packet_hash(raw: dict[str, Any]) -> str:
    return sha256_of_canonical_json({
        "domain": "veritas." + raw["format_version"],
        "value": {k: v for k, v in raw.items() if k not in {"packet_id", "packet_hash"}},
    })


def _assemble(
    source: BaseModel,
    satisfaction: PromotionHumanApprovalRequirementSatisfactionPacket,
    decision: Any,
    recorded_at: datetime,
    *,
    gate: bool,
) -> dict[str, Any]:
    decision = RequirementBindReviewDecision.model_validate(_json(decision))
    reviewed = _timestamp(decision.reviewed_at)
    recorded = _timestamp(recorded_at)
    if not (
        datetime.fromisoformat(source.recorded_at)
        <= datetime.fromisoformat(reviewed)
        <= datetime.fromisoformat(recorded)
    ):
        raise PromotionRequirementBindReviewError("PRBR_TIMESTAMP_ORDER")
    decision = decision.model_copy(update={"reviewed_at": reviewed})
    requirements = list(AUTHORIZATION_REQUIREMENTS)
    if not satisfaction.required_human_approval:
        requirements = [name for name in requirements if name not in {
            "signed_gate_bound_human_approval_issuance",
            "human_approval_receipt_verification",
        }]
    if not gate:
        requirements.insert(0, "promotion_native_bind_authorization_gate_review")
    sat = satisfaction.model_dump(mode="json")
    resolution = sat["human_approval_requirement_resolution_packet"]
    raw = {
        "format_version": "promotion-requirement-bind-gate/v1" if gate
        else "promotion-requirement-final-readiness/v1",
        "recorded_at": recorded,
        "review_decision": decision.model_dump(mode="json"),
        "source_packet": source.model_dump(mode="json"),
        "source_packet_id": source.packet_id,
        "source_packet_hash": source.packet_hash,
        **{name: sat[name] for name in (
            "source_authority_evidence_linkage_review_id",
            "source_authority_evidence_linkage_review_hash",
            "action_contract_digest", "required_human_approval",
            "requirement_state", "satisfaction_state", "execution_intent",
            "execution_intent_id", "execution_intent_hash",
            "human_approval_created", "human_approval_proven",
            "authority_evidence_proven", "execution_authority_created",
            "bind_authorization_created", "bind_invoked", "bind_receipt_created",
            "credential_material_accessed", "network_used",
            "external_effect_occurred", "ready_for_real_bind",
        )},
        "requirement_resolution_hash": resolution["human_approval_requirement_resolution_hash"],
        "future_authorization_requirements": requirements,
        "future_invocation_requirements": list(INVOCATION_REQUIREMENTS),
        "fail_closed": not decision.accepted,
        ("ready_for_fresh_verified_source_gate" if gate
         else "ready_for_bind_authorization_gate_review"): decision.accepted,
    }
    digest = _packet_hash(raw)
    return {**raw, "packet_hash": digest,
            "packet_id": f"{raw['format_version']}:sha256:{digest}"}


def build_promotion_requirement_final_readiness_packet(
    satisfaction: Any, decision: Any, recorded_at: datetime, *,
    expected_source: Any, expected_contract: ActionClassContract,
) -> PromotionRequirementFinalReadinessPacket:
    """Consume only satisfaction rebuilt against external source and policy."""
    verified = verify_satisfaction(
        satisfaction, expected_source=expected_source, expected_contract=expected_contract
    )
    return PromotionRequirementFinalReadinessPacket.model_validate(
        _assemble(verified, verified, decision, recorded_at, gate=False)
    )


def verify_promotion_requirement_final_readiness_packet(
    packet: Any, *, expected_source: Any, expected_contract: ActionClassContract,
) -> PromotionRequirementFinalReadinessPacket:
    """Reconstruct every field; embedded source/contract never supply anchors."""
    candidate = PromotionRequirementFinalReadinessPacket.model_validate(_json(packet))
    rebuilt = build_promotion_requirement_final_readiness_packet(
        candidate.source_packet, candidate.review_decision,
        datetime.fromisoformat(_timestamp(candidate.recorded_at)),
        expected_source=expected_source, expected_contract=expected_contract,
    )
    # Input was normalized before schema validation; builders return JSON-valued
    # fields. Compare every field without recursively normalizing both again.
    if candidate.model_dump(mode="python") != rebuilt.model_dump(mode="python"):
        raise PromotionRequirementBindReviewError("PRBR_RECONSTRUCTION_MISMATCH")
    return rebuilt


def build_promotion_requirement_bind_gate_packet(
    readiness: Any, decision: Any, recorded_at: datetime, *,
    expected_source: Any, expected_contract: ActionClassContract,
) -> PromotionRequirementBindGatePacket:
    """Propagate independent anchors through readiness and satisfaction."""
    verified = verify_promotion_requirement_final_readiness_packet(
        readiness, expected_source=expected_source, expected_contract=expected_contract
    )
    if verified.fail_closed or not verified.ready_for_bind_authorization_gate_review:
        raise PromotionRequirementBindReviewError("PRBR_READINESS_REJECTED")
    # The readiness verifier returned a full reconstruction against the external
    # anchors above. Project its reconstructed child, never readiness.source_packet.
    satisfaction = PromotionHumanApprovalRequirementSatisfactionPacket.model_validate(
        verified.source_packet,
    )
    return PromotionRequirementBindGatePacket.model_validate(
        _assemble(verified, satisfaction, decision, recorded_at, gate=True)
    )


def verify_promotion_requirement_bind_gate_packet(
    packet: Any, *, expected_source: Any, expected_contract: ActionClassContract,
) -> PromotionRequirementBindGatePacket:
    """Return only the gate rebuilt using the complete external trust chain."""
    candidate = PromotionRequirementBindGatePacket.model_validate(_json(packet))
    rebuilt = build_promotion_requirement_bind_gate_packet(
        candidate.source_packet, candidate.review_decision,
        datetime.fromisoformat(_timestamp(candidate.recorded_at)),
        expected_source=expected_source, expected_contract=expected_contract,
    )
    # Input was normalized before schema validation; builders return JSON-valued
    # fields. Compare every field without recursively normalizing both again.
    if candidate.model_dump(mode="python") != rebuilt.model_dump(mode="python"):
        raise PromotionRequirementBindReviewError("PRBR_RECONSTRUCTION_MISMATCH")
    return rebuilt
