"""Record promotion-native Bind pre-dispatch review without effects.

The packet produced here is review evidence only.  It preserves and
independently reverifies the complete promotion-native operator-review source;
it never creates execution authority, Human Approval, Authority Evidence, or
Bind authorization and never performs I/O.
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
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_operator_dispatch_review import (
    CanonicalPromotionLiveAdapterDryRunOperatorDispatchReviewError,
    CanonicalPromotionLiveAdapterDryRunOperatorDispatchReviewPacket,
    verify_canonical_promotion_live_adapter_dry_run_operator_dispatch_review_packet,
)

FORMAT_VERSION = "canonical-promotion-live-adapter-dry-run-bind-pre-dispatch-review/v1"
REVIEW_MECHANISM = (
    "review_promotion_live_adapter_dry_run_bind_pre_dispatch_without_bind_invocation/v1"
)
STATUS = "PROMOTION_NATIVE_BIND_PRE_DISPATCH_REVIEW_RECORDED_NOT_BOUND"
CHECK_MODE = "deterministic_local_promotion_native_bind_pre_dispatch_review_only"
PREFIX = "veritas.promotion-live-adapter-dry-run-bind-pre-dispatch-review"
DECISION_DOMAIN = PREFIX + ".decision/v1"
RESULT_DOMAIN = PREFIX + ".result/v1"
PRECONDITIONS_DOMAIN = PREFIX + ".preconditions/v1"
CHECKS_DOMAIN = PREFIX + ".checks/v1"
REQUIREMENTS_DOMAIN = PREFIX + ".future-requirements/v1"
PACKET_DOMAIN = PREFIX + ".packet/v1"

REVIEW_OUTCOMES = (
    "ACCEPTED_FOR_FUTURE_BIND_DISPATCH_GATE_REVIEW",
    "REJECTED_FOR_FUTURE_BIND_DISPATCH_GATE_REVIEW",
)
CHECK_NAMES = (
    "source_promotion_native_operator_review_verified",
    "source_operator_review_approved",
    "source_request_remains_not_dispatched",
    "exact_execution_intent_preserved",
    "exact_adapter_preserved",
    "exact_endpoint_identity_binding_preserved",
    "exact_credential_scope_binding_preserved",
    "exact_operator_review_preserved",
    "bind_pre_dispatch_decision_closed_schema_valid",
    "reviewer_identity_present",
    "reviewer_role_present",
    "reviewer_attestation_present",
    "review_outcome_allowed",
    "acknowledged_not_bind_authorization",
    "acknowledged_no_bind_invocation",
    "acknowledged_no_bind_receipt",
    "acknowledged_no_trustlog_write",
    "acknowledged_no_dispatch",
    "acknowledged_no_credential_access",
    "acknowledged_no_network",
    "acknowledged_semantic_match_not_authority",
    "bind_boundary_preconditions_constructed",
    "bind_not_invoked",
    "bind_receipt_not_created",
    "trustlog_not_written",
    "request_not_dispatched",
    "endpoint_not_resolved",
    "credential_material_not_accessed",
    "authorization_header_not_constructed",
    "network_not_used",
    "adapter_not_instantiated",
    "execution_authority_not_created",
    "human_approval_not_created",
    "authority_evidence_not_created",
    "future_authority_evidence_linkage_boundary_required",
    "future_fresh_source_gate_required",
    "future_real_bind_authorization_required",
)
FUTURE_REQUIREMENT_NAMES = (
    "promotion_native_authority_evidence_linkage_review",
    "promotion_native_human_approval_reference_linkage_stage",
    "final_policy_admissibility",
    "final_endpoint_identity_binding_recheck",
    "final_credential_reference_scope_recheck",
    "credential_material_resolution_boundary",
    "authorization_header_construction_boundary",
    "runtime_risk_review",
    "idempotency_binding",
    "fresh_source_gate",
    "gate_bound_cryptographic_human_approval",
    "cryptographic_authority_evidence_verification",
    "real_bind_authorization",
    "network_dispatch",
    "bind_invocation",
    "bind_receipt_creation",
    "trustlog_write",
    "external_effect",
    "postcondition_rollback_reconciliation",
)
EFFECT_FIELDS = (
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
    "bind_authorization_issued",
    "bind_receipt_created",
    "trustlog_written",
    "filesystem_used",
    "database_used",
    "provider_called",
    "subprocess_used",
    "external_effect_used",
    "operation_committed",
    "execution_authority_created",
    "human_approval_created",
    "authority_evidence_created",
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


class CanonicalPromotionLiveAdapterDryRunBindPreDispatchReviewError(ValueError):
    """Fail-closed error for invalid promotion-native Bind review evidence."""


class BindPreDispatchReviewDecision(BaseModel):
    """Closed reviewer decision carrying mandatory no-authority attestations."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    bind_pre_dispatch_review_decision_id: str = Field(min_length=1)
    reviewer_id: str = Field(min_length=1)
    reviewer_role: str = Field(min_length=1)
    reviewer_attestation: str = Field(min_length=1)
    reviewed_at: str
    review_outcome: Literal[*REVIEW_OUTCOMES]
    review_reason: str = Field(min_length=1)
    acknowledged_not_bind_authorization: Literal[True]
    acknowledged_no_bind_invocation: Literal[True]
    acknowledged_no_bind_receipt: Literal[True]
    acknowledged_no_trustlog_write: Literal[True]
    acknowledged_no_dispatch: Literal[True]
    acknowledged_no_credential_access: Literal[True]
    acknowledged_no_network_call: Literal[True]
    acknowledged_semantic_match_not_authority: Literal[True]


