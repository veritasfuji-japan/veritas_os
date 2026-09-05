"""Unify required and not-required Human Approval paths for dry-run Bind governance.

This module does not create Human Approval or execution authority.  It combines
an independently verified Action Class Contract requirement-resolution artifact
with either:

* the existing Human Approval linkage review when approval is required, or
* an explicit zero-reference NOT_REQUIRED path when the contract does not
  require approval.

The resulting packet deliberately exposes the same downstream linkage surface
used by final Bind readiness while preserving the requirement-resolution proof.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from veritas_os.governance.action_contracts import (
    ActionClassContract,
    ActionClassContractValidationError,
    validate_action_class_contract,
)
from veritas_os.policy.human_approval_requirement_resolution import (
    CanonicalHumanApprovalRequirementResolutionPacket,
    HumanApprovalRequirementResolutionError,
    requires_human_approval_for_action_contract,
    verify_human_approval_requirement_resolution_packet,
)
from veritas_os.policy.live_adapter_dry_run_authority_evidence_linkage import (
    CanonicalLiveAdapterDryRunAuthorityEvidenceLinkageReviewPacket,
    LiveAdapterDryRunAuthorityEvidenceLinkageError,
    verify_live_adapter_dry_run_authority_evidence_linkage_review_packet,
)
from veritas_os.policy.live_adapter_dry_run_human_approval_linkage import (
    BIND_REQUIREMENTS,
    COPIED_FIELDS,
    SCOPE_LIMITATIONS as HUMAN_LINKAGE_SCOPE_LIMITATIONS,
    CanonicalLiveAdapterDryRunHumanApprovalLinkageReviewPacket,
    LiveAdapterDryRunHumanApprovalLinkageError,
    verify_live_adapter_dry_run_human_approval_linkage_review_packet,
)

FORMAT_VERSION = (
    "canonical-live-adapter-dry-run-human-approval-requirement-satisfaction/v1"
)
MECHANISM = "satisfy_human_approval_requirement_without_authority_creation/v1"
STATUS = "LIVE_ADAPTER_DRY_RUN_HUMAN_APPROVAL_REQUIREMENT_SATISFIED_NOT_APPROVED"
CHECK_MODE = "deterministic_local_human_approval_requirement_satisfaction_only"
DOMAIN = "veritas.live-adapter-dry-run-human-approval-requirement-satisfaction.packet/v1"
RESULT_DOMAIN = (
    "veritas.live-adapter-dry-run-human-approval-requirement-satisfaction.result/v1"
)
BUNDLE_DOMAIN = (
    "veritas.live-adapter-dry-run-human-approval-requirement-satisfaction.bundle/v1"
)
MATRIX_DOMAIN = (
    "veritas.live-adapter-dry-run-human-approval-requirement-satisfaction.matrix/v1"
)
CHECKS_DOMAIN = (
    "veritas.live-adapter-dry-run-human-approval-requirement-satisfaction.checks/v1"
)
REQUIREMENTS_DOMAIN = (
    "veritas.live-adapter-dry-run-human-approval-requirement-satisfaction."
    "future-bind-requirements/v1"
)

REQUIREMENT_STATES = ("REQUIRED", "NOT_REQUIRED_BY_ACTION_CONTRACT")
SATISFACTION_STATES = (
    "SATISFIED_BY_VERIFIED_HUMAN_APPROVAL_LINKAGE",
    "SATISFIED_AS_NOT_REQUIRED_BY_ACTION_CONTRACT",
)
SCOPE_LIMITATIONS = HUMAN_LINKAGE_SCOPE_LIMITATIONS + (
    "HUMAN_APPROVAL_REQUIREMENT_RESOLUTION_BOUND",
    "ACTION_CONTRACT_SNAPSHOT_BOUND",
)


class LiveAdapterDryRunHumanApprovalRequirementSatisfactionError(ValueError):
    """Stable fail-closed error for requirement-satisfaction evidence."""


class HumanApprovalRequirementSatisfactionResult(BaseModel):
    """Downstream-compatible result with explicit requirement semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    all_required_approval_references_present: bool
    all_approval_references_structurally_linked: bool
    all_binding_claims_matched: bool
    approval_requirement_satisfied: Literal[True]
    required_human_approval: bool
    requirement_state: Literal[*REQUIREMENT_STATES]
    satisfaction_state: Literal[*SATISFACTION_STATES]
    approval_linkage_used: bool
    rejected_approval_reference_ids: tuple[str, ...]
    rejection_reasons: tuple[str, ...]
    comparison_mode: Literal[CHECK_MODE]
    semantic_match_used: Literal[False]
    creates_human_approval: Literal[False]
    creates_authority_evidence: Literal[False]
    creates_execution_authority: Literal[False]
    creates_bind_authorization: Literal[False]


