"""Record Bind Authorization Gate review without creating authority.

This module performs only deterministic, local comparisons over a previously
verified Human Approval linkage review packet.  It deliberately has no runtime,
credential, persistence, adapter, or transport dependencies.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from veritas_os.policy.live_adapter_dry_run_final_bind_authorization_readiness import (
    CanonicalLiveAdapterDryRunFinalBindAuthorizationReadinessPacket,
    LiveAdapterDryRunFinalBindAuthorizationReadinessError,
    verify_live_adapter_dry_run_final_bind_authorization_readiness_packet,
)

FORMAT_VERSION = "canonical-live-adapter-dry-run-bind-authorization-gate-review/v1"
MECHANISM = "review_live_adapter_dry_run_bind_authorization_gate_without_authorization_creation/v1"
STATUS = "LIVE_ADAPTER_DRY_RUN_BIND_AUTHORIZATION_GATE_REVIEWED_NOT_AUTHORIZED"
SOURCE_STATUS = (
    "LIVE_ADAPTER_DRY_RUN_FINAL_BIND_AUTHORIZATION_READINESS_RECORDED_NOT_AUTHORIZED"
)
CHECK_MODE = "deterministic_local_bind_authorization_gate_review_only"
OUTCOMES = (
    "PASSED_FOR_FUTURE_BIND_AUTHORIZATION_ARTIFACT",
    "FAILED_FOR_FUTURE_BIND_AUTHORIZATION_ARTIFACT",
)
CHECK_NAMES = (
    "source_final_bind_authorization_readiness_verified",
    "source_request_not_dispatched",
    "source_bind_not_invoked",
    "source_bind_not_authorized",
    "source_human_approval_linkage_passed",
    "source_authority_evidence_linkage_passed",
    "source_bind_pre_dispatch_review_passed",
    "gate_review_decision_closed_schema_valid",
    "reviewer_identity_present",
    "reviewer_role_present",
    "reviewer_attestation_present",
    "acknowledged_not_real_bind_authorization",
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
    "request_descriptor_preserved",
    "execution_intent_identity_preserved",
    "adapter_contract_identity_preserved",
    "endpoint_identity_binding_preserved",
    "credential_scope_binding_preserved",
    "authority_evidence_linkage_result_preserved",
    "human_approval_linkage_result_preserved",
    "final_readiness_result_preserved",
    "gate_review_result_constructed",
    "future_real_bind_authorization_artifact_required",
    "future_bind_invocation_gate_required",
    "bind_authorization_not_created",
    "execution_authority_not_created",
    "human_approval_not_created",
    "authority_evidence_not_created",
    "bind_not_invoked",
    "bind_receipt_not_created",
    "trustlog_not_written",
    "request_not_dispatched",
    "endpoint_not_resolved",
    "credential_material_not_accessed",
    "authorization_header_not_constructed",
    "network_not_used",
    "webhook_not_called",
    "live_adapter_not_instantiated",
)
EFFECT_FIELDS = (
    "bind_authorization_created",
    "execution_authority_created",
    "human_approval_created",
    "authority_evidence_created",
    "bind_invoked",
    "bind_receipt_created",
    "trustlog_written",
    "request_dispatched",
    "endpoint_resolved",
    "credential_material_accessed",
    "credential_material_embedded",
    "authorization_header_constructed",
    "token_embedded",
    "secret_embedded",
    "network_used",
    "dns_used",
    "webhook_called",
    "live_adapter_instantiated",
    "live_adapter_method_called",
    "external_effect_used",
    "filesystem_used",
    "database_used",
    "provider_used",
    "subprocess_used",
    "operation_committed",
)
ACKNOWLEDGEMENTS = (
    "acknowledged_not_real_bind_authorization",
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
SCOPE_LIMITATIONS = (
    "NOT_DISPATCHED",
    "NOT_BIND_INVOCATION",
    "NOT_BIND_AUTHORIZATION",
    "NOT_BIND_AUTHORIZATION_CREATION",
    "NOT_BIND_RECEIPT",
    "NOT_TRUSTLOG_WRITE",
    "NOT_EXECUTION_AUTHORITY",
    "NOT_HUMAN_APPROVAL",
    "NOT_HUMAN_APPROVAL_CREATION",
    "NOT_AUTHORITY_EVIDENCE",
    "NOT_AUTHORITY_EVIDENCE_CREATION",
    "NOT_CREDENTIAL_RESOLUTION",
    "NOT_CREDENTIAL_ACCESS",
    "NOT_CREDENTIAL_EMBEDDING",
    "NOT_AUTHORIZATION_HEADER",
    "NOT_TOKEN",
    "NOT_SECRET",
    "NOT_ENDPOINT_RESOLUTION",
    "NOT_DNS_RESOLUTION",
    "NOT_NETWORK_CALL",
    "NOT_WEBHOOK_CALL",
    "NOT_LIVE_ADAPTER_INSTANCE",
    "NOT_LIVE_ADAPTER_RESULT",
    "NOT_OPERATION_COMMIT",
    "NOT_PRODUCTION_CLAIM",
    "NOT_CUSTOMER_CLAIM",
    "NOT_REGULATORY_CERTIFICATION",
)
AUTHORIZATION_REQUIREMENTS = (
    "real_authority_evidence_verification",
    "real_human_approval_verification_where_required",
    "final_policy_admissibility",
    "final_runtime_risk_review",
    "final_endpoint_identity_binding",
    "final_credential_resolution_authorization",
    "final_authorization_header_construction_boundary",
    "idempotency_key_binding",
    "final_no_replay_no_duplicate_dispatch_review",
    "final_operator_human_go_no_go_confirmation",
    "explicit_real_bind_authorization_decision_boundary",
)
INVOCATION_REQUIREMENTS = (
    "bind_authorization_exists",
    "request_dispatch_boundary_approved",
    "credential_material_boundary_controlled",
    "authorization_header_construction_boundary_controlled",
    "bind_invocation_boundary_explicit",
    "bind_receipt_creation_boundary_explicit",
    "trustlog_write_boundary_after_bind_explicit",
    "postcondition_and_rollback_requirements_exist_for_later_apply_path",
)
DOMAINS = {
    "decision": "veritas.live-adapter-dry-run-bind-authorization-gate-review.decision/v1",
    "result": "veritas.live-adapter-dry-run-bind-authorization-gate-review.result/v1",
    "checks": "veritas.live-adapter-dry-run-bind-authorization-gate-review.checks/v1",
    "authorization": "veritas.live-adapter-dry-run-bind-authorization-gate-review.future-real-bind-authorization-artifact-requirements/v1",
    "invocation": "veritas.live-adapter-dry-run-bind-authorization-gate-review.future-bind-invocation-requirements/v1",
    "packet": "veritas.live-adapter-dry-run-bind-authorization-gate-review.packet/v1",
}
COPIED_FIELDS = (
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
    "credential_scope_binding",
    "credential_scope_binding_digest",
    "authority_evidence_reference_bundle",
    "authority_evidence_reference_bundle_digest",
    "authority_evidence_linkage_result",
    "authority_evidence_linkage_result_digest",
    "human_approval_reference_bundle",
    "human_approval_reference_bundle_digest",
    "human_approval_linkage_result",
    "human_approval_linkage_result_digest",
    "final_bind_authorization_readiness_result",
    "final_bind_authorization_readiness_result_digest",
    "source_to_execution_intent_mapping",
    "field_mapping_proof",
    "required_field_presence",
    "source_decision_identity",
    "candidate_identity",
    "evidence_lineage",
    "replay_summary",
)


class LiveAdapterDryRunBindAuthorizationGateReviewError(ValueError):
    """Stable fail-closed error for invalid gate review evidence."""


class BindAuthorizationGateReviewDecision(BaseModel):
    """Closed human review metadata that explicitly is not authorization."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    bind_authorization_gate_review_decision_id: str = Field(min_length=1)
    reviewer_id: str = Field(min_length=1)
    reviewer_role: str = Field(min_length=1)
    reviewer_attestation: str = Field(min_length=1)
    reviewed_at: str
    review_outcome: Literal[*OUTCOMES]
    review_reason: str = Field(min_length=1)
    acknowledged_not_real_bind_authorization: bool
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


