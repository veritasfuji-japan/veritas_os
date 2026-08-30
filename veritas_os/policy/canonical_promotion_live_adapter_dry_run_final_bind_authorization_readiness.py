"""Record promotion-native final Bind authorization readiness evidence.

This module is an inert, deterministic review boundary.  It preserves and
verifies the complete promotion-native metadata chain, but deliberately does
not create approval, authority, authorization, dispatch, Bind, or effects.
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
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_human_approval_linkage import (
    CanonicalPromotionLiveAdapterDryRunHumanApprovalLinkageError,
    CanonicalPromotionLiveAdapterDryRunHumanApprovalLinkageReviewPacket,
    PRESERVED_FIELDS as UPSTREAM_PRESERVED_FIELDS,
    verify_canonical_promotion_live_adapter_dry_run_human_approval_linkage_review_packet,
)

FORMAT_VERSION = (
    "canonical-promotion-live-adapter-dry-run-final-bind-authorization-readiness/v1"
)
REVIEW_MECHANISM = (
    "evaluate_promotion_live_adapter_dry_run_final_bind_authorization_readiness_"
    "without_authorization/v1"
)
STATUS = "PROMOTION_NATIVE_FINAL_BIND_AUTHORIZATION_READINESS_RECORDED_NOT_AUTHORIZED"
COMPARISON_MODE = (
    "deterministic_local_promotion_native_final_bind_authorization_readiness_only"
)
ACCEPTED = "ACCEPTED_FOR_FUTURE_PROMOTION_NATIVE_BIND_AUTHORIZATION_GATE_REVIEW"
REJECTED = "REJECTED_FOR_FUTURE_PROMOTION_NATIVE_BIND_AUTHORIZATION_GATE_REVIEW"
PREFIX = "veritas.promotion-live-adapter-dry-run-final-bind-authorization-readiness"
DOMAINS = {
    name: f"{PREFIX}.{name}/v1"
    for name in (
        "decision",
        "result",
        "context",
        "checks",
        "future-authorization-requirements",
        "future-invocation-requirements",
        "packet",
    )
}

ACKNOWLEDGEMENTS = (
    "acknowledged_not_bind_authorization",
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
    "acknowledged_final_fresh_source_gate_still_required",
    "acknowledged_gate_bound_human_approval_still_required",
    "acknowledged_cryptographic_authority_verification_still_required",
)
CHECK_NAMES = (
    "source_promotion_native_human_approval_linkage_verified",
    "source_human_approval_reference_linkage_structurally_passed",
    "source_authority_evidence_reference_linkage_preserved",
    "source_bind_pre_dispatch_review_preserved",
    "source_operator_review_preserved",
    "source_request_not_dispatched",
    "source_not_bound",
    "source_not_authorized",
    "source_not_approved",
    "required_human_approval_true_preserved",
    "exact_execution_intent_verified",
    "exact_adapter_verified",
    "exact_endpoint_identity_preserved",
    "exact_credential_scope_preserved",
    "exact_authority_evidence_reference_set_preserved",
    "exact_human_approval_reference_set_preserved",
    "authority_linkage_context_preserved",
    "human_approval_linkage_context_preserved",
    "final_readiness_decision_closed_schema_valid",
    "reviewer_identity_present",
    "reviewer_role_present",
    "reviewer_attestation_present",
    "all_required_acknowledgements_true",
    "final_readiness_context_constructed",
    "human_approval_not_created",
    "human_approval_not_externally_verified",
    "authority_evidence_not_created",
    "authority_evidence_not_externally_verified",
    "execution_authority_not_created",
    "bind_authorization_not_created",
    "request_not_dispatched",
    "bind_not_invoked",
    "bind_receipt_not_created",
    "trustlog_not_written",
    "network_not_used",
    "credential_material_not_accessed",
    "authorization_header_not_constructed",
    "future_promotion_native_gate_review_required",
    "future_fresh_verified_source_gate_required",
    "future_exact_bind_context_hash_required",
    "future_signed_gate_bound_human_approval_required",
    "future_cryptographic_authority_verification_required",
    "future_real_bind_authorization_required",
)
FUTURE_AUTHORIZATION_REQUIREMENTS = (
    "promotion_native_bind_authorization_gate_review",
    "fresh_verified_source_gate",
    "exact_bind_context_hash_derivation",
    "final_policy_admissibility",
    "final_endpoint_identity_recheck",
    "final_credential_reference_scope_recheck",
    "runtime_risk_review",
    "idempotency_binding",
    "no_replay_no_duplicate_dispatch_review",
    "gate_bound_signed_human_approval_issuance",
    "gate_bound_human_approval_receipt_verification",
    "cryptographic_authority_evidence_verification",
    "authority_revocation_verification_where_applicable",
    "final_operator_human_go_no_go_confirmation",
    "real_bind_authorization_decision_boundary",
)
FUTURE_INVOCATION_REQUIREMENTS = (
    "real_bind_authorization_exists",
    "real_bind_authorization_verified",
    "authorization_consumption_boundary",
    "single_use_consumption",
    "idempotency_consumption",
    "credential_material_resolution_boundary",
    "authorization_header_construction_boundary",
    "network_dispatch_boundary",
    "bind_invocation",
    "bind_receipt_creation",
    "trustlog_write",
    "effect_state_recording",
    "effect_unknown_handling",
    "external_reconciliation",
    "confirmed_effect",
    "outcome_receipt",
)
EFFECT_FIELDS = (
    "bind_authorization_created", "bind_authorization_issued",
    "execution_authority_created", "execution_authorized",
    "human_approval_created", "human_approval_externally_verified",
    "authority_evidence_created", "authority_evidence_externally_verified",
    "credential_resolved", "credential_material_accessed",
    "credential_material_embedded", "credential_store_accessed",
    "authorization_header_constructed", "token_embedded", "secret_embedded",
    "cookie_embedded", "password_embedded", "private_key_embedded",
    "endpoint_resolved", "endpoint_contacted", "dns_used", "network_used",
    "webhook_invoked", "live_adapter_instantiated",
    "live_adapter_method_invoked", "request_dispatched", "bind_invoked",
    "bind_receipt_created", "trustlog_written", "filesystem_used",
    "database_used", "provider_called", "subprocess_used",
    "external_effect_used", "operation_committed", "apply_performed",
    "postcondition_verified", "rollback_or_revert_performed",
)
HUMAN_LINKAGE_FIELDS = (
    "human_approval_reference_bundle", "human_approval_reference_digests",
    "human_approval_reference_bundle_digest", "human_approval_binding_matrix",
    "human_approval_binding_matrix_digest", "human_approval_linkage_result",
    "human_approval_linkage_result_digest", "human_approval_linkage_context",
    "human_approval_linkage_context_digest",
)
PRESERVED_FIELDS = tuple(dict.fromkeys((*UPSTREAM_PRESERVED_FIELDS, *HUMAN_LINKAGE_FIELDS)))


class FinalBindAuthorizationReadinessReviewDecision(BaseModel):
    """Closed human review statement that grants no authorization."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    final_bind_authorization_readiness_review_decision_id: str = Field(min_length=1)
    reviewer_id: str = Field(min_length=1)
    reviewer_role: str = Field(min_length=1)
    reviewer_attestation: str = Field(min_length=1)
    reviewed_at: str
    review_outcome: Literal[ACCEPTED, REJECTED]
    review_reason: str = Field(min_length=1)
    acknowledged_not_bind_authorization: Literal[True]
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
    acknowledged_final_fresh_source_gate_still_required: Literal[True]
    acknowledged_gate_bound_human_approval_still_required: Literal[True]
    acknowledged_cryptographic_authority_verification_still_required: Literal[True]


