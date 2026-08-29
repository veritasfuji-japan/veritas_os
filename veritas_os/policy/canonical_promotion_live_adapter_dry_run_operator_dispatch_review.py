"""Record a promotion-native operator review without dispatch or effects.

This boundary consumes only independently verified promotion-native credential
authorization evidence.  Operator approval is procedural evidence: it never
creates Human Approval, Authority Evidence, execution authority, or Bind
authorization.
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
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_credential_authorization import (
    CanonicalPromotionLiveAdapterDryRunCredentialAuthorizationError,
    CanonicalPromotionLiveAdapterDryRunCredentialAuthorizationEvaluationPacket,
    verify_canonical_promotion_live_adapter_dry_run_credential_authorization_evaluation_packet,
)

FORMAT_VERSION = "canonical-promotion-live-adapter-dry-run-operator-dispatch-review/v1"
REVIEW_MECHANISM = (
    "record_promotion_live_adapter_dry_run_operator_dispatch_review_without_dispatch/v1"
)
STATUS = "PROMOTION_NATIVE_OPERATOR_DISPATCH_REVIEW_RECORDED_NOT_DISPATCHED"
CHECK_MODE = "deterministic_local_promotion_native_operator_review_only"
PREFIX = "veritas.promotion-live-adapter-dry-run-operator-dispatch-review"
DECISION_DOMAIN = PREFIX + ".decision/v1"
BINDING_DOMAIN = PREFIX + ".binding/v1"
CHECKS_DOMAIN = PREFIX + ".checks/v1"
REQUIREMENTS_DOMAIN = PREFIX + ".future-requirements/v1"
PACKET_DOMAIN = PREFIX + ".packet/v1"

REVIEW_DECISIONS = (
    "APPROVE_FOR_BIND_PRE_DISPATCH_REVIEW",
    "REJECT",
    "HOLD_FOR_MORE_EVIDENCE",
)
LINEAGE_FIELDS = (
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
) + LINEAGE_FIELDS
CHECK_NAMES = (
    "source_promotion_native_credential_authorization_verified",
    "source_credential_authorization_accepted",
    "source_remains_not_dispatched",
    "exact_execution_intent_preserved",
    "exact_adapter_preserved",
    "exact_endpoint_identity_preserved",
    "exact_credential_reference_preserved",
    "exact_credential_scope_binding_preserved",
    "operator_decision_closed_schema_valid",
    "reviewer_identity_present",
    "reviewer_role_present",
    "reviewer_organization_present",
    "review_decision_allowed",
    "reviewed_endpoint_exact_match",
    "reviewed_credential_exact_match",
    "reviewed_adapter_exact_match",
    "reviewed_target_system_exact_match",
    "reviewed_target_resource_exact_match",
    "scope_limitations_acknowledged",
    "non_effect_guarantees_acknowledged",
    "future_bind_pre_dispatch_review_acknowledged",
    "no_dispatch_acknowledged",
    "no_credential_access_acknowledged",
    "no_network_acknowledged",
    "no_bind_acknowledged",
    "no_bind_receipt_acknowledged",
    "no_trustlog_write_acknowledged",
    "operator_review_binding_constructed",
    "credential_not_resolved",
    "credential_material_not_accessed",
    "network_not_used",
    "adapter_not_instantiated",
    "bind_not_invoked",
    "trustlog_not_written",
    "request_not_dispatched",
    "future_promotion_native_bind_pre_dispatch_review_required",
)
FUTURE_REQUIREMENT_NAMES = (
    "promotion_native_bind_pre_dispatch_review",
    "authority_evidence_verification",
    "fresh_source_gate",
    "gate_bound_human_approval",
    "final_endpoint_identity_recheck",
    "final_credential_reference_scope_recheck",
    "credential_material_resolution_boundary",
    "authorization_header_construction_boundary",
    "runtime_risk_review",
    "idempotency_binding",
    "real_bind_authorization",
    "network_dispatch",
    "bind_invocation",
    "bind_receipt_creation",
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
    "apply_performed",
    "postcondition_verified",
    "rollback_or_revert_performed",
)


class CanonicalPromotionLiveAdapterDryRunOperatorDispatchReviewError(ValueError):
    """Stable fail-closed error for invalid promotion-native review evidence."""


class OperatorReviewDecision(BaseModel):
    """Closed reviewer decision with mandatory no-effect acknowledgements."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    operator_review_id: str = Field(min_length=1)
    reviewer_id: str = Field(min_length=1)
    reviewer_role: str = Field(min_length=1)
    reviewer_organization: str = Field(min_length=1)
    reviewed_at: str
    review_decision: Literal[*REVIEW_DECISIONS]
    review_reason: str = Field(min_length=1)
    reviewed_endpoint_candidate_id: str = Field(min_length=1)
    reviewed_credential_reference_id: str = Field(min_length=1)
    reviewed_adapter_contract_id: str = Field(min_length=1)
    reviewed_target_system: str = Field(min_length=1)
    reviewed_target_resource_scope: str = Field(min_length=1)
    acknowledged_scope_limitations: Literal[True]
    acknowledged_non_effect_guarantees: Literal[True]
    acknowledged_future_bind_pre_dispatch_review_required: Literal[True]
    acknowledged_no_dispatch: Literal[True]
    acknowledged_no_credential_access: Literal[True]
    acknowledged_no_network: Literal[True]
    acknowledged_no_bind: Literal[True]
    acknowledged_no_bind_receipt: Literal[True]
    acknowledged_no_trustlog_write: Literal[True]