class BindAuthorizationGateReviewResult(BaseModel):
    """Deterministic readiness conclusion with explicit non-authority flags."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    source_final_readiness_passed: bool
    source_human_approval_linkage_passed: bool
    source_authority_evidence_linkage_passed: bool
    source_bind_pre_dispatch_review_passed: bool
    gate_review_passed: bool
    accepted_for_future_real_bind_authorization_artifact: bool
    rejection_reasons: tuple[str, ...]
    comparison_mode: Literal[CHECK_MODE]
    semantic_match_used: Literal[False]
    creates_real_bind_authorization: Literal[False]
    creates_execution_authority: Literal[False]
    creates_human_approval: Literal[False]
    creates_authority_evidence: Literal[False]


class GateReviewCheck(BaseModel):
    """One ordered local check whose effect flags are all false."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    check_id: str
    ordinal: int = Field(ge=1, le=49)
    name: Literal[*CHECK_NAMES]
    mode: Literal[CHECK_MODE]
    passed: bool
    evidence_ref: str
    bind_authorization_created: Literal[False]
    execution_authority_created: Literal[False]
    human_approval_created: Literal[False]
    authority_evidence_created: Literal[False]
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
    """A requirement that only a separate future artifact may satisfy."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    ordinal: int
    name: str
    separate_future_artifact_required: Literal[True]
    satisfied_by_this_packet: Literal[False]


class CanonicalLiveAdapterDryRunBindAuthorizationGateReviewPacket(BaseModel):
    """Closed content-addressed gate review packet without authorization."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    format_version: Literal[FORMAT_VERSION]
    live_adapter_dry_run_bind_authorization_gate_review_id: str
    live_adapter_dry_run_bind_authorization_gate_review_hash: str
    bind_authorization_gate_review_mechanism: Literal[MECHANISM]
    bind_authorization_gate_review_recorded_at: str
    source_final_bind_authorization_readiness_id: str
    source_final_bind_authorization_readiness_hash: str
    source_final_bind_authorization_readiness_packet: dict[str, Any]
    source_authority_evidence_linkage_review_hash: str
    source_bind_pre_dispatch_review_hash: str
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
    authority_evidence_reference_bundle: dict[str, Any]
    authority_evidence_reference_bundle_digest: str
    authority_evidence_linkage_result: dict[str, Any]
    authority_evidence_linkage_result_digest: str
    human_approval_reference_bundle: dict[str, Any]
    human_approval_reference_bundle_digest: str
    human_approval_linkage_result: dict[str, Any]
    human_approval_linkage_result_digest: str
    final_bind_authorization_readiness_result: dict[str, Any]
    final_bind_authorization_readiness_result_digest: str
    bind_authorization_gate_review_decision: BindAuthorizationGateReviewDecision
    bind_authorization_gate_review_decision_digest: str
    bind_authorization_gate_review_result: BindAuthorizationGateReviewResult
    bind_authorization_gate_review_result_digest: str
    bind_authorization_gate_review_checks: tuple[GateReviewCheck, ...]
    bind_authorization_gate_review_check_digest: str
    future_real_bind_authorization_artifact_requirements: tuple[FutureRequirement, ...]
    future_real_bind_authorization_artifact_requirements_digest: str
    future_bind_invocation_requirements: tuple[FutureRequirement, ...]
    future_bind_invocation_requirements_digest: str
    source_to_execution_intent_mapping: dict[str, Any]
    field_mapping_proof: dict[str, Any]
    required_field_presence: dict[str, str]
    source_decision_identity: dict[str, Any]
    candidate_identity: dict[str, Any]
    evidence_lineage: dict[str, Any]
    replay_summary: dict[str, Any]
    bind_authorization_gate_review_status: Literal[STATUS]
    request_dispatch_state: Literal["NOT_DISPATCHED"]
    bind_state: Literal["NOT_BOUND"]
    authority_state: Literal["NOT_AUTHORIZED"]
    human_approval_state: Literal["NOT_APPROVED"]
    bind_authorization_state: Literal["NOT_AUTHORIZED"]
    gate_review_state: Literal[
        "PASSED_FOR_FUTURE_BIND_AUTHORIZATION_ARTIFACT",
        "FAILED_FOR_FUTURE_BIND_AUTHORIZATION_ARTIFACT",
    ]
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
    fail_closed: bool
    scope_limitations: tuple[Literal[*SCOPE_LIMITATIONS], ...]


