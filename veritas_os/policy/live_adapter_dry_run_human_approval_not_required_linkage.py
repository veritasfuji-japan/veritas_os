"""Bind contract-derived Human Approval non-requirement to the dry-run chain.

This module is deliberately non-authorizing. It verifies both the upstream
Authority Evidence linkage packet and a HumanApprovalRequirementResolution
packet, requires the latter to resolve to NOT_REQUIRED_BY_ACTION_CONTRACT, and
emits a content-addressed linkage artifact without fabricating Human Approval.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from veritas_os.policy.human_approval_requirement_resolution import (
    CanonicalHumanApprovalRequirementResolutionPacket,
    HumanApprovalRequirementResolutionError,
    verify_human_approval_requirement_resolution_packet,
)
from veritas_os.policy.live_adapter_dry_run_authority_evidence_linkage import (
    CanonicalLiveAdapterDryRunAuthorityEvidenceLinkageReviewPacket,
    LiveAdapterDryRunAuthorityEvidenceLinkageError,
    verify_live_adapter_dry_run_authority_evidence_linkage_review_packet,
)

FORMAT_VERSION = "canonical-live-adapter-dry-run-human-approval-not-required-linkage/v1"
MECHANISM = "bind_contract_derived_human_approval_non_requirement/v1"
STATUS = "LIVE_ADAPTER_DRY_RUN_HUMAN_APPROVAL_REQUIREMENT_SATISFIED_NOT_AUTHORIZED"
DOMAIN = "veritas.live-adapter-dry-run-human-approval-not-required-linkage.packet/v1"
REQUIREMENT_STATE = "NOT_REQUIRED_BY_ACTION_CONTRACT"
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


class LiveAdapterDryRunHumanApprovalNotRequiredLinkageError(ValueError):
    """Stable fail-closed error for the no-approval linkage route."""


class HumanApprovalNotRequiredLinkageResult(BaseModel):
    """Deterministic result proving only that approval is not required."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    source_authority_evidence_linkage_verified: Literal[True]
    requirement_resolution_verified: Literal[True]
    human_approval_required: Literal[False]
    human_approval_reference_count: Literal[0]
    human_approval_references_absent: Literal[True]
    accepted_for_final_bind_authorization_readiness: Literal[True]
    creates_human_approval: Literal[False]
    creates_execution_authority: Literal[False]
    creates_bind_authorization: Literal[False]


