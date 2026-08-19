"""Record local Authority Evidence reference linkage without creating authority.

Only caller-supplied metadata is validated and content-addressed.  The module
does not resolve evidence, credentials, endpoints, or perform external effects.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from veritas_os.policy.live_adapter_dry_run_bind_pre_dispatch_review import (
    CanonicalLiveAdapterDryRunBindPreDispatchReviewPacket,
    LiveAdapterDryRunBindPreDispatchReviewError,
    verify_live_adapter_dry_run_bind_pre_dispatch_review_packet,
)

FORMAT_VERSION = (
    "canonical-live-adapter-dry-run-authority-evidence-linkage-review/v1"
)
REVIEW_MECHANISM = (
    "review_live_adapter_dry_run_authority_evidence_linkage_without_"
    "authority_creation/v1"
)
STATUS = "LIVE_ADAPTER_DRY_RUN_AUTHORITY_EVIDENCE_LINKAGE_REVIEWED_NOT_AUTHORIZED"
SOURCE_STATUS = "LIVE_ADAPTER_DRY_RUN_BIND_PRE_DISPATCH_REVIEW_RECORDED_NOT_BOUND"
CHECK_MODE = "deterministic_local_authority_evidence_linkage_review_only"
BINDING_MODE = "deterministic_local_authority_reference_binding_only"
DECLARED_STATES = (
    "DECLARED_VERIFIED_BY_UPSTREAM_ARTIFACT",
    "DECLARED_PENDING_EXTERNAL_VERIFICATION",
    "DECLARED_REJECTED_BY_UPSTREAM_ARTIFACT",
)
DOMAINS = {
    "bundle": "veritas.live-adapter-dry-run-authority-evidence-linkage.reference-bundle/v1",
    "matrix": "veritas.live-adapter-dry-run-authority-evidence-linkage.binding-matrix/v1",
    "result": "veritas.live-adapter-dry-run-authority-evidence-linkage.result/v1",
    "checks": "veritas.live-adapter-dry-run-authority-evidence-linkage.checks/v1",
    "human": "veritas.live-adapter-dry-run-authority-evidence-linkage.future-human-approval-requirements/v1",
    "bind": "veritas.live-adapter-dry-run-authority-evidence-linkage.future-bind-authorization-requirements/v1",
    "packet": "veritas.live-adapter-dry-run-authority-evidence-linkage.packet/v1",
}
CHECK_NAMES = (
    "source_bind_pre_dispatch_review_verified", "source_request_not_dispatched",
    "source_bind_not_invoked", "source_bind_pre_dispatch_review_accepted",
    "authority_evidence_reference_bundle_closed_schema_valid",
    "authority_evidence_references_present", "authority_evidence_reference_ids_unique",
    "authority_evidence_reference_hashes_present", "authority_policy_ids_present",
    "authority_scope_present", "declared_verification_state_allowed",
    "rejected_declared_verification_state_fails_closed",
    "pending_declared_verification_state_fails_closed",
    "authority_expiry_checked_against_recorded_at",
    "expired_authority_reference_fails_closed", "execution_intent_id_exactly_linked",
    "adapter_contract_id_exactly_linked", "endpoint_candidate_id_exactly_linked",
    "credential_reference_id_exactly_linked", "target_system_exactly_linked",
    "target_resource_scope_exactly_linked", "purpose_exactly_linked",
    "authority_evidence_binding_matrix_constructed", "all_binding_claims_matched",
    "request_descriptor_preserved", "execution_intent_identity_preserved",
    "adapter_contract_identity_preserved", "endpoint_identity_binding_preserved",
    "credential_scope_binding_preserved", "bind_pre_dispatch_review_decision_preserved",
    "authority_evidence_not_created", "human_approval_not_created",
    "execution_authority_not_created", "bind_authorization_not_created",
    "bind_not_invoked", "bind_receipt_not_created", "trustlog_not_written",
    "request_not_dispatched", "endpoint_not_resolved",
    "credential_material_not_accessed", "authorization_header_not_constructed",
    "network_not_used", "webhook_not_called", "live_adapter_not_instantiated",
    "future_human_approval_gate_required", "future_bind_authorization_gate_required",
)
EFFECT_FIELDS = (
    "authority_evidence_created", "human_approval_created",
    "execution_authority_created", "bind_authorization_created", "bind_invoked",
    "bind_receipt_created", "trustlog_written", "request_dispatched",
    "endpoint_resolved", "credential_material_accessed",
    "credential_material_embedded", "authorization_header_constructed",
    "token_embedded", "secret_embedded", "network_used", "dns_used",
    "webhook_called", "live_adapter_instantiated", "live_adapter_method_called",
    "external_effect_used", "filesystem_used", "database_used", "provider_used",
    "subprocess_used", "operation_committed",
)
SCOPE_LIMITATIONS = (
    "NOT_DISPATCHED", "NOT_BIND_INVOCATION", "NOT_BIND_AUTHORIZATION",
    "NOT_BIND_RECEIPT", "NOT_TRUSTLOG_WRITE", "NOT_EXECUTION_AUTHORITY",
    "NOT_HUMAN_APPROVAL", "NOT_AUTHORITY_EVIDENCE",
    "NOT_AUTHORITY_EVIDENCE_CREATION",
    "NOT_AUTHORITY_EVIDENCE_EXTERNAL_VERIFICATION", "NOT_CREDENTIAL_RESOLUTION",
    "NOT_CREDENTIAL_ACCESS", "NOT_CREDENTIAL_EMBEDDING",
    "NOT_AUTHORIZATION_HEADER", "NOT_TOKEN", "NOT_SECRET",
    "NOT_ENDPOINT_RESOLUTION", "NOT_DNS_RESOLUTION", "NOT_NETWORK_CALL",
    "NOT_WEBHOOK_CALL", "NOT_LIVE_ADAPTER_INSTANCE", "NOT_LIVE_ADAPTER_RESULT",
    "NOT_OPERATION_COMMIT", "NOT_PRODUCTION_CLAIM", "NOT_CUSTOMER_CLAIM",
    "NOT_REGULATORY_CERTIFICATION",
)
HUMAN_REQUIREMENTS = (
    "explicit_human_approval_where_required", "approver_identity",
    "approver_authority_or_role", "approval_scope_binding", "approval_timestamp",
    "approval_expiry_or_freshness_boundary", "approval_reason",
    "acknowledgement_approval_is_not_execution_by_itself",
    "acknowledgement_bind_authorization_remains_separate",
)
BIND_REQUIREMENTS = (
    "valid_authority_evidence_through_real_authority_verification_path",
    "valid_human_approval_where_required", "final_policy_admissibility",
    "final_runtime_risk_review", "final_endpoint_identity_binding",
    "final_credential_resolution_boundary",
    "final_authorization_header_construction_boundary", "idempotency_key_binding",
    "request_dispatch_boundary", "bind_invocation_boundary",
    "bind_receipt_creation_boundary", "trustlog_write_boundary_after_bind",
    "postcondition_and_rollback_requirements_for_later_apply_path",
)
COPIED_FIELDS = (
    "request_descriptor", "execution_intent", "execution_intent_id",
    "execution_intent_hash", "adapter_contract_descriptor", "adapter_contract_id",
    "adapter_contract_hash", "adapter_contract_version", "endpoint_candidate",
    "endpoint_candidate_digest", "endpoint_identity_binding",
    "endpoint_identity_binding_digest", "credential_reference",
    "credential_reference_digest", "credential_scope_binding",
    "credential_scope_binding_digest", "operator_review_decision",
    "operator_review_decision_digest", "bind_pre_dispatch_review_decision",
    "bind_pre_dispatch_review_decision_digest", "source_to_execution_intent_mapping",
    "field_mapping_proof", "required_field_presence", "source_decision_identity",
    "candidate_identity", "evidence_lineage", "replay_summary",
)


class LiveAdapterDryRunAuthorityEvidenceLinkageError(ValueError):
    """Stable fail-closed error for invalid linkage review evidence."""


class AuthorityEvidenceReference(BaseModel):
    """Closed metadata-only reference; no referenced resource is accessed."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    authority_evidence_reference_id: str = Field(min_length=1)
    authority_evidence_kind: str = Field(min_length=1)
    authority_source_type: str = Field(min_length=1)
    authority_source_id: str = Field(min_length=1)
    authority_policy_id: str = Field(min_length=1)
    authority_policy_version: str = Field(min_length=1)
    authority_scope: str = Field(min_length=1)
    authority_subject: str = Field(min_length=1)
    authority_issuer: str = Field(min_length=1)
    authority_issued_at: str
    authority_expires_at: str
    authority_evidence_hash: str = Field(min_length=1)
    authority_evidence_format: str = Field(min_length=1)
    declared_verification_state: Literal[*DECLARED_STATES]
    linked_execution_intent_id: str = Field(min_length=1)
    linked_adapter_contract_id: str = Field(min_length=1)
    linked_endpoint_candidate_id: str = Field(min_length=1)
    linked_credential_reference_id: str = Field(min_length=1)
    linked_target_system: str = Field(min_length=1)
    linked_target_resource_scope: str = Field(min_length=1)
    linked_purpose: str = Field(min_length=1)