def _timestamp(value: Any) -> str:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise LiveAdapterDryRunBindAuthorizationGateReviewError(
            "LADBAGR_TIMESTAMP_INVALID"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LiveAdapterDryRunBindAuthorizationGateReviewError(
            "LADBAGR_TIMESTAMP_INVALID"
        )
    return parsed.astimezone(timezone.utc).isoformat()


def _json(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if (
        isinstance(value, float)
        and value == value
        and value not in (float("inf"), float("-inf"))
    ):
        return value
    if isinstance(value, datetime):
        return _timestamp(value)
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _json(item) for key, item in value.items()}
    raise LiveAdapterDryRunBindAuthorizationGateReviewError("LADBAGR_INVALID")


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
        "live_adapter_dry_run_bind_authorization_gate_review_id",
        "live_adapter_dry_run_bind_authorization_gate_review_hash",
    }
    return _digest(
        DOMAINS["packet"],
        {key: value for key, value in raw.items() if key not in omitted},
    )


def _source(
    value: Any,
) -> CanonicalLiveAdapterDryRunFinalBindAuthorizationReadinessPacket:
    try:
        return verify_live_adapter_dry_run_final_bind_authorization_readiness_packet(
            value
        )
    except (
        LiveAdapterDryRunFinalBindAuthorizationReadinessError,
        TypeError,
        ValueError,
    ) as exc:
        raise LiveAdapterDryRunBindAuthorizationGateReviewError(
            "LADBAGR_SOURCE_INVALID"
        ) from exc