class CanonicalLiveAdapterDryRunHumanApprovalNotRequiredLinkagePacket(BaseModel):
    """Content-addressed proof that Human Approval is contractually not required."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format_version: Literal[FORMAT_VERSION]
    live_adapter_dry_run_human_approval_not_required_linkage_id: str = Field(
        pattern=r"^ladhanr:v1:sha256:[0-9a-f]{64}$"
    )
    live_adapter_dry_run_human_approval_not_required_linkage_hash: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )
    linkage_mechanism: Literal[MECHANISM]
    linkage_recorded_at: str
    source_authority_evidence_linkage_review_id: str
    source_authority_evidence_linkage_review_hash: str
    source_authority_evidence_linkage_review_packet: dict[str, Any]
    human_approval_requirement_resolution_id: str
    human_approval_requirement_resolution_hash: str
    human_approval_requirement_resolution_packet: dict[str, Any]
    execution_intent_id: str
    execution_intent_hash: str
    action_contract_id: str
    action_contract_version: str
    action_contract_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    requested_scope: tuple[str, ...]
    human_approval_requirement_state: Literal[REQUIREMENT_STATE]
    human_approval_reference_count: Literal[0]
    human_approval_not_required_linkage_result: HumanApprovalNotRequiredLinkageResult
    request_dispatch_state: Literal["NOT_DISPATCHED"]
    bind_state: Literal["NOT_BOUND"]
    authority_state: Literal["NOT_AUTHORIZED"]
    human_approval_state: Literal["NOT_REQUIRED"]
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
    linkage_status: Literal[STATUS]
    scope_limitations: tuple[Literal[*SCOPE_LIMITATIONS], ...]


def _timestamp(value: Any) -> str:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise LiveAdapterDryRunHumanApprovalNotRequiredLinkageError(
            "LADHANR_TIMESTAMP_INVALID"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LiveAdapterDryRunHumanApprovalNotRequiredLinkageError(
            "LADHANR_TIMESTAMP_INVALID"
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
    raise LiveAdapterDryRunHumanApprovalNotRequiredLinkageError(
        "LADHANR_INVALID_JSON_VALUE"
    )


def _digest(value: Any) -> str:
    encoded = json.dumps(
        {"domain": DOMAIN, "value": _json(value)},
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _packet_hash(raw: dict[str, Any]) -> str:
    omitted = {
        "live_adapter_dry_run_human_approval_not_required_linkage_id",
        "live_adapter_dry_run_human_approval_not_required_linkage_hash",
    }
    return _digest({key: value for key, value in raw.items() if key not in omitted})


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
        raise LiveAdapterDryRunHumanApprovalNotRequiredLinkageError(
            "LADHANR_SOURCE_INVALID"
        ) from exc


def _verified_resolution(
    value: Any,
) -> CanonicalHumanApprovalRequirementResolutionPacket:
    try:
        return verify_human_approval_requirement_resolution_packet(value)
    except (
        HumanApprovalRequirementResolutionError,
        TypeError,
        ValueError,
    ) as exc:
        raise LiveAdapterDryRunHumanApprovalNotRequiredLinkageError(
            "LADHANR_RESOLUTION_INVALID"
        ) from exc


def _validate_source(
    source: CanonicalLiveAdapterDryRunAuthorityEvidenceLinkageReviewPacket,
) -> None:
    if source.request_dispatch_state != "NOT_DISPATCHED" or source.request_dispatched:
        raise LiveAdapterDryRunHumanApprovalNotRequiredLinkageError(
            "LADHANR_SOURCE_DISPATCHED"
        )
    if source.bind_state != "NOT_BOUND" or source.bind_invoked:
        raise LiveAdapterDryRunHumanApprovalNotRequiredLinkageError(
            "LADHANR_SOURCE_BOUND"
        )
    if source.authority_state != "NOT_AUTHORIZED":
        raise LiveAdapterDryRunHumanApprovalNotRequiredLinkageError(
            "LADHANR_SOURCE_AUTHORIZED"
        )
    result = source.authority_evidence_linkage_result
    if source.fail_closed or not (
        result.all_required_references_present
        and result.all_references_structurally_linked
        and result.all_binding_claims_matched
    ):
        raise LiveAdapterDryRunHumanApprovalNotRequiredLinkageError(
            "LADHANR_SOURCE_REJECTED"
        )


def _validate_binding(
    source: CanonicalLiveAdapterDryRunAuthorityEvidenceLinkageReviewPacket,
    resolution: CanonicalHumanApprovalRequirementResolutionPacket,
) -> None:
    if (
        resolution.required_human_approval
        or resolution.requirement_state != REQUIREMENT_STATE
    ):
        raise LiveAdapterDryRunHumanApprovalNotRequiredLinkageError(
            "LADHANR_APPROVAL_IS_REQUIRED"
        )
    if (
        resolution.source_authority_evidence_linkage_review_id
        != source.live_adapter_dry_run_authority_evidence_linkage_review_id
        or resolution.source_authority_evidence_linkage_review_hash
        != source.live_adapter_dry_run_authority_evidence_linkage_review_hash
        or resolution.source_execution_intent_id != source.execution_intent_id
        or resolution.source_execution_intent_hash != source.execution_intent_hash
    ):
        raise LiveAdapterDryRunHumanApprovalNotRequiredLinkageError(
            "LADHANR_SOURCE_RESOLUTION_MISMATCH"
        )
    scope_raw = source.authority_evidence_reference_bundle.get("bundle_scope")
    if not isinstance(scope_raw, list):
        raise LiveAdapterDryRunHumanApprovalNotRequiredLinkageError(
            "LADHANR_SOURCE_SCOPE_INVALID"
        )
    requested_scope = tuple(
        str(item).strip() for item in scope_raw if str(item).strip()
    )
    if requested_scope != resolution.requested_scope:
        raise LiveAdapterDryRunHumanApprovalNotRequiredLinkageError(
            "LADHANR_SCOPE_RESOLUTION_MISMATCH"
        )


def build_live_adapter_dry_run_human_approval_not_required_linkage_packet(
    source_authority_evidence_linkage_review_packet: Any,
    human_approval_requirement_resolution_packet: Any,
    linkage_recorded_at: datetime,
) -> CanonicalLiveAdapterDryRunHumanApprovalNotRequiredLinkagePacket:
    """Build a no-approval linkage packet without creating an approval artifact."""

    source = _verified_source(source_authority_evidence_linkage_review_packet)
    _validate_source(source)
    resolution = _verified_resolution(human_approval_requirement_resolution_packet)
    _validate_binding(source, resolution)

    source_raw = source.model_dump(mode="json")
    resolution_raw = resolution.model_dump(mode="json")
    result = {
        "source_authority_evidence_linkage_verified": True,
        "requirement_resolution_verified": True,
        "human_approval_required": False,
        "human_approval_reference_count": 0,
        "human_approval_references_absent": True,
        "accepted_for_final_bind_authorization_readiness": True,
        "creates_human_approval": False,
        "creates_execution_authority": False,
        "creates_bind_authorization": False,
    }
    raw = {
        "format_version": FORMAT_VERSION,
        "linkage_mechanism": MECHANISM,
        "linkage_recorded_at": _timestamp(linkage_recorded_at),
        "source_authority_evidence_linkage_review_id": (
            source.live_adapter_dry_run_authority_evidence_linkage_review_id
        ),
        "source_authority_evidence_linkage_review_hash": (
            source.live_adapter_dry_run_authority_evidence_linkage_review_hash
        ),
        "source_authority_evidence_linkage_review_packet": source_raw,
        "human_approval_requirement_resolution_id": (
            resolution.human_approval_requirement_resolution_id
        ),
        "human_approval_requirement_resolution_hash": (
            resolution.human_approval_requirement_resolution_hash
        ),
        "human_approval_requirement_resolution_packet": resolution_raw,
        "execution_intent_id": source.execution_intent_id,
        "execution_intent_hash": source.execution_intent_hash,
        "action_contract_id": resolution.action_contract_id,
        "action_contract_version": resolution.action_contract_version,
        "action_contract_digest": resolution.action_contract_digest,
        "requested_scope": resolution.requested_scope,
        "human_approval_requirement_state": REQUIREMENT_STATE,
        "human_approval_reference_count": 0,
        "human_approval_not_required_linkage_result": result,
        "request_dispatch_state": "NOT_DISPATCHED",
        "bind_state": "NOT_BOUND",
        "authority_state": "NOT_AUTHORIZED",
        "human_approval_state": "NOT_REQUIRED",
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
        "linkage_status": STATUS,
        "scope_limitations": SCOPE_LIMITATIONS,
    }
    digest = _packet_hash(raw)
    raw["live_adapter_dry_run_human_approval_not_required_linkage_hash"] = digest
    raw["live_adapter_dry_run_human_approval_not_required_linkage_id"] = (
        f"ladhanr:v1:sha256:{digest}"
    )
    return verify_live_adapter_dry_run_human_approval_not_required_linkage_packet(raw)


def verify_live_adapter_dry_run_human_approval_not_required_linkage_packet(
    value: Any,
) -> CanonicalLiveAdapterDryRunHumanApprovalNotRequiredLinkagePacket:
    """Re-verify source, resolution, identity binding, non-effects, and hash."""

    try:
        packet = (
            value
            if isinstance(
                value,
                CanonicalLiveAdapterDryRunHumanApprovalNotRequiredLinkagePacket,
            )
            else CanonicalLiveAdapterDryRunHumanApprovalNotRequiredLinkagePacket.model_validate(
                _json(value)
            )
        )
    except (
        ValidationError,
        TypeError,
        LiveAdapterDryRunHumanApprovalNotRequiredLinkageError,
    ) as exc:
        raise LiveAdapterDryRunHumanApprovalNotRequiredLinkageError(
            "LADHANR_PACKET_SCHEMA_INVALID"
        ) from exc

    source = _verified_source(packet.source_authority_evidence_linkage_review_packet)
    _validate_source(source)
    resolution = _verified_resolution(
        packet.human_approval_requirement_resolution_packet
    )
    _validate_binding(source, resolution)

    expected_identity = (
        packet.source_authority_evidence_linkage_review_id
        == source.live_adapter_dry_run_authority_evidence_linkage_review_id,
        packet.source_authority_evidence_linkage_review_hash
        == source.live_adapter_dry_run_authority_evidence_linkage_review_hash,
        packet.human_approval_requirement_resolution_id
        == resolution.human_approval_requirement_resolution_id,
        packet.human_approval_requirement_resolution_hash
        == resolution.human_approval_requirement_resolution_hash,
        packet.execution_intent_id == source.execution_intent_id,
        packet.execution_intent_hash == source.execution_intent_hash,
        packet.action_contract_id == resolution.action_contract_id,
        packet.action_contract_version == resolution.action_contract_version,
        packet.action_contract_digest == resolution.action_contract_digest,
        packet.requested_scope == resolution.requested_scope,
    )
    if not all(expected_identity):
        raise LiveAdapterDryRunHumanApprovalNotRequiredLinkageError(
            "LADHANR_IDENTITY_MISMATCH"
        )

    result = packet.human_approval_not_required_linkage_result
    if not (
        result.source_authority_evidence_linkage_verified
        and result.requirement_resolution_verified
        and not result.human_approval_required
        and result.human_approval_reference_count == 0
        and result.human_approval_references_absent
        and result.accepted_for_final_bind_authorization_readiness
        and not result.creates_human_approval
        and not result.creates_execution_authority
        and not result.creates_bind_authorization
    ):
        raise LiveAdapterDryRunHumanApprovalNotRequiredLinkageError(
            "LADHANR_RESULT_INVALID"
        )

    effects = (
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
    if any(effects) or packet.fail_closed:
        raise LiveAdapterDryRunHumanApprovalNotRequiredLinkageError(
            "LADHANR_EFFECT_OR_FAIL_CLOSED_INVALID"
        )
    if packet.scope_limitations != SCOPE_LIMITATIONS:
        raise LiveAdapterDryRunHumanApprovalNotRequiredLinkageError(
            "LADHANR_SCOPE_LIMITATIONS_MISMATCH"
        )

    actual = packet.model_dump(mode="python")
    digest = _packet_hash(actual)
    if (
        packet.live_adapter_dry_run_human_approval_not_required_linkage_hash
        != digest
        or packet.live_adapter_dry_run_human_approval_not_required_linkage_id
        != f"ladhanr:v1:sha256:{digest}"
    ):
        raise LiveAdapterDryRunHumanApprovalNotRequiredLinkageError(
            "LADHANR_HASH_MISMATCH"
        )
    return packet
