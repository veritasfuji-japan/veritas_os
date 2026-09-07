"""Non-authorizing requirement satisfaction for native promotion sources.

Keep the complete native source; never synthesize legacy handoff or replay
fields. Independent expected source and contract are mandatory for verification.
Satisfaction here means metadata linkage, not a cryptographic Human Approval.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from veritas_os.governance.action_contracts import (
    ActionClassContract,
    validate_action_class_contract,
)
from veritas_os.policy.human_approval_requirement_resolution import (
    _json,
    _timestamp,
    _verify_resolution_and_source,
)
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_authority_evidence_linkage import (
    CanonicalPromotionLiveAdapterDryRunAuthorityEvidenceLinkageReviewPacket,
)
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_human_approval_linkage import (
    verify_canonical_promotion_live_adapter_dry_run_human_approval_linkage_review_packet as verify_linkage,
)
from veritas_os.security.hash import sha256_of_canonical_json

FORMAT_VERSION = "promotion-human-approval-requirement-satisfaction/v1"
DOMAIN = "veritas.promotion-human-approval-requirement-satisfaction/v1"
REQUIRED_STATE = "SATISFIED_BY_VERIFIED_HUMAN_APPROVAL_LINKAGE"
NOT_REQUIRED_STATE = "SATISFIED_AS_NOT_REQUIRED_BY_ACTION_CONTRACT"


class PromotionHumanApprovalRequirementSatisfactionError(ValueError):
    """Fail-closed native requirement satisfaction failure."""


class PromotionHumanApprovalRequirementSatisfactionPacket(BaseModel):
    """Complete source/policy binding with explicit non-authorizing semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    format_version: Literal[FORMAT_VERSION]
    packet_id: str = Field(pattern=r"^phars:v1:sha256:[0-9a-f]{64}$")
    packet_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    recorded_at: str
    source_authority_evidence_linkage_review_packet: dict[str, Any]
    source_authority_evidence_linkage_review_id: str
    source_authority_evidence_linkage_review_hash: str
    action_contract_snapshot: dict[str, Any]
    action_contract_digest: str
    human_approval_requirement_resolution_packet: dict[str, Any]
    required_human_approval: bool
    requirement_state: Literal["REQUIRED", "NOT_REQUIRED_BY_ACTION_CONTRACT"]
    satisfaction_state: Literal[REQUIRED_STATE, NOT_REQUIRED_STATE]
    required_human_approval_linkage_packet: dict[str, Any] | None
    execution_intent: dict[str, Any]
    execution_intent_id: str
    execution_intent_hash: str
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


def _packet_hash(raw: dict[str, Any]) -> str:
    return sha256_of_canonical_json(
        {
            "domain": DOMAIN,
            "value": {
                key: value
                for key, value in raw.items()
                if key not in {"packet_id", "packet_hash"}
            },
        }
    )


def build_promotion_human_approval_requirement_satisfaction_packet(
    source: Any,
    resolution: Any,
    contract: ActionClassContract,
    required_linkage: Any | None,
    recorded_at: datetime,
) -> PromotionHumanApprovalRequirementSatisfactionPacket:
    """Verify native inputs and derive solely from the rebuilt resolution."""
    if not isinstance(contract, ActionClassContract):
        raise PromotionHumanApprovalRequirementSatisfactionError(
            "PHARS_CONTRACT_REQUIRED"
        )
    contract = validate_action_class_contract(contract.to_dict())
    resolution, source = _verify_resolution_and_source(
        resolution, source, contract
    )
    if not isinstance(source, CanonicalPromotionLiveAdapterDryRunAuthorityEvidenceLinkageReviewPacket):
        raise PromotionHumanApprovalRequirementSatisfactionError("PHARS_NATIVE_SOURCE_REQUIRED")
    recorded = _timestamp(recorded_at)
    if datetime.fromisoformat(recorded) < datetime.fromisoformat(
        resolution.resolved_at
    ):
        raise PromotionHumanApprovalRequirementSatisfactionError(
            "PHARS_TIMESTAMP_ORDER"
        )
    source_raw = source.model_dump(mode="json")
    linkage_raw = None
    if resolution.required_human_approval:
        if required_linkage is None:
            raise PromotionHumanApprovalRequirementSatisfactionError(
                "PHARS_REQUIRED_LINKAGE_MISSING"
            )
        linkage = verify_linkage(required_linkage)
        if linkage.source_authority_evidence_linkage_review_packet != source_raw:
            raise PromotionHumanApprovalRequirementSatisfactionError(
                "PHARS_LINKAGE_SOURCE_MISMATCH"
            )
        if datetime.fromisoformat(recorded) < datetime.fromisoformat(
            linkage.human_approval_linkage_review_recorded_at
        ):
            raise PromotionHumanApprovalRequirementSatisfactionError(
                "PHARS_TIMESTAMP_ORDER"
            )
        linkage_raw = linkage.model_dump(mode="json")
    elif required_linkage is not None:
        raise PromotionHumanApprovalRequirementSatisfactionError(
            "PHARS_UNEXPECTED_LINKAGE"
        )
    raw = {
        "format_version": FORMAT_VERSION,
        "recorded_at": recorded,
        "source_authority_evidence_linkage_review_packet": source_raw,
        "source_authority_evidence_linkage_review_id": resolution.source_authority_evidence_linkage_review_id,
        "source_authority_evidence_linkage_review_hash": resolution.source_authority_evidence_linkage_review_hash,
        "action_contract_snapshot": contract.to_dict(),
        "action_contract_digest": resolution.action_contract_digest,
        "human_approval_requirement_resolution_packet": resolution.model_dump(
            mode="json"
        ),
        "required_human_approval": resolution.required_human_approval,
        "requirement_state": resolution.requirement_state,
        "satisfaction_state": REQUIRED_STATE
        if resolution.required_human_approval
        else NOT_REQUIRED_STATE,
        "required_human_approval_linkage_packet": linkage_raw,
        "execution_intent": source.execution_intent,
        "execution_intent_id": source.execution_intent_id,
        "execution_intent_hash": source.execution_intent_hash,
        **{
            name: False
            for name in (
                "human_approval_created",
                "human_approval_proven",
                "authority_evidence_proven",
                "execution_authority_created",
                "bind_authorization_created",
                "bind_invoked",
                "bind_receipt_created",
                "credential_material_accessed",
                "network_used",
                "external_effect_occurred",
                "ready_for_real_bind",
            )
        },
    }
    digest = _packet_hash(raw)
    return PromotionHumanApprovalRequirementSatisfactionPacket(
        packet_id=f"phars:v1:sha256:{digest}", packet_hash=digest, **raw
    )


def verify_promotion_human_approval_requirement_satisfaction_packet(
    packet: Any,
    *,
    expected_source: Any,
    expected_contract: ActionClassContract,
) -> PromotionHumanApprovalRequirementSatisfactionPacket:
    """Rebuild all fields against independent anchors; return the rebuilt result."""
    candidate = PromotionHumanApprovalRequirementSatisfactionPacket.model_validate(
        _json(packet)
    )
    rebuilt = build_promotion_human_approval_requirement_satisfaction_packet(
        expected_source,
        candidate.human_approval_requirement_resolution_packet,
        expected_contract,
        candidate.required_human_approval_linkage_packet,
        datetime.fromisoformat(_timestamp(candidate.recorded_at)),
    )
    if _json(candidate) != _json(rebuilt):
        raise PromotionHumanApprovalRequirementSatisfactionError(
            "PHARS_RECONSTRUCTION_MISMATCH"
        )
    return rebuilt
