"""Create deterministic Bind-boundary review evidence without invoking Bind.

This module is deliberately pure: it validates and hashes caller-supplied
metadata only.  The resulting packet is neither authorization nor execution
authority and performs no dispatch, credential, persistence, or network work.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from veritas_os.policy.live_adapter_dry_run_operator_dispatch_review import (
    CanonicalLiveAdapterDryRunOperatorDispatchReviewPacket,
    LiveAdapterDryRunOperatorDispatchReviewError,
    verify_live_adapter_dry_run_operator_dispatch_review_packet,
)

FORMAT_VERSION = "canonical-live-adapter-dry-run-bind-pre-dispatch-review/v1"
REVIEW_MECHANISM = (
    "review_live_adapter_dry_run_bind_pre_dispatch_without_bind_invocation/v1"
)
STATUS = "LIVE_ADAPTER_DRY_RUN_BIND_PRE_DISPATCH_REVIEW_RECORDED_NOT_BOUND"
SOURCE_STATUS = (
    "LIVE_ADAPTER_DRY_RUN_OPERATOR_DISPATCH_REVIEW_RECORDED_NOT_DISPATCHED"
)
CHECK_MODE = "deterministic_local_bind_pre_dispatch_review_only"
DECISION_DOMAIN = "veritas.live-adapter-dry-run-bind-pre-dispatch-review.decision/v1"
RESULT_DOMAIN = "veritas.live-adapter-dry-run-bind-pre-dispatch-review.result/v1"
PRECONDITIONS_DOMAIN = (
    "veritas.live-adapter-dry-run-bind-pre-dispatch-review.preconditions/v1"
)
CHECKS_DOMAIN = "veritas.live-adapter-dry-run-bind-pre-dispatch-review.checks/v1"
REQUIREMENTS_DOMAIN = (
    "veritas.live-adapter-dry-run-bind-pre-dispatch-review."
    "future-bind-invocation-requirements/v1"
)
PACKET_DOMAIN = "veritas.live-adapter-dry-run-bind-pre-dispatch-review.packet/v1"

REVIEW_OUTCOMES = (
    "ACCEPTED_FOR_FUTURE_BIND_DISPATCH_GATE_REVIEW",
    "REJECTED_FOR_FUTURE_BIND_DISPATCH_GATE_REVIEW",
)
CHECK_NAMES = (
    "source_operator_dispatch_review_verified", "source_request_not_dispatched",
    "source_bind_not_invoked", "source_operator_review_accepted",
    "bind_pre_dispatch_review_decision_closed_schema_valid",
    "reviewer_identity_present", "reviewer_role_present",
    "reviewer_attestation_present", "acknowledged_not_bind_authorization",
    "acknowledged_no_bind_invocation", "acknowledged_no_bind_receipt",
    "acknowledged_no_trustlog_write", "acknowledged_no_dispatch",
    "acknowledged_no_credential_access", "acknowledged_no_network_call",
    "acknowledged_semantic_match_not_authority",
    "request_descriptor_preserved", "execution_intent_identity_preserved",
    "adapter_contract_identity_preserved",
    "endpoint_identity_binding_preserved", "credential_scope_binding_preserved",
    "operator_review_decision_preserved",
    "bind_boundary_preconditions_constructed", "bind_not_invoked",
    "bind_receipt_not_created", "trustlog_not_written",
    "request_not_dispatched", "endpoint_not_resolved",
    "credential_material_not_accessed",
    "authorization_header_not_constructed", "network_not_used",
    "webhook_not_called", "live_adapter_not_instantiated",
    "no_execution_authority_created", "no_human_approval_created",
    "no_authority_evidence_created", "future_bind_invocation_gate_required",
)
EFFECT_FIELDS = (
    "bind_invoked", "bind_receipt_created", "trustlog_written",
    "request_dispatched", "endpoint_resolved", "credential_material_accessed",
    "credential_material_embedded", "authorization_header_constructed",
    "token_embedded", "secret_embedded", "network_used", "dns_used",
    "webhook_called", "live_adapter_instantiated",
    "live_adapter_method_called", "external_effect_used", "filesystem_used",
    "database_used", "provider_used", "subprocess_used", "operation_committed",
    "execution_authority_created", "human_approval_created",
    "authority_evidence_created",
)
SCOPE_LIMITATIONS = (
    "NOT_DISPATCHED", "NOT_BIND_INVOCATION", "NOT_BIND_AUTHORIZATION",
    "NOT_BIND_RECEIPT", "NOT_TRUSTLOG_WRITE", "NOT_EXECUTION_AUTHORITY",
    "NOT_HUMAN_APPROVAL", "NOT_AUTHORITY_EVIDENCE",
    "NOT_CREDENTIAL_RESOLUTION", "NOT_CREDENTIAL_ACCESS",
    "NOT_CREDENTIAL_EMBEDDING", "NOT_AUTHORIZATION_HEADER", "NOT_TOKEN",
    "NOT_SECRET", "NOT_ENDPOINT_RESOLUTION", "NOT_DNS_RESOLUTION",
    "NOT_NETWORK_CALL", "NOT_WEBHOOK_CALL", "NOT_LIVE_ADAPTER_INSTANCE",
    "NOT_LIVE_ADAPTER_RESULT", "NOT_OPERATION_COMMIT",
    "NOT_PRODUCTION_CLAIM", "NOT_CUSTOMER_CLAIM",
    "NOT_REGULATORY_CERTIFICATION",
)
FUTURE_REQUIREMENT_NAMES = (
    "valid_authority_evidence", "valid_human_approval_where_required",
    "final_policy_admissibility", "final_endpoint_identity_binding",
    "final_credential_resolution_boundary",
    "final_authorization_header_construction_boundary", "runtime_risk_review",
    "idempotency_key_binding", "request_dispatch_boundary",
    "bind_invocation_boundary", "bind_receipt_creation_boundary",
    "trustlog_write_boundary_after_bind",
    "postcondition_and_rollback_requirements_for_later_apply_path",
)
COPIED_FIELDS = (
    "request_descriptor", "execution_intent", "execution_intent_id",
    "execution_intent_hash", "adapter_contract_descriptor",
    "adapter_contract_id", "adapter_contract_hash", "adapter_contract_version",
    "endpoint_candidate", "endpoint_candidate_digest",
    "endpoint_identity_binding", "endpoint_identity_binding_digest",
    "credential_reference", "credential_reference_digest",
    "credential_scope_binding", "credential_scope_binding_digest",
    "operator_review_decision", "operator_review_decision_digest",
    "source_to_execution_intent_mapping", "field_mapping_proof",
    "required_field_presence", "source_decision_identity", "candidate_identity",
    "evidence_lineage", "replay_summary",
)


class LiveAdapterDryRunBindPreDispatchReviewError(ValueError):
    """Stable fail-closed refusal for invalid Bind-boundary review evidence."""


class BindPreDispatchReviewDecision(BaseModel):
    """Closed reviewer decision with mandatory non-authority acknowledgements."""

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
    """Deterministic outcome that explicitly creates no authority."""

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


class BindPreDispatchReviewCheck(BaseModel):
    """One ordered local check with explicit false effect flags."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    check_id: str
    ordinal: int = Field(ge=1, le=37)
    name: Literal[*CHECK_NAMES]
    mode: Literal[CHECK_MODE]
    passed: bool
    evidence_ref: str
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
    execution_authority_created: Literal[False]
    human_approval_created: Literal[False]
    authority_evidence_created: Literal[False]