class CanonicalLiveAdapterDryRunHumanApprovalRequirementSatisfactionPacket(BaseModel):
    """Content-addressed bridge from requirement resolution to final readiness."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format_version: Literal[FORMAT_VERSION]
    live_adapter_dry_run_human_approval_linkage_review_id: str = Field(
        pattern=r"^ladhars:v1:sha256:[0-9a-f]{64}$"
    )
    live_adapter_dry_run_human_approval_linkage_review_hash: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )
    human_approval_linkage_review_mechanism: Literal[MECHANISM]
    human_approval_linkage_review_recorded_at: str

    source_authority_evidence_linkage_review_id: str
    source_authority_evidence_linkage_review_hash: str
    source_authority_evidence_linkage_review_packet: dict[str, Any]
    source_bind_pre_dispatch_review_hash: str
    source_operator_dispatch_review_hash: str
    source_credential_authorization_hash: str
    source_endpoint_allowlist_evaluation_hash: str
    source_dispatch_readiness_hash: str
    source_live_adapter_dry_run_request_hash: str

    human_approval_requirement_resolution_id: str
    human_approval_requirement_resolution_hash: str
    human_approval_requirement_resolution_packet: dict[str, Any]
    action_contract_snapshot: dict[str, Any]
    action_contract_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    required_human_approval: bool
    requirement_state: Literal[*REQUIREMENT_STATES]
    requirement_satisfaction_state: Literal[*SATISFACTION_STATES]

    source_required_human_approval_linkage_review_id: str | None
    source_required_human_approval_linkage_review_hash: str | None
    source_required_human_approval_linkage_review_packet: dict[str, Any] | None

    request_descriptor: dict[str, Any]
    execution_intent: dict[str, Any]
    execution_intent_id: str
    execution_intent_hash: str
    adapter_contract_descriptor: dict[str, Any]
    adapter_contract_id: str
    adapter_contract_hash: str
    adapter_contract_version: str
    endpoint_candidate: dict[str, Any]
    endpoint_candidate_digest: str
    endpoint_identity_binding: dict[str, Any]
    endpoint_identity_binding_digest: str
    credential_reference: dict[str, Any]
    credential_reference_digest: str
    credential_scope_binding: dict[str, Any]
    credential_scope_binding_digest: str
    operator_review_decision: dict[str, Any]
    operator_review_decision_digest: str
    bind_pre_dispatch_review_decision: dict[str, Any]
    bind_pre_dispatch_review_decision_digest: str
    authority_evidence_reference_bundle: dict[str, Any]
    authority_evidence_reference_bundle_digest: str
    authority_evidence_linkage_result: dict[str, Any]
    authority_evidence_linkage_result_digest: str
    source_to_execution_intent_mapping: dict[str, Any]
    field_mapping_proof: dict[str, Any]
    required_field_presence: dict[str, str]
    source_decision_identity: dict[str, Any]
    candidate_identity: dict[str, Any]
    evidence_lineage: dict[str, Any]
    replay_summary: dict[str, Any]

    human_approval_reference_bundle: dict[str, Any]
    human_approval_reference_bundle_digest: str
    human_approval_linkage_result: HumanApprovalRequirementSatisfactionResult
    human_approval_linkage_result_digest: str
    human_approval_binding_matrix: tuple[dict[str, Any], ...]
    human_approval_binding_matrix_digest: str
    human_approval_linkage_checks: tuple[dict[str, Any], ...]
    human_approval_linkage_check_digest: str
    future_bind_authorization_requirements: tuple[dict[str, Any], ...]
    future_bind_authorization_requirement_digest: str

    human_approval_linkage_status: Literal[STATUS]
    request_dispatch_state: Literal["NOT_DISPATCHED"]
    bind_state: Literal["NOT_BOUND"]
    authority_state: Literal["NOT_AUTHORIZED"]
    human_approval_state: Literal["NOT_APPROVED"]
    human_approval_created: Literal[False]
    authority_evidence_created: Literal[False]
    execution_authority_created: Literal[False]
    bind_authorization_created: Literal[False]
    bind_invoked: Literal[False]
    bind_receipt_created: Literal[False]
    trustlog_written: Literal[False]
    request_dispatched: Literal[False]
    endpoint_resolved: Literal[False]
    credential_material_accessed: Literal[False]
    authorization_header_constructed: Literal[False]
    network_used: Literal[False]
    live_adapter_instantiated: Literal[False]
    webhook_called: Literal[False]
    fail_closed: Literal[False]
    scope_limitations: tuple[str, ...]


def _timestamp(value: Any) -> str:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise LiveAdapterDryRunHumanApprovalRequirementSatisfactionError(
            "LADHARS_TIMESTAMP_INVALID"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LiveAdapterDryRunHumanApprovalRequirementSatisfactionError(
            "LADHARS_TIMESTAMP_INVALID"
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
    raise LiveAdapterDryRunHumanApprovalRequirementSatisfactionError(
        "LADHARS_INVALID_JSON_VALUE"
    )


def _digest(domain: str, value: Any) -> str:
    encoded = json.dumps(
        {"domain": domain, "value": _json(value)},
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _packet_hash(raw: dict[str, Any]) -> str:
    omitted = {
        "live_adapter_dry_run_human_approval_linkage_review_id",
        "live_adapter_dry_run_human_approval_linkage_review_hash",
    }
    return _digest(
        DOMAIN,
        {key: value for key, value in raw.items() if key not in omitted},
    )


def _authority_source(
    value: Any,
) -> CanonicalLiveAdapterDryRunAuthorityEvidenceLinkageReviewPacket:
    try:
        source = verify_live_adapter_dry_run_authority_evidence_linkage_review_packet(
            value
        )
    except (
        LiveAdapterDryRunAuthorityEvidenceLinkageError,
        TypeError,
        ValueError,
    ) as exc:
        raise LiveAdapterDryRunHumanApprovalRequirementSatisfactionError(
            "LADHARS_AUTHORITY_SOURCE_INVALID"
        ) from exc
    result = source.authority_evidence_linkage_result
    if source.fail_closed or not (
        result.all_required_references_present
        and result.all_references_structurally_linked
        and result.all_binding_claims_matched
    ):
        raise LiveAdapterDryRunHumanApprovalRequirementSatisfactionError(
            "LADHARS_AUTHORITY_SOURCE_REJECTED"
        )
    return source


def _resolution(
    value: Any,
) -> CanonicalHumanApprovalRequirementResolutionPacket:
    try:
        return verify_human_approval_requirement_resolution_packet(value)
    except (
        HumanApprovalRequirementResolutionError,
        TypeError,
        ValueError,
    ) as exc:
        raise LiveAdapterDryRunHumanApprovalRequirementSatisfactionError(
            "LADHARS_REQUIREMENT_RESOLUTION_INVALID"
        ) from exc


def _contract(value: Any) -> ActionClassContract:
    try:
        raw = value.to_dict() if isinstance(value, ActionClassContract) else _json(value)
        return validate_action_class_contract(raw)
    except (
        ActionClassContractValidationError,
        TypeError,
        ValueError,
    ) as exc:
        raise LiveAdapterDryRunHumanApprovalRequirementSatisfactionError(
            "LADHARS_ACTION_CONTRACT_INVALID"
        ) from exc


def _required_linkage(
    value: Any,
) -> CanonicalLiveAdapterDryRunHumanApprovalLinkageReviewPacket:
    try:
        return verify_live_adapter_dry_run_human_approval_linkage_review_packet(value)
    except (
        LiveAdapterDryRunHumanApprovalLinkageError,
        TypeError,
        ValueError,
    ) as exc:
        raise LiveAdapterDryRunHumanApprovalRequirementSatisfactionError(
            "LADHARS_REQUIRED_LINKAGE_INVALID"
        ) from exc


def _validate_resolution_binding(
    source: CanonicalLiveAdapterDryRunAuthorityEvidenceLinkageReviewPacket,
    resolution: CanonicalHumanApprovalRequirementResolutionPacket,
    contract: ActionClassContract,
) -> None:
    expected_required = requires_human_approval_for_action_contract(contract)
    expected_state = (
        "REQUIRED" if expected_required else "NOT_REQUIRED_BY_ACTION_CONTRACT"
    )
    expected_scope = tuple(
        source.authority_evidence_reference_bundle.bundle_scope
    )
    checks = (
        resolution.source_authority_evidence_linkage_review_id
        == source.live_adapter_dry_run_authority_evidence_linkage_review_id,
        resolution.source_authority_evidence_linkage_review_hash
        == source.live_adapter_dry_run_authority_evidence_linkage_review_hash,
        resolution.source_execution_intent_id == source.execution_intent_id,
        resolution.source_execution_intent_hash == source.execution_intent_hash,
        resolution.action_contract_id == contract.id,
        resolution.action_contract_version == contract.version,
        resolution.action_contract_digest == contract.deterministic_digest(),
        resolution.action_class == contract.action_class,
        tuple(resolution.requested_scope) == expected_scope,
        resolution.required_human_approval is expected_required,
        resolution.requirement_state == expected_state,
    )
    if not all(checks):
        raise LiveAdapterDryRunHumanApprovalRequirementSatisfactionError(
            "LADHARS_REQUIREMENT_RESOLUTION_BINDING_MISMATCH"
        )


def _validate_required_linkage_binding(
    source: CanonicalLiveAdapterDryRunAuthorityEvidenceLinkageReviewPacket,
    linkage: CanonicalLiveAdapterDryRunHumanApprovalLinkageReviewPacket,
) -> None:
    source_raw = source.model_dump(mode="json")
    linkage_raw = linkage.model_dump(mode="json")
    if (
        linkage.source_authority_evidence_linkage_review_id
        != source.live_adapter_dry_run_authority_evidence_linkage_review_id
        or linkage.source_authority_evidence_linkage_review_hash
        != source.live_adapter_dry_run_authority_evidence_linkage_review_hash
        or any(
            _json(linkage_raw[field]) != _json(source_raw[field])
            for field in COPIED_FIELDS
        )
    ):
        raise LiveAdapterDryRunHumanApprovalRequirementSatisfactionError(
            "LADHARS_REQUIRED_LINKAGE_SOURCE_MISMATCH"
        )
    result = linkage.human_approval_linkage_result
    if linkage.fail_closed or not (
        result.all_required_approval_references_present
        and result.all_approval_references_structurally_linked
        and result.all_binding_claims_matched
    ):
        raise LiveAdapterDryRunHumanApprovalRequirementSatisfactionError(
            "LADHARS_REQUIRED_LINKAGE_REJECTED"
        )


def _requirements() -> list[dict[str, Any]]:
    return [
        {
            "ordinal": ordinal,
            "name": name,
            "separate_future_artifact_required": True,
            "satisfied_by_this_packet": False,
        }
        for ordinal, name in enumerate(BIND_REQUIREMENTS, 1)
    ]


def _empty_bundle(
    resolution: CanonicalHumanApprovalRequirementResolutionPacket,
    recorded_at: str,
) -> dict[str, Any]:
    return {
        "human_approval_reference_bundle_id": (
            "approval-not-required:v1:"
            + resolution.human_approval_requirement_resolution_hash
        ),
        "bundle_declared_by": "veritas:action-contract-requirement-resolution",
        "bundle_declared_at": recorded_at,
        "bundle_scope": list(resolution.requested_scope),
        "human_approval_references": [],
        "human_approval_binding_claims": [],
        "bundle_limitations": [
            "human-approval-not-required-by-action-contract",
            "no-human-approval-created",
            "no-external-verification",
        ],
    }


def _derive(
    source: CanonicalLiveAdapterDryRunAuthorityEvidenceLinkageReviewPacket,
    resolution: CanonicalHumanApprovalRequirementResolutionPacket,
    required_linkage: CanonicalLiveAdapterDryRunHumanApprovalLinkageReviewPacket | None,
    recorded_at: str,
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    HumanApprovalRequirementSatisfactionResult,
    list[dict[str, Any]],
    list[dict[str, Any]],
    str | None,
    str | None,
    dict[str, Any] | None,
]:
    required = resolution.required_human_approval
    if required:
        if required_linkage is None:
            raise LiveAdapterDryRunHumanApprovalRequirementSatisfactionError(
                "LADHARS_REQUIRED_LINKAGE_MISSING"
            )
        _validate_required_linkage_binding(source, required_linkage)
        child = required_linkage.model_dump(mode="json")
        bundle = _json(child["human_approval_reference_bundle"])
        matrix = _json(child["human_approval_binding_matrix"])
        rejected = tuple(
            child["human_approval_linkage_result"][
                "rejected_approval_reference_ids"
            ]
        )
        reasons = tuple(
            child["human_approval_linkage_result"]["rejection_reasons"]
        )
        satisfaction_state = "SATISFIED_BY_VERIFIED_HUMAN_APPROVAL_LINKAGE"
        child_id = required_linkage.live_adapter_dry_run_human_approval_linkage_review_id
        child_hash = (
            required_linkage.live_adapter_dry_run_human_approval_linkage_review_hash
        )
        child_packet = child
        branch_check = "required_path_verified_human_approval_linkage"
    else:
        if required_linkage is not None:
            raise LiveAdapterDryRunHumanApprovalRequirementSatisfactionError(
                "LADHARS_APPROVAL_LINKAGE_UNEXPECTED_FOR_CONTRACT"
            )
        bundle = _empty_bundle(resolution, recorded_at)
        matrix = []
        rejected = ()
        reasons = ()
        satisfaction_state = "SATISFIED_AS_NOT_REQUIRED_BY_ACTION_CONTRACT"
        child_id = None
        child_hash = None
        child_packet = None
        branch_check = "not_required_path_contract_exemption_verified"

    result = HumanApprovalRequirementSatisfactionResult(
        all_required_approval_references_present=True,
        all_approval_references_structurally_linked=True,
        all_binding_claims_matched=True,
        approval_requirement_satisfied=True,
        required_human_approval=required,
        requirement_state=resolution.requirement_state,
        satisfaction_state=satisfaction_state,
        approval_linkage_used=required,
        rejected_approval_reference_ids=rejected,
        rejection_reasons=reasons,
        comparison_mode=CHECK_MODE,
        semantic_match_used=False,
        creates_human_approval=False,
        creates_authority_evidence=False,
        creates_execution_authority=False,
        creates_bind_authorization=False,
    )

    common_names = [
        "source_authority_evidence_linkage_verified",
        "human_approval_requirement_resolution_verified",
        "resolution_bound_to_authority_source",
        "action_contract_snapshot_validated",
        "action_contract_digest_matched",
        "approval_requirement_recomputed_from_contract",
        branch_check,
        "approval_requirement_satisfied",
        "human_approval_not_created",
        "execution_authority_not_created",
        "bind_authorization_not_created",
        "bind_not_invoked",
        "credential_material_not_accessed",
        "network_not_used",
        "future_bind_authorization_gate_required",
    ]
    resolution_hash = resolution.human_approval_requirement_resolution_hash
    checks = [
        {
            "check_id": f"ladhars-check:v1:{ordinal}:{name.replace('_', '-')}",
            "ordinal": ordinal,
            "name": name,
            "mode": CHECK_MODE,
            "passed": True,
            "evidence_ref": f"resolution:{resolution_hash}:{name}",
            "human_approval_created": False,
            "authority_evidence_created": False,
            "execution_authority_created": False,
            "bind_authorization_created": False,
            "bind_invoked": False,
            "bind_receipt_created": False,
            "trustlog_written": False,
            "request_dispatched": False,
            "credential_material_accessed": False,
            "authorization_header_constructed": False,
            "network_used": False,
            "external_effect_used": False,
        }
        for ordinal, name in enumerate(common_names, 1)
    ]
    return (
        bundle,
        matrix,
        result,
        checks,
        _requirements(),
        child_id,
        child_hash,
        child_packet,
    )


def build_live_adapter_dry_run_human_approval_requirement_satisfaction_packet(
    source_authority_evidence_linkage_review_packet: Any,
    human_approval_requirement_resolution_packet: Any,
    action_contract: ActionClassContract,
    required_human_approval_linkage_review_packet: Any | None,
    human_approval_linkage_review_recorded_at: datetime,
) -> CanonicalLiveAdapterDryRunHumanApprovalRequirementSatisfactionPacket:
    """Build a fail-closed bridge for both REQUIRED and NOT_REQUIRED paths."""
    source = _authority_source(_json(source_authority_evidence_linkage_review_packet))
    resolution = _resolution(_json(human_approval_requirement_resolution_packet))
    contract = _contract(action_contract)
    _validate_resolution_binding(source, resolution, contract)

    required_linkage = (
        _required_linkage(_json(required_human_approval_linkage_review_packet))
        if required_human_approval_linkage_review_packet is not None
        else None
    )
    recorded_at = _timestamp(human_approval_linkage_review_recorded_at)
    (
        bundle,
        matrix,
        result,
        checks,
        requirements,
        child_id,
        child_hash,
        child_packet,
    ) = _derive(source, resolution, required_linkage, recorded_at)

    source_raw = source.model_dump(mode="json")
    resolution_raw = resolution.model_dump(mode="json")
    raw = {
        "format_version": FORMAT_VERSION,
        "human_approval_linkage_review_mechanism": MECHANISM,
        "human_approval_linkage_review_recorded_at": recorded_at,
        "source_authority_evidence_linkage_review_id": (
            source.live_adapter_dry_run_authority_evidence_linkage_review_id
        ),
        "source_authority_evidence_linkage_review_hash": (
            source.live_adapter_dry_run_authority_evidence_linkage_review_hash
        ),
        "source_authority_evidence_linkage_review_packet": source_raw,
        "source_bind_pre_dispatch_review_hash": source.source_bind_pre_dispatch_review_hash,
        "source_operator_dispatch_review_hash": source.source_operator_dispatch_review_hash,
        "source_credential_authorization_hash": source.source_credential_authorization_hash,
        "source_endpoint_allowlist_evaluation_hash": (
            source.source_endpoint_allowlist_evaluation_hash
        ),
        "source_dispatch_readiness_hash": source.source_dispatch_readiness_hash,
        "source_live_adapter_dry_run_request_hash": (
            source.source_live_adapter_dry_run_request_hash
        ),
        "human_approval_requirement_resolution_id": (
            resolution.human_approval_requirement_resolution_id
        ),
        "human_approval_requirement_resolution_hash": (
            resolution.human_approval_requirement_resolution_hash
        ),
        "human_approval_requirement_resolution_packet": resolution_raw,
        "action_contract_snapshot": contract.to_dict(),
        "action_contract_digest": contract.deterministic_digest(),
        "required_human_approval": resolution.required_human_approval,
        "requirement_state": resolution.requirement_state,
        "requirement_satisfaction_state": result.satisfaction_state,
        "source_required_human_approval_linkage_review_id": child_id,
        "source_required_human_approval_linkage_review_hash": child_hash,
        "source_required_human_approval_linkage_review_packet": child_packet,
        **{field: source_raw[field] for field in COPIED_FIELDS},
        "human_approval_reference_bundle": bundle,
        "human_approval_reference_bundle_digest": _digest(BUNDLE_DOMAIN, bundle),
        "human_approval_linkage_result": result.model_dump(mode="json"),
        "human_approval_linkage_result_digest": _digest(RESULT_DOMAIN, result),
        "human_approval_binding_matrix": matrix,
        "human_approval_binding_matrix_digest": _digest(MATRIX_DOMAIN, matrix),
        "human_approval_linkage_checks": checks,
        "human_approval_linkage_check_digest": _digest(CHECKS_DOMAIN, checks),
        "future_bind_authorization_requirements": requirements,
        "future_bind_authorization_requirement_digest": _digest(
            REQUIREMENTS_DOMAIN, requirements
        ),
        "human_approval_linkage_status": STATUS,
        "request_dispatch_state": "NOT_DISPATCHED",
        "bind_state": "NOT_BOUND",
        "authority_state": "NOT_AUTHORIZED",
        "human_approval_state": "NOT_APPROVED",
        "human_approval_created": False,
        "authority_evidence_created": False,
        "execution_authority_created": False,
        "bind_authorization_created": False,
        "bind_invoked": False,
        "bind_receipt_created": False,
        "trustlog_written": False,
        "request_dispatched": False,
        "endpoint_resolved": False,
        "credential_material_accessed": False,
        "authorization_header_constructed": False,
        "network_used": False,
        "live_adapter_instantiated": False,
        "webhook_called": False,
        "fail_closed": False,
        "scope_limitations": SCOPE_LIMITATIONS,
    }
    digest = _packet_hash(raw)
    raw["live_adapter_dry_run_human_approval_linkage_review_hash"] = digest
    raw["live_adapter_dry_run_human_approval_linkage_review_id"] = (
        f"ladhars:v1:sha256:{digest}"
    )
    return verify_live_adapter_dry_run_human_approval_requirement_satisfaction_packet(
        raw
    )


def verify_live_adapter_dry_run_human_approval_requirement_satisfaction_packet(
    raw: Any,
) -> CanonicalLiveAdapterDryRunHumanApprovalRequirementSatisfactionPacket:
    """Reverify source, contract requirement, branch choice, and packet hash."""
    try:
        value = raw.model_dump(mode="json") if isinstance(raw, BaseModel) else raw
        packet = (
            CanonicalLiveAdapterDryRunHumanApprovalRequirementSatisfactionPacket
            .model_validate(_json(value))
        )
    except (
        ValidationError,
        TypeError,
        LiveAdapterDryRunHumanApprovalRequirementSatisfactionError,
    ) as exc:
        raise LiveAdapterDryRunHumanApprovalRequirementSatisfactionError(
            "LADHARS_PACKET_INVALID"
        ) from exc

    actual = packet.model_dump(mode="json")
    source = _authority_source(packet.source_authority_evidence_linkage_review_packet)
    resolution = _resolution(packet.human_approval_requirement_resolution_packet)
    contract = _contract(packet.action_contract_snapshot)
    _validate_resolution_binding(source, resolution, contract)

    child = (
        _required_linkage(packet.source_required_human_approval_linkage_review_packet)
        if packet.source_required_human_approval_linkage_review_packet is not None
        else None
    )
    recorded_at = _timestamp(packet.human_approval_linkage_review_recorded_at)
    (
        bundle,
        matrix,
        result,
        checks,
        requirements,
        child_id,
        child_hash,
        child_packet,
    ) = _derive(source, resolution, child, recorded_at)

    source_raw = source.model_dump(mode="json")
    resolution_raw = resolution.model_dump(mode="json")
    identities = (
        packet.source_authority_evidence_linkage_review_id
        == source.live_adapter_dry_run_authority_evidence_linkage_review_id,
        packet.source_authority_evidence_linkage_review_hash
        == source.live_adapter_dry_run_authority_evidence_linkage_review_hash,
        packet.human_approval_requirement_resolution_id
        == resolution.human_approval_requirement_resolution_id,
        packet.human_approval_requirement_resolution_hash
        == resolution.human_approval_requirement_resolution_hash,
        _json(packet.human_approval_requirement_resolution_packet) == resolution_raw,
        packet.action_contract_digest == contract.deterministic_digest(),
        packet.required_human_approval is resolution.required_human_approval,
        packet.requirement_state == resolution.requirement_state,
        packet.requirement_satisfaction_state == result.satisfaction_state,
        packet.source_required_human_approval_linkage_review_id == child_id,
        packet.source_required_human_approval_linkage_review_hash == child_hash,
        _json(packet.source_required_human_approval_linkage_review_packet)
        == _json(child_packet),
    )
    if not all(identities):
        raise LiveAdapterDryRunHumanApprovalRequirementSatisfactionError(
            "LADHARS_IDENTITY_MISMATCH"
        )

    if any(
        _json(getattr(packet, field)) != _json(source_raw[field])
        for field in COPIED_FIELDS
    ):
        raise LiveAdapterDryRunHumanApprovalRequirementSatisfactionError(
            "LADHARS_SOURCE_MISMATCH"
        )

    expected = (
        _json(packet.human_approval_reference_bundle) == _json(bundle),
        packet.human_approval_reference_bundle_digest
        == _digest(BUNDLE_DOMAIN, bundle),
        _json(packet.human_approval_linkage_result)
        == _json(result.model_dump(mode="json")),
        packet.human_approval_linkage_result_digest
        == _digest(RESULT_DOMAIN, result),
        _json(packet.human_approval_binding_matrix) == _json(matrix),
        packet.human_approval_binding_matrix_digest == _digest(MATRIX_DOMAIN, matrix),
        _json(packet.human_approval_linkage_checks) == _json(checks),
        packet.human_approval_linkage_check_digest == _digest(CHECKS_DOMAIN, checks),
        _json(packet.future_bind_authorization_requirements)
        == _json(requirements),
        packet.future_bind_authorization_requirement_digest
        == _digest(REQUIREMENTS_DOMAIN, requirements),
        packet.scope_limitations == SCOPE_LIMITATIONS,
        packet.fail_closed is False,
    )
    if not all(expected):
        raise LiveAdapterDryRunHumanApprovalRequirementSatisfactionError(
            "LADHARS_DERIVED_MISMATCH"
        )

    effect_values = (
        packet.human_approval_created,
        packet.authority_evidence_created,
        packet.execution_authority_created,
        packet.bind_authorization_created,
        packet.bind_invoked,
        packet.bind_receipt_created,
        packet.trustlog_written,
        packet.request_dispatched,
        packet.endpoint_resolved,
        packet.credential_material_accessed,
        packet.authorization_header_constructed,
        packet.network_used,
        packet.live_adapter_instantiated,
        packet.webhook_called,
    )
    if any(effect_values):
        raise LiveAdapterDryRunHumanApprovalRequirementSatisfactionError(
            "LADHARS_EFFECT_INVALID"
        )

    digest = _packet_hash(actual)
    if packet.live_adapter_dry_run_human_approval_linkage_review_hash != digest:
        raise LiveAdapterDryRunHumanApprovalRequirementSatisfactionError(
            "LADHARS_HASH_MISMATCH"
        )
    if (
        packet.live_adapter_dry_run_human_approval_linkage_review_id
        != f"ladhars:v1:sha256:{digest}"
    ):
        raise LiveAdapterDryRunHumanApprovalRequirementSatisfactionError(
            "LADHARS_ID_MISMATCH"
        )
    return packet
