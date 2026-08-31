"""Record promotion-native final Bind authorization readiness evidence.

The boundary is deterministic and local.  It independently verifies the
Human Approval reference-linkage source and preserves its promotion-native
bindings, but creates no proof, authority, authorization, dispatch, or effect.
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
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_human_approval_linkage import (
    CanonicalPromotionLiveAdapterDryRunHumanApprovalLinkageError,
    CanonicalPromotionLiveAdapterDryRunHumanApprovalLinkageReviewPacket,
    verify_canonical_promotion_live_adapter_dry_run_human_approval_linkage_review_packet,
)

FORMAT_VERSION = (
    "canonical-promotion-live-adapter-dry-run-final-bind-authorization-"
    "readiness/v1"
)
MECHANISM = (
    "review_promotion_native_final_bind_authorization_readiness_without_"
    "authorization_or_external_effect/v1"
)
STATUS = "PROMOTION_NATIVE_FINAL_BIND_AUTHORIZATION_READINESS_RECORDED_NOT_AUTHORIZED"
SOURCE_STATUS = "PROMOTION_NATIVE_HUMAN_APPROVAL_REFERENCE_LINKAGE_REVIEWED_NOT_APPROVED"
CHECK_MODE = (
    "deterministic_local_promotion_native_final_bind_authorization_readiness_only"
)
OUTCOMES = (
    "ACCEPTED_FOR_FUTURE_PROMOTION_NATIVE_BIND_AUTHORIZATION_GATE_REVIEW",
    "REJECTED_FOR_FUTURE_PROMOTION_NATIVE_BIND_AUTHORIZATION_GATE_REVIEW",
)
PREFIX = "veritas.promotion-live-adapter-dry-run-final-bind-authorization-readiness"
DOMAINS = {
    name: f"{PREFIX}.{name}/v1"
    for name in ("decision", "result", "context", "checks", "future", "packet")
}
ACKNOWLEDGEMENTS = (
    "acknowledged_not_bind_authorization",
    "acknowledged_no_bind_invocation",
    "acknowledged_no_bind_receipt",
    "acknowledged_no_trustlog_write",
    "acknowledged_no_dispatch",
    "acknowledged_no_execution_authority",
    "acknowledged_no_human_approval_creation",
    "acknowledged_no_authority_evidence_creation",
    "acknowledged_no_credential_access",
    "acknowledged_no_authorization_header",
    "acknowledged_no_network_call",
    "acknowledged_semantic_match_not_authority",
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
FUTURE_REQUIREMENTS = (
    "promotion_native_bind_authorization_gate_review",
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
COPY_FIELDS = (
    "request_descriptor", "execution_intent", "execution_intent_id",
    "execution_intent_hash", "adapter_contract_descriptor",
    "adapter_contract_id", "adapter_contract_hash", "adapter_contract_version",
    "endpoint_candidate", "endpoint_candidate_digest",
    "endpoint_identity_binding", "endpoint_identity_binding_digest",
    "credential_reference", "credential_reference_digest",
    "credential_scope_binding", "credential_scope_binding_digest",
    "operator_review_binding", "operator_review_binding_digest",
    "bind_boundary_preconditions", "bind_boundary_precondition_digest",
    "authority_evidence_reference_bundle",
    "authority_evidence_reference_bundle_digest",
    "authority_evidence_binding_matrix",
    "authority_evidence_binding_matrix_digest",
    "authority_evidence_linkage_context",
    "authority_evidence_linkage_context_digest",
    "human_approval_reference_bundle", "human_approval_reference_bundle_digest",
    "human_approval_binding_matrix", "human_approval_binding_matrix_digest",
    "human_approval_linkage_context", "human_approval_linkage_context_digest",
)
EFFECT_FIELDS = (
    "human_approval_created", "human_approval_externally_verified",
    "human_approval_proven", "authority_evidence_created",
    "authority_evidence_externally_verified", "authority_evidence_proven",
    "execution_authority_created", "execution_authorized",
    "bind_authorization_created", "bind_authorization_issued",
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
    "ready_for_real_bind", "ready_for_network_dispatch",
)


class CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessError(
    ValueError
):
    """Stable fail-closed error for invalid final readiness evidence."""


class FinalBindAuthorizationReadinessReviewDecision(BaseModel):
    """Closed reviewer decision which expressly grants no authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    final_bind_authorization_readiness_review_decision_id: str = Field(min_length=1)
    reviewer_id: str = Field(min_length=1)
    reviewer_role: str = Field(min_length=1)
    reviewer_attestation: str = Field(min_length=1)
    reviewed_at: str
    review_outcome: Literal[*OUTCOMES]
    review_reason: str = Field(min_length=1)
    acknowledged_not_bind_authorization: bool
    acknowledged_no_bind_invocation: bool
    acknowledged_no_bind_receipt: bool
    acknowledged_no_trustlog_write: bool
    acknowledged_no_dispatch: bool
    acknowledged_no_execution_authority: bool
    acknowledged_no_human_approval_creation: bool
    acknowledged_no_authority_evidence_creation: bool
    acknowledged_no_credential_access: bool
    acknowledged_no_authorization_header: bool
    acknowledged_no_network_call: bool
    acknowledged_semantic_match_not_authority: bool


