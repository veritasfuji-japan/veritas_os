"""Review the promotion-native Bind authorization gate without granting authority.

The boundary is deterministic and local. It independently verifies the
promotion-native Final Bind Authorization Readiness source and preserves its
bindings, but creates no proof, authority, authorization, bind context,
dispatch, or external effect.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

from veritas_os.policy.bind_adapter_contract_selection import (
    BindAdapterContractSelectionError,
    verify_bind_adapter_contract_descriptor,
)
from veritas_os.policy.bind_artifacts import ExecutionIntent, hash_execution_intent
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_final_bind_authorization_readiness import (
    PRESERVED_FIELDS as UPSTREAM_PRESERVED_FIELDS,
    CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessError,
    CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessPacket,
    verify_canonical_promotion_live_adapter_dry_run_final_bind_authorization_readiness_packet,
)

FORMAT_VERSION = "canonical-promotion-live-adapter-dry-run-bind-authorization-gate-review/v1"
MECHANISM = (
    "review_promotion_native_bind_authorization_gate_without_"
    "authorization_creation_or_external_effect/v1"
)
STATUS = "PROMOTION_NATIVE_BIND_AUTHORIZATION_GATE_REVIEWED_NOT_AUTHORIZED"
SOURCE_STATUS = "PROMOTION_NATIVE_FINAL_BIND_AUTHORIZATION_READINESS_RECORDED_NOT_AUTHORIZED"
CHECK_MODE = "deterministic_local_promotion_native_bind_authorization_gate_review_only"
OUTCOMES = (
    "PASSED_FOR_FUTURE_PROMOTION_NATIVE_FRESH_VERIFIED_SOURCE_GATE",
    "FAILED_FOR_FUTURE_PROMOTION_NATIVE_FRESH_VERIFIED_SOURCE_GATE",
)
PREFIX = "veritas.promotion-live-adapter-dry-run-bind-authorization-gate-review"
DOMAINS = {
    name: f"{PREFIX}.{name}/v1"
    for name in (
        "decision",
        "result",
        "context",
        "checks",
        "authorization",
        "invocation",
        "packet",
    )
}

ACKNOWLEDGEMENTS = (
    "acknowledged_not_real_bind_authorization",
    "acknowledged_no_bind_invocation",
    "acknowledged_no_bind_receipt",
    "acknowledged_no_trustlog_write",
    "acknowledged_no_dispatch",
    "acknowledged_no_execution_authority",
    "acknowledged_no_human_approval_creation",
    "acknowledged_no_human_approval_verification",
    "acknowledged_no_authority_evidence_creation",
    "acknowledged_no_authority_evidence_verification",
    "acknowledged_no_credential_access",
    "acknowledged_no_authorization_header",
    "acknowledged_no_network_call",
    "acknowledged_fresh_verified_source_gate_still_required",
    "acknowledged_bind_context_hash_not_derived",
    "acknowledged_gate_bound_human_approval_still_required",
    "acknowledged_cryptographic_authority_verification_still_required",
    "acknowledged_real_bind_authorization_still_required",
)
CHECK_NAMES = (
    "source_human_approval_reference_linkage_verified",
    "exact_execution_intent_reconstructed",
    "exact_adapter_descriptor_verified",
    "endpoint_identity_binding_preserved",
    "credential_scope_binding_preserved",
    "operator_review_binding_preserved",
    "bind_boundary_precondition_preserved",
    "authority_evidence_reference_linkage_preserved",
    "human_approval_reference_linkage_preserved",
    "final_review_decision_valid",
    "all_acknowledgements_present",
    "timestamp_ordering_valid",
    "future_requirements_unsatisfied",
    "human_approval_proof_absent",
    "authority_evidence_proof_absent",
    "execution_authority_absent",
    "bind_authorization_absent",
    "dispatch_absent",
    "network_access_absent",
    "external_effect_absent",
)
AUTHORIZATION_REQUIREMENTS = (
    "fresh_verified_source_gate",
    "exact_bind_context_hash_derivation",
    "final_endpoint_identity_recheck",
    "final_credential_scope_recheck",
    "runtime_risk_review",
    "idempotency_and_replay_review",
    "signed_gate_bound_human_approval_issuance",
    "human_approval_receipt_verification",
    "cryptographic_authority_evidence_verification",
    "revocation_verification_where_applicable",
    "real_bind_authorization",
)
INVOCATION_REQUIREMENTS = (
    "authorization_consumption",
    "single_use_consumption",
    "credential_material_resolution",
    "authorization_header_construction",
    "network_dispatch",
    "bind_invocation",
    "bind_receipt",
    "trustlog_write",
    "effect_state_handling",
    "reconciliation",
    "outcome_receipt",
)
SOURCE_AUTHORIZATION_REQUIREMENTS = (
    "promotion_native_bind_authorization_gate_review",
    *AUTHORIZATION_REQUIREMENTS,
)

# Final Readiness evidence preserved under its original names. The source
# future-requirement fields are deliberately excluded because the Gate owns
# fields with those names for the remaining lifecycle requirements.
FINAL_READINESS_EVIDENCE_FIELDS = (
    "final_bind_authorization_readiness_review_decision",
    "final_bind_authorization_readiness_review_decision_digest",
    "final_bind_authorization_readiness_result",
    "final_bind_authorization_readiness_result_digest",
    "final_readiness_context",
    "final_readiness_context_digest",
    "final_bind_authorization_readiness_checks",
    "final_bind_authorization_readiness_check_digest",
    "source_human_approval_linkage_review_id",
    "source_human_approval_linkage_review_hash",
)
PRESERVED_FIELDS = tuple(
    dict.fromkeys((*UPSTREAM_PRESERVED_FIELDS, *FINAL_READINESS_EVIDENCE_FIELDS))
)
COPY_FIELDS = PRESERVED_FIELDS
SOURCE_REQUIREMENT_FIELD_MAP = {
    "source_final_bind_authorization_requirements": "future_bind_authorization_requirements",
    "source_final_bind_authorization_requirement_digest": "future_bind_authorization_requirement_digest",
    "source_final_bind_invocation_requirements": "future_bind_invocation_requirements",
    "source_final_bind_invocation_requirement_digest": "future_bind_invocation_requirement_digest",
}
EFFECT_FIELDS = (
    "human_approval_created",
    "human_approval_externally_verified",
    "human_approval_proven",
    "authority_evidence_created",
    "authority_evidence_externally_verified",
    "authority_evidence_proven",
    "execution_authority_created",
    "execution_authorized",
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
    "ready_for_real_bind",
    "ready_for_network_dispatch",
)


class CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewError(ValueError):
    """Stable fail-closed error for invalid promotion-native Gate evidence."""


class BindAuthorizationGateReviewDecision(BaseModel):
    """Closed reviewer decision which expressly grants no authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    bind_authorization_gate_review_decision_id: str = Field(min_length=1)
    reviewer_id: str = Field(min_length=1)
    reviewer_role: str = Field(min_length=1)
    reviewer_attestation: str = Field(min_length=1)
    reviewed_at: str
    review_outcome: Literal[*OUTCOMES]
    review_reason: str = Field(min_length=1)
    acknowledged_not_real_bind_authorization: Literal[True]
    acknowledged_no_bind_invocation: Literal[True]
    acknowledged_no_bind_receipt: Literal[True]
    acknowledged_no_trustlog_write: Literal[True]
    acknowledged_no_dispatch: Literal[True]
    acknowledged_no_execution_authority: Literal[True]
    acknowledged_no_human_approval_creation: Literal[True]
    acknowledged_no_human_approval_verification: Literal[True]
    acknowledged_no_authority_evidence_creation: Literal[True]
    acknowledged_no_authority_evidence_verification: Literal[True]
    acknowledged_no_credential_access: Literal[True]
    acknowledged_no_authorization_header: Literal[True]
    acknowledged_no_network_call: Literal[True]
    acknowledged_fresh_verified_source_gate_still_required: Literal[True]
    acknowledged_bind_context_hash_not_derived: Literal[True]
    acknowledged_gate_bound_human_approval_still_required: Literal[True]
    acknowledged_cryptographic_authority_verification_still_required: Literal[True]
    acknowledged_real_bind_authorization_still_required: Literal[True]


