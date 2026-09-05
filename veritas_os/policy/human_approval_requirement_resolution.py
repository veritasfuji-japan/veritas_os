"""Resolve whether Human Approval is required before Bind governance.

This module is deliberately non-authorizing. It verifies the preceding Authority
Evidence linkage packet, evaluates the exact Action Class Contract, and emits a
content-addressed requirement-resolution artifact. It never creates Human
Approval, execution authority, Bind authorization, credentials, network calls,
or external effects.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from veritas_os.governance.action_contracts import ActionClassContract
from veritas_os.policy.live_adapter_dry_run_authority_evidence_linkage import (
    CanonicalLiveAdapterDryRunAuthorityEvidenceLinkageReviewPacket,
    LiveAdapterDryRunAuthorityEvidenceLinkageError,
    verify_live_adapter_dry_run_authority_evidence_linkage_review_packet,
)

FORMAT_VERSION = "human-approval-requirement-resolution/v1"
MECHANISM = "resolve_human_approval_requirement_from_action_contract/v1"
STATUS = "HUMAN_APPROVAL_REQUIREMENT_RESOLVED_NOT_AUTHORIZED"
DOMAIN = "veritas.human-approval-requirement-resolution.packet/v1"
REQUIREMENT_STATES = (
    "REQUIRED",
    "NOT_REQUIRED_BY_ACTION_CONTRACT",
)
SCOPE_LIMITATIONS = (
    "NOT_HUMAN_APPROVAL",
    "NOT_HUMAN_APPROVAL_CREATION",
    "NOT_EXECUTION_AUTHORITY",
    "NOT_BIND_AUTHORIZATION",
    "NOT_BIND_INVOCATION",
    "NOT_BIND_RECEIPT",
    "NOT_CREDENTIAL_ACCESS",
    "NOT_AUTHORIZATION_HEADER",
    "NOT_NETWORK_CALL",
    "NOT_EXTERNAL_EFFECT",
)


class HumanApprovalRequirementResolutionError(ValueError):
    """Stable fail-closed error for requirement resolution."""


class CanonicalHumanApprovalRequirementResolutionPacket(BaseModel):
    """Immutable proof of whether Human Approval is required by contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format_version: Literal[FORMAT_VERSION]
    human_approval_requirement_resolution_id: str = Field(
        pattern=r"^harr:v1:sha256:[0-9a-f]{64}$"
    )
    human_approval_requirement_resolution_hash: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )
    resolution_mechanism: Literal[MECHANISM]
    resolved_at: str

    source_authority_evidence_linkage_review_id: str
    source_authority_evidence_linkage_review_hash: str
    source_execution_intent_id: str
    source_execution_intent_hash: str

    action_contract_id: str
    action_contract_version: str
    action_contract_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    action_class: str
    requested_scope: tuple[str, ...]

    required_human_approval: bool
    requirement_state: Literal[*REQUIREMENT_STATES]
    requirement_reason: str

    human_approval_created: Literal[False]
    execution_authority_created: Literal[False]
    bind_authorization_created: Literal[False]
    bind_invoked: Literal[False]
    bind_receipt_created: Literal[False]
    credential_material_accessed: Literal[False]
    authorization_header_constructed: Literal[False]
    network_used: Literal[False]
    external_effect_occurred: Literal[False]
    fail_closed: Literal[False]
    requirement_resolution_status: Literal[STATUS]
    scope_limitations: tuple[Literal[*SCOPE_LIMITATIONS], ...]


def requires_human_approval_for_action_contract(
    contract: ActionClassContract,
) -> bool:
    """Return the canonical contract-derived Human Approval requirement."""
    if not isinstance(contract, ActionClassContract):
        raise HumanApprovalRequirementResolutionError(
            "HARR_ACTION_CONTRACT_REQUIRED"
        )
    rules = contract.human_approval_rules
    minimum_approvals = int(rules.get("minimum_approvals", 0) or 0)
    if bool(rules.get("required", False)):
        return True
    return contract.irreversibility.get("level") == "high" and minimum_approvals > 0


