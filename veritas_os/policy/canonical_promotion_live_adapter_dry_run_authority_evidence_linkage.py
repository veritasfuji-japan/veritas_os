"""Bind Authority Evidence reference metadata to a promotion-native source.

This boundary performs deterministic, local metadata linkage only.  In
particular, a declared upstream verification state is not cryptographic proof,
and this module neither accesses evidence resources nor creates approval,
execution authority, Bind authorization, dispatch, or any external effect.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from veritas_os.policy.bind_adapter_contract_selection import (
    BindAdapterContractSelectionError,
    verify_bind_adapter_contract_descriptor,
)
from veritas_os.policy.bind_artifacts import ExecutionIntent, hash_execution_intent
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_bind_pre_dispatch_review import (
    CanonicalPromotionLiveAdapterDryRunBindPreDispatchReviewError,
    CanonicalPromotionLiveAdapterDryRunBindPreDispatchReviewPacket,
    verify_canonical_promotion_live_adapter_dry_run_bind_pre_dispatch_review_packet,
)

FORMAT_VERSION = (
    "canonical-promotion-live-adapter-dry-run-authority-evidence-linkage-review/v1"
)
REVIEW_MECHANISM = (
    "review_promotion_live_adapter_dry_run_authority_evidence_reference_linkage_"
    "without_external_verification/v1"
)
STATUS = "PROMOTION_NATIVE_AUTHORITY_EVIDENCE_LINKAGE_REVIEWED_NOT_AUTHORIZED"
CHECK_MODE = "deterministic_local_promotion_native_authority_reference_binding_only"
DECLARED_STATES = (
    "DECLARED_VERIFIED_BY_UPSTREAM_ARTIFACT",
    "DECLARED_PENDING_EXTERNAL_VERIFICATION",
    "DECLARED_REJECTED_BY_UPSTREAM_ARTIFACT",
)
PREFIX = "veritas.promotion-live-adapter-dry-run-authority-evidence-linkage"
DOMAINS = {
    name: f"{PREFIX}.{name}/v1"
    for name in (
        "reference",
        "bundle",
        "matrix",
        "result",
        "context",
        "checks",
        "future-requirements",
        "packet",
    )
}
BINDINGS = (
    ("execution_intent_id", "linked_execution_intent_id"),
    ("execution_intent_hash", "linked_execution_intent_hash"),
    ("adapter_contract_id", "linked_adapter_contract_id"),
    ("adapter_contract_hash", "linked_adapter_contract_hash"),
    ("endpoint_candidate_id", "linked_endpoint_candidate_id"),
    (
        "endpoint_identity_binding_digest",
        "linked_endpoint_identity_binding_digest",
    ),
    ("credential_reference_id", "linked_credential_reference_id"),
    ("credential_scope_binding_digest", "linked_credential_scope_binding_digest"),
    ("target_system", "linked_target_system"),
    ("target_resource_scope", "linked_target_resource_scope"),
    ("purpose", "linked_purpose"),
    (
        "bind_pre_dispatch_review_id",
        "linked_bind_pre_dispatch_review_id",
    ),
    (
        "bind_pre_dispatch_review_hash",
        "linked_bind_pre_dispatch_review_hash",
    ),
)
CHECK_NAMES = (
    "source_promotion_native_bind_pre_dispatch_review_verified",
    "source_bind_pre_dispatch_review_accepted",
    "source_request_not_dispatched",
    "source_not_bound",
    "exact_execution_intent_verified",
    "exact_adapter_verified",
    "exact_endpoint_identity_preserved",
    "exact_credential_scope_preserved",
    "exact_operator_review_preserved",
    "exact_bind_pre_dispatch_review_preserved",
    "authority_reference_bundle_closed_schema_valid",
    "authority_references_present",
    "authority_reference_ids_unique",
    "declared_verification_states_admissible",
    "pending_state_rejected",
    "rejected_state_rejected",
    "expiry_checked",
    *tuple(f"{name}_exact_linked" for name, _ in BINDINGS),
    "binding_matrix_independently_constructed",
    "all_binding_claims_matched",
    "authority_linkage_context_constructed",
    "authority_evidence_not_created",
    "authority_evidence_not_externally_verified",
    "human_approval_not_created",
    "execution_authority_not_created",
    "bind_authorization_not_created",
    "bind_not_invoked",
    "bind_receipt_not_created",
    "trustlog_not_written",
    "request_not_dispatched",
    "network_not_used",
    "credential_material_not_accessed",
    "future_human_approval_reference_linkage_stage_required",
    "future_fresh_source_gate_required",
    "future_cryptographic_authority_evidence_verification_required",
    "future_real_bind_authorization_required",
)
FUTURE_REQUIREMENTS = (
    "promotion_native_human_approval_reference_linkage_review",
    "final_policy_admissibility",
    "final_endpoint_identity_recheck",
    "final_credential_reference_scope_recheck",
    "runtime_risk_review",
    "idempotency_binding",
    "fresh_source_gate",
    "gate_bound_cryptographic_human_approval",
    "cryptographic_authority_evidence_verification_through_real_authority_path",
    "revocation_verification_where_applicable",
    "real_bind_authorization",
    "credential_material_resolution",
    "authorization_header_construction",
    "network_dispatch",
    "bind_invocation",
    "bind_receipt",
    "trustlog_write",
    "external_effect",
    "postcondition_rollback_reconciliation",
)
EFFECT_FIELDS = (
    "authority_evidence_created",
    "authority_evidence_externally_verified",
    "human_approval_created",
    "execution_authority_created",
    "bind_authorization_created",
    "bind_authorization_issued",
    "credential_resolved",
    "credential_material_accessed",
    "credential_material_embedded",
    "credential_store_accessed",
    "authorization_header_constructed",
    "token_embedded",
    "secret_embedded",
    "cookie_embedded",
    "password_embedded",
    "private_key_embedded",
    "endpoint_resolved",
    "endpoint_contacted",
    "dns_used",
    "network_used",
    "webhook_invoked",
    "live_adapter_instantiated",
    "live_adapter_method_invoked",
    "request_dispatched",
    "bind_invoked",
    "bind_receipt_created",
    "trustlog_written",
    "filesystem_used",
    "database_used",
    "provider_called",
    "subprocess_used",
    "external_effect_used",
    "operation_committed",
    "apply_performed",
    "postcondition_verified",
    "rollback_or_revert_performed",
)
PRESERVED_FIELDS = (
    "request_descriptor",
    "execution_intent",
    "execution_intent_id",
    "execution_intent_hash",
    "adapter_contract_descriptor",
    "adapter_contract_id",
    "adapter_contract_hash",
    "adapter_contract_version",
    "endpoint_candidate",
    "endpoint_candidate_digest",
    "endpoint_identity_binding",
    "endpoint_identity_binding_digest",
    "credential_reference",
    "credential_reference_digest",
    "credential_policy_snapshot",
    "credential_policy_snapshot_hash",
    "credential_authorization_result",
    "credential_authorization_result_digest",
    "credential_scope_binding",
    "credential_scope_binding_digest",
    "operator_review_decision",
    "operator_review_decision_digest",
    "operator_review_binding",
    "operator_review_binding_digest",
    "bind_pre_dispatch_review_decision",
    "bind_pre_dispatch_review_decision_digest",
    "bind_pre_dispatch_review_result",
    "bind_pre_dispatch_review_result_digest",
    "bind_boundary_preconditions",
    "bind_boundary_precondition_digest",
    "source_endpoint_allowlist_evaluation_id",
    "source_endpoint_allowlist_evaluation_hash",
    "source_dispatch_readiness_id",
    "source_dispatch_readiness_hash",
    "source_live_adapter_dry_run_request_id",
    "source_live_adapter_dry_run_request_hash",
    "source_live_adapter_dry_run_readiness_id",
    "source_live_adapter_dry_run_readiness_hash",
    "source_reference_rehearsal_id",
    "source_reference_rehearsal_hash",
    "source_adapter_dry_run_fixture_result_id",
    "source_adapter_dry_run_fixture_result_hash",
    "source_adapter_dry_run_plan_id",
    "source_adapter_dry_run_plan_hash",
    "source_adapter_contract_selection_id",
    "source_adapter_contract_selection_hash",
    "source_bind_preflight_adjudication_id",
    "source_bind_preflight_adjudication_hash",
    "source_pre_bind_validation_id",
    "source_pre_bind_validation_hash",
    "source_readiness_id",
    "source_readiness_hash",
    "source_promotion_id",
    "source_promotion_hash",
    "source_decision_identity",
    "candidate_identity",
    "selected_action_lineage",
    "policy_snapshot_lineage",
    "approval_context",
    "policy_lineage",
)


class CanonicalPromotionLiveAdapterDryRunAuthorityEvidenceLinkageError(ValueError):
    """Fail-closed error for promotion-native Authority Evidence linkage."""


class AuthorityEvidenceReference(BaseModel):
    """Closed, metadata-only reference to an unverified authority artifact."""

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
    linked_execution_intent_id: str
    linked_execution_intent_hash: str
    linked_adapter_contract_id: str
    linked_adapter_contract_hash: str
    linked_endpoint_candidate_id: str
    linked_endpoint_identity_binding_digest: str
    linked_credential_reference_id: str
    linked_credential_scope_binding_digest: str
    linked_target_system: str
    linked_target_resource_scope: str
    linked_purpose: str
    linked_bind_pre_dispatch_review_id: str
    linked_bind_pre_dispatch_review_hash: str


class AuthorityEvidenceBindingClaim(BaseModel):
    """One exact comparison, independently reconstructed by the verifier."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    binding_claim_id: str
    authority_evidence_reference_id: str
    claim_type: Literal[*tuple(name for name, _ in BINDINGS)]
    expected_value: str
    actual_value: str
    matched: bool
    comparison_mode: Literal[CHECK_MODE]