class FutureBindInvocationRequirement(BaseModel):
    """A future proof boundary that this packet does not satisfy."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    ordinal: int = Field(ge=1, le=13)
    name: Literal[*FUTURE_REQUIREMENT_NAMES]
    separate_future_artifact_required: Literal[True]
    satisfied_by_this_packet: Literal[False]


class CanonicalLiveAdapterDryRunBindPreDispatchReviewPacket(BaseModel):
    """Closed content-addressed, non-effecting Bind review packet."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    format_version: Literal[FORMAT_VERSION]
    live_adapter_dry_run_bind_pre_dispatch_review_id: str
    live_adapter_dry_run_bind_pre_dispatch_review_hash: str
    bind_pre_dispatch_review_mechanism: Literal[REVIEW_MECHANISM]
    bind_pre_dispatch_review_recorded_at: str
    source_operator_dispatch_review_id: str
    source_operator_dispatch_review_hash: str
    source_operator_dispatch_review_packet: dict[str, Any]
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
    bind_pre_dispatch_review_decision: BindPreDispatchReviewDecision
    bind_pre_dispatch_review_decision_digest: str
    bind_pre_dispatch_review_result: BindPreDispatchReviewResult
    bind_pre_dispatch_review_result_digest: str
    bind_boundary_preconditions: dict[str, Any]
    bind_boundary_precondition_digest: str
    bind_pre_dispatch_review_checks: tuple[BindPreDispatchReviewCheck, ...]
    bind_pre_dispatch_review_check_digest: str
    future_bind_invocation_requirements: tuple[FutureBindInvocationRequirement, ...]
    future_bind_invocation_requirement_digest: str
    source_to_execution_intent_mapping: dict[str, Any]
    field_mapping_proof: dict[str, Any]
    required_field_presence: dict[str, str]
    source_decision_identity: dict[str, Any]
    candidate_identity: dict[str, Any]
    evidence_lineage: dict[str, Any]
    replay_summary: dict[str, Any]
    bind_pre_dispatch_review_status: Literal[STATUS]
    request_dispatch_state: Literal["NOT_DISPATCHED"]
    bind_state: Literal["NOT_BOUND"]
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
        raise LiveAdapterDryRunBindPreDispatchReviewError(
            "LADRBPR_TIMESTAMP_INVALID"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LiveAdapterDryRunBindPreDispatchReviewError(
            "LADRBPR_TIMESTAMP_INVALID"
        )
    return parsed.astimezone(timezone.utc).isoformat()


def _json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise LiveAdapterDryRunBindPreDispatchReviewError("LADRBPR_INVALID")
        return value
    if isinstance(value, datetime):
        return _timestamp(value)
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _json_value(item) for key, item in value.items()}
    raise LiveAdapterDryRunBindPreDispatchReviewError("LADRBPR_INVALID")