def _timestamp(value: Any) -> str:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise HumanApprovalRequirementResolutionError(
            "HARR_TIMESTAMP_INVALID"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise HumanApprovalRequirementResolutionError(
            "HARR_TIMESTAMP_INVALID"
        )
    return parsed.astimezone(timezone.utc).isoformat()


def _json(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and value == value and value not in (
        float("inf"),
        float("-inf"),
    ):
        return value
    if isinstance(value, datetime):
        return _timestamp(value)
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _json(item) for key, item in value.items()}
    raise HumanApprovalRequirementResolutionError("HARR_INVALID_JSON_VALUE")


def _digest(value: Any) -> str:
    encoded = json.dumps(
        {"domain": DOMAIN, "value": _json(value)},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _verified_source(
    value: Any,
) -> CanonicalLiveAdapterDryRunAuthorityEvidenceLinkageReviewPacket:
    try:
        return verify_live_adapter_dry_run_authority_evidence_linkage_review_packet(
            value
        )
    except (
        LiveAdapterDryRunAuthorityEvidenceLinkageError,
        TypeError,
        ValueError,
    ) as exc:
        raise HumanApprovalRequirementResolutionError(
            "HARR_SOURCE_INVALID"
        ) from exc


def _validate_contract_binding(
    source: CanonicalLiveAdapterDryRunAuthorityEvidenceLinkageReviewPacket,
    contract: ActionClassContract,
) -> tuple[str, ...]:
    intent = source.execution_intent
    intended_action = str(intent.get("intended_action") or "").strip()
    if not intended_action:
        raise HumanApprovalRequirementResolutionError(
            "HARR_INTENDED_ACTION_MISSING"
        )
    if contract.id != intended_action:
        raise HumanApprovalRequirementResolutionError(
            "HARR_ACTION_CONTRACT_SOURCE_MISMATCH"
        )

    bundle = source.authority_evidence_reference_bundle
    scope_raw = (
        bundle.bundle_scope
        if hasattr(bundle, "bundle_scope")
        else bundle.get("bundle_scope")
        if isinstance(bundle, dict)
        else None
    )
    if not isinstance(scope_raw, (list, tuple)):
        raise HumanApprovalRequirementResolutionError("HARR_SOURCE_SCOPE_INVALID")
    requested_scope = tuple(
        str(item).strip() for item in scope_raw if str(item).strip()
    )
    if not requested_scope or len(set(requested_scope)) != len(requested_scope):
        raise HumanApprovalRequirementResolutionError("HARR_SOURCE_SCOPE_INVALID")
    if any(item not in contract.allowed_scope for item in requested_scope):
        raise HumanApprovalRequirementResolutionError(
            "HARR_ACTION_CONTRACT_SCOPE_MISMATCH"
        )
    return requested_scope


def build_human_approval_requirement_resolution_packet(
    source_authority_evidence_linkage_review_packet: Any,
    action_contract: ActionClassContract,
    resolved_at: datetime,
) -> CanonicalHumanApprovalRequirementResolutionPacket:
    """Build a fail-closed, non-authorizing requirement-resolution packet."""
    source = _verified_source(source_authority_evidence_linkage_review_packet)
    if source.fail_closed:
        raise HumanApprovalRequirementResolutionError(
            "HARR_SOURCE_FAIL_CLOSED"
        )
    result = source.authority_evidence_linkage_result
    if not (
        result.all_required_references_present
        and result.all_references_structurally_linked
        and result.all_binding_claims_matched
    ):
        raise HumanApprovalRequirementResolutionError(
            "HARR_SOURCE_AUTHORITY_LINKAGE_NOT_ACCEPTED"
        )

    if not isinstance(action_contract, ActionClassContract):
        raise HumanApprovalRequirementResolutionError(
            "HARR_ACTION_CONTRACT_REQUIRED"
        )
    requested_scope = _validate_contract_binding(source, action_contract)
    required = requires_human_approval_for_action_contract(action_contract)
    state = "REQUIRED" if required else "NOT_REQUIRED_BY_ACTION_CONTRACT"
    reason = (
        "action_contract_requires_human_approval"
        if required
        else "action_contract_does_not_require_human_approval"
    )

    payload = {
        "format_version": FORMAT_VERSION,
        "resolution_mechanism": MECHANISM,
        "resolved_at": _timestamp(resolved_at),
        "source_authority_evidence_linkage_review_id": (
            source.live_adapter_dry_run_authority_evidence_linkage_review_id
        ),
        "source_authority_evidence_linkage_review_hash": (
            source.live_adapter_dry_run_authority_evidence_linkage_review_hash
        ),
        "source_execution_intent_id": source.execution_intent_id,
        "source_execution_intent_hash": source.execution_intent_hash,
        "action_contract_id": action_contract.id,
        "action_contract_version": action_contract.version,
        "action_contract_digest": action_contract.deterministic_digest(),
        "action_class": action_contract.action_class,
        "requested_scope": requested_scope,
        "required_human_approval": required,
        "requirement_state": state,
        "requirement_reason": reason,
        "human_approval_created": False,
        "execution_authority_created": False,
        "bind_authorization_created": False,
        "bind_invoked": False,
        "bind_receipt_created": False,
        "credential_material_accessed": False,
        "authorization_header_constructed": False,
        "network_used": False,
        "external_effect_occurred": False,
        "fail_closed": False,
        "requirement_resolution_status": STATUS,
        "scope_limitations": SCOPE_LIMITATIONS,
    }
    packet_hash = _digest(payload)
    return CanonicalHumanApprovalRequirementResolutionPacket(
        human_approval_requirement_resolution_id=(
            f"harr:v1:sha256:{packet_hash}"
        ),
        human_approval_requirement_resolution_hash=packet_hash,
        **payload,
    )


def verify_human_approval_requirement_resolution_packet(
    value: Any,
) -> CanonicalHumanApprovalRequirementResolutionPacket:
    """Verify schema, state consistency, non-effect flags, and packet hash."""
    try:
        packet = (
            value
            if isinstance(value, CanonicalHumanApprovalRequirementResolutionPacket)
            else CanonicalHumanApprovalRequirementResolutionPacket.model_validate(value)
        )
    except ValidationError as exc:
        raise HumanApprovalRequirementResolutionError(
            "HARR_PACKET_SCHEMA_INVALID"
        ) from exc

    if packet.required_human_approval != (packet.requirement_state == "REQUIRED"):
        raise HumanApprovalRequirementResolutionError(
            "HARR_REQUIREMENT_STATE_INCONSISTENT"
        )

    effect_values = (
        packet.human_approval_created,
        packet.execution_authority_created,
        packet.bind_authorization_created,
        packet.bind_invoked,
        packet.bind_receipt_created,
        packet.credential_material_accessed,
        packet.authorization_header_constructed,
        packet.network_used,
        packet.external_effect_occurred,
    )
    if any(effect_values) or packet.fail_closed:
        raise HumanApprovalRequirementResolutionError(
            "HARR_EFFECT_OR_FAIL_CLOSED_INVALID"
        )

    raw = packet.model_dump(mode="python")
    packet_id = raw.pop("human_approval_requirement_resolution_id")
    packet_hash = raw.pop("human_approval_requirement_resolution_hash")
    expected = _digest(raw)
    if packet_hash != expected or packet_id != f"harr:v1:sha256:{expected}":
        raise HumanApprovalRequirementResolutionError("HARR_HASH_MISMATCH")
    return packet