class FinalReadinessResult(BaseModel):
    """Deterministic result carrying structural readiness only."""

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
    accepted_for_future_promotion_native_bind_authorization_gate_review: bool
    rejection_reasons: tuple[str, ...]
    comparison_mode: Literal[COMPARISON_MODE]
    semantic_match_used: Literal[False]
    creates_bind_authorization: Literal[False]
    creates_execution_authority: Literal[False]
    creates_human_approval: Literal[False]
    externally_verifies_human_approval: Literal[False]
    creates_authority_evidence: Literal[False]
    externally_verifies_authority_evidence: Literal[False]


class ReadinessCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    ordinal: int = Field(ge=1, le=len(CHECK_NAMES))
    name: Literal[*CHECK_NAMES]
    passed: Literal[True]
    comparison_mode: Literal[COMPARISON_MODE]
    evidence_ref: str = Field(min_length=1)


class FutureRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    ordinal: int = Field(ge=1)
    name: str = Field(min_length=1)
    separate_future_artifact_required: Literal[True]
    satisfied_by_this_packet: Literal[False]


_PACKET_FIELDS: dict[str, tuple[Any, Any]] = {
    "format_version": (Literal[FORMAT_VERSION], ...),
    "promotion_live_adapter_dry_run_final_bind_authorization_readiness_id":
        (str, Field(pattern=r"^pladfbar:v1:sha256:[0-9a-f]{64}$")),
    "promotion_live_adapter_dry_run_final_bind_authorization_readiness_hash": (str, ...),
    "final_bind_authorization_readiness_mechanism": (Literal[REVIEW_MECHANISM], ...),
    "final_bind_authorization_readiness_recorded_at": (str, ...),
    "source_human_approval_linkage_review_id": (str, ...),
    "source_human_approval_linkage_review_hash": (str, ...),
    "source_human_approval_linkage_review_packet": (dict[str, Any], ...),
    "source_human_approval_linkage_context_digest": (str, ...),
    "final_bind_authorization_readiness_review_decision":
        (FinalBindAuthorizationReadinessReviewDecision, ...),
    "final_bind_authorization_readiness_review_decision_digest": (str, ...),
    "final_bind_authorization_readiness_result": (FinalReadinessResult, ...),
    "final_bind_authorization_readiness_result_digest": (str, ...),
    "final_bind_authorization_readiness_context": (dict[str, Any], ...),
    "final_bind_authorization_readiness_context_digest": (str, ...),
    "final_bind_authorization_readiness_checks": (tuple[ReadinessCheck, ...], ...),
    "final_bind_authorization_readiness_check_digest": (str, ...),
    "future_bind_authorization_requirements": (tuple[FutureRequirement, ...], ...),
    "future_bind_authorization_requirement_digest": (str, ...),
    "future_bind_invocation_requirements": (tuple[FutureRequirement, ...], ...),
    "future_bind_invocation_requirement_digest": (str, ...),
    "final_readiness_status": (Literal[STATUS], ...),
    "final_readiness_state": (str, ...),
    "ready_for_promotion_native_bind_authorization_gate_review": (bool, ...),
    "fresh_verified_source_gate_still_required": (Literal[True], ...),
    "request_dispatch_state": (Literal["NOT_DISPATCHED"], ...),
    "bind_state": (Literal["NOT_BOUND"], ...),
    "authority_state": (Literal["NOT_AUTHORIZED"], ...),
    "human_approval_state": (Literal["NOT_APPROVED"], ...),
    "fail_closed": (bool, ...),
    "human_approval_proven": (Literal[False], ...),
    "authority_evidence_proven": (Literal[False], ...),
    "ready_for_real_bind": (Literal[False], ...),
    "ready_for_network_dispatch": (Literal[False], ...),
}
for _field_name in PRESERVED_FIELDS:
    _field = CanonicalPromotionLiveAdapterDryRunHumanApprovalLinkageReviewPacket.model_fields[
        _field_name
    ]
    _PACKET_FIELDS[_field_name] = (_field.annotation, ...)