class FinalReadinessResult(BaseModel):
    """Final local comparison result with no proof or authorization semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    review_outcome: Literal[*OUTCOMES]
    ready_for_promotion_native_bind_authorization_gate_review: bool
    rejection_reasons: tuple[str, ...]
    comparison_mode: Literal[CHECK_MODE]
    human_approval_proven: Literal[False]
    human_approval_externally_verified: Literal[False]
    authority_evidence_proven: Literal[False]
    authority_evidence_externally_verified: Literal[False]
    execution_authorized: Literal[False]
    bind_authorization_issued: Literal[False]


class ReadinessCheck(BaseModel):
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
    name: Literal[*FUTURE_REQUIREMENTS]
    separate_future_artifact_required: Literal[True]
    satisfied_by_this_packet: Literal[False]


class CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessPacket(
    BaseModel
):
    """Content-addressed promotion-native final readiness evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    format_version: Literal[FORMAT_VERSION]
    promotion_live_adapter_dry_run_final_bind_authorization_readiness_id: str
    promotion_live_adapter_dry_run_final_bind_authorization_readiness_hash: str
    final_bind_authorization_readiness_mechanism: Literal[MECHANISM]
    final_bind_authorization_readiness_recorded_at: str
    source_human_approval_linkage_review_id: str
    source_human_approval_linkage_review_hash: str
    source_human_approval_linkage_review_packet: dict[str, Any]
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
    operator_review_binding: dict[str, Any]
    operator_review_binding_digest: str
    bind_boundary_preconditions: dict[str, Any]
    bind_boundary_precondition_digest: str
    authority_evidence_reference_bundle: dict[str, Any]
    authority_evidence_reference_bundle_digest: str
    authority_evidence_binding_matrix: tuple[dict[str, Any], ...]
    authority_evidence_binding_matrix_digest: str
    authority_evidence_linkage_context: dict[str, Any]
    authority_evidence_linkage_context_digest: str
    human_approval_reference_bundle: dict[str, Any]
    human_approval_reference_bundle_digest: str
    human_approval_binding_matrix: tuple[dict[str, Any], ...]
    human_approval_binding_matrix_digest: str
    human_approval_linkage_context: dict[str, Any]
    human_approval_linkage_context_digest: str
    final_bind_authorization_readiness_review_decision: FinalBindAuthorizationReadinessReviewDecision
    final_bind_authorization_readiness_review_decision_digest: str
    final_bind_authorization_readiness_result: FinalReadinessResult
    final_bind_authorization_readiness_result_digest: str
    final_readiness_context: dict[str, Any]
    final_readiness_context_digest: str
    final_bind_authorization_readiness_checks: tuple[ReadinessCheck, ...]
    final_bind_authorization_readiness_check_digest: str
    future_requirements: tuple[FutureRequirement, ...]
    future_requirement_digest: str
    final_bind_authorization_readiness_status: Literal[STATUS]
    request_dispatch_state: Literal["NOT_DISPATCHED"]
    bind_state: Literal["NOT_BOUND"]
    authority_state: Literal["NOT_AUTHORIZED"]
    human_approval_state: Literal["NOT_APPROVED"]
    ready_for_promotion_native_bind_authorization_gate_review: bool
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


def _fail(code: str) -> None:
    raise CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessError(
        code
    )