class BindAuthorizationGateReviewResult(BaseModel):
    """Deterministic local Gate result with explicit non-authority semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_human_approval_reference_linkage_passed: Literal[True]
    source_authority_evidence_reference_linkage_passed: Literal[True]
    source_bind_pre_dispatch_review_passed: Literal[True]
    exact_execution_intent_preserved: Literal[True]
    exact_adapter_preserved: Literal[True]
    exact_endpoint_binding_preserved: Literal[True]
    exact_credential_scope_binding_preserved: Literal[True]
    all_required_local_linkage_artifacts_present: Literal[True]
    all_required_local_linkage_artifacts_verified: Literal[True]
    source_final_readiness_passed: Literal[True]
    gate_review_passed: bool
    accepted_for_future_promotion_native_fresh_verified_source_gate: bool
    rejection_reasons: tuple[str, ...]
    comparison_mode: Literal[CHECK_MODE]
    semantic_match_used: Literal[False]
    creates_bind_authorization: Literal[False]
    creates_execution_authority: Literal[False]
    creates_human_approval: Literal[False]
    externally_verifies_human_approval: Literal[False]
    creates_authority_evidence: Literal[False]
    externally_verifies_authority_evidence: Literal[False]
    derives_bind_context_hash: Literal[False]


class GateReviewCheck(BaseModel):
    """An ordered deterministic check that cannot perform an effect."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    ordinal: int = Field(ge=1)
    name: Literal[*CHECK_NAMES]
    passed: Literal[True]
    comparison_mode: Literal[CHECK_MODE]