def _validate_source(
    source: CanonicalLiveAdapterDryRunFinalBindAuthorizationReadinessPacket,
) -> None:
    if source.request_dispatch_state != "NOT_DISPATCHED" or source.request_dispatched:
        raise LiveAdapterDryRunBindAuthorizationGateReviewError(
            "LADBAGR_SOURCE_DISPATCHED"
        )
    if source.bind_state != "NOT_BOUND" or source.bind_invoked:
        raise LiveAdapterDryRunBindAuthorizationGateReviewError("LADBAGR_SOURCE_BOUND")
    if source.authority_state != "NOT_AUTHORIZED":
        raise LiveAdapterDryRunBindAuthorizationGateReviewError(
            "LADBAGR_SOURCE_AUTHORIZED"
        )
    if source.human_approval_state != "NOT_APPROVED":
        raise LiveAdapterDryRunBindAuthorizationGateReviewError(
            "LADBAGR_SOURCE_APPROVED"
        )
    if source.final_bind_authorization_readiness_status != SOURCE_STATUS:
        raise LiveAdapterDryRunBindAuthorizationGateReviewError("LADBAGR_SOURCE_STATUS")
    result = source.final_bind_authorization_readiness_result
    if (
        source.fail_closed
        or not result.accepted_for_future_bind_authorization_gate_review
    ):
        raise LiveAdapterDryRunBindAuthorizationGateReviewError(
            "LADBAGR_SOURCE_REJECTED"
        )


def _decision(value: Any) -> BindAuthorizationGateReviewDecision:
    try:
        decision = BindAuthorizationGateReviewDecision.model_validate(_json(value))
        normalized = decision.model_copy(
            update={"reviewed_at": _timestamp(decision.reviewed_at)}
        )
    except (
        ValidationError,
        TypeError,
        LiveAdapterDryRunBindAuthorizationGateReviewError,
    ) as exc:
        raise LiveAdapterDryRunBindAuthorizationGateReviewError(
            "LADBAGR_DECISION_INVALID"
        ) from exc
    if not all(getattr(normalized, field) for field in ACKNOWLEDGEMENTS):
        raise LiveAdapterDryRunBindAuthorizationGateReviewError(
            "LADBAGR_ACKNOWLEDGEMENT_MISSING"
        )
    return normalized


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


def _derived(
    source: CanonicalLiveAdapterDryRunFinalBindAuthorizationReadinessPacket,
    decision: BindAuthorizationGateReviewDecision,
) -> tuple[Any, ...]:
    accepted = decision.review_outcome == OUTCOMES[0]
    result = {
        "source_final_readiness_passed": True,
        "source_human_approval_linkage_passed": True,
        "source_authority_evidence_linkage_passed": True,
        "source_bind_pre_dispatch_review_passed": True,
        "gate_review_passed": accepted,
        "accepted_for_future_real_bind_authorization_artifact": accepted,
        "rejection_reasons": []
        if accepted
        else ["BIND_AUTHORIZATION_GATE_REVIEW_FAILED"],
        "comparison_mode": CHECK_MODE,
        "semantic_match_used": False,
        "creates_real_bind_authorization": False,
        "creates_execution_authority": False,
        "creates_human_approval": False,
        "creates_authority_evidence": False,
    }
    decision_digest = _digest(DOMAINS["decision"], decision)
    checks = [
        {
            "check_id": f"ladbagr-check:v1:{ordinal}:{name.replace('_', '-')}",
            "ordinal": ordinal,
            "name": name,
            "mode": CHECK_MODE,
            "passed": accepted if name == "gate_review_result_constructed" else True,
            "evidence_ref": f"decision:{decision_digest}:{name}",
            **{field: False for field in EFFECT_FIELDS},
        }
        for ordinal, name in enumerate(CHECK_NAMES, 1)
    ]
    return (
        result,
        checks,
        _requirements(AUTHORIZATION_REQUIREMENTS),
        _requirements(INVOCATION_REQUIREMENTS),
    )