class AuthorityEvidenceReferenceBundle(BaseModel):
    """Closed bundle whose claims must equal the complete derived matrix."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    authority_evidence_reference_bundle_id: str = Field(min_length=1)
    bundle_declared_by: str = Field(min_length=1)
    bundle_declared_at: str
    bundle_scope: tuple[str, ...] = Field(min_length=1)
    authority_evidence_references: tuple[AuthorityEvidenceReference, ...] = Field(
        min_length=1
    )
    authority_evidence_binding_claims: tuple[AuthorityEvidenceBindingClaim, ...]
    bundle_limitations: tuple[str, ...] = Field(min_length=1)


class AuthorityEvidenceLinkageResult(BaseModel):
    """Structural result explicitly carrying no proof or authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    all_required_references_present: Literal[True]
    all_references_structurally_linked: Literal[True]
    all_binding_claims_matched: Literal[True]
    rejected_reference_ids: tuple[str, ...]
    rejection_reasons: tuple[str, ...]
    comparison_mode: Literal[CHECK_MODE]
    semantic_match_used: Literal[False]
    creates_authority_evidence: Literal[False]
    externally_verifies_authority_evidence: Literal[False]
    creates_human_approval: Literal[False]
    creates_execution_authority: Literal[False]
    creates_bind_authorization: Literal[False]