class AuthorityEvidenceBindingClaim(BaseModel):
    """One caller-declared exact local comparison claim."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    binding_claim_id: str = Field(min_length=1)
    authority_evidence_reference_id: str = Field(min_length=1)
    claim_type: str = Field(min_length=1)
    expected_value: str
    actual_value: str
    matched: bool
    comparison_mode: Literal[BINDING_MODE]


class AuthorityEvidenceReferenceBundle(BaseModel):
    """Closed collection of declared Authority Evidence reference metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    authority_evidence_reference_bundle_id: str = Field(min_length=1)
    bundle_declared_by: str = Field(min_length=1)
    bundle_declared_at: str
    bundle_scope: tuple[str, ...] = Field(min_length=1)
    authority_evidence_references: tuple[AuthorityEvidenceReference, ...]
    authority_evidence_binding_claims: tuple[AuthorityEvidenceBindingClaim, ...]
    bundle_limitations: tuple[str, ...] = Field(min_length=1)


class AuthorityEvidenceLinkageResult(BaseModel):
    """Deterministic result that explicitly creates no authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    all_required_references_present: bool
    all_references_structurally_linked: bool
    all_binding_claims_matched: bool
    rejected_reference_ids: tuple[str, ...]
    rejection_reasons: tuple[str, ...]
    comparison_mode: Literal[CHECK_MODE]
    semantic_match_used: Literal[False]
    creates_authority_evidence: Literal[False]
    creates_human_approval: Literal[False]
    creates_execution_authority: Literal[False]
    creates_bind_authorization: Literal[False]


class AuthorityEvidenceLinkageCheck(BaseModel):
    """One ordered deterministic check with false effect flags."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    check_id: str
    ordinal: int = Field(ge=1, le=46)
    name: Literal[*CHECK_NAMES]
    mode: Literal[CHECK_MODE]
    passed: Literal[True]
    evidence_ref: str
    authority_evidence_created: Literal[False]
    human_approval_created: Literal[False]
    execution_authority_created: Literal[False]
    bind_authorization_created: Literal[False]
    bind_invoked: Literal[False]
    bind_receipt_created: Literal[False]
    trustlog_written: Literal[False]
    request_dispatched: Literal[False]
    endpoint_resolved: Literal[False]
    credential_material_accessed: Literal[False]
    credential_material_embedded: Literal[False]
    authorization_header_constructed: Literal[False]
    token_embedded: Literal[False]
    secret_embedded: Literal[False]
    network_used: Literal[False]
    dns_used: Literal[False]
    webhook_called: Literal[False]
    live_adapter_instantiated: Literal[False]
    live_adapter_method_called: Literal[False]
    external_effect_used: Literal[False]
    filesystem_used: Literal[False]
    database_used: Literal[False]
    provider_used: Literal[False]
    subprocess_used: Literal[False]
    operation_committed: Literal[False]