def build_live_adapter_dry_run_bind_authorization_gate_review_packet(
    source_final_bind_authorization_readiness_packet: Any,
    bind_authorization_gate_review_decision: Any,
    bind_authorization_gate_review_recorded_at: datetime,
) -> CanonicalLiveAdapterDryRunBindAuthorizationGateReviewPacket:
    """Build and self-verify deterministic, non-authorizing gate review evidence."""
    source = _source(_json(source_final_bind_authorization_readiness_packet))
    _validate_source(source)
    decision = _decision(bind_authorization_gate_review_decision)
    recorded_at = _timestamp(bind_authorization_gate_review_recorded_at)
    result, checks, authorization, invocation = _derived(source, decision)
    source_raw = source.model_dump(mode="json")
    accepted = result["accepted_for_future_real_bind_authorization_artifact"]
    raw = {
        "format_version": FORMAT_VERSION,
        "bind_authorization_gate_review_mechanism": MECHANISM,
        "bind_authorization_gate_review_recorded_at": recorded_at,
        "source_final_bind_authorization_readiness_id": source.live_adapter_dry_run_final_bind_authorization_readiness_id,
        "source_final_bind_authorization_readiness_hash": source.live_adapter_dry_run_final_bind_authorization_readiness_hash,
        "source_final_bind_authorization_readiness_packet": source_raw,
        **{field: source_raw[field] for field in COPIED_FIELDS},
        **{
            field: source_raw[field]
            for field in (
                "source_human_approval_linkage_review_hash",
                "source_authority_evidence_linkage_review_hash",
                "source_bind_pre_dispatch_review_hash",
                "source_operator_dispatch_review_hash",
                "source_credential_authorization_hash",
                "source_endpoint_allowlist_evaluation_hash",
                "source_dispatch_readiness_hash",
                "source_live_adapter_dry_run_request_hash",
            )
        },
        "bind_authorization_gate_review_decision": decision.model_dump(mode="json"),
        "bind_authorization_gate_review_decision_digest": _digest(
            DOMAINS["decision"], decision
        ),
        "bind_authorization_gate_review_result": result,
        "bind_authorization_gate_review_result_digest": _digest(
            DOMAINS["result"], result
        ),
        "bind_authorization_gate_review_checks": checks,
        "bind_authorization_gate_review_check_digest": _digest(
            DOMAINS["checks"], checks
        ),
        "future_real_bind_authorization_artifact_requirements": authorization,
        "future_real_bind_authorization_artifact_requirements_digest": _digest(
            DOMAINS["authorization"], authorization
        ),
        "future_bind_invocation_requirements": invocation,
        "future_bind_invocation_requirements_digest": _digest(
            DOMAINS["invocation"], invocation
        ),
        "bind_authorization_gate_review_status": STATUS,
        "request_dispatch_state": "NOT_DISPATCHED",
        "bind_state": "NOT_BOUND",
        "authority_state": "NOT_AUTHORIZED",
        "human_approval_state": "NOT_APPROVED",
        "bind_authorization_state": "NOT_AUTHORIZED",
        "gate_review_state": OUTCOMES[0] if accepted else OUTCOMES[1],
        **{
            field: False
            for field in EFFECT_FIELDS
            if field
            in {
                "authority_evidence_created",
                "human_approval_created",
                "execution_authority_created",
                "bind_authorization_created",
                "bind_invoked",
                "bind_receipt_created",
                "trustlog_written",
                "request_dispatched",
                "endpoint_resolved",
                "credential_material_accessed",
                "authorization_header_constructed",
                "network_used",
                "live_adapter_instantiated",
                "webhook_called",
            }
        },
        "fail_closed": not accepted,
        "scope_limitations": SCOPE_LIMITATIONS,
    }
    digest = _packet_hash(raw)
    raw["live_adapter_dry_run_bind_authorization_gate_review_hash"] = digest
    raw["live_adapter_dry_run_bind_authorization_gate_review_id"] = (
        f"ladbagr:v1:sha256:{digest}"
    )
    return verify_live_adapter_dry_run_bind_authorization_gate_review_packet(raw)