class BindPreDispatchReviewResult(BaseModel):
    """Deterministic review outcome that explicitly creates no authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    accepted_for_future_bind_dispatch_gate_review: bool
    rejection_reasons: tuple[str, ...]
    review_reason: str
    comparison_mode: Literal[CHECK_MODE]
    semantic_match_used: Literal[False]
    creates_bind_authorization: Literal[False]
    creates_execution_authority: Literal[False]
    creates_human_approval: Literal[False]
    creates_authority_evidence: Literal[False]


class BindBoundaryPreconditions(BaseModel):
    """Content-addressed facts required before any later Bind boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    source_operator_review_id: str
    source_operator_review_hash: str
    source_credential_authorization_id: str
    source_credential_authorization_hash: str
    execution_intent_id: str
    execution_intent_hash: str
    adapter_contract_id: str
    adapter_contract_hash: str
    endpoint_identity_binding_digest: str
    credential_scope_binding_digest: str
    operator_review_binding_digest: str
    bind_pre_dispatch_review_decision_digest: str
    source_verified: Literal[True]
    source_operator_review_accepted: Literal[True]
    request_not_dispatched: Literal[True]
    bind_not_invoked: Literal[True]
    separate_future_authority_evidence_boundary_required: Literal[True]
    separate_future_fresh_source_gate_required: Literal[True]
    separate_future_real_bind_authorization_required: Literal[True]
    satisfied_by_this_packet: Literal[False]


class ReviewCheck(BaseModel):
    """One deterministic ordered no-effect proof."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    check_id: str
    ordinal: int = Field(ge=1, le=len(CHECK_NAMES))
    name: Literal[*CHECK_NAMES]
    mode: Literal[CHECK_MODE]
    passed: Literal[True]
    evidence_ref: str


class FutureRequirement(BaseModel):
    """A future boundary explicitly left unsatisfied by this packet."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    ordinal: int = Field(ge=1, le=len(FUTURE_REQUIREMENT_NAMES))
    name: Literal[*FUTURE_REQUIREMENT_NAMES]
    separate_future_artifact_required: Literal[True]
    satisfied_by_this_packet: Literal[False]