class LinkageCheck(BaseModel):
    """One ordered deterministic linkage or no-effect check."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    check_id: str
    ordinal: int = Field(ge=1, le=len(CHECK_NAMES))
    name: Literal[*CHECK_NAMES]
    comparison_mode: Literal[CHECK_MODE]
    passed: Literal[True]
    evidence_ref: str


class FutureRequirement(BaseModel):
    """A future governance input explicitly unsatisfied here."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    ordinal: int = Field(ge=1, le=len(FUTURE_REQUIREMENTS))
    name: Literal[*FUTURE_REQUIREMENTS]
    separate_future_artifact_required: Literal[True]
    satisfied_by_this_packet: Literal[False]


class CanonicalPromotionLiveAdapterDryRunAuthorityEvidenceLinkageReviewPacket(
    BaseModel
):
    """Closed promotion-native metadata-linkage packet with no capabilities."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    format_version: Literal[FORMAT_VERSION]
    promotion_live_adapter_dry_run_authority_evidence_linkage_review_id: str = Field(
        pattern=r"^pladrael:v1:sha256:[0-9a-f]{64}$"
    )
    promotion_live_adapter_dry_run_authority_evidence_linkage_review_hash: str
    authority_evidence_linkage_review_mechanism: Literal[REVIEW_MECHANISM]
    authority_evidence_linkage_review_recorded_at: str
    source_bind_pre_dispatch_review_id: str
    source_bind_pre_dispatch_review_hash: str
    source_bind_pre_dispatch_review_packet: dict[str, Any]
    source_operator_review_id: str
    source_operator_review_hash: str
    source_credential_authorization_id: str
    source_credential_authorization_hash: str
    authority_evidence_reference_bundle: AuthorityEvidenceReferenceBundle
    authority_evidence_reference_digests: dict[str, str]
    authority_evidence_reference_bundle_digest: str
    authority_evidence_binding_matrix: tuple[AuthorityEvidenceBindingClaim, ...]
    authority_evidence_binding_matrix_digest: str
    authority_evidence_linkage_result: AuthorityEvidenceLinkageResult
    authority_evidence_linkage_result_digest: str
    authority_evidence_linkage_context: dict[str, Any]
    authority_evidence_linkage_context_digest: str
    authority_evidence_linkage_checks: tuple[LinkageCheck, ...]
    authority_evidence_linkage_check_digest: str
    future_requirements: tuple[FutureRequirement, ...]
    future_requirement_digest: str
    authority_evidence_linkage_status: Literal[STATUS]
    request_dispatch_state: Literal["NOT_DISPATCHED"]
    bind_state: Literal["NOT_BOUND"]
    authority_state: Literal["NOT_AUTHORIZED"]
    ready_for_promotion_native_human_approval_reference_linkage_review: Literal[True]
    fail_closed: Literal[False]
    authority_evidence_proven: Literal[False]
    authority_evidence_externally_verified: Literal[False]
    human_approval_proven: Literal[False]
    execution_authorized: Literal[False]
    ready_for_real_bind: Literal[False]
    ready_for_network_dispatch: Literal[False]
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
    credential_policy_snapshot: dict[str, Any]
    credential_policy_snapshot_hash: str
    credential_authorization_result: dict[str, Any]
    credential_authorization_result_digest: str
    credential_scope_binding: dict[str, Any]
    credential_scope_binding_digest: str
    operator_review_decision: dict[str, Any]
    operator_review_decision_digest: str
    operator_review_binding: dict[str, Any]
    operator_review_binding_digest: str
    bind_pre_dispatch_review_decision: dict[str, Any]
    bind_pre_dispatch_review_decision_digest: str
    bind_pre_dispatch_review_result: dict[str, Any]
    bind_pre_dispatch_review_result_digest: str
    bind_boundary_preconditions: dict[str, Any]
    bind_boundary_precondition_digest: str
    source_endpoint_allowlist_evaluation_id: str
    source_endpoint_allowlist_evaluation_hash: str
    source_dispatch_readiness_id: str
    source_dispatch_readiness_hash: str
    source_live_adapter_dry_run_request_id: str
    source_live_adapter_dry_run_request_hash: str
    source_live_adapter_dry_run_readiness_id: str
    source_live_adapter_dry_run_readiness_hash: str
    source_reference_rehearsal_id: str
    source_reference_rehearsal_hash: str
    source_adapter_dry_run_fixture_result_id: str
    source_adapter_dry_run_fixture_result_hash: str
    source_adapter_dry_run_plan_id: str
    source_adapter_dry_run_plan_hash: str
    source_adapter_contract_selection_id: str
    source_adapter_contract_selection_hash: str
    source_bind_preflight_adjudication_id: str
    source_bind_preflight_adjudication_hash: str
    source_pre_bind_validation_id: str
    source_pre_bind_validation_hash: str
    source_readiness_id: str
    source_readiness_hash: str
    source_promotion_id: str
    source_promotion_hash: str
    source_decision_identity: dict[str, Any]
    candidate_identity: dict[str, Any]
    selected_action_lineage: dict[str, Any]
    policy_snapshot_lineage: dict[str, Any]
    approval_context: dict[str, Any]
    policy_lineage: dict[str, Any]
    authority_evidence_created: Literal[False]
    authority_evidence_externally_verified: Literal[False]
    human_approval_created: Literal[False]
    execution_authority_created: Literal[False]
    bind_authorization_created: Literal[False]
    bind_authorization_issued: Literal[False]
    credential_resolved: Literal[False]
    credential_material_accessed: Literal[False]
    credential_material_embedded: Literal[False]
    credential_store_accessed: Literal[False]
    authorization_header_constructed: Literal[False]
    token_embedded: Literal[False]
    secret_embedded: Literal[False]
    cookie_embedded: Literal[False]
    password_embedded: Literal[False]
    private_key_embedded: Literal[False]
    endpoint_resolved: Literal[False]
    endpoint_contacted: Literal[False]
    dns_used: Literal[False]
    network_used: Literal[False]
    webhook_invoked: Literal[False]
    live_adapter_instantiated: Literal[False]
    live_adapter_method_invoked: Literal[False]
    request_dispatched: Literal[False]
    bind_invoked: Literal[False]
    bind_receipt_created: Literal[False]
    trustlog_written: Literal[False]
    filesystem_used: Literal[False]
    database_used: Literal[False]
    provider_called: Literal[False]
    subprocess_used: Literal[False]
    external_effect_used: Literal[False]
    operation_committed: Literal[False]
    apply_performed: Literal[False]
    postcondition_verified: Literal[False]
    rollback_or_revert_performed: Literal[False]


def _fail(code: str) -> None:
    raise CanonicalPromotionLiveAdapterDryRunAuthorityEvidenceLinkageError(code)


def _aware(value: Any, code: str) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunAuthorityEvidenceLinkageError(
            code
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail(code)
    return parsed


def _json(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            _fail("PLADRAEL_INVALID")
        return value
    if isinstance(value, datetime):
        return (
            _aware(value, "PLADRAEL_TIMESTAMP_INVALID")
            .astimezone(timezone.utc)
            .isoformat()
        )
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _json(item) for key, item in value.items()}
    _fail("PLADRAEL_INVALID")


def _digest(domain: str, value: Any) -> str:
    encoded = json.dumps(
        {"domain": domain, "value": _json(value)},
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _packet_hash(raw: dict[str, Any]) -> str:
    omitted = {
        "promotion_live_adapter_dry_run_authority_evidence_linkage_review_id",
        "promotion_live_adapter_dry_run_authority_evidence_linkage_review_hash",
    }
    return _digest(
        DOMAINS["packet"],
        {key: value for key, value in raw.items() if key not in omitted},
    )


def _source(
    value: Any,
) -> CanonicalPromotionLiveAdapterDryRunBindPreDispatchReviewPacket:
    try:
        return verify_canonical_promotion_live_adapter_dry_run_bind_pre_dispatch_review_packet(
            value
        )
    except (
        CanonicalPromotionLiveAdapterDryRunBindPreDispatchReviewError,
        TypeError,
        ValueError,
    ) as exc:
        raise CanonicalPromotionLiveAdapterDryRunAuthorityEvidenceLinkageError(
            "PLADRAEL_SOURCE_INVALID"
        ) from exc


def _validate_source(source: Any) -> None:
    if (
        not source.bind_pre_dispatch_review_result.accepted_for_future_bind_dispatch_gate_review
        or not source.ready_for_promotion_native_authority_evidence_linkage_review
        or source.fail_closed
        or source.request_dispatch_state != "NOT_DISPATCHED"
        or source.bind_state != "NOT_BOUND"
    ):
        _fail("PLADRAEL_SOURCE_NOT_ADMISSIBLE")
    if any(
        (
            source.execution_authorized,
            source.human_approval_proven,
            source.authority_evidence_proven,
            source.ready_for_real_bind,
            source.ready_for_network_dispatch,
        )
    ):
        _fail("PLADRAEL_SOURCE_AUTHORITY_INVALID")
    try:
        intent = ExecutionIntent(**source.execution_intent)
        descriptor = verify_bind_adapter_contract_descriptor(
            source.adapter_contract_descriptor, intent
        )
    except (TypeError, ValueError, BindAdapterContractSelectionError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunAuthorityEvidenceLinkageError(
            "PLADRAEL_EXACT_OBJECT_INVALID"
        ) from exc
    if (
        intent.to_dict() != source.execution_intent
        or intent.execution_intent_id != source.execution_intent_id
        or hash_execution_intent(intent) != source.execution_intent_hash
    ):
        _fail("PLADRAEL_EXECUTION_INTENT_MISMATCH")
    if (
        descriptor.model_dump(mode="json") != source.adapter_contract_descriptor
        or descriptor.adapter_contract_id != source.adapter_contract_id
        or descriptor.adapter_contract_hash != source.adapter_contract_hash
        or descriptor.adapter_contract_version != source.adapter_contract_version
    ):
        _fail("PLADRAEL_ADAPTER_MISMATCH")


def _expected_values(source: Any) -> dict[str, str]:
    intent = source.execution_intent
    credential = source.credential_reference
    target_system = str(intent["target_system"])
    target_scope = str(credential["target_resource_scope"])
    purpose = str(credential["credential_purpose"])
    if credential["target_system"] != target_system:
        _fail("PLADRAEL_TARGET_SYSTEM_SOURCE_CONFLICT")
    return {
        "execution_intent_id": source.execution_intent_id,
        "execution_intent_hash": source.execution_intent_hash,
        "adapter_contract_id": source.adapter_contract_id,
        "adapter_contract_hash": source.adapter_contract_hash,
        "endpoint_candidate_id": str(
            source.endpoint_candidate["endpoint_candidate_id"]
        ),
        "endpoint_identity_binding_digest": source.endpoint_identity_binding_digest,
        "credential_reference_id": str(credential["credential_reference_id"]),
        "credential_scope_binding_digest": source.credential_scope_binding_digest,
        "target_system": target_system,
        "target_resource_scope": target_scope,
        "purpose": purpose,
        "bind_pre_dispatch_review_id": (
            source.promotion_live_adapter_dry_run_bind_pre_dispatch_review_id
        ),
        "bind_pre_dispatch_review_hash": (
            source.promotion_live_adapter_dry_run_bind_pre_dispatch_review_hash
        ),
    }


def _matrix(source: Any, bundle: Any) -> list[dict[str, Any]]:
    expected = _expected_values(source)
    return [
        {
            "binding_claim_id": (
                f"pladrael-claim:v1:{reference.authority_evidence_reference_id}:"
                f"{claim_type}"
            ),
            "authority_evidence_reference_id": (
                reference.authority_evidence_reference_id
            ),
            "claim_type": claim_type,
            "expected_value": expected[claim_type],
            "actual_value": str(getattr(reference, attribute)),
            "matched": expected[claim_type] == str(getattr(reference, attribute)),
            "comparison_mode": CHECK_MODE,
        }
        for reference in bundle.authority_evidence_references
        for claim_type, attribute in BINDINGS
    ]


def _bundle(value: Any, source: Any, recorded_at: datetime) -> Any:
    try:
        bundle = AuthorityEvidenceReferenceBundle.model_validate(_json(value))
    except (ValidationError, TypeError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunAuthorityEvidenceLinkageError(
            "PLADRAEL_BUNDLE_INVALID"
        ) from exc
    declared_at = _aware(bundle.bundle_declared_at, "PLADRAEL_BUNDLE_TIME_INVALID")
    if declared_at > recorded_at:
        _fail("PLADRAEL_BUNDLE_FUTURE")
    references = bundle.authority_evidence_references
    ids = [item.authority_evidence_reference_id for item in references]
    if len(ids) != len(set(ids)):
        _fail("PLADRAEL_REFERENCE_IDS_DUPLICATE")
    if not set(bundle.bundle_scope).issubset(
        {item.authority_scope for item in references}
    ):
        _fail("PLADRAEL_SCOPE_MISSING")
    for reference in references:
        if reference.declared_verification_state != DECLARED_STATES[0]:
            _fail("PLADRAEL_DECLARED_STATE_REJECTED")
        issued = _aware(reference.authority_issued_at, "PLADRAEL_ISSUED_AT_INVALID")
        expires = _aware(reference.authority_expires_at, "PLADRAEL_EXPIRES_AT_INVALID")
        if issued > recorded_at or expires <= recorded_at or expires <= issued:
            _fail("PLADRAEL_REFERENCE_TIME_INVALID")
    expected_matrix = _matrix(source, bundle)
    supplied = [
        claim.model_dump(mode="json")
        for claim in bundle.authority_evidence_binding_claims
    ]
    if supplied != expected_matrix or not all(
        item["matched"] for item in expected_matrix
    ):
        _fail("PLADRAEL_BINDING_MATRIX_MISMATCH")
    return bundle


def _derived(source: Any, bundle: Any) -> tuple[Any, ...]:
    matrix = _matrix(source, bundle)
    references = [
        item.model_dump(mode="json") for item in bundle.authority_evidence_references
    ]
    reference_digests = {
        item["authority_evidence_reference_id"]: _digest(DOMAINS["reference"], item)
        for item in references
    }
    bundle_digest = _digest(DOMAINS["bundle"], bundle)
    matrix_digest = _digest(DOMAINS["matrix"], matrix)
    result = {
        "all_required_references_present": True,
        "all_references_structurally_linked": True,
        "all_binding_claims_matched": True,
        "rejected_reference_ids": [],
        "rejection_reasons": [],
        "comparison_mode": CHECK_MODE,
        "semantic_match_used": False,
        "creates_authority_evidence": False,
        "externally_verifies_authority_evidence": False,
        "creates_human_approval": False,
        "creates_execution_authority": False,
        "creates_bind_authorization": False,
    }
    context = {
        "source_bind_pre_dispatch_review_id": source.promotion_live_adapter_dry_run_bind_pre_dispatch_review_id,
        "source_bind_pre_dispatch_review_hash": source.promotion_live_adapter_dry_run_bind_pre_dispatch_review_hash,
        "source_operator_review_id": source.source_operator_dispatch_review_id,
        "source_operator_review_hash": source.source_operator_dispatch_review_hash,
        "source_credential_authorization_id": source.source_credential_authorization_id,
        "source_credential_authorization_hash": source.source_credential_authorization_hash,
        "source_endpoint_allowlist_id": source.source_endpoint_allowlist_evaluation_id,
        "source_endpoint_allowlist_hash": source.source_endpoint_allowlist_evaluation_hash,
        **_expected_values(source),
        "endpoint_candidate_digest": source.endpoint_candidate_digest,
        "credential_reference_digest": source.credential_reference_digest,
        "operator_review_binding_digest": source.operator_review_binding_digest,
        "bind_boundary_precondition_digest": source.bind_boundary_precondition_digest,
        "authority_evidence_reference_ids": list(reference_digests),
        "authority_evidence_reference_digests": reference_digests,
        "authority_evidence_reference_bundle_id": bundle.authority_evidence_reference_bundle_id,
        "authority_evidence_reference_bundle_digest": bundle_digest,
        "authority_evidence_binding_matrix_digest": matrix_digest,
        "policy_snapshot_lineage": source.policy_snapshot_lineage,
        "policy_lineage": source.policy_lineage,
        "approval_context": source.approval_context,
    }
    checks = [
        {
            "check_id": f"pladrael-check:v1:{ordinal}:{name.replace('_', '-')}",
            "ordinal": ordinal,
            "name": name,
            "comparison_mode": CHECK_MODE,
            "passed": True,
            "evidence_ref": f"bundle:{bundle_digest}:matrix:{matrix_digest}:{name}",
        }
        for ordinal, name in enumerate(CHECK_NAMES, 1)
    ]
    requirements = [
        {
            "ordinal": ordinal,
            "name": name,
            "separate_future_artifact_required": True,
            "satisfied_by_this_packet": False,
        }
        for ordinal, name in enumerate(FUTURE_REQUIREMENTS, 1)
    ]
    return (
        reference_digests,
        bundle_digest,
        matrix,
        result,
        context,
        checks,
        requirements,
    )


def build_canonical_promotion_live_adapter_dry_run_authority_evidence_linkage_review_packet(
    source_bind_pre_dispatch_review_packet: Any,
    authority_evidence_reference_bundle: Any,
    authority_evidence_linkage_review_recorded_at: datetime,
) -> CanonicalPromotionLiveAdapterDryRunAuthorityEvidenceLinkageReviewPacket:
    """Build and self-verify an inert promotion-native reference linkage."""
    source = _source(_json(source_bind_pre_dispatch_review_packet))
    _validate_source(source)
    recorded_at = _aware(
        authority_evidence_linkage_review_recorded_at,
        "PLADRAEL_RECORDED_AT_INVALID",
    )
    source_at = _aware(
        source.bind_pre_dispatch_review_recorded_at,
        "PLADRAEL_SOURCE_TIME_INVALID",
    )
    if recorded_at < source_at:
        _fail("PLADRAEL_TIMESTAMP_ORDER_INVALID")
    bundle = _bundle(authority_evidence_reference_bundle, source, recorded_at)
    digests, bundle_digest, matrix, result, context, checks, requirements = _derived(
        source, bundle
    )
    source_raw = source.model_dump(mode="json")
    raw = {
        "format_version": FORMAT_VERSION,
        "authority_evidence_linkage_review_mechanism": REVIEW_MECHANISM,
        "authority_evidence_linkage_review_recorded_at": recorded_at.astimezone(
            timezone.utc
        ).isoformat(),
        "source_bind_pre_dispatch_review_id": source.promotion_live_adapter_dry_run_bind_pre_dispatch_review_id,
        "source_bind_pre_dispatch_review_hash": source.promotion_live_adapter_dry_run_bind_pre_dispatch_review_hash,
        "source_bind_pre_dispatch_review_packet": source_raw,
        "source_operator_review_id": source.source_operator_dispatch_review_id,
        "source_operator_review_hash": source.source_operator_dispatch_review_hash,
        "source_credential_authorization_id": source.source_credential_authorization_id,
        "source_credential_authorization_hash": source.source_credential_authorization_hash,
        **{field: source_raw[field] for field in PRESERVED_FIELDS},
        "authority_evidence_reference_bundle": bundle.model_dump(mode="json"),
        "authority_evidence_reference_digests": digests,
        "authority_evidence_reference_bundle_digest": bundle_digest,
        "authority_evidence_binding_matrix": matrix,
        "authority_evidence_binding_matrix_digest": _digest(DOMAINS["matrix"], matrix),
        "authority_evidence_linkage_result": result,
        "authority_evidence_linkage_result_digest": _digest(DOMAINS["result"], result),
        "authority_evidence_linkage_context": context,
        "authority_evidence_linkage_context_digest": _digest(
            DOMAINS["context"], context
        ),
        "authority_evidence_linkage_checks": checks,
        "authority_evidence_linkage_check_digest": _digest(DOMAINS["checks"], checks),
        "future_requirements": requirements,
        "future_requirement_digest": _digest(
            DOMAINS["future-requirements"], requirements
        ),
        "authority_evidence_linkage_status": STATUS,
        "request_dispatch_state": "NOT_DISPATCHED",
        "bind_state": "NOT_BOUND",
        "authority_state": "NOT_AUTHORIZED",
        "ready_for_promotion_native_human_approval_reference_linkage_review": True,
        "fail_closed": False,
        "authority_evidence_proven": False,
        "authority_evidence_externally_verified": False,
        "human_approval_proven": False,
        "execution_authorized": False,
        "ready_for_real_bind": False,
        "ready_for_network_dispatch": False,
        **{field: False for field in EFFECT_FIELDS},
    }
    digest = _packet_hash(raw)
    raw["promotion_live_adapter_dry_run_authority_evidence_linkage_review_hash"] = (
        digest
    )
    raw["promotion_live_adapter_dry_run_authority_evidence_linkage_review_id"] = (
        f"pladrael:v1:sha256:{digest}"
    )
    return verify_canonical_promotion_live_adapter_dry_run_authority_evidence_linkage_review_packet(
        raw
    )


def verify_canonical_promotion_live_adapter_dry_run_authority_evidence_linkage_review_packet(
    raw: Any,
) -> CanonicalPromotionLiveAdapterDryRunAuthorityEvidenceLinkageReviewPacket:
    """Independently verify the source and recompute every linkage artifact."""
    try:
        value = raw.model_dump(mode="json") if isinstance(raw, BaseModel) else raw
        packet = CanonicalPromotionLiveAdapterDryRunAuthorityEvidenceLinkageReviewPacket.model_validate(
            _json(value)
        )
    except (
        ValidationError,
        TypeError,
        CanonicalPromotionLiveAdapterDryRunAuthorityEvidenceLinkageError,
    ) as exc:
        raise CanonicalPromotionLiveAdapterDryRunAuthorityEvidenceLinkageError(
            "PLADRAEL_PACKET_INVALID"
        ) from exc
    actual = packet.model_dump(mode="json")
    source = _source(packet.source_bind_pre_dispatch_review_packet)
    _validate_source(source)
    source_raw = source.model_dump(mode="json")
    identities = (
        packet.source_bind_pre_dispatch_review_id
        == source.promotion_live_adapter_dry_run_bind_pre_dispatch_review_id,
        packet.source_bind_pre_dispatch_review_hash
        == source.promotion_live_adapter_dry_run_bind_pre_dispatch_review_hash,
        packet.source_operator_review_id == source.source_operator_dispatch_review_id,
        packet.source_operator_review_hash
        == source.source_operator_dispatch_review_hash,
        packet.source_credential_authorization_id
        == source.source_credential_authorization_id,
        packet.source_credential_authorization_hash
        == source.source_credential_authorization_hash,
    )
    if not all(identities) or any(
        _json(getattr(packet, field)) != _json(source_raw[field])
        for field in PRESERVED_FIELDS
    ):
        _fail("PLADRAEL_SOURCE_MISMATCH")
    recorded_at = _aware(
        packet.authority_evidence_linkage_review_recorded_at,
        "PLADRAEL_RECORDED_AT_INVALID",
    )
    if recorded_at < _aware(
        source.bind_pre_dispatch_review_recorded_at, "PLADRAEL_SOURCE_TIME_INVALID"
    ):
        _fail("PLADRAEL_TIMESTAMP_ORDER_INVALID")
    bundle = _bundle(packet.authority_evidence_reference_bundle, source, recorded_at)
    digests, bundle_digest, matrix, result, context, checks, requirements = _derived(
        source, bundle
    )
    comparisons = (
        packet.authority_evidence_reference_digests == digests,
        packet.authority_evidence_reference_bundle_digest == bundle_digest,
        _json(packet.authority_evidence_binding_matrix) == matrix,
        packet.authority_evidence_binding_matrix_digest
        == _digest(DOMAINS["matrix"], matrix),
        _json(packet.authority_evidence_linkage_result) == result,
        packet.authority_evidence_linkage_result_digest
        == _digest(DOMAINS["result"], result),
        packet.authority_evidence_linkage_context == context,
        packet.authority_evidence_linkage_context_digest
        == _digest(DOMAINS["context"], context),
        _json(packet.authority_evidence_linkage_checks) == checks,
        packet.authority_evidence_linkage_check_digest
        == _digest(DOMAINS["checks"], checks),
        _json(packet.future_requirements) == requirements,
        packet.future_requirement_digest
        == _digest(DOMAINS["future-requirements"], requirements),
    )
    if not all(comparisons):
        _fail("PLADRAEL_DERIVED_MISMATCH")
    if any(getattr(packet, field) for field in EFFECT_FIELDS):
        _fail("PLADRAEL_EFFECT_INVALID")
    digest = _packet_hash(actual)
    if (
        packet.promotion_live_adapter_dry_run_authority_evidence_linkage_review_hash
        != digest
    ):
        _fail("PLADRAEL_PACKET_HASH_MISMATCH")
    if (
        packet.promotion_live_adapter_dry_run_authority_evidence_linkage_review_id
        != f"pladrael:v1:sha256:{digest}"
    ):
        _fail("PLADRAEL_PACKET_ID_MISMATCH")
    return packet