for _field_name in EFFECT_FIELDS:
    _PACKET_FIELDS[_field_name] = (Literal[False], ...)

CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessPacket = create_model(
    "CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessPacket",
    __config__=ConfigDict(extra="forbid", frozen=True),
    **_PACKET_FIELDS,
)


class CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessError(
    ValueError
):
    """Fail-closed final-readiness verification error."""


def _fail(code: str) -> None:
    raise CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessError(code)


def _json(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            _fail("PLADFBAR_INVALID")
        return value
    if isinstance(value, datetime):
        return _aware(value, "PLADFBAR_TIMESTAMP_INVALID").astimezone(
            timezone.utc
        ).isoformat()
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _json(item) for key, item in value.items()}
    _fail("PLADFBAR_INVALID")


def _aware(value: Any, code: str) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessError(
            code
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail(code)
    return parsed


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
        "promotion_live_adapter_dry_run_final_bind_authorization_readiness_id",
        "promotion_live_adapter_dry_run_final_bind_authorization_readiness_hash",
    }
    return _digest(
        DOMAINS["packet"],
        {key: value for key, value in raw.items() if key not in omitted},
    )


def _source(value: Any) -> Any:
    try:
        return verify_canonical_promotion_live_adapter_dry_run_human_approval_linkage_review_packet(
            value
        )
    except (CanonicalPromotionLiveAdapterDryRunHumanApprovalLinkageError, TypeError, ValueError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessError(
            "PLADFBAR_SOURCE_INVALID"
        ) from exc


def _validate_source(source: Any) -> None:
    if (
        not source.ready_for_promotion_native_final_bind_authorization_readiness_review
        or source.fail_closed
        or source.request_dispatch_state != "NOT_DISPATCHED"
        or source.bind_state != "NOT_BOUND"
        or source.authority_state != "NOT_AUTHORIZED"
        or source.human_approval_state != "NOT_APPROVED"
        or source.approval_context.get("required_human_approval") is not True
    ):
        _fail("PLADFBAR_SOURCE_NOT_ADMISSIBLE")
    forbidden = (
        source.human_approval_proven,
        source.human_approval_externally_verified,
        source.authority_evidence_proven,
        source.authority_evidence_externally_verified,
        source.execution_authorized,
        source.bind_authorization_issued,
        source.ready_for_real_bind,
        source.ready_for_network_dispatch,
    )
    if any(forbidden):
        _fail("PLADFBAR_SOURCE_AUTHORITY_INVALID")
    try:
        intent = ExecutionIntent(**source.execution_intent)
        descriptor = verify_bind_adapter_contract_descriptor(
            source.adapter_contract_descriptor, intent
        )
    except (TypeError, ValueError, BindAdapterContractSelectionError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessError(
            "PLADFBAR_EXACT_OBJECT_INVALID"
        ) from exc
    if (
        intent.to_dict() != source.execution_intent
        or intent.execution_intent_id != source.execution_intent_id
        or hash_execution_intent(intent) != source.execution_intent_hash
    ):
        _fail("PLADFBAR_EXECUTION_INTENT_MISMATCH")
    if (
        descriptor.model_dump(mode="json") != source.adapter_contract_descriptor
        or descriptor.adapter_contract_id != source.adapter_contract_id
        or descriptor.adapter_contract_hash != source.adapter_contract_hash
        or descriptor.adapter_contract_version != source.adapter_contract_version
    ):
        _fail("PLADFBAR_ADAPTER_MISMATCH")


def _decision(value: Any) -> FinalBindAuthorizationReadinessReviewDecision:
    try:
        decision = FinalBindAuthorizationReadinessReviewDecision.model_validate(
            _json(value)
        )
    except (ValidationError, TypeError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessError(
            "PLADFBAR_DECISION_INVALID"
        ) from exc
    _aware(decision.reviewed_at, "PLADFBAR_REVIEWED_AT_INVALID")
    return decision


def _requirements(names: tuple[str, ...]) -> list[dict[str, Any]]:
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
    accepted = decision.review_outcome == ACCEPTED
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
        "accepted_for_future_promotion_native_bind_authorization_gate_review": accepted,
        "rejection_reasons": [] if accepted else [decision.review_reason],
        "comparison_mode": COMPARISON_MODE,
        "semantic_match_used": False,
        "creates_bind_authorization": False,
        "creates_execution_authority": False,
        "creates_human_approval": False,
        "externally_verifies_human_approval": False,
        "creates_authority_evidence": False,
        "externally_verifies_authority_evidence": False,
    }
    context = {
        "source_human_approval_linkage_review_id": source.promotion_live_adapter_dry_run_human_approval_linkage_review_id,
        "source_human_approval_linkage_review_hash": source.promotion_live_adapter_dry_run_human_approval_linkage_review_hash,
        "source_human_approval_linkage_context_digest": source.human_approval_linkage_context_digest,
        "source_authority_linkage_review_id": source.source_authority_evidence_linkage_review_id,
        "source_authority_linkage_review_hash": source.source_authority_evidence_linkage_review_hash,
        "source_authority_linkage_context_digest": source.source_authority_evidence_linkage_context_digest,
        "source_bind_pre_dispatch_review_id": source.source_bind_pre_dispatch_review_id,
        "source_bind_pre_dispatch_review_hash": source.source_bind_pre_dispatch_review_hash,
        "source_operator_review_id": source.source_operator_review_id,
        "source_operator_review_hash": source.source_operator_review_hash,
        "source_credential_authorization_id": source.source_credential_authorization_id,
        "source_credential_authorization_hash": source.source_credential_authorization_hash,
        "source_endpoint_allowlist_id": source.source_endpoint_allowlist_evaluation_id,
        "source_endpoint_allowlist_hash": source.source_endpoint_allowlist_evaluation_hash,
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
        "final_readiness_decision_digest": decision_digest,
        "policy_snapshot_lineage": source.policy_snapshot_lineage,
        "policy_lineage": source.policy_lineage,
        "approval_context": source.approval_context,
    }
    checks = [
        {
            "ordinal": ordinal,
            "name": name,
            "passed": True,
            "comparison_mode": COMPARISON_MODE,
            "evidence_ref": f"source:{source.promotion_live_adapter_dry_run_human_approval_linkage_review_hash}:{name}",
        }
        for ordinal, name in enumerate(CHECK_NAMES, 1)
    ]
    return (
        decision_digest,
        result,
        context,
        checks,
        _requirements(FUTURE_AUTHORIZATION_REQUIREMENTS),
        _requirements(FUTURE_INVOCATION_REQUIREMENTS),
    )


def build_canonical_promotion_live_adapter_dry_run_final_bind_authorization_readiness_packet(
    source_human_approval_linkage_review_packet: Any,
    final_bind_authorization_readiness_review_decision: Any,
    final_bind_authorization_readiness_recorded_at: datetime,
) -> CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessPacket:
    """Build and self-verify non-authorizing final-readiness evidence."""
    source = _source(_json(source_human_approval_linkage_review_packet))
    _validate_source(source)
    decision = _decision(final_bind_authorization_readiness_review_decision)
    reviewed_at = _aware(decision.reviewed_at, "PLADFBAR_REVIEWED_AT_INVALID")
    source_at = _aware(source.human_approval_linkage_review_recorded_at, "PLADFBAR_SOURCE_TIME_INVALID")
    recorded_at = _aware(final_bind_authorization_readiness_recorded_at, "PLADFBAR_RECORDED_AT_INVALID")
    if reviewed_at < source_at or recorded_at < reviewed_at:
        _fail("PLADFBAR_TIMESTAMP_ORDER_INVALID")
    decision_digest, result, context, checks, auth_requirements, invoke_requirements = _derived(source, decision)
    accepted = decision.review_outcome == ACCEPTED
    source_raw = source.model_dump(mode="json")
    raw = {
        "format_version": FORMAT_VERSION,
        "final_bind_authorization_readiness_mechanism": REVIEW_MECHANISM,
        "final_bind_authorization_readiness_recorded_at": recorded_at.astimezone(timezone.utc).isoformat(),
        "source_human_approval_linkage_review_id": source.promotion_live_adapter_dry_run_human_approval_linkage_review_id,
        "source_human_approval_linkage_review_hash": source.promotion_live_adapter_dry_run_human_approval_linkage_review_hash,
        "source_human_approval_linkage_review_packet": source_raw,
        "source_human_approval_linkage_context_digest": source.human_approval_linkage_context_digest,
        **{field: source_raw[field] for field in PRESERVED_FIELDS},
        "final_bind_authorization_readiness_review_decision": decision.model_dump(mode="json"),
        "final_bind_authorization_readiness_review_decision_digest": decision_digest,
        "final_bind_authorization_readiness_result": result,
        "final_bind_authorization_readiness_result_digest": _digest(DOMAINS["result"], result),
        "final_bind_authorization_readiness_context": context,
        "final_bind_authorization_readiness_context_digest": _digest(DOMAINS["context"], context),
        "final_bind_authorization_readiness_checks": checks,
        "final_bind_authorization_readiness_check_digest": _digest(DOMAINS["checks"], checks),
        "future_bind_authorization_requirements": auth_requirements,
        "future_bind_authorization_requirement_digest": _digest(DOMAINS["future-authorization-requirements"], auth_requirements),
        "future_bind_invocation_requirements": invoke_requirements,
        "future_bind_invocation_requirement_digest": _digest(DOMAINS["future-invocation-requirements"], invoke_requirements),
        "final_readiness_status": STATUS,
        "final_readiness_state": "READY_FOR_FUTURE_PROMOTION_NATIVE_BIND_AUTHORIZATION_GATE" if accepted else "NOT_READY_FOR_FUTURE_PROMOTION_NATIVE_BIND_AUTHORIZATION_GATE",
        "ready_for_promotion_native_bind_authorization_gate_review": accepted,
        "fresh_verified_source_gate_still_required": True,
        "request_dispatch_state": "NOT_DISPATCHED",
        "bind_state": "NOT_BOUND",
        "authority_state": "NOT_AUTHORIZED",
        "human_approval_state": "NOT_APPROVED",
        "fail_closed": not accepted,
        "human_approval_proven": False,
        "authority_evidence_proven": False,
        "ready_for_real_bind": False,
        "ready_for_network_dispatch": False,
        **{field: False for field in EFFECT_FIELDS},
    }
    digest = _packet_hash(raw)
    raw["promotion_live_adapter_dry_run_final_bind_authorization_readiness_hash"] = digest
    raw["promotion_live_adapter_dry_run_final_bind_authorization_readiness_id"] = f"pladfbar:v1:sha256:{digest}"
    return verify_canonical_promotion_live_adapter_dry_run_final_bind_authorization_readiness_packet(raw)


def verify_canonical_promotion_live_adapter_dry_run_final_bind_authorization_readiness_packet(
    raw: Any,
) -> CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessPacket:
    """Independently reconstruct and fail closed on every packet value."""
    try:
        value = raw.model_dump(mode="json") if isinstance(raw, BaseModel) else raw
        packet = CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessPacket.model_validate(_json(value))
    except (ValidationError, TypeError, CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessError("PLADFBAR_PACKET_INVALID") from exc
    actual = packet.model_dump(mode="json")
    source = _source(packet.source_human_approval_linkage_review_packet)
    _validate_source(source)
    source_raw = source.model_dump(mode="json")
    if (
        packet.source_human_approval_linkage_review_id != source.promotion_live_adapter_dry_run_human_approval_linkage_review_id
        or packet.source_human_approval_linkage_review_hash != source.promotion_live_adapter_dry_run_human_approval_linkage_review_hash
        or packet.source_human_approval_linkage_context_digest != source.human_approval_linkage_context_digest
        or any(_json(getattr(packet, field)) != _json(source_raw[field]) for field in PRESERVED_FIELDS)
    ):
        _fail("PLADFBAR_SOURCE_MISMATCH")
    decision = _decision(packet.final_bind_authorization_readiness_review_decision)
    reviewed_at = _aware(decision.reviewed_at, "PLADFBAR_REVIEWED_AT_INVALID")
    recorded_at = _aware(packet.final_bind_authorization_readiness_recorded_at, "PLADFBAR_RECORDED_AT_INVALID")
    if reviewed_at < _aware(source.human_approval_linkage_review_recorded_at, "PLADFBAR_SOURCE_TIME_INVALID") or recorded_at < reviewed_at:
        _fail("PLADFBAR_TIMESTAMP_ORDER_INVALID")
    decision_digest, result, context, checks, auth_requirements, invoke_requirements = _derived(source, decision)
    comparisons = (
        packet.final_bind_authorization_readiness_review_decision_digest == decision_digest,
        _json(packet.final_bind_authorization_readiness_result) == result,
        packet.final_bind_authorization_readiness_result_digest == _digest(DOMAINS["result"], result),
        packet.final_bind_authorization_readiness_context == context,
        packet.final_bind_authorization_readiness_context_digest == _digest(DOMAINS["context"], context),
        _json(packet.final_bind_authorization_readiness_checks) == checks,
        packet.final_bind_authorization_readiness_check_digest == _digest(DOMAINS["checks"], checks),
        _json(packet.future_bind_authorization_requirements) == auth_requirements,
        packet.future_bind_authorization_requirement_digest == _digest(DOMAINS["future-authorization-requirements"], auth_requirements),
        _json(packet.future_bind_invocation_requirements) == invoke_requirements,
        packet.future_bind_invocation_requirement_digest == _digest(DOMAINS["future-invocation-requirements"], invoke_requirements),
    )
    if not all(comparisons):
        _fail("PLADFBAR_DERIVED_MISMATCH")
    accepted = decision.review_outcome == ACCEPTED
    if (
        packet.ready_for_promotion_native_bind_authorization_gate_review is not accepted
        or packet.fail_closed is accepted
        or packet.final_readiness_state != ("READY_FOR_FUTURE_PROMOTION_NATIVE_BIND_AUTHORIZATION_GATE" if accepted else "NOT_READY_FOR_FUTURE_PROMOTION_NATIVE_BIND_AUTHORIZATION_GATE")
    ):
        _fail("PLADFBAR_ROUTING_INVALID")
    if any(getattr(packet, field) for field in EFFECT_FIELDS):
        _fail("PLADFBAR_EFFECT_INVALID")
    digest = _packet_hash(actual)
    if packet.promotion_live_adapter_dry_run_final_bind_authorization_readiness_hash != digest:
        _fail("PLADFBAR_PACKET_HASH_MISMATCH")
    if packet.promotion_live_adapter_dry_run_final_bind_authorization_readiness_id != f"pladfbar:v1:sha256:{digest}":
        _fail("PLADFBAR_PACKET_ID_MISMATCH")
    return packet