def _timestamp(value: Any) -> str:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessError(
            "CPLADFBAR_TIMESTAMP_INVALID"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail("CPLADFBAR_TIMESTAMP_INVALID")
    return parsed.astimezone(timezone.utc).isoformat()


def _json(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
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
    _fail("CPLADFBAR_JSON_INVALID")


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


def _source(
    value: Any,
) -> CanonicalPromotionLiveAdapterDryRunHumanApprovalLinkageReviewPacket:
    try:
        return verify_canonical_promotion_live_adapter_dry_run_human_approval_linkage_review_packet(
            value
        )
    except (
        CanonicalPromotionLiveAdapterDryRunHumanApprovalLinkageError,
        TypeError,
        ValueError,
    ) as exc:
        raise CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessError(
            "CPLADFBAR_SOURCE_INVALID"
        ) from exc


def _validate_source(
    source: CanonicalPromotionLiveAdapterDryRunHumanApprovalLinkageReviewPacket,
) -> None:
    required = (
        source.human_approval_linkage_status == SOURCE_STATUS,
        source.request_dispatch_state == "NOT_DISPATCHED",
        source.bind_state == "NOT_BOUND",
        source.authority_state == "NOT_AUTHORIZED",
        source.human_approval_state == "NOT_APPROVED",
        source.ready_for_promotion_native_final_bind_authorization_readiness_review,
        not source.fail_closed,
    )
    if not all(required) or any(getattr(source, field) for field in EFFECT_FIELDS):
        _fail("CPLADFBAR_SOURCE_STATE_INVALID")
    try:
        intent = ExecutionIntent(**source.execution_intent)
        descriptor = verify_bind_adapter_contract_descriptor(
            source.adapter_contract_descriptor, intent
        )
    except (
        TypeError,
        ValidationError,
        BindAdapterContractSelectionError,
        ValueError,
    ) as exc:
        raise CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessError(
            "CPLADFBAR_SOURCE_BINDING_INVALID"
        ) from exc
    if hash_execution_intent(intent) != source.execution_intent_hash:
        _fail("CPLADFBAR_EXECUTION_INTENT_INVALID")
    if intent.execution_intent_id != source.execution_intent_id:
        _fail("CPLADFBAR_EXECUTION_INTENT_INVALID")
    if descriptor.adapter_contract_id != source.adapter_contract_id:
        _fail("CPLADFBAR_ADAPTER_INVALID")
    if descriptor.adapter_contract_hash != source.adapter_contract_hash:
        _fail("CPLADFBAR_ADAPTER_INVALID")


def _decision(value: Any) -> FinalBindAuthorizationReadinessReviewDecision:
    try:
        decision = FinalBindAuthorizationReadinessReviewDecision.model_validate(
            _json(value)
        )
        decision = decision.model_copy(
            update={"reviewed_at": _timestamp(decision.reviewed_at)}
        )
    except (ValidationError, TypeError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessError(
            "CPLADFBAR_DECISION_INVALID"
        ) from exc
    if not all(getattr(decision, field) for field in ACKNOWLEDGEMENTS):
        _fail("CPLADFBAR_ACKNOWLEDGEMENT_MISSING")
    return decision


def _derived(source: Any, decision: Any) -> tuple[Any, ...]:
    accepted = decision.review_outcome == OUTCOMES[0]
    result = {
        "review_outcome": decision.review_outcome,
        "ready_for_promotion_native_bind_authorization_gate_review": accepted,
        "rejection_reasons": [] if accepted else ["FINAL_READINESS_REVIEW_REJECTED"],
        "comparison_mode": CHECK_MODE,
        "human_approval_proven": False,
        "human_approval_externally_verified": False,
        "authority_evidence_proven": False,
        "authority_evidence_externally_verified": False,
        "execution_authorized": False,
        "bind_authorization_issued": False,
    }
    context = {
        field: _json(getattr(source, field))
        for field in COPY_FIELDS
        if field.endswith(("_id", "_hash", "_digest"))
    }
    context["review_outcome"] = decision.review_outcome
    checks = [
        {
            "ordinal": ordinal,
            "name": name,
            "passed": True,
            "comparison_mode": CHECK_MODE,
        }
        for ordinal, name in enumerate(CHECK_NAMES, 1)
    ]
    future = [
        {
            "ordinal": ordinal,
            "name": name,
            "separate_future_artifact_required": True,
            "satisfied_by_this_packet": False,
        }
        for ordinal, name in enumerate(FUTURE_REQUIREMENTS, 1)
    ]
    return result, context, checks, future


def _assemble(source: Any, decision: Any, recorded_at: str) -> dict[str, Any]:
    source_raw = source.model_dump(mode="json")
    result, context, checks, future = _derived(source, decision)
    accepted = result[
        "ready_for_promotion_native_bind_authorization_gate_review"
    ]
    raw = {
        "format_version": FORMAT_VERSION,
        "final_bind_authorization_readiness_mechanism": MECHANISM,
        "final_bind_authorization_readiness_recorded_at": recorded_at,
        "source_human_approval_linkage_review_id": source.promotion_live_adapter_dry_run_human_approval_linkage_review_id,
        "source_human_approval_linkage_review_hash": source.promotion_live_adapter_dry_run_human_approval_linkage_review_hash,
        "source_human_approval_linkage_review_packet": source_raw,
        **{field: source_raw[field] for field in COPY_FIELDS},
        "final_bind_authorization_readiness_review_decision": decision.model_dump(
            mode="json"
        ),
        "final_bind_authorization_readiness_review_decision_digest": _digest(
            DOMAINS["decision"], decision
        ),
        "final_bind_authorization_readiness_result": result,
        "final_bind_authorization_readiness_result_digest": _digest(
            DOMAINS["result"], result
        ),
        "final_readiness_context": context,
        "final_readiness_context_digest": _digest(DOMAINS["context"], context),
        "final_bind_authorization_readiness_checks": checks,
        "final_bind_authorization_readiness_check_digest": _digest(
            DOMAINS["checks"], checks
        ),
        "future_requirements": future,
        "future_requirement_digest": _digest(DOMAINS["future"], future),
        "final_bind_authorization_readiness_status": STATUS,
        "request_dispatch_state": "NOT_DISPATCHED",
        "bind_state": "NOT_BOUND",
        "authority_state": "NOT_AUTHORIZED",
        "human_approval_state": "NOT_APPROVED",
        "ready_for_promotion_native_bind_authorization_gate_review": accepted,
        "fail_closed": not accepted,
        **{field: False for field in EFFECT_FIELDS},
    }
    digest = _packet_hash(raw)
    raw[
        "promotion_live_adapter_dry_run_final_bind_authorization_readiness_hash"
    ] = digest
    raw[
        "promotion_live_adapter_dry_run_final_bind_authorization_readiness_id"
    ] = f"pladfbar:v1:sha256:{digest}"
    return raw


def build_canonical_promotion_live_adapter_dry_run_final_bind_authorization_readiness_packet(
    source_human_approval_linkage_review_packet: Any,
    final_bind_authorization_readiness_review_decision: Any,
    final_bind_authorization_readiness_recorded_at: datetime,
) -> CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessPacket:
    """Build self-verifying final readiness evidence without granting authority."""
    source = _source(_json(source_human_approval_linkage_review_packet))
    _validate_source(source)
    decision = _decision(final_bind_authorization_readiness_review_decision)
    recorded_at = _timestamp(final_bind_authorization_readiness_recorded_at)
    source_at = _timestamp(source.human_approval_linkage_review_recorded_at)
    if _timestamp(decision.reviewed_at) < source_at or recorded_at < _timestamp(
        decision.reviewed_at
    ):
        _fail("CPLADFBAR_TIMESTAMP_ORDER_INVALID")
    return verify_canonical_promotion_live_adapter_dry_run_final_bind_authorization_readiness_packet(
        _assemble(source, decision, recorded_at)
    )


def verify_canonical_promotion_live_adapter_dry_run_final_bind_authorization_readiness_packet(
    raw: Any,
) -> CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessPacket:
    """Independently reconstruct and verify the source, bindings, and hashes."""
    try:
        value = raw.model_dump(mode="json") if isinstance(raw, BaseModel) else raw
        packet = CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessPacket.model_validate(
            _json(value)
        )
    except (ValidationError, TypeError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunFinalBindAuthorizationReadinessError(
            "CPLADFBAR_PACKET_INVALID"
        ) from exc
    source = _source(packet.source_human_approval_linkage_review_packet)
    _validate_source(source)
    decision = _decision(packet.final_bind_authorization_readiness_review_decision)
    source_at = _timestamp(source.human_approval_linkage_review_recorded_at)
    reviewed_at = _timestamp(decision.reviewed_at)
    recorded_at = _timestamp(packet.final_bind_authorization_readiness_recorded_at)
    if reviewed_at < source_at or recorded_at < reviewed_at:
        _fail("CPLADFBAR_TIMESTAMP_ORDER_INVALID")
    expected = _assemble(source, decision, recorded_at)
    if packet.model_dump(mode="json") != expected:
        _fail("CPLADFBAR_RECONSTRUCTION_MISMATCH")
    return packet