def _digest(domain: str, value: Any) -> str:
    encoded = json.dumps(
        {"domain": domain, "value": _json_value(value)}, allow_nan=False,
        ensure_ascii=False, separators=(",", ":"), sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _packet_hash(raw: dict[str, Any]) -> str:
    omitted = {
        "live_adapter_dry_run_bind_pre_dispatch_review_id",
        "live_adapter_dry_run_bind_pre_dispatch_review_hash",
    }
    return _digest(PACKET_DOMAIN, {k: v for k, v in raw.items() if k not in omitted})


def _source(value: Any) -> CanonicalLiveAdapterDryRunOperatorDispatchReviewPacket:
    try:
        return verify_live_adapter_dry_run_operator_dispatch_review_packet(value)
    except (LiveAdapterDryRunOperatorDispatchReviewError, TypeError, ValueError) as exc:
        raise LiveAdapterDryRunBindPreDispatchReviewError(
            "LADRBPR_SOURCE_INVALID"
        ) from exc


def _validate_source(
    source: CanonicalLiveAdapterDryRunOperatorDispatchReviewPacket,
) -> None:
    if source.request_dispatch_state != "NOT_DISPATCHED":
        raise LiveAdapterDryRunBindPreDispatchReviewError("LADRBPR_SOURCE_DISPATCHED")
    if source.operator_dispatch_review_status != SOURCE_STATUS:
        raise LiveAdapterDryRunBindPreDispatchReviewError(
            "LADRBPR_SOURCE_STATUS_INVALID"
        )
    if source.bind_invoked:
        raise LiveAdapterDryRunBindPreDispatchReviewError("LADRBPR_SOURCE_BOUND")
    if source.fail_closed or source.operator_review_decision.review_decision != (
        "APPROVE_FOR_BIND_PRE_DISPATCH_REVIEW"
    ):
        raise LiveAdapterDryRunBindPreDispatchReviewError(
            "LADRBPR_SOURCE_REVIEW_NOT_ACCEPTED"
        )


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


def _preconditions(source_hash: str, decision_digest: str) -> dict[str, Any]:
    return {
        "source_operator_dispatch_review_hash": source_hash,
        "bind_pre_dispatch_review_decision_digest": decision_digest,
        "source_verified": True,
        "source_operator_review_accepted": True,
        "request_not_dispatched": True,
        "bind_not_invoked": True,
        "separate_future_bind_invocation_gate_required": True,
        "satisfied_by_this_packet": False,
    }


def _checks(source_hash: str, decision_digest: str) -> list[dict[str, Any]]:
    return [{
        "check_id": f"ladrbpr-check:v1:{ordinal}:{name.replace('_', '-')}",
        "ordinal": ordinal, "name": name, "mode": CHECK_MODE, "passed": True,
        "evidence_ref": f"source:{source_hash}:decision:{decision_digest}:{name}",
        **{field: False for field in EFFECT_FIELDS},
    } for ordinal, name in enumerate(CHECK_NAMES, 1)]


def _requirements() -> list[dict[str, Any]]:
    return [{
        "ordinal": ordinal, "name": name,
        "separate_future_artifact_required": True,
        "satisfied_by_this_packet": False,
    } for ordinal, name in enumerate(FUTURE_REQUIREMENT_NAMES, 1)]


def build_live_adapter_dry_run_bind_pre_dispatch_review_packet(
    source_operator_dispatch_review_packet: Any,
    bind_pre_dispatch_review_decision: Any,
    bind_pre_dispatch_review_recorded_at: datetime,
) -> CanonicalLiveAdapterDryRunBindPreDispatchReviewPacket:
    """Build and self-verify deterministic pre-dispatch review evidence."""
    source = _source(_json_value(source_operator_dispatch_review_packet))
    _validate_source(source)
    try:
        decision = BindPreDispatchReviewDecision.model_validate(
            _json_value(bind_pre_dispatch_review_decision)
        )
    except ValidationError as exc:
        raise LiveAdapterDryRunBindPreDispatchReviewError(
            "LADRBPR_DECISION_INVALID"
        ) from exc
    reviewed_at = _timestamp(decision.reviewed_at)
    recorded_at = _timestamp(bind_pre_dispatch_review_recorded_at)
    if datetime.fromisoformat(recorded_at) < datetime.fromisoformat(reviewed_at):
        raise LiveAdapterDryRunBindPreDispatchReviewError(
            "LADRBPR_RECORDED_TOO_EARLY"
        )
    source_raw = source.model_dump(mode="json")
    decision_raw = decision.model_dump(mode="json")
    decision_raw["reviewed_at"] = reviewed_at
    decision_digest = _digest(DECISION_DOMAIN, decision_raw)
    result = _result(decision)
    preconditions = _preconditions(
        source.live_adapter_dry_run_operator_dispatch_review_hash,
        decision_digest,
    )
    checks = _checks(
        source.live_adapter_dry_run_operator_dispatch_review_hash,
        decision_digest,
    )
    requirements = _requirements()
    raw = {
        "format_version": FORMAT_VERSION,
        "bind_pre_dispatch_review_mechanism": REVIEW_MECHANISM,
        "bind_pre_dispatch_review_recorded_at": recorded_at,
        "source_operator_dispatch_review_id": (
            source.live_adapter_dry_run_operator_dispatch_review_id
        ),
        "source_operator_dispatch_review_hash": (
            source.live_adapter_dry_run_operator_dispatch_review_hash
        ),
        "source_operator_dispatch_review_packet": source_raw,
        "source_credential_authorization_hash": (
            source.source_credential_authorization_evaluation_hash
        ),
        "source_endpoint_allowlist_evaluation_hash": (
            source.source_endpoint_allowlist_evaluation_hash
        ),
        "source_dispatch_readiness_hash": source.source_dispatch_readiness_hash,
        "source_live_adapter_dry_run_request_hash": (
            source.source_live_adapter_dry_run_request_hash
        ),
        **{field: source_raw[field] for field in COPIED_FIELDS},
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
        "future_bind_invocation_requirements": requirements,
        "future_bind_invocation_requirement_digest": _digest(
            REQUIREMENTS_DOMAIN, requirements
        ),
        "bind_pre_dispatch_review_status": STATUS,
        "request_dispatch_state": "NOT_DISPATCHED", "bind_state": "NOT_BOUND",
        **{field: False for field in (
            "bind_invoked", "bind_receipt_created", "trustlog_written",
            "request_dispatched", "endpoint_resolved",
            "credential_material_accessed", "authorization_header_constructed",
            "network_used", "live_adapter_instantiated", "webhook_called",
        )},
        "fail_closed": not result["accepted_for_future_bind_dispatch_gate_review"],
        "scope_limitations": SCOPE_LIMITATIONS,
    }
    digest = _packet_hash(raw)
    raw["live_adapter_dry_run_bind_pre_dispatch_review_hash"] = digest
    raw["live_adapter_dry_run_bind_pre_dispatch_review_id"] = (
        f"ladrbpr:v1:sha256:{digest}"
    )
    return verify_live_adapter_dry_run_bind_pre_dispatch_review_packet(raw)


def verify_live_adapter_dry_run_bind_pre_dispatch_review_packet(
    raw: Any,
) -> CanonicalLiveAdapterDryRunBindPreDispatchReviewPacket:
    """Reverify the source and every deterministic field, digest, hash, and ID."""
    try:
        value = raw.model_dump(mode="json") if isinstance(raw, BaseModel) else raw
        packet = CanonicalLiveAdapterDryRunBindPreDispatchReviewPacket.model_validate(
            _json_value(value)
        )
    except (ValidationError, TypeError,
            LiveAdapterDryRunBindPreDispatchReviewError) as exc:
        raise LiveAdapterDryRunBindPreDispatchReviewError(
            "LADRBPR_PACKET_INVALID"
        ) from exc
    actual = packet.model_dump(mode="json")
    source = _source(packet.source_operator_dispatch_review_packet)
    _validate_source(source)
    source_raw = source.model_dump(mode="json")
    if (packet.source_operator_dispatch_review_id,
            packet.source_operator_dispatch_review_hash) != (
                source.live_adapter_dry_run_operator_dispatch_review_id,
                source.live_adapter_dry_run_operator_dispatch_review_hash):
        raise LiveAdapterDryRunBindPreDispatchReviewError(
            "LADRBPR_SOURCE_IDENTITY_MISMATCH"
        )
    lineage = (
        packet.source_credential_authorization_hash,
        packet.source_endpoint_allowlist_evaluation_hash,
        packet.source_dispatch_readiness_hash,
        packet.source_live_adapter_dry_run_request_hash,
    )
    if lineage != (
        source.source_credential_authorization_evaluation_hash,
        source.source_endpoint_allowlist_evaluation_hash,
        source.source_dispatch_readiness_hash,
        source.source_live_adapter_dry_run_request_hash,
    ):
        raise LiveAdapterDryRunBindPreDispatchReviewError("LADRBPR_LINEAGE_MISMATCH")
    for field in COPIED_FIELDS:
        if _json_value(getattr(packet, field)) != _json_value(source_raw[field]):
            raise LiveAdapterDryRunBindPreDispatchReviewError(
                "LADRBPR_SOURCE_FIELD_MISMATCH"
            )
    reviewed_at = _timestamp(packet.bind_pre_dispatch_review_decision.reviewed_at)
    recorded_at = _timestamp(packet.bind_pre_dispatch_review_recorded_at)
    if datetime.fromisoformat(recorded_at) < datetime.fromisoformat(reviewed_at):
        raise LiveAdapterDryRunBindPreDispatchReviewError(
            "LADRBPR_RECORDED_TOO_EARLY"
        )
    decision_raw = packet.bind_pre_dispatch_review_decision.model_dump(mode="json")
    decision_raw["reviewed_at"] = reviewed_at
    decision_digest = _digest(DECISION_DOMAIN, decision_raw)
    result = _result(packet.bind_pre_dispatch_review_decision)
    preconditions = _preconditions(packet.source_operator_dispatch_review_hash,
                                   decision_digest)
    checks = _checks(packet.source_operator_dispatch_review_hash, decision_digest)
    requirements = _requirements()
    comparisons = (
        packet.bind_pre_dispatch_review_decision_digest == decision_digest,
        _json_value(packet.bind_pre_dispatch_review_result) == result,
        packet.bind_pre_dispatch_review_result_digest == _digest(RESULT_DOMAIN, result),
        packet.bind_boundary_preconditions == preconditions,
        packet.bind_boundary_precondition_digest
        == _digest(PRECONDITIONS_DOMAIN, preconditions),
        _json_value(packet.bind_pre_dispatch_review_checks) == checks,
        packet.bind_pre_dispatch_review_check_digest == _digest(CHECKS_DOMAIN, checks),
        _json_value(packet.future_bind_invocation_requirements) == requirements,
        packet.future_bind_invocation_requirement_digest
        == _digest(REQUIREMENTS_DOMAIN, requirements),
    )
    if not all(comparisons):
        raise LiveAdapterDryRunBindPreDispatchReviewError(
            "LADRBPR_DERIVED_VALUE_MISMATCH"
        )
    accepted = result["accepted_for_future_bind_dispatch_gate_review"]
    if packet.fail_closed != (not accepted) or packet.scope_limitations != (
        SCOPE_LIMITATIONS
    ):
        raise LiveAdapterDryRunBindPreDispatchReviewError(
            "LADRBPR_FAIL_CLOSED_OR_SCOPE_MISMATCH"
        )
    digest = _packet_hash(actual)
    if packet.live_adapter_dry_run_bind_pre_dispatch_review_hash != digest:
        raise LiveAdapterDryRunBindPreDispatchReviewError(
            "LADRBPR_PACKET_HASH_MISMATCH"
        )
    if packet.live_adapter_dry_run_bind_pre_dispatch_review_id != (
        f"ladrbpr:v1:sha256:{digest}"
    ):
        raise LiveAdapterDryRunBindPreDispatchReviewError(
            "LADRBPR_PACKET_ID_MISMATCH"
        )
    return packet