class OperatorDispatchReviewCheck(BaseModel):
    """One deterministic ordered proof with explicit no-effect facts."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    check_id: str
    ordinal: int = Field(ge=1, le=len(CHECK_NAMES))
    name: Literal[*CHECK_NAMES]
    mode: Literal[CHECK_MODE]
    passed: Literal[True]
    evidence_ref: str
    credential_material_accessed: Literal[False]
    network_used: Literal[False]
    request_dispatched: Literal[False]
    bind_invoked: Literal[False]
    trustlog_written: Literal[False]


class FutureRequirement(BaseModel):
    """A future authority or effect boundary not satisfied by this packet."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    ordinal: int = Field(ge=1, le=len(FUTURE_REQUIREMENT_NAMES))
    name: Literal[*FUTURE_REQUIREMENT_NAMES]
    separate_future_artifact_required: Literal[True]
    satisfied_by_this_packet: Literal[False]


class CanonicalPromotionLiveAdapterDryRunOperatorDispatchReviewPacket(BaseModel):
    """Closed content-addressed promotion-native operator review packet."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    format_version: Literal[FORMAT_VERSION]
    promotion_live_adapter_dry_run_operator_dispatch_review_id: str = Field(
        pattern=r"^plador:v1:sha256:[0-9a-f]{64}$"
    )
    promotion_live_adapter_dry_run_operator_dispatch_review_hash: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )
    operator_dispatch_review_mechanism: Literal[REVIEW_MECHANISM]
    operator_dispatch_review_recorded_at: str
    source_credential_authorization_evaluation_id: str
    source_credential_authorization_evaluation_hash: str
    source_credential_authorization_evaluation_packet: dict[str, Any]
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
    operator_review_decision: OperatorReviewDecision
    operator_review_decision_digest: str
    operator_review_binding: dict[str, Any]
    operator_review_binding_digest: str
    operator_dispatch_review_checks: tuple[OperatorDispatchReviewCheck, ...]
    operator_dispatch_review_check_digest: str
    future_requirements: tuple[FutureRequirement, ...]
    future_requirement_digest: str
    operator_dispatch_review_status: Literal[STATUS]
    request_dispatch_state: Literal["NOT_DISPATCHED"]
    ready_for_promotion_native_bind_pre_dispatch_review: bool
    fail_closed: bool
    operator_review_is_human_approval: Literal[False]
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
    apply_performed: Literal[False]
    postcondition_verified: Literal[False]
    rollback_or_revert_performed: Literal[False]


def _fail(code: str) -> None:
    raise CanonicalPromotionLiveAdapterDryRunOperatorDispatchReviewError(code)


def _aware(value: Any, code: str) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunOperatorDispatchReviewError(
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
            _fail("PLADOR_PACKET_INVALID")
        return value
    if isinstance(value, datetime):
        return (
            value.astimezone(timezone.utc).isoformat()
            if _aware(value, "PLADOR_TIMESTAMP_INVALID")
            else None
        )
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _json(item) for key, item in value.items()}
    _fail("PLADOR_PACKET_INVALID")


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
        "promotion_live_adapter_dry_run_operator_dispatch_review_id",
        "promotion_live_adapter_dry_run_operator_dispatch_review_hash",
    }
    return _digest(
        PACKET_DOMAIN, {key: value for key, value in raw.items() if key not in omitted}
    )


def _source(
    value: Any,
) -> CanonicalPromotionLiveAdapterDryRunCredentialAuthorizationEvaluationPacket:
    try:
        return verify_canonical_promotion_live_adapter_dry_run_credential_authorization_evaluation_packet(
            value
        )
    except (
        CanonicalPromotionLiveAdapterDryRunCredentialAuthorizationError,
        TypeError,
        ValueError,
    ) as exc:
        raise CanonicalPromotionLiveAdapterDryRunOperatorDispatchReviewError(
            "PLADOR_SOURCE_INVALID"
        ) from exc


def _validate_source(
    source: CanonicalPromotionLiveAdapterDryRunCredentialAuthorizationEvaluationPacket,
) -> None:
    if not source.credential_authorization_result.authorized:
        _fail("PLADOR_SOURCE_CREDENTIAL_REFUSED")
    if (
        not source.ready_for_promotion_native_operator_dispatch_review
        or source.fail_closed
        or source.request_dispatch_state != "NOT_DISPATCHED"
    ):
        _fail("PLADOR_SOURCE_NOT_READY")
    if (
        source.execution_authorized
        or source.human_approval_proven
        or source.authority_evidence_proven
        or source.ready_for_real_bind
        or source.ready_for_network_dispatch
    ):
        _fail("PLADOR_SOURCE_AUTHORITY_INVALID")


def _verify_intent_adapter(
    source: CanonicalPromotionLiveAdapterDryRunCredentialAuthorizationEvaluationPacket,
) -> None:
    try:
        intent = ExecutionIntent(**source.execution_intent)
        descriptor = verify_bind_adapter_contract_descriptor(
            source.adapter_contract_descriptor, intent
        )
    except (TypeError, ValueError, BindAdapterContractSelectionError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunOperatorDispatchReviewError(
            "PLADOR_EXACT_OBJECT_INVALID"
        ) from exc
    if (
        intent.to_dict() != source.execution_intent
        or intent.execution_intent_id != source.execution_intent_id
        or hash_execution_intent(intent) != source.execution_intent_hash
    ):
        _fail("PLADOR_EXECUTION_INTENT_MISMATCH")
    if (
        descriptor.model_dump(mode="json") != source.adapter_contract_descriptor
        or descriptor.adapter_contract_id != source.adapter_contract_id
        or descriptor.adapter_contract_hash != source.adapter_contract_hash
        or descriptor.adapter_contract_version != source.adapter_contract_version
    ):
        _fail("PLADOR_ADAPTER_MISMATCH")


def _decision(value: Any) -> OperatorReviewDecision:
    try:
        return OperatorReviewDecision.model_validate(_json(value))
    except ValidationError as exc:
        raise CanonicalPromotionLiveAdapterDryRunOperatorDispatchReviewError(
            "PLADOR_DECISION_INVALID"
        ) from exc


def _validate_decision(
    source: CanonicalPromotionLiveAdapterDryRunCredentialAuthorizationEvaluationPacket,
    decision: OperatorReviewDecision,
) -> None:
    expected = (
        source.endpoint_candidate["endpoint_candidate_id"],
        source.credential_reference.credential_reference_id,
        source.adapter_contract_id,
        source.execution_intent["target_system"],
        source.execution_intent["target_resource"],
    )
    actual = (
        decision.reviewed_endpoint_candidate_id,
        decision.reviewed_credential_reference_id,
        decision.reviewed_adapter_contract_id,
        decision.reviewed_target_system,
        decision.reviewed_target_resource_scope,
    )
    if actual != expected:
        _fail("PLADOR_REVIEWED_IDENTITY_MISMATCH")


def _binding(
    source: CanonicalPromotionLiveAdapterDryRunCredentialAuthorizationEvaluationPacket,
    decision: OperatorReviewDecision,
    decision_digest: str,
) -> dict[str, Any]:
    return {
        "source_credential_authorization_id": source.promotion_live_adapter_dry_run_credential_authorization_evaluation_id,
        "source_credential_authorization_hash": source.promotion_live_adapter_dry_run_credential_authorization_evaluation_hash,
        **{field: _json(getattr(source, field)) for field in LINEAGE_FIELDS[:6]},
        "execution_intent_id": source.execution_intent_id,
        "execution_intent_hash": source.execution_intent_hash,
        "adapter_contract_id": source.adapter_contract_id,
        "adapter_contract_hash": source.adapter_contract_hash,
        "endpoint_candidate_id": source.endpoint_candidate["endpoint_candidate_id"],
        "endpoint_candidate_digest": source.endpoint_candidate_digest,
        "endpoint_identity_binding_digest": source.endpoint_identity_binding_digest,
        "credential_reference_id": source.credential_reference.credential_reference_id,
        "credential_reference_digest": source.credential_reference_digest,
        "credential_scope_binding_digest": source.credential_scope_binding_digest,
        "operator_review_id": decision.operator_review_id,
        "reviewer_id": decision.reviewer_id,
        "reviewer_role": decision.reviewer_role,
        "reviewer_organization": decision.reviewer_organization,
        "review_decision": decision.review_decision,
        "operator_review_decision_digest": decision_digest,
        "target_system": decision.reviewed_target_system,
        "target_resource_scope": decision.reviewed_target_resource_scope,
        "bind_pre_dispatch_review_required": True,
        "execution_authorized_by_this_packet": False,
        "human_approval_created_by_this_packet": False,
        "authority_evidence_created_by_this_packet": False,
    }


def _checks(source_hash: str, decision_digest: str) -> list[dict[str, Any]]:
    return [
        {
            "check_id": f"plador-check:v1:{ordinal}:{name.replace('_', '-')}",
            "ordinal": ordinal,
            "name": name,
            "mode": CHECK_MODE,
            "passed": True,
            "evidence_ref": f"source:{source_hash}:decision:{decision_digest}:{name}",
            "credential_material_accessed": False,
            "network_used": False,
            "request_dispatched": False,
            "bind_invoked": False,
            "trustlog_written": False,
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


def build_canonical_promotion_live_adapter_dry_run_operator_dispatch_review_packet(
    source_credential_authorization_evaluation_packet: Any,
    operator_review_decision: Any,
    operator_dispatch_review_recorded_at: datetime,
) -> CanonicalPromotionLiveAdapterDryRunOperatorDispatchReviewPacket:
    """Build and self-verify inert promotion-native operator review evidence."""
    source = _source(_json(source_credential_authorization_evaluation_packet))
    _validate_source(source)
    _verify_intent_adapter(source)
    decision = _decision(operator_review_decision)
    _validate_decision(source, decision)
    reviewed_at = _aware(decision.reviewed_at, "PLADOR_REVIEWED_AT_INVALID")
    recorded_at = _aware(
        operator_dispatch_review_recorded_at, "PLADOR_RECORDED_AT_INVALID"
    )
    source_at = _aware(
        source.credential_authorization_evaluated_at, "PLADOR_SOURCE_TIME_INVALID"
    )
    if reviewed_at < source_at or recorded_at < reviewed_at:
        _fail("PLADOR_TIMESTAMP_ORDER_INVALID")
    source_raw = source.model_dump(mode="json")
    decision_raw = decision.model_dump(mode="json")
    decision_raw["reviewed_at"] = reviewed_at.astimezone(timezone.utc).isoformat()
    decision_digest = _digest(DECISION_DOMAIN, decision_raw)
    binding = _binding(source, decision, decision_digest)
    checks = _checks(
        source.promotion_live_adapter_dry_run_credential_authorization_evaluation_hash,
        decision_digest,
    )
    requirements = _requirements()
    approved = decision.review_decision == REVIEW_DECISIONS[0]
    raw = {
        "format_version": FORMAT_VERSION,
        "operator_dispatch_review_mechanism": REVIEW_MECHANISM,
        "operator_dispatch_review_recorded_at": recorded_at.astimezone(
            timezone.utc
        ).isoformat(),
        "source_credential_authorization_evaluation_id": source.promotion_live_adapter_dry_run_credential_authorization_evaluation_id,
        "source_credential_authorization_evaluation_hash": source.promotion_live_adapter_dry_run_credential_authorization_evaluation_hash,
        "source_credential_authorization_evaluation_packet": source_raw,
        **{field: source_raw[field] for field in PRESERVED_FIELDS},
        "operator_review_decision": decision_raw,
        "operator_review_decision_digest": decision_digest,
        "operator_review_binding": binding,
        "operator_review_binding_digest": _digest(BINDING_DOMAIN, binding),
        "operator_dispatch_review_checks": checks,
        "operator_dispatch_review_check_digest": _digest(CHECKS_DOMAIN, checks),
        "future_requirements": requirements,
        "future_requirement_digest": _digest(REQUIREMENTS_DOMAIN, requirements),
        "operator_dispatch_review_status": STATUS,
        "request_dispatch_state": "NOT_DISPATCHED",
        "ready_for_promotion_native_bind_pre_dispatch_review": approved,
        "fail_closed": not approved,
        "operator_review_is_human_approval": False,
        "execution_authorized": False,
        "human_approval_proven": False,
        "authority_evidence_proven": False,
        "ready_for_real_bind": False,
        "ready_for_network_dispatch": False,
        **{field: False for field in EFFECT_FIELDS},
    }
    digest = _packet_hash(raw)
    raw["promotion_live_adapter_dry_run_operator_dispatch_review_hash"] = digest
    raw["promotion_live_adapter_dry_run_operator_dispatch_review_id"] = (
        f"plador:v1:sha256:{digest}"
    )
    return (
        verify_canonical_promotion_live_adapter_dry_run_operator_dispatch_review_packet(
            raw
        )
    )


def verify_canonical_promotion_live_adapter_dry_run_operator_dispatch_review_packet(
    raw: Any,
) -> CanonicalPromotionLiveAdapterDryRunOperatorDispatchReviewPacket:
    """Independently reconstruct every source, decision, binding, and digest."""
    try:
        value = raw.model_dump(mode="json") if isinstance(raw, BaseModel) else raw
        packet = CanonicalPromotionLiveAdapterDryRunOperatorDispatchReviewPacket.model_validate(
            _json(value)
        )
    except (
        ValidationError,
        TypeError,
        CanonicalPromotionLiveAdapterDryRunOperatorDispatchReviewError,
    ) as exc:
        raise CanonicalPromotionLiveAdapterDryRunOperatorDispatchReviewError(
            "PLADOR_PACKET_INVALID"
        ) from exc
    actual = packet.model_dump(mode="json")
    source = _source(packet.source_credential_authorization_evaluation_packet)
    _validate_source(source)
    _verify_intent_adapter(source)
    source_raw = source.model_dump(mode="json")
    if (
        packet.source_credential_authorization_evaluation_id
        != source.promotion_live_adapter_dry_run_credential_authorization_evaluation_id
        or packet.source_credential_authorization_evaluation_hash
        != source.promotion_live_adapter_dry_run_credential_authorization_evaluation_hash
    ):
        _fail("PLADOR_SOURCE_IDENTITY_MISMATCH")
    for field in PRESERVED_FIELDS:
        if _json(getattr(packet, field)) != _json(source_raw[field]):
            _fail("PLADOR_PRESERVED_FIELD_MISMATCH")
    decision = packet.operator_review_decision
    _validate_decision(source, decision)
    reviewed_at = _aware(decision.reviewed_at, "PLADOR_REVIEWED_AT_INVALID")
    recorded_at = _aware(
        packet.operator_dispatch_review_recorded_at, "PLADOR_RECORDED_AT_INVALID"
    )
    source_at = _aware(
        source.credential_authorization_evaluated_at, "PLADOR_SOURCE_TIME_INVALID"
    )
    if reviewed_at < source_at or recorded_at < reviewed_at:
        _fail("PLADOR_TIMESTAMP_ORDER_INVALID")
    decision_raw = decision.model_dump(mode="json")
    decision_raw["reviewed_at"] = reviewed_at.astimezone(timezone.utc).isoformat()
    decision_digest = _digest(DECISION_DOMAIN, decision_raw)
    if packet.operator_review_decision_digest != decision_digest:
        _fail("PLADOR_DECISION_DIGEST_MISMATCH")
    binding = _binding(source, decision, decision_digest)
    if (
        packet.operator_review_binding != binding
        or packet.operator_review_binding_digest != _digest(BINDING_DOMAIN, binding)
    ):
        _fail("PLADOR_BINDING_MISMATCH")
    checks = _checks(
        source.promotion_live_adapter_dry_run_credential_authorization_evaluation_hash,
        decision_digest,
    )
    if _json(
        packet.operator_dispatch_review_checks
    ) != checks or packet.operator_dispatch_review_check_digest != _digest(
        CHECKS_DOMAIN, checks
    ):
        _fail("PLADOR_CHECKS_MISMATCH")
    requirements = _requirements()
    if _json(
        packet.future_requirements
    ) != requirements or packet.future_requirement_digest != _digest(
        REQUIREMENTS_DOMAIN, requirements
    ):
        _fail("PLADOR_REQUIREMENTS_MISMATCH")
    approved = decision.review_decision == REVIEW_DECISIONS[0]
    if (
        packet.fail_closed == approved
        or packet.ready_for_promotion_native_bind_pre_dispatch_review != approved
    ):
        _fail("PLADOR_OUTCOME_MISMATCH")
    digest = _packet_hash(actual)
    if packet.promotion_live_adapter_dry_run_operator_dispatch_review_hash != digest:
        _fail("PLADOR_PACKET_HASH_MISMATCH")
    if (
        packet.promotion_live_adapter_dry_run_operator_dispatch_review_id
        != f"plador:v1:sha256:{digest}"
    ):
        _fail("PLADOR_PACKET_ID_MISMATCH")
    return packet