def verify_live_adapter_dry_run_bind_authorization_gate_review_packet(
    raw: Any,
) -> CanonicalLiveAdapterDryRunBindAuthorizationGateReviewPacket:
    """Reverify the embedded source and every deterministic derived field."""
    try:
        value = raw.model_dump(mode="json") if isinstance(raw, BaseModel) else raw
        packet = (
            CanonicalLiveAdapterDryRunBindAuthorizationGateReviewPacket.model_validate(
                _json(value)
            )
        )
    except (
        ValidationError,
        TypeError,
        LiveAdapterDryRunBindAuthorizationGateReviewError,
    ) as exc:
        raise LiveAdapterDryRunBindAuthorizationGateReviewError(
            "LADBAGR_PACKET_INVALID"
        ) from exc
    actual = packet.model_dump(mode="json")
    source = _source(packet.source_final_bind_authorization_readiness_packet)
    _validate_source(source)
    source_raw = source.model_dump(mode="json")
    if (
        packet.source_final_bind_authorization_readiness_id
        != source.live_adapter_dry_run_final_bind_authorization_readiness_id
        or packet.source_final_bind_authorization_readiness_hash
        != source.live_adapter_dry_run_final_bind_authorization_readiness_hash
        or any(
            _json(getattr(packet, field)) != _json(source_raw[field])
            for field in COPIED_FIELDS
        )
        or any(
            getattr(packet, field) != source_raw[field]
            for field in (
                "source_human_approval_linkage_review_hash",
                "source_authority_evidence_linkage_review_hash",
                "source_bind_pre_dispatch_review_hash",
                "source_operator_dispatch_review_hash",
                "source_credential_authorization_hash",
                "source_endpoint_allowlist_evaluation_hash",
                "source_dispatch_readiness_hash",
                "source_live_adapter_dry_run_request_hash",
            )
        )
    ):
        raise LiveAdapterDryRunBindAuthorizationGateReviewError(
            "LADBAGR_SOURCE_MISMATCH"
        )
    decision = _decision(packet.bind_authorization_gate_review_decision)
    result, checks, authorization, invocation = _derived(source, decision)
    accepted = result["accepted_for_future_real_bind_authorization_artifact"]
    expected = (
        packet.bind_authorization_gate_review_decision_digest
        == _digest(DOMAINS["decision"], decision),
        _json(packet.bind_authorization_gate_review_result) == result,
        packet.bind_authorization_gate_review_result_digest
        == _digest(DOMAINS["result"], result),
        _json(packet.bind_authorization_gate_review_checks) == checks,
        packet.bind_authorization_gate_review_check_digest
        == _digest(DOMAINS["checks"], checks),
        _json(packet.future_real_bind_authorization_artifact_requirements)
        == authorization,
        packet.future_real_bind_authorization_artifact_requirements_digest
        == _digest(DOMAINS["authorization"], authorization),
        _json(packet.future_bind_invocation_requirements) == invocation,
        packet.future_bind_invocation_requirements_digest
        == _digest(DOMAINS["invocation"], invocation),
        packet.scope_limitations == SCOPE_LIMITATIONS,
        packet.fail_closed is (not accepted),
        packet.gate_review_state == (OUTCOMES[0] if accepted else OUTCOMES[1]),
        packet.bind_authorization_gate_review_recorded_at
        == _timestamp(packet.bind_authorization_gate_review_recorded_at),
    )
    if not all(expected):
        raise LiveAdapterDryRunBindAuthorizationGateReviewError(
            "LADBAGR_DERIVED_MISMATCH"
        )
    digest = _packet_hash(actual)
    if packet.live_adapter_dry_run_bind_authorization_gate_review_hash != digest:
        raise LiveAdapterDryRunBindAuthorizationGateReviewError("LADBAGR_HASH_MISMATCH")
    if (
        packet.live_adapter_dry_run_bind_authorization_gate_review_id
        != f"ladbagr:v1:sha256:{digest}"
    ):
        raise LiveAdapterDryRunBindAuthorizationGateReviewError("LADBAGR_ID_MISMATCH")
    return packet