class CanonicalPromotionLiveAdapterDryRunBindPreDispatchReviewPacket(BaseModel):
    """Closed, content-addressed promotion-native Bind review packet."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    format_version: Literal[FORMAT_VERSION]
    promotion_live_adapter_dry_run_bind_pre_dispatch_review_id: str = Field(
        pattern=r"^pladbpr:v1:sha256:[0-9a-f]{64}$"
    )
    promotion_live_adapter_dry_run_bind_pre_dispatch_review_hash: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )
    bind_pre_dispatch_review_mechanism: Literal[REVIEW_MECHANISM]
    bind_pre_dispatch_review_recorded_at: str
    source_operator_dispatch_review_id: str
    source_operator_dispatch_review_hash: str
    source_operator_dispatch_review_packet: dict[str, Any]
    source_credential_authorization_id: str
    source_credential_authorization_hash: str
    bind_pre_dispatch_review_decision: BindPreDispatchReviewDecision
    bind_pre_dispatch_review_decision_digest: str
    bind_pre_dispatch_review_result: BindPreDispatchReviewResult
    bind_pre_dispatch_review_result_digest: str
    bind_boundary_preconditions: BindBoundaryPreconditions
    bind_boundary_precondition_digest: str
    bind_pre_dispatch_review_checks: tuple[ReviewCheck, ...]
    bind_pre_dispatch_review_check_digest: str
    future_requirements: tuple[FutureRequirement, ...]
    future_requirement_digest: str
    bind_pre_dispatch_review_status: Literal[STATUS]
    request_dispatch_state: Literal["NOT_DISPATCHED"]
    bind_state: Literal["NOT_BOUND"]
    ready_for_promotion_native_authority_evidence_linkage_review: bool
    fail_closed: bool
    bind_pre_dispatch_review_is_bind_authorization: Literal[False]
    execution_authorized: Literal[False]
    human_approval_proven: Literal[False]
    authority_evidence_proven: Literal[False]
    ready_for_real_bind: Literal[False]
    ready_for_network_dispatch: Literal[False]
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
    bind_authorization_issued: Literal[False]
    bind_receipt_created: Literal[False]
    trustlog_written: Literal[False]
    filesystem_used: Literal[False]
    database_used: Literal[False]
    provider_called: Literal[False]
    subprocess_used: Literal[False]
    external_effect_used: Literal[False]
    operation_committed: Literal[False]
    execution_authority_created: Literal[False]
    human_approval_created: Literal[False]
    authority_evidence_created: Literal[False]
    apply_performed: Literal[False]
    postcondition_verified: Literal[False]
    rollback_or_revert_performed: Literal[False]
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


def _fail(code: str) -> None:
    raise CanonicalPromotionLiveAdapterDryRunBindPreDispatchReviewError(code)


def _aware(value: Any, code: str) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunBindPreDispatchReviewError(
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
            _fail("PLADBPR_PACKET_INVALID")
        return value
    if isinstance(value, datetime):
        return (
            _aware(value, "PLADBPR_TIMESTAMP_INVALID")
            .astimezone(timezone.utc)
            .isoformat()
        )
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _json(item) for key, item in value.items()}
    _fail("PLADBPR_PACKET_INVALID")


def _digest(domain: str, value: Any) -> str:
    encoded = json.dumps(
        {"domain": domain, "value": _json(value)},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _packet_hash(raw: dict[str, Any]) -> str:
    omitted = {
        "promotion_live_adapter_dry_run_bind_pre_dispatch_review_id",
        "promotion_live_adapter_dry_run_bind_pre_dispatch_review_hash",
    }
    return _digest(
        PACKET_DOMAIN,
        {key: value for key, value in raw.items() if key not in omitted},
    )


def _source(
    value: Any,
) -> CanonicalPromotionLiveAdapterDryRunOperatorDispatchReviewPacket:
    try:
        return verify_canonical_promotion_live_adapter_dry_run_operator_dispatch_review_packet(
            value
        )
    except (
        CanonicalPromotionLiveAdapterDryRunOperatorDispatchReviewError,
        TypeError,
        ValueError,
    ) as exc:
        raise CanonicalPromotionLiveAdapterDryRunBindPreDispatchReviewError(
            "PLADBPR_SOURCE_INVALID"
        ) from exc


def _validate_source(
    source: CanonicalPromotionLiveAdapterDryRunOperatorDispatchReviewPacket,
) -> None:
    if (
        source.operator_review_decision.review_decision
        != "APPROVE_FOR_BIND_PRE_DISPATCH_REVIEW"
        or not source.ready_for_promotion_native_bind_pre_dispatch_review
        or source.fail_closed
        or source.request_dispatch_state != "NOT_DISPATCHED"
    ):
        _fail("PLADBPR_SOURCE_NOT_APPROVED")
    if any(
        (
            source.execution_authorized,
            source.human_approval_proven,
            source.authority_evidence_proven,
            source.ready_for_real_bind,
            source.ready_for_network_dispatch,
        )
    ):
        _fail("PLADBPR_SOURCE_AUTHORITY_INVALID")


def _verify_exact_objects(
    source: CanonicalPromotionLiveAdapterDryRunOperatorDispatchReviewPacket,
) -> None:
    try:
        intent = ExecutionIntent(**source.execution_intent)
        descriptor = verify_bind_adapter_contract_descriptor(
            source.adapter_contract_descriptor, intent
        )
    except (TypeError, ValueError, BindAdapterContractSelectionError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunBindPreDispatchReviewError(
            "PLADBPR_EXACT_OBJECT_INVALID"
        ) from exc
    if (
        intent.to_dict() != source.execution_intent
        or intent.execution_intent_id != source.execution_intent_id
        or hash_execution_intent(intent) != source.execution_intent_hash
    ):
        _fail("PLADBPR_EXECUTION_INTENT_MISMATCH")
    if (
        descriptor.model_dump(mode="json") != source.adapter_contract_descriptor
        or descriptor.adapter_contract_id != source.adapter_contract_id
        or descriptor.adapter_contract_hash != source.adapter_contract_hash
        or descriptor.adapter_contract_version != source.adapter_contract_version
    ):
        _fail("PLADBPR_ADAPTER_MISMATCH")


def _result(decision: BindPreDispatchReviewDecision) -> dict[str, Any]:
    accepted = decision.review_outcome == REVIEW_OUTCOMES[0]
    return {
        "accepted_for_future_bind_dispatch_gate_review": accepted,
        "rejection_reasons": [] if accepted else ["bind_pre_dispatch_review_rejected"],
        "review_reason": decision.review_reason,
        "comparison_mode": CHECK_MODE,
        "semantic_match_used": False,
        "creates_bind_authorization": False,
        "creates_execution_authority": False,
        "creates_human_approval": False,
        "creates_authority_evidence": False,
    }


def _preconditions(source: Any, decision_digest: str) -> dict[str, Any]:
    return {
        "source_operator_review_id": (
            source.promotion_live_adapter_dry_run_operator_dispatch_review_id
        ),
        "source_operator_review_hash": (
            source.promotion_live_adapter_dry_run_operator_dispatch_review_hash
        ),
        "source_credential_authorization_id": (
            source.source_credential_authorization_evaluation_id
        ),
        "source_credential_authorization_hash": (
            source.source_credential_authorization_evaluation_hash
        ),
        "execution_intent_id": source.execution_intent_id,
        "execution_intent_hash": source.execution_intent_hash,
        "adapter_contract_id": source.adapter_contract_id,
        "adapter_contract_hash": source.adapter_contract_hash,
        "endpoint_identity_binding_digest": source.endpoint_identity_binding_digest,
        "credential_scope_binding_digest": source.credential_scope_binding_digest,
        "operator_review_binding_digest": source.operator_review_binding_digest,
        "bind_pre_dispatch_review_decision_digest": decision_digest,
        "source_verified": True,
        "source_operator_review_accepted": True,
        "request_not_dispatched": True,
        "bind_not_invoked": True,
        "separate_future_authority_evidence_boundary_required": True,
        "separate_future_fresh_source_gate_required": True,
        "separate_future_real_bind_authorization_required": True,
        "satisfied_by_this_packet": False,
    }


def _checks(source_hash: str, decision_digest: str) -> list[dict[str, Any]]:
    return [
        {
            "check_id": f"pladbpr-check:v1:{ordinal}:{name.replace('_', '-')}",
            "ordinal": ordinal,
            "name": name,
            "mode": CHECK_MODE,
            "passed": True,
            "evidence_ref": f"source:{source_hash}:decision:{decision_digest}:{name}",
        }
        for ordinal, name in enumerate(CHECK_NAMES, 1)
    ]


def _requirements() -> list[dict[str, Any]]:
    return [
        {
            "ordinal": ordinal,
            "name": name,
            "separate_future_artifact_required": True,
            "satisfied_by_this_packet": False,
        }
        for ordinal, name in enumerate(FUTURE_REQUIREMENT_NAMES, 1)
    ]


def _derived(source: Any, decision: Any) -> tuple[Any, ...]:
    decision_raw = decision.model_dump(mode="json")
    reviewed_at = _aware(decision.reviewed_at, "PLADBPR_REVIEWED_AT_INVALID")
    decision_raw["reviewed_at"] = reviewed_at.astimezone(timezone.utc).isoformat()
    decision_digest = _digest(DECISION_DOMAIN, decision_raw)
    result = _result(decision)
    preconditions = _preconditions(source, decision_digest)
    checks = _checks(
        source.promotion_live_adapter_dry_run_operator_dispatch_review_hash,
        decision_digest,
    )
    return decision_raw, decision_digest, result, preconditions, checks, _requirements()


def build_canonical_promotion_live_adapter_dry_run_bind_pre_dispatch_review_packet(
    source_operator_dispatch_review_packet: Any,
    bind_pre_dispatch_review_decision: Any,
    bind_pre_dispatch_review_recorded_at: datetime,
) -> CanonicalPromotionLiveAdapterDryRunBindPreDispatchReviewPacket:
    """Build and self-verify inert promotion-native Bind review evidence."""
    source = _source(_json(source_operator_dispatch_review_packet))
    _validate_source(source)
    _verify_exact_objects(source)
    try:
        decision = BindPreDispatchReviewDecision.model_validate(
            _json(bind_pre_dispatch_review_decision)
        )
    except ValidationError as exc:
        raise CanonicalPromotionLiveAdapterDryRunBindPreDispatchReviewError(
            "PLADBPR_DECISION_INVALID"
        ) from exc
    reviewed_at = _aware(decision.reviewed_at, "PLADBPR_REVIEWED_AT_INVALID")
    recorded_at = _aware(
        bind_pre_dispatch_review_recorded_at, "PLADBPR_RECORDED_AT_INVALID"
    )
    source_at = _aware(
        source.operator_dispatch_review_recorded_at,
        "PLADBPR_SOURCE_TIME_INVALID",
    )
    if reviewed_at < source_at or recorded_at < reviewed_at:
        _fail("PLADBPR_TIMESTAMP_ORDER_INVALID")
    decision_raw, decision_digest, result, preconditions, checks, requirements = (
        _derived(source, decision)
    )
    source_raw = source.model_dump(mode="json")
    accepted = result["accepted_for_future_bind_dispatch_gate_review"]
    raw = {
        "format_version": FORMAT_VERSION,
        "bind_pre_dispatch_review_mechanism": REVIEW_MECHANISM,
        "bind_pre_dispatch_review_recorded_at": recorded_at.astimezone(
            timezone.utc
        ).isoformat(),
        "source_operator_dispatch_review_id": (
            source.promotion_live_adapter_dry_run_operator_dispatch_review_id
        ),
        "source_operator_dispatch_review_hash": (
            source.promotion_live_adapter_dry_run_operator_dispatch_review_hash
        ),
        "source_operator_dispatch_review_packet": source_raw,
        "source_credential_authorization_id": (
            source.source_credential_authorization_evaluation_id
        ),
        "source_credential_authorization_hash": (
            source.source_credential_authorization_evaluation_hash
        ),
        **{field: source_raw[field] for field in PRESERVED_FIELDS},
        "bind_pre_dispatch_review_decision": decision_raw,
        "bind_pre_dispatch_review_decision_digest": decision_digest,
        "bind_pre_dispatch_review_result": result,
        "bind_pre_dispatch_review_result_digest": _digest(RESULT_DOMAIN, result),
        "bind_boundary_preconditions": preconditions,
        "bind_boundary_precondition_digest": _digest(
            PRECONDITIONS_DOMAIN, preconditions
        ),
        "bind_pre_dispatch_review_checks": checks,
        "bind_pre_dispatch_review_check_digest": _digest(CHECKS_DOMAIN, checks),
        "future_requirements": requirements,
        "future_requirement_digest": _digest(REQUIREMENTS_DOMAIN, requirements),
        "bind_pre_dispatch_review_status": STATUS,
        "request_dispatch_state": "NOT_DISPATCHED",
        "bind_state": "NOT_BOUND",
        "ready_for_promotion_native_authority_evidence_linkage_review": accepted,
        "fail_closed": not accepted,
        "bind_pre_dispatch_review_is_bind_authorization": False,
        "execution_authorized": False,
        "human_approval_proven": False,
        "authority_evidence_proven": False,
        "ready_for_real_bind": False,
        "ready_for_network_dispatch": False,
        **{field: False for field in EFFECT_FIELDS},
    }
    digest = _packet_hash(raw)
    raw["promotion_live_adapter_dry_run_bind_pre_dispatch_review_hash"] = digest
    raw["promotion_live_adapter_dry_run_bind_pre_dispatch_review_id"] = (
        f"pladbpr:v1:sha256:{digest}"
    )
    return (
        verify_canonical_promotion_live_adapter_dry_run_bind_pre_dispatch_review_packet(
            raw
        )
    )


def verify_canonical_promotion_live_adapter_dry_run_bind_pre_dispatch_review_packet(
    raw: Any,
) -> CanonicalPromotionLiveAdapterDryRunBindPreDispatchReviewPacket:
    """Independently reconstruct every source, proof, digest, hash, and ID."""
    try:
        value = raw.model_dump(mode="json") if isinstance(raw, BaseModel) else raw
        packet = CanonicalPromotionLiveAdapterDryRunBindPreDispatchReviewPacket.model_validate(
            _json(value)
        )
    except (
        ValidationError,
        TypeError,
        CanonicalPromotionLiveAdapterDryRunBindPreDispatchReviewError,
    ) as exc:
        raise CanonicalPromotionLiveAdapterDryRunBindPreDispatchReviewError(
            "PLADBPR_PACKET_INVALID"
        ) from exc
    actual = packet.model_dump(mode="json")
    source = _source(packet.source_operator_dispatch_review_packet)
    _validate_source(source)
    _verify_exact_objects(source)
    source_raw = source.model_dump(mode="json")
    identities = (
        packet.source_operator_dispatch_review_id,
        packet.source_operator_dispatch_review_hash,
        packet.source_credential_authorization_id,
        packet.source_credential_authorization_hash,
    )
    expected = (
        source.promotion_live_adapter_dry_run_operator_dispatch_review_id,
        source.promotion_live_adapter_dry_run_operator_dispatch_review_hash,
        source.source_credential_authorization_evaluation_id,
        source.source_credential_authorization_evaluation_hash,
    )
    if identities != expected:
        _fail("PLADBPR_SOURCE_IDENTITY_MISMATCH")
    for field in PRESERVED_FIELDS:
        if _json(getattr(packet, field)) != _json(source_raw[field]):
            _fail("PLADBPR_PRESERVED_FIELD_MISMATCH")
    reviewed_at = _aware(
        packet.bind_pre_dispatch_review_decision.reviewed_at,
        "PLADBPR_REVIEWED_AT_INVALID",
    )
    recorded_at = _aware(
        packet.bind_pre_dispatch_review_recorded_at,
        "PLADBPR_RECORDED_AT_INVALID",
    )
    source_at = _aware(
        source.operator_dispatch_review_recorded_at,
        "PLADBPR_SOURCE_TIME_INVALID",
    )
    if reviewed_at < source_at or recorded_at < reviewed_at:
        _fail("PLADBPR_TIMESTAMP_ORDER_INVALID")
    _, decision_digest, result, preconditions, checks, requirements = _derived(
        source, packet.bind_pre_dispatch_review_decision
    )
    comparisons = (
        packet.bind_pre_dispatch_review_decision_digest == decision_digest,
        _json(packet.bind_pre_dispatch_review_result) == result,
        packet.bind_pre_dispatch_review_result_digest == _digest(RESULT_DOMAIN, result),
        _json(packet.bind_boundary_preconditions) == preconditions,
        packet.bind_boundary_precondition_digest
        == _digest(PRECONDITIONS_DOMAIN, preconditions),
        _json(packet.bind_pre_dispatch_review_checks) == checks,
        packet.bind_pre_dispatch_review_check_digest == _digest(CHECKS_DOMAIN, checks),
        _json(packet.future_requirements) == requirements,
        packet.future_requirement_digest == _digest(REQUIREMENTS_DOMAIN, requirements),
    )
    if not all(comparisons):
        _fail("PLADBPR_DERIVED_VALUE_MISMATCH")
    accepted = result["accepted_for_future_bind_dispatch_gate_review"]
    if (
        packet.fail_closed != (not accepted)
        or packet.ready_for_promotion_native_authority_evidence_linkage_review
        != accepted
    ):
        _fail("PLADBPR_OUTCOME_MISMATCH")
    if any(getattr(packet, field) for field in EFFECT_FIELDS):
        _fail("PLADBPR_EFFECT_INVALID")
    digest = _packet_hash(actual)
    if packet.promotion_live_adapter_dry_run_bind_pre_dispatch_review_hash != digest:
        _fail("PLADBPR_PACKET_HASH_MISMATCH")
    if packet.promotion_live_adapter_dry_run_bind_pre_dispatch_review_id != (
        f"pladbpr:v1:sha256:{digest}"
    ):
        _fail("PLADBPR_PACKET_ID_MISMATCH")
    return packet