class FutureRequirement(BaseModel):
    """A separate future proof that this packet does not satisfy."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    ordinal: int
    name: str
    separate_future_artifact_required: Literal[True]
    satisfied_by_this_packet: Literal[False]


class CanonicalLiveAdapterDryRunAuthorityEvidenceLinkageReviewPacket(BaseModel):
    """Closed, content-addressed, non-authorizing linkage review packet."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    format_version: Literal[FORMAT_VERSION]
    live_adapter_dry_run_authority_evidence_linkage_review_id: str
    live_adapter_dry_run_authority_evidence_linkage_review_hash: str
    authority_evidence_linkage_review_mechanism: Literal[REVIEW_MECHANISM]
    authority_evidence_linkage_review_recorded_at: str
    source_bind_pre_dispatch_review_id: str
    source_bind_pre_dispatch_review_hash: str
    source_bind_pre_dispatch_review_packet: dict[str, Any]
    source_operator_dispatch_review_hash: str
    source_credential_authorization_hash: str
    source_endpoint_allowlist_evaluation_hash: str
    source_dispatch_readiness_hash: str
    source_live_adapter_dry_run_request_hash: str
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
    authority_evidence_reference_bundle: AuthorityEvidenceReferenceBundle
    authority_evidence_reference_bundle_digest: str
    authority_evidence_linkage_result: AuthorityEvidenceLinkageResult
    authority_evidence_linkage_result_digest: str
    authority_evidence_binding_matrix: tuple[AuthorityEvidenceBindingClaim, ...]
    authority_evidence_binding_matrix_digest: str
    authority_evidence_linkage_checks: tuple[AuthorityEvidenceLinkageCheck, ...]
    authority_evidence_linkage_check_digest: str
    future_human_approval_requirements: tuple[FutureRequirement, ...]
    future_human_approval_requirement_digest: str
    future_bind_authorization_requirements: tuple[FutureRequirement, ...]
    future_bind_authorization_requirement_digest: str
    source_to_execution_intent_mapping: dict[str, Any]
    field_mapping_proof: dict[str, Any]
    required_field_presence: dict[str, str]
    source_decision_identity: dict[str, Any]
    candidate_identity: dict[str, Any]
    evidence_lineage: dict[str, Any]
    replay_summary: dict[str, Any]
    authority_evidence_linkage_status: Literal[STATUS]
    request_dispatch_state: Literal["NOT_DISPATCHED"]
    bind_state: Literal["NOT_BOUND"]
    authority_state: Literal["NOT_AUTHORIZED"]
    authority_evidence_created: Literal[False]
    human_approval_created: Literal[False]
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
    scope_limitations: tuple[Literal[*SCOPE_LIMITATIONS], ...]