class FutureRequirement(BaseModel):
    """A lifecycle requirement deliberately unsatisfied by this artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    ordinal: int = Field(ge=1)
    name: Literal[*AUTHORIZATION_REQUIREMENTS, *INVOCATION_REQUIREMENTS]
    separate_future_artifact_required: Literal[True]
    satisfied_by_this_packet: Literal[False]


class _BindAuthorizationGateReviewPacketBase(BaseModel):
    """Content-addressed promotion-native Bind Gate Review evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format_version: Literal[FORMAT_VERSION]
    promotion_live_adapter_dry_run_bind_authorization_gate_review_id: str
    promotion_live_adapter_dry_run_bind_authorization_gate_review_hash: str
    bind_authorization_gate_review_mechanism: Literal[MECHANISM]
    bind_authorization_gate_review_recorded_at: str
    source_final_bind_authorization_readiness_id: str
    source_final_bind_authorization_readiness_hash: str
    source_final_bind_authorization_readiness_packet: dict[str, Any]
    bind_authorization_gate_review_decision: BindAuthorizationGateReviewDecision
    bind_authorization_gate_review_decision_digest: str
    bind_authorization_gate_review_result: BindAuthorizationGateReviewResult
    bind_authorization_gate_review_result_digest: str
    bind_authorization_gate_review_context: dict[str, Any]
    bind_authorization_gate_review_context_digest: str
    bind_authorization_gate_review_checks: tuple[GateReviewCheck, ...]
    bind_authorization_gate_review_check_digest: str
    future_bind_authorization_requirements: tuple[FutureRequirement, ...]
    future_bind_authorization_requirement_digest: str
    future_bind_invocation_requirements: tuple[FutureRequirement, ...]
    future_bind_invocation_requirement_digest: str
    bind_authorization_gate_review_status: Literal[STATUS]
    request_dispatch_state: Literal["NOT_DISPATCHED"]
    bind_state: Literal["NOT_BOUND"]
    authority_state: Literal["NOT_AUTHORIZED"]
    human_approval_state: Literal["NOT_APPROVED"]
    gate_review_state: Literal[*OUTCOMES]
    ready_for_promotion_native_fresh_verified_source_gate: bool
    bind_authorization_state: Literal["NOT_AUTHORIZED"]
    bind_context_hash_derived: Literal[False]
    fresh_verified_source_gate_still_required: Literal[True]
    fail_closed: bool
    human_approval_proven: Literal[False]
    human_approval_externally_verified: Literal[False]
    authority_evidence_proven: Literal[False]
    authority_evidence_externally_verified: Literal[False]
    execution_authorized: Literal[False]
    bind_authorization_issued: Literal[False]
    ready_for_real_bind: Literal[False]
    ready_for_network_dispatch: Literal[False]
    human_approval_created: Literal[False]
    authority_evidence_created: Literal[False]
    execution_authority_created: Literal[False]
    bind_authorization_created: Literal[False]
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


_PRESERVED_PACKET_FIELDS = {
    field_name: (
        CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessPacket
        .model_fields[field_name]
        .annotation,
        ...,
    )
    for field_name in PRESERVED_FIELDS
}
_SOURCE_REQUIREMENT_PACKET_FIELDS = {
    target_name: (
        CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessPacket
        .model_fields[source_name]
        .annotation,
        ...,
    )
    for target_name, source_name in SOURCE_REQUIREMENT_FIELD_MAP.items()
}

CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewPacket = create_model(
    "CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewPacket",
    __base__=_BindAuthorizationGateReviewPacketBase,
    **_PRESERVED_PACKET_FIELDS,
    **_SOURCE_REQUIREMENT_PACKET_FIELDS,
)


def _fail(code: str) -> None:
    raise CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewError(code)


def _timestamp(value: Any) -> str:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewError(
            "CPLADBAGR_TIMESTAMP_INVALID"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail("CPLADBAGR_TIMESTAMP_INVALID")
    return parsed.astimezone(timezone.utc).isoformat()


def _json(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
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
    _fail("CPLADBAGR_JSON_INVALID")


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
        "promotion_live_adapter_dry_run_bind_authorization_gate_review_id",
        "promotion_live_adapter_dry_run_bind_authorization_gate_review_hash",
    }
    return _digest(
        DOMAINS["packet"],
        {key: value for key, value in raw.items() if key not in omitted},
    )


def _source(
    value: Any,
) -> CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessPacket:
    try:
        return verify_canonical_promotion_live_adapter_dry_run_final_bind_authorization_readiness_packet(
            value
        )
    except (
        CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessError,
        TypeError,
        ValueError,
    ) as exc:
        raise CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewError(
            "CPLADBAGR_SOURCE_INVALID"
        ) from exc


def _requirement_names(items: Any) -> tuple[str, ...]:
    try:
        return tuple(item.name for item in items)
    except (AttributeError, TypeError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewError(
            "CPLADBAGR_SOURCE_REQUIREMENTS_INVALID"
        ) from exc


def _validate_source_requirements(
    source: CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessPacket,
) -> None:
    if _requirement_names(source.future_bind_authorization_requirements) != (
        SOURCE_AUTHORIZATION_REQUIREMENTS
    ):
        _fail("CPLADBAGR_SOURCE_AUTHORIZATION_REQUIREMENTS_MISMATCH")
    if _requirement_names(source.future_bind_invocation_requirements) != (
        INVOCATION_REQUIREMENTS
    ):
        _fail("CPLADBAGR_SOURCE_INVOCATION_REQUIREMENTS_MISMATCH")
    source_requirements = (
        *source.future_bind_authorization_requirements,
        *source.future_bind_invocation_requirements,
    )
    if any(
        not item.separate_future_artifact_required or item.satisfied_by_this_packet
        for item in source_requirements
    ):
        _fail("CPLADBAGR_SOURCE_REQUIREMENT_STATE_INVALID")


def _validate_source(
    source: CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessPacket,
) -> None:
    required = (
        source.final_bind_authorization_readiness_status == SOURCE_STATUS,
        source.request_dispatch_state == "NOT_DISPATCHED",
        source.bind_state == "NOT_BOUND",
        source.authority_state == "NOT_AUTHORIZED",
        source.human_approval_state == "NOT_APPROVED",
        source.final_readiness_state
        == "READY_FOR_FUTURE_PROMOTION_NATIVE_BIND_AUTHORIZATION_GATE",
        source.ready_for_promotion_native_bind_authorization_gate_review,
        source.fresh_verified_source_gate_still_required,
        source.final_bind_authorization_readiness_result
        .accepted_for_future_promotion_native_bind_authorization_gate_review,
        source.approval_context.get("required_human_approval") is True,
        not source.fail_closed,
    )
    if not all(required) or any(getattr(source, field) for field in EFFECT_FIELDS):
        _fail("CPLADBAGR_SOURCE_STATE_INVALID")
    _validate_source_requirements(source)

    try:
        intent = ExecutionIntent(**source.execution_intent)
        descriptor = verify_bind_adapter_contract_descriptor(
            source.adapter_contract_descriptor,
            intent,
        )
    except (
        TypeError,
        ValidationError,
        BindAdapterContractSelectionError,
        ValueError,
    ) as exc:
        raise CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewError(
            "CPLADBAGR_SOURCE_BINDING_INVALID"
        ) from exc

    if (
        intent.to_dict() != source.execution_intent
        or hash_execution_intent(intent) != source.execution_intent_hash
        or intent.execution_intent_id != source.execution_intent_id
    ):
        _fail("CPLADBAGR_EXECUTION_INTENT_INVALID")
    if (
        descriptor.adapter_contract_id != source.adapter_contract_id
        or descriptor.adapter_contract_hash != source.adapter_contract_hash
        or descriptor.adapter_contract_version != source.adapter_contract_version
        or descriptor.model_dump(mode="json") != source.adapter_contract_descriptor
    ):
        _fail("CPLADBAGR_ADAPTER_INVALID")


def _decision(value: Any) -> BindAuthorizationGateReviewDecision:
    try:
        decision = BindAuthorizationGateReviewDecision.model_validate(_json(value))
        decision = decision.model_copy(
            update={"reviewed_at": _timestamp(decision.reviewed_at)}
        )
    except (ValidationError, TypeError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewError(
            "CPLADBAGR_DECISION_INVALID"
        ) from exc
    if not all(getattr(decision, field) for field in ACKNOWLEDGEMENTS):
        _fail("CPLADBAGR_ACKNOWLEDGEMENT_MISSING")
    return decision


def _future_requirements(names: tuple[str, ...]) -> list[dict[str, Any]]:
    return [
        {
            "ordinal": ordinal,
            "name": name,
            "separate_future_artifact_required": True,
            "satisfied_by_this_packet": False,
        }
        for ordinal, name in enumerate(names, 1)
    ]


def _derived(source: Any, decision: Any) -> tuple[Any, ...]:
    accepted = decision.review_outcome == OUTCOMES[0]
    decision_digest = _digest(DOMAINS["decision"], decision)
    result = {
        "source_human_approval_reference_linkage_passed": True,
        "source_authority_evidence_reference_linkage_passed": True,
        "source_bind_pre_dispatch_review_passed": True,
        "exact_execution_intent_preserved": True,
        "exact_adapter_preserved": True,
        "exact_endpoint_binding_preserved": True,
        "exact_credential_scope_binding_preserved": True,
        "all_required_local_linkage_artifacts_present": True,
        "all_required_local_linkage_artifacts_verified": True,
        "source_final_readiness_passed": True,
        "gate_review_passed": accepted,
        "accepted_for_future_promotion_native_fresh_verified_source_gate": accepted,
        "rejection_reasons": []
        if accepted
        else ["BIND_AUTHORIZATION_GATE_REVIEW_FAILED"],
        "comparison_mode": CHECK_MODE,
        "semantic_match_used": False,
        "creates_bind_authorization": False,
        "creates_execution_authority": False,
        "creates_human_approval": False,
        "externally_verifies_human_approval": False,
        "creates_authority_evidence": False,
        "externally_verifies_authority_evidence": False,
        "derives_bind_context_hash": False,
    }
    context = {
        "source_final_bind_authorization_readiness_id": source.promotion_live_adapter_dry_run_final_bind_authorization_readiness_id,
        "source_final_bind_authorization_readiness_hash": source.promotion_live_adapter_dry_run_final_bind_authorization_readiness_hash,
        "source_final_readiness_context_digest": source.final_readiness_context_digest,
        "source_final_readiness_decision_digest": source.final_bind_authorization_readiness_review_decision_digest,
        "source_final_readiness_result_digest": source.final_bind_authorization_readiness_result_digest,
        "source_final_readiness_check_digest": source.final_bind_authorization_readiness_check_digest,
        "source_final_readiness_authorization_requirements_digest": source.future_bind_authorization_requirement_digest,
        "source_final_readiness_invocation_requirements_digest": source.future_bind_invocation_requirement_digest,
        "source_human_approval_linkage_review_id": source.source_human_approval_linkage_review_id,
        "source_human_approval_linkage_review_hash": source.source_human_approval_linkage_review_hash,
        "source_human_approval_linkage_context_digest": source.human_approval_linkage_context_digest,
        "source_authority_evidence_linkage_review_id": source.source_authority_evidence_linkage_review_id,
        "source_authority_evidence_linkage_review_hash": source.source_authority_evidence_linkage_review_hash,
        "source_authority_evidence_linkage_context_digest": source.source_authority_evidence_linkage_context_digest,
        "source_bind_pre_dispatch_review_id": source.source_bind_pre_dispatch_review_id,
        "source_bind_pre_dispatch_review_hash": source.source_bind_pre_dispatch_review_hash,
        "source_operator_review_id": source.source_operator_review_id,
        "source_operator_review_hash": source.source_operator_review_hash,
        "source_credential_authorization_id": source.source_credential_authorization_id,
        "source_credential_authorization_hash": source.source_credential_authorization_hash,
        "source_endpoint_allowlist_evaluation_id": source.source_endpoint_allowlist_evaluation_id,
        "source_endpoint_allowlist_evaluation_hash": source.source_endpoint_allowlist_evaluation_hash,
        "execution_intent_id": source.execution_intent_id,
        "execution_intent_hash": source.execution_intent_hash,
        "adapter_contract_id": source.adapter_contract_id,
        "adapter_contract_hash": source.adapter_contract_hash,
        "endpoint_candidate_id": source.endpoint_candidate["endpoint_candidate_id"],
        "endpoint_candidate_digest": source.endpoint_candidate_digest,
        "endpoint_identity_binding_digest": source.endpoint_identity_binding_digest,
        "credential_reference_id": source.credential_reference["credential_reference_id"],
        "credential_reference_digest": source.credential_reference_digest,
        "credential_scope_binding_digest": source.credential_scope_binding_digest,
        "operator_review_binding_digest": source.operator_review_binding_digest,
        "bind_boundary_precondition_digest": source.bind_boundary_precondition_digest,
        "authority_evidence_reference_bundle_digest": source.authority_evidence_reference_bundle_digest,
        "authority_evidence_binding_matrix_digest": source.authority_evidence_binding_matrix_digest,
        "authority_evidence_linkage_context_digest": source.authority_evidence_linkage_context_digest,
        "human_approval_reference_bundle_digest": source.human_approval_reference_bundle_digest,
        "human_approval_binding_matrix_digest": source.human_approval_binding_matrix_digest,
        "human_approval_linkage_context_digest": source.human_approval_linkage_context_digest,
        "bind_authorization_gate_review_decision_digest": decision_digest,
        "policy_snapshot_lineage": _json(source.policy_snapshot_lineage),
        "policy_lineage": _json(source.policy_lineage),
        "approval_context": _json(source.approval_context),
    }
    checks = [
        {
            "ordinal": ordinal,
            "name": name,
            "passed": True,
            "comparison_mode": CHECK_MODE,
        }
        for ordinal, name in enumerate(CHECK_NAMES, 1)
    ]
    return (
        decision_digest,
        result,
        context,
        checks,
        _future_requirements(AUTHORIZATION_REQUIREMENTS),
        _future_requirements(INVOCATION_REQUIREMENTS),
    )


def _assemble(source: Any, decision: Any, recorded_at: str) -> dict[str, Any]:
    source_raw = source.model_dump(mode="json")
    decision_digest, result, context, checks, authorization, invocation = _derived(
        source, decision
    )
    accepted = result[
        "accepted_for_future_promotion_native_fresh_verified_source_gate"
    ]
    raw = {
        "format_version": FORMAT_VERSION,
        "bind_authorization_gate_review_mechanism": MECHANISM,
        "bind_authorization_gate_review_recorded_at": recorded_at,
        "source_final_bind_authorization_readiness_id": source.promotion_live_adapter_dry_run_final_bind_authorization_readiness_id,
        "source_final_bind_authorization_readiness_hash": source.promotion_live_adapter_dry_run_final_bind_authorization_readiness_hash,
        "source_final_bind_authorization_readiness_packet": source_raw,
        **{field: source_raw[field] for field in COPY_FIELDS},
        **{
            target_name: source_raw[source_name]
            for target_name, source_name in SOURCE_REQUIREMENT_FIELD_MAP.items()
        },
        "bind_authorization_gate_review_decision": decision.model_dump(mode="json"),
        "bind_authorization_gate_review_decision_digest": decision_digest,
        "bind_authorization_gate_review_result": result,
        "bind_authorization_gate_review_result_digest": _digest(
            DOMAINS["result"], result
        ),
        "bind_authorization_gate_review_context": context,
        "bind_authorization_gate_review_context_digest": _digest(
            DOMAINS["context"], context
        ),
        "bind_authorization_gate_review_checks": checks,
        "bind_authorization_gate_review_check_digest": _digest(
            DOMAINS["checks"], checks
        ),
        "future_bind_authorization_requirements": authorization,
        "future_bind_authorization_requirement_digest": _digest(
            DOMAINS["authorization"], authorization
        ),
        "future_bind_invocation_requirements": invocation,
        "future_bind_invocation_requirement_digest": _digest(
            DOMAINS["invocation"], invocation
        ),
        "bind_authorization_gate_review_status": STATUS,
        "request_dispatch_state": "NOT_DISPATCHED",
        "bind_state": "NOT_BOUND",
        "authority_state": "NOT_AUTHORIZED",
        "human_approval_state": "NOT_APPROVED",
        "gate_review_state": OUTCOMES[0] if accepted else OUTCOMES[1],
        "ready_for_promotion_native_fresh_verified_source_gate": accepted,
        "bind_authorization_state": "NOT_AUTHORIZED",
        "bind_context_hash_derived": False,
        "fresh_verified_source_gate_still_required": True,
        "fail_closed": not accepted,
        **{field: False for field in EFFECT_FIELDS},
    }
    digest = _packet_hash(raw)
    raw["promotion_live_adapter_dry_run_bind_authorization_gate_review_hash"] = digest
    raw["promotion_live_adapter_dry_run_bind_authorization_gate_review_id"] = (
        f"pladbagr:v1:sha256:{digest}"
    )
    return raw


def build_canonical_promotion_live_adapter_dry_run_bind_authorization_gate_review_packet(
    source_final_bind_authorization_readiness_packet: Any,
    bind_authorization_gate_review_decision: Any,
    bind_authorization_gate_review_recorded_at: datetime,
) -> CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewPacket:
    """Build self-verifying Gate Review evidence without granting authority."""

    source = _source(_json(source_final_bind_authorization_readiness_packet))
    _validate_source(source)
    decision = _decision(bind_authorization_gate_review_decision)
    recorded_at = _timestamp(bind_authorization_gate_review_recorded_at)
    source_at = _timestamp(source.final_bind_authorization_readiness_recorded_at)
    reviewed_at = _timestamp(decision.reviewed_at)
    if reviewed_at < source_at or recorded_at < reviewed_at:
        _fail("CPLADBAGR_TIMESTAMP_ORDER_INVALID")
    return verify_canonical_promotion_live_adapter_dry_run_bind_authorization_gate_review_packet(
        _assemble(source, decision, recorded_at)
    )


def verify_canonical_promotion_live_adapter_dry_run_bind_authorization_gate_review_packet(
    raw: Any,
) -> CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewPacket:
    """Independently reconstruct and verify the source, bindings, and hashes."""

    try:
        value = raw.model_dump(mode="json") if isinstance(raw, BaseModel) else raw
        packet = CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewPacket.model_validate(
            _json(value)
        )
    except (ValidationError, TypeError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewError(
            "CPLADBAGR_PACKET_INVALID"
        ) from exc

    source = _source(packet.source_final_bind_authorization_readiness_packet)
    _validate_source(source)
    decision = _decision(packet.bind_authorization_gate_review_decision)
    source_at = _timestamp(source.final_bind_authorization_readiness_recorded_at)
    reviewed_at = _timestamp(decision.reviewed_at)
    recorded_at = _timestamp(packet.bind_authorization_gate_review_recorded_at)
    if reviewed_at < source_at or recorded_at < reviewed_at:
        _fail("CPLADBAGR_TIMESTAMP_ORDER_INVALID")

    expected = _assemble(source, decision, recorded_at)
    if packet.model_dump(mode="json") != expected:
        _fail("CPLADBAGR_RECONSTRUCTION_MISMATCH")
    return packet