def _timestamp(value: Any) -> str:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise LiveAdapterDryRunAuthorityEvidenceLinkageError(
            "LADRAEL_TIMESTAMP_INVALID"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LiveAdapterDryRunAuthorityEvidenceLinkageError(
            "LADRAEL_TIMESTAMP_INVALID"
        )
    return parsed.astimezone(timezone.utc).isoformat()


def _json(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and value == value and value not in (
        float("inf"), float("-inf")
    ):
        return value
    if isinstance(value, datetime):
        return _timestamp(value)
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _json(item) for key, item in value.items()}
    raise LiveAdapterDryRunAuthorityEvidenceLinkageError("LADRAEL_INVALID")


def _digest(domain: str, value: Any) -> str:
    encoded = json.dumps(
        {"domain": domain, "value": _json(value)}, allow_nan=False,
        ensure_ascii=False, separators=(",", ":"), sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _packet_hash(raw: dict[str, Any]) -> str:
    omitted = {
        "live_adapter_dry_run_authority_evidence_linkage_review_id",
        "live_adapter_dry_run_authority_evidence_linkage_review_hash",
    }
    return _digest(DOMAINS["packet"], {k: v for k, v in raw.items() if k not in omitted})


def _source(value: Any) -> CanonicalLiveAdapterDryRunBindPreDispatchReviewPacket:
    try:
        return verify_live_adapter_dry_run_bind_pre_dispatch_review_packet(value)
    except (LiveAdapterDryRunBindPreDispatchReviewError, TypeError, ValueError) as exc:
        raise LiveAdapterDryRunAuthorityEvidenceLinkageError(
            "LADRAEL_SOURCE_INVALID"
        ) from exc


def _source_value(source: CanonicalLiveAdapterDryRunBindPreDispatchReviewPacket,
                  name: str) -> str:
    if name == "endpoint_candidate_id":
        return str(source.endpoint_candidate["endpoint_candidate_id"])
    if name == "credential_reference_id":
        return str(source.credential_reference["credential_reference_id"])
    if name == "target_resource_scope":
        return str(source.credential_reference["target_resource_scope"])
    if name == "purpose":
        return str(source.credential_reference["credential_purpose"])
    if name == "target_system":
        return str(source.credential_reference["target_system"])
    return str(source.execution_intent[name])


def _validate_source(source: CanonicalLiveAdapterDryRunBindPreDispatchReviewPacket) -> None:
    if source.request_dispatch_state != "NOT_DISPATCHED":
        raise LiveAdapterDryRunAuthorityEvidenceLinkageError("LADRAEL_SOURCE_DISPATCHED")
    if source.bind_state != "NOT_BOUND" or source.bind_invoked:
        raise LiveAdapterDryRunAuthorityEvidenceLinkageError("LADRAEL_SOURCE_BOUND")
    if source.bind_pre_dispatch_review_status != SOURCE_STATUS:
        raise LiveAdapterDryRunAuthorityEvidenceLinkageError("LADRAEL_SOURCE_STATUS")
    if source.fail_closed or not (
        source.bind_pre_dispatch_review_result
        .accepted_for_future_bind_dispatch_gate_review
    ):
        raise LiveAdapterDryRunAuthorityEvidenceLinkageError("LADRAEL_SOURCE_REJECTED")


def _bundle(value: Any, recorded_at: str) -> AuthorityEvidenceReferenceBundle:
    try:
        bundle = AuthorityEvidenceReferenceBundle.model_validate(_json(value))
    except (ValidationError, TypeError) as exc:
        raise LiveAdapterDryRunAuthorityEvidenceLinkageError(
            "LADRAEL_BUNDLE_INVALID"
        ) from exc
    references = bundle.authority_evidence_references
    ids = [item.authority_evidence_reference_id for item in references]
    if not references:
        raise LiveAdapterDryRunAuthorityEvidenceLinkageError("LADRAEL_REFERENCES_MISSING")
    if len(ids) != len(set(ids)):
        raise LiveAdapterDryRunAuthorityEvidenceLinkageError("LADRAEL_REFERENCE_IDS_DUPLICATE")
    scopes = {item.authority_scope for item in references}
    if not set(bundle.bundle_scope).issubset(scopes):
        raise LiveAdapterDryRunAuthorityEvidenceLinkageError("LADRAEL_SCOPE_MISSING")
    when = datetime.fromisoformat(recorded_at)
    for item in references:
        if item.declared_verification_state != DECLARED_STATES[0]:
            raise LiveAdapterDryRunAuthorityEvidenceLinkageError("LADRAEL_STATE_FAIL_CLOSED")
        issued = datetime.fromisoformat(_timestamp(item.authority_issued_at))
        expires = datetime.fromisoformat(_timestamp(item.authority_expires_at))
        if expires <= when or issued > when or expires <= issued:
            raise LiveAdapterDryRunAuthorityEvidenceLinkageError("LADRAEL_EXPIRED")
    return bundle


def _matrix(source: CanonicalLiveAdapterDryRunBindPreDispatchReviewPacket,
            bundle: AuthorityEvidenceReferenceBundle) -> list[dict[str, Any]]:
    pairs = (
        ("execution_intent_id", "linked_execution_intent_id", source.execution_intent_id),
        ("adapter_contract_id", "linked_adapter_contract_id", source.adapter_contract_id),
        ("endpoint_candidate_id", "linked_endpoint_candidate_id",
         _source_value(source, "endpoint_candidate_id")),
        ("credential_reference_id", "linked_credential_reference_id",
         _source_value(source, "credential_reference_id")),
        ("target_system", "linked_target_system", _source_value(source, "target_system")),
        ("target_resource_scope", "linked_target_resource_scope",
         _source_value(source, "target_resource_scope")),
        ("purpose", "linked_purpose", _source_value(source, "purpose")),
    )
    matrix = []
    for reference in bundle.authority_evidence_references:
        for claim_type, attribute, expected in pairs:
            actual = str(getattr(reference, attribute))
            matrix.append({
                "binding_claim_id": (
                    f"ladrael-claim:v1:{reference.authority_evidence_reference_id}:"
                    f"{claim_type}"
                ),
                "authority_evidence_reference_id": reference.authority_evidence_reference_id,
                "claim_type": claim_type, "expected_value": expected,
                "actual_value": actual, "matched": expected == actual,
                "comparison_mode": BINDING_MODE,
            })
    return matrix


def _requirements(names: tuple[str, ...]) -> list[dict[str, Any]]:
    return [{"ordinal": ordinal, "name": name,
             "separate_future_artifact_required": True,
             "satisfied_by_this_packet": False}
            for ordinal, name in enumerate(names, 1)]


def _derived(source: CanonicalLiveAdapterDryRunBindPreDispatchReviewPacket,
             bundle: AuthorityEvidenceReferenceBundle) -> tuple[Any, ...]:
    matrix = _matrix(source, bundle)
    supplied_claims = [claim.model_dump(mode="json")
                       for claim in bundle.authority_evidence_binding_claims]
    claims_valid = all(
        claim["matched"] == (claim["expected_value"] == claim["actual_value"])
        and claim["authority_evidence_reference_id"] in {
            ref.authority_evidence_reference_id
            for ref in bundle.authority_evidence_references
        }
        for claim in supplied_claims
    )
    linked = all(claim["matched"] for claim in matrix)
    if not linked or not claims_valid:
        raise LiveAdapterDryRunAuthorityEvidenceLinkageError("LADRAEL_LINK_MISMATCH")
    result = {
        "all_required_references_present": True,
        "all_references_structurally_linked": True,
        "all_binding_claims_matched": True,
        "rejected_reference_ids": [], "rejection_reasons": [],
        "comparison_mode": CHECK_MODE, "semantic_match_used": False,
        "creates_authority_evidence": False, "creates_human_approval": False,
        "creates_execution_authority": False, "creates_bind_authorization": False,
    }
    bundle_digest = _digest(DOMAINS["bundle"], bundle)
    checks = [{
        "check_id": f"ladrael-check:v1:{ordinal}:{name.replace('_', '-')}",
        "ordinal": ordinal, "name": name, "mode": CHECK_MODE, "passed": True,
        "evidence_ref": f"bundle:{bundle_digest}:{name}",
        **{field: False for field in EFFECT_FIELDS},
    } for ordinal, name in enumerate(CHECK_NAMES, 1)]
    return matrix, result, checks, _requirements(HUMAN_REQUIREMENTS), _requirements(BIND_REQUIREMENTS)


def build_live_adapter_dry_run_authority_evidence_linkage_review_packet(
    source_bind_pre_dispatch_review_packet: Any,
    authority_evidence_reference_bundle: Any,
    authority_evidence_linkage_review_recorded_at: datetime,
) -> CanonicalLiveAdapterDryRunAuthorityEvidenceLinkageReviewPacket:
    """Build and self-verify deterministic metadata-only linkage evidence."""
    source = _source(_json(source_bind_pre_dispatch_review_packet))
    _validate_source(source)
    recorded_at = _timestamp(authority_evidence_linkage_review_recorded_at)
    bundle = _bundle(authority_evidence_reference_bundle, recorded_at)
    matrix, result, checks, human, bind = _derived(source, bundle)
    source_raw = source.model_dump(mode="json")
    raw = {
        "format_version": FORMAT_VERSION,
        "authority_evidence_linkage_review_mechanism": REVIEW_MECHANISM,
        "authority_evidence_linkage_review_recorded_at": recorded_at,
        "source_bind_pre_dispatch_review_id": source.live_adapter_dry_run_bind_pre_dispatch_review_id,
        "source_bind_pre_dispatch_review_hash": source.live_adapter_dry_run_bind_pre_dispatch_review_hash,
        "source_bind_pre_dispatch_review_packet": source_raw,
        "source_operator_dispatch_review_hash": source.source_operator_dispatch_review_hash,
        "source_credential_authorization_hash": source.source_credential_authorization_hash,
        "source_endpoint_allowlist_evaluation_hash": source.source_endpoint_allowlist_evaluation_hash,
        "source_dispatch_readiness_hash": source.source_dispatch_readiness_hash,
        "source_live_adapter_dry_run_request_hash": source.source_live_adapter_dry_run_request_hash,
        **{field: source_raw[field] for field in COPIED_FIELDS},
        "authority_evidence_reference_bundle": bundle.model_dump(mode="json"),
        "authority_evidence_reference_bundle_digest": _digest(DOMAINS["bundle"], bundle),
        "authority_evidence_linkage_result": result,
        "authority_evidence_linkage_result_digest": _digest(DOMAINS["result"], result),
        "authority_evidence_binding_matrix": matrix,
        "authority_evidence_binding_matrix_digest": _digest(DOMAINS["matrix"], matrix),
        "authority_evidence_linkage_checks": checks,
        "authority_evidence_linkage_check_digest": _digest(DOMAINS["checks"], checks),
        "future_human_approval_requirements": human,
        "future_human_approval_requirement_digest": _digest(DOMAINS["human"], human),
        "future_bind_authorization_requirements": bind,
        "future_bind_authorization_requirement_digest": _digest(DOMAINS["bind"], bind),
        "authority_evidence_linkage_status": STATUS,
        "request_dispatch_state": "NOT_DISPATCHED", "bind_state": "NOT_BOUND",
        "authority_state": "NOT_AUTHORIZED",
        **{field: False for field in EFFECT_FIELDS if field in {
            "authority_evidence_created", "human_approval_created",
            "execution_authority_created", "bind_authorization_created", "bind_invoked",
            "bind_receipt_created", "trustlog_written", "request_dispatched",
            "endpoint_resolved", "credential_material_accessed",
            "authorization_header_constructed", "network_used",
            "live_adapter_instantiated", "webhook_called",
        }},
        "fail_closed": False, "scope_limitations": SCOPE_LIMITATIONS,
    }
    digest = _packet_hash(raw)
    raw["live_adapter_dry_run_authority_evidence_linkage_review_hash"] = digest
    raw["live_adapter_dry_run_authority_evidence_linkage_review_id"] = (
        f"ladrael:v1:sha256:{digest}"
    )
    return verify_live_adapter_dry_run_authority_evidence_linkage_review_packet(raw)


def verify_live_adapter_dry_run_authority_evidence_linkage_review_packet(
    raw: Any,
) -> CanonicalLiveAdapterDryRunAuthorityEvidenceLinkageReviewPacket:
    """Reverify the source plus every derived value, digest, packet hash and ID."""
    try:
        value = raw.model_dump(mode="json") if isinstance(raw, BaseModel) else raw
        packet = CanonicalLiveAdapterDryRunAuthorityEvidenceLinkageReviewPacket.model_validate(
            _json(value)
        )
    except (ValidationError, TypeError,
            LiveAdapterDryRunAuthorityEvidenceLinkageError) as exc:
        raise LiveAdapterDryRunAuthorityEvidenceLinkageError(
            "LADRAEL_PACKET_INVALID"
        ) from exc
    actual = packet.model_dump(mode="json")
    source = _source(packet.source_bind_pre_dispatch_review_packet)
    _validate_source(source)
    source_raw = source.model_dump(mode="json")
    identities = (
        packet.source_bind_pre_dispatch_review_id == source.live_adapter_dry_run_bind_pre_dispatch_review_id,
        packet.source_bind_pre_dispatch_review_hash == source.live_adapter_dry_run_bind_pre_dispatch_review_hash,
        packet.source_operator_dispatch_review_hash == source.source_operator_dispatch_review_hash,
        packet.source_credential_authorization_hash == source.source_credential_authorization_hash,
        packet.source_endpoint_allowlist_evaluation_hash == source.source_endpoint_allowlist_evaluation_hash,
        packet.source_dispatch_readiness_hash == source.source_dispatch_readiness_hash,
        packet.source_live_adapter_dry_run_request_hash == source.source_live_adapter_dry_run_request_hash,
    )
    if not all(identities) or any(
        _json(getattr(packet, field)) != _json(source_raw[field])
        for field in COPIED_FIELDS
    ):
        raise LiveAdapterDryRunAuthorityEvidenceLinkageError("LADRAEL_SOURCE_MISMATCH")
    recorded_at = _timestamp(packet.authority_evidence_linkage_review_recorded_at)
    bundle = _bundle(packet.authority_evidence_reference_bundle, recorded_at)
    matrix, result, checks, human, bind = _derived(source, bundle)
    expected = (
        packet.authority_evidence_reference_bundle_digest == _digest(DOMAINS["bundle"], bundle),
        _json(packet.authority_evidence_binding_matrix) == matrix,
        packet.authority_evidence_binding_matrix_digest == _digest(DOMAINS["matrix"], matrix),
        _json(packet.authority_evidence_linkage_result) == result,
        packet.authority_evidence_linkage_result_digest == _digest(DOMAINS["result"], result),
        _json(packet.authority_evidence_linkage_checks) == checks,
        packet.authority_evidence_linkage_check_digest == _digest(DOMAINS["checks"], checks),
        _json(packet.future_human_approval_requirements) == human,
        packet.future_human_approval_requirement_digest == _digest(DOMAINS["human"], human),
        _json(packet.future_bind_authorization_requirements) == bind,
        packet.future_bind_authorization_requirement_digest == _digest(DOMAINS["bind"], bind),
        packet.scope_limitations == SCOPE_LIMITATIONS,
    )
    if not all(expected):
        raise LiveAdapterDryRunAuthorityEvidenceLinkageError("LADRAEL_DERIVED_MISMATCH")
    digest = _packet_hash(actual)
    if packet.live_adapter_dry_run_authority_evidence_linkage_review_hash != digest:
        raise LiveAdapterDryRunAuthorityEvidenceLinkageError("LADRAEL_HASH_MISMATCH")
    if packet.live_adapter_dry_run_authority_evidence_linkage_review_id != (
        f"ladrael:v1:sha256:{digest}"
    ):
        raise LiveAdapterDryRunAuthorityEvidenceLinkageError("LADRAEL_ID_MISMATCH")
    return packet
