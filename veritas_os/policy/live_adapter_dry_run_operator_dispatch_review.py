"""Record an operator dispatch review without dispatching or external effects.

The packet produced here is metadata-only evidence.  It is not execution
authority, Bind authorization, a receipt, or an audit-log write.  All inputs
are caller supplied and every derived value is deterministic and reverified.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from veritas_os.policy.live_adapter_dry_run_credential_authorization import (
    CanonicalLiveAdapterDryRunCredentialAuthorizationEvaluationPacket,
    LiveAdapterDryRunCredentialAuthorizationError,
    verify_live_adapter_dry_run_credential_authorization_evaluation_packet,
)

FORMAT_VERSION = "canonical-live-adapter-dry-run-operator-dispatch-review/v1"
REVIEW_MECHANISM = (
    "record_live_adapter_dry_run_operator_dispatch_review_without_dispatch/v1"
)
STATUS = "LIVE_ADAPTER_DRY_RUN_OPERATOR_DISPATCH_REVIEW_RECORDED_NOT_DISPATCHED"
SOURCE_STATUS = (
    "LIVE_ADAPTER_DRY_RUN_CREDENTIAL_AUTHORIZATION_EVALUATED_NOT_DISPATCHED"
)
CHECK_MODE = "deterministic_local_operator_dispatch_review_record_only"
DECISION_DOMAIN = "veritas.live-adapter-dry-run-operator-dispatch-review.decision/v1"
BINDING_DOMAIN = "veritas.live-adapter-dry-run-operator-dispatch-review.binding/v1"
CHECKS_DOMAIN = "veritas.live-adapter-dry-run-operator-dispatch-review.checks/v1"
REQUIREMENTS_DOMAIN = (
    "veritas.live-adapter-dry-run-operator-dispatch-review."
    "future-bind-pre-dispatch-requirements/v1"
)
PACKET_DOMAIN = "veritas.live-adapter-dry-run-operator-dispatch-review.packet/v1"

REVIEW_DECISIONS = (
    "APPROVE_FOR_BIND_PRE_DISPATCH_REVIEW",
    "REJECT",
    "HOLD_FOR_MORE_EVIDENCE",
)
CHECK_NAMES = (
    "source_credential_authorization_evaluation_verified",
    "source_request_not_dispatched",
    "source_credential_authorized",
    "operator_review_decision_closed_schema_valid",
    "reviewer_identity_present",
    "reviewer_role_present",
    "review_decision_allowed_value",
    "reviewed_endpoint_candidate_identity_matches_source",
    "reviewed_credential_reference_identity_matches_source",
    "reviewed_adapter_contract_identity_matches_source",
    "reviewed_target_system_matches_source",
    "reviewed_target_resource_scope_matches_source",
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
    "authorization_header_not_constructed",
    "network_not_used",
    "webhook_not_called",
    "live_adapter_not_instantiated",
    "bind_not_invoked",
    "bind_receipt_not_created",
    "trustlog_not_written",
    "request_not_dispatched",
    "future_bind_pre_dispatch_review_required",
)
EFFECT_FIELDS = (
    "credential_resolved", "credential_material_accessed",
    "credential_material_embedded", "authorization_header_constructed",
    "token_embedded", "secret_embedded", "endpoint_resolved", "dns_used",
    "network_used", "webhook_called", "live_adapter_instantiated",
    "live_adapter_method_called", "request_dispatched", "bind_invoked",
    "bind_receipt_created", "trustlog_written", "external_effect_used",
    "filesystem_used", "database_used", "provider_used", "subprocess_used",
    "operation_committed",
)
SCOPE_LIMITATIONS = (
    "NOT_DISPATCHED", "NOT_BIND_AUTHORIZATION", "NOT_BIND_RECEIPT",
    "NOT_TRUSTLOG_WRITE", "NOT_CREDENTIAL_RESOLUTION",
    "NOT_CREDENTIAL_ACCESS", "NOT_CREDENTIAL_EMBEDDING",
    "NOT_AUTHORIZATION_HEADER", "NOT_TOKEN", "NOT_SECRET",
    "NOT_ENDPOINT_RESOLUTION", "NOT_DNS_RESOLUTION", "NOT_NETWORK_CALL",
    "NOT_WEBHOOK_CALL", "NOT_LIVE_ADAPTER_INSTANCE",
    "NOT_LIVE_ADAPTER_RESULT", "NOT_OPERATION_COMMIT",
    "NOT_PRODUCTION_CLAIM", "NOT_CUSTOMER_CLAIM",
    "NOT_REGULATORY_CERTIFICATION",
)
FUTURE_REQUIREMENT_NAMES = (
    "bind_pre_dispatch_policy_review",
    "authority_evidence_recheck",
    "human_approval_boundary_verification_if_applicable",
    "endpoint_identity_recheck",
    "credential_authorization_recheck",
    "credential_material_resolution_boundary",
    "authorization_header_construction_boundary",
    "network_dispatch_boundary",
    "request_dispatch_receipt_boundary",
    "trustlog_write_boundary_after_proper_authorization",
    "bind_receipt_boundary_only_after_bind",
    "rollback_postcondition_requirements_for_later_apply_path",
)
COPIED_FIELDS = (
    "request_descriptor", "execution_intent", "execution_intent_id",
    "execution_intent_hash", "adapter_contract_descriptor",
    "adapter_contract_id", "adapter_contract_hash", "adapter_contract_version",
    "endpoint_candidate", "endpoint_candidate_digest",
    "endpoint_identity_binding", "endpoint_identity_binding_digest",
    "credential_reference", "credential_reference_digest",
    "credential_scope_binding", "credential_scope_binding_digest",
    "source_to_execution_intent_mapping", "field_mapping_proof",
    "required_field_presence", "source_decision_identity",
    "candidate_identity", "evidence_lineage", "replay_summary",
)


class LiveAdapterDryRunOperatorDispatchReviewError(ValueError):
    """Stable fail-closed refusal for invalid operator review evidence."""


class OperatorReviewDecision(BaseModel):
    """Closed explicit operator decision and mandatory acknowledgements."""

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
    """One deterministic local check carrying explicit non-effect facts."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    check_id: str
    ordinal: int = Field(ge=1, le=33)
    name: Literal[*CHECK_NAMES]
    mode: Literal[CHECK_MODE]
    passed: bool
    evidence_ref: str
    credential_resolved: Literal[False]
    credential_material_accessed: Literal[False]
    credential_material_embedded: Literal[False]
    authorization_header_constructed: Literal[False]
    token_embedded: Literal[False]
    secret_embedded: Literal[False]
    endpoint_resolved: Literal[False]
    dns_used: Literal[False]
    network_used: Literal[False]
    webhook_called: Literal[False]
    live_adapter_instantiated: Literal[False]
    live_adapter_method_called: Literal[False]
    request_dispatched: Literal[False]
    bind_invoked: Literal[False]
    bind_receipt_created: Literal[False]
    trustlog_written: Literal[False]
    external_effect_used: Literal[False]
    filesystem_used: Literal[False]
    database_used: Literal[False]
    provider_used: Literal[False]
    subprocess_used: Literal[False]
    operation_committed: Literal[False]


class FutureBindPreDispatchReviewRequirement(BaseModel):
    """One future boundary that this review explicitly does not satisfy."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    ordinal: int = Field(ge=1, le=12)
    name: Literal[*FUTURE_REQUIREMENT_NAMES]
    separate_future_artifact_required: Literal[True]
    satisfied_by_this_packet: Literal[False]


class CanonicalLiveAdapterDryRunOperatorDispatchReviewPacket(BaseModel):
    """Closed content-addressed operator dispatch review packet."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    format_version: Literal[FORMAT_VERSION]
    live_adapter_dry_run_operator_dispatch_review_id: str
    live_adapter_dry_run_operator_dispatch_review_hash: str
    operator_dispatch_review_mechanism: Literal[REVIEW_MECHANISM]
    operator_dispatch_review_recorded_at: str
    source_credential_authorization_evaluation_id: str
    source_credential_authorization_evaluation_hash: str
    source_credential_authorization_evaluation_packet: dict[str, Any]
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
    operator_review_decision: OperatorReviewDecision
    operator_review_decision_digest: str
    operator_review_binding: dict[str, Any]
    operator_review_binding_digest: str
    operator_dispatch_review_checks: tuple[OperatorDispatchReviewCheck, ...]
    operator_dispatch_review_check_digest: str
    future_bind_pre_dispatch_review_requirements: tuple[
        FutureBindPreDispatchReviewRequirement, ...
    ]
    future_bind_pre_dispatch_review_requirement_digest: str
    source_to_execution_intent_mapping: dict[str, Any]
    field_mapping_proof: dict[str, Any]
    required_field_presence: dict[str, str]
    source_decision_identity: dict[str, Any]
    candidate_identity: dict[str, Any]
    evidence_lineage: dict[str, Any]
    replay_summary: dict[str, Any]
    operator_dispatch_review_status: Literal[STATUS]
    request_dispatch_state: Literal["NOT_DISPATCHED"]
    credential_resolved: Literal[False]
    credential_material_accessed: Literal[False]
    credential_material_embedded: Literal[False]
    authorization_header_constructed: Literal[False]
    token_embedded: Literal[False]
    secret_embedded: Literal[False]
    endpoint_resolved: Literal[False]
    network_used: Literal[False]
    live_adapter_instantiated: Literal[False]
    webhook_called: Literal[False]
    bind_invoked: Literal[False]
    bind_receipt_created: Literal[False]
    trustlog_written: Literal[False]
    request_dispatched: Literal[False]
    fail_closed: bool
    scope_limitations: tuple[Literal[*SCOPE_LIMITATIONS], ...]


def _timestamp(value: Any) -> str:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise LiveAdapterDryRunOperatorDispatchReviewError(
            "LADROR_TIMESTAMP_INVALID"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LiveAdapterDryRunOperatorDispatchReviewError(
            "LADROR_TIMESTAMP_INVALID"
        )
    return parsed.astimezone(timezone.utc).isoformat()


def _json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise LiveAdapterDryRunOperatorDispatchReviewError(
                "LADROR_PACKET_INVALID"
            )
        return value
    if isinstance(value, datetime):
        return _timestamp(value)
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _json_value(item) for key, item in value.items()}
    raise LiveAdapterDryRunOperatorDispatchReviewError("LADROR_PACKET_INVALID")


def _digest(domain: str, value: Any) -> str:
    encoded = json.dumps(
        {"domain": domain, "value": _json_value(value)},
        allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _packet_hash(raw: dict[str, Any]) -> str:
    omitted = {
        "live_adapter_dry_run_operator_dispatch_review_id",
        "live_adapter_dry_run_operator_dispatch_review_hash",
    }
    return _digest(
        PACKET_DOMAIN, {key: value for key, value in raw.items() if key not in omitted}
    )


def _source(
    value: Any,
) -> CanonicalLiveAdapterDryRunCredentialAuthorizationEvaluationPacket:
    try:
        return verify_live_adapter_dry_run_credential_authorization_evaluation_packet(
            value
        )
    except (LiveAdapterDryRunCredentialAuthorizationError, TypeError, ValueError) as exc:
        raise LiveAdapterDryRunOperatorDispatchReviewError(
            "LADROR_SOURCE_INVALID"
        ) from exc


def _validate_source(
    source: CanonicalLiveAdapterDryRunCredentialAuthorizationEvaluationPacket,
) -> None:
    if source.request_dispatch_state != "NOT_DISPATCHED":
        raise LiveAdapterDryRunOperatorDispatchReviewError(
            "LADROR_SOURCE_DISPATCHED"
        )
    if source.credential_authorization_status != SOURCE_STATUS:
        raise LiveAdapterDryRunOperatorDispatchReviewError(
            "LADROR_SOURCE_STATUS_INVALID"
        )
    if not source.credential_authorization_result.authorized:
        raise LiveAdapterDryRunOperatorDispatchReviewError(
            "LADROR_SOURCE_CREDENTIAL_UNAUTHORIZED"
        )


def _validate_decision(
    source: CanonicalLiveAdapterDryRunCredentialAuthorizationEvaluationPacket,
    decision: OperatorReviewDecision,
) -> None:
    expected = (
        source.endpoint_candidate["endpoint_candidate_id"],
        source.credential_reference.credential_reference_id,
        source.adapter_contract_id,
        source.credential_reference.target_system,
        source.credential_reference.target_resource_scope,
    )
    actual = (
        decision.reviewed_endpoint_candidate_id,
        decision.reviewed_credential_reference_id,
        decision.reviewed_adapter_contract_id,
        decision.reviewed_target_system,
        decision.reviewed_target_resource_scope,
    )
    if actual != expected:
        raise LiveAdapterDryRunOperatorDispatchReviewError(
            "LADROR_REVIEWED_IDENTITY_MISMATCH"
        )


def _binding(
    source: CanonicalLiveAdapterDryRunCredentialAuthorizationEvaluationPacket,
    decision: OperatorReviewDecision,
) -> dict[str, Any]:
    return {
        "operator_review_id": decision.operator_review_id,
        "reviewer_id": decision.reviewer_id,
        "review_decision": decision.review_decision,
        "source_credential_authorization_evaluation_id": (
            source.live_adapter_dry_run_credential_authorization_evaluation_id
        ),
        "source_credential_authorization_evaluation_hash": (
            source.live_adapter_dry_run_credential_authorization_evaluation_hash
        ),
        "endpoint_candidate_id": decision.reviewed_endpoint_candidate_id,
        "credential_reference_id": decision.reviewed_credential_reference_id,
        "adapter_contract_id": decision.reviewed_adapter_contract_id,
        "target_system": decision.reviewed_target_system,
        "target_resource_scope": decision.reviewed_target_resource_scope,
        "bind_pre_dispatch_review_required": True,
        "execution_authorized_by_this_packet": False,
    }


def _checks(source_hash: str, decision_digest: str) -> list[dict[str, Any]]:
    return [{
        "check_id": f"ladror-check:v1:{ordinal}:{name.replace('_', '-')}",
        "ordinal": ordinal,
        "name": name,
        "mode": CHECK_MODE,
        "passed": True,
        "evidence_ref": f"source:{source_hash}:decision:{decision_digest}:{name}",
        **{field: False for field in EFFECT_FIELDS},
    } for ordinal, name in enumerate(CHECK_NAMES, 1)]


def _requirements() -> list[dict[str, Any]]:
    return [{
        "ordinal": ordinal,
        "name": name,
        "separate_future_artifact_required": True,
        "satisfied_by_this_packet": False,
    } for ordinal, name in enumerate(FUTURE_REQUIREMENT_NAMES, 1)]


def build_live_adapter_dry_run_operator_dispatch_review_packet(
    source_credential_authorization_evaluation_packet: Any,
    operator_review_decision: Any,
    operator_dispatch_review_recorded_at: datetime,
) -> CanonicalLiveAdapterDryRunOperatorDispatchReviewPacket:
    """Build and self-verify a deterministic, non-dispatching review packet."""
    source = _source(_json_value(source_credential_authorization_evaluation_packet))
    _validate_source(source)
    try:
        decision = OperatorReviewDecision.model_validate(
            _json_value(operator_review_decision)
        )
    except ValidationError as exc:
        raise LiveAdapterDryRunOperatorDispatchReviewError(
            "LADROR_DECISION_INVALID"
        ) from exc
    reviewed_at = _timestamp(decision.reviewed_at)
    recorded_at = _timestamp(operator_dispatch_review_recorded_at)
    if datetime.fromisoformat(recorded_at) < datetime.fromisoformat(reviewed_at):
        raise LiveAdapterDryRunOperatorDispatchReviewError(
            "LADROR_RECORDED_TOO_EARLY"
        )
    _validate_decision(source, decision)
    source_raw = source.model_dump(mode="json")
    decision_raw = decision.model_dump(mode="json")
    decision_raw["reviewed_at"] = reviewed_at
    decision_digest = _digest(DECISION_DOMAIN, decision_raw)
    binding = _binding(source, decision)
    checks = _checks(
        source.live_adapter_dry_run_credential_authorization_evaluation_hash,
        decision_digest,
    )
    requirements = _requirements()
    raw = {
        "format_version": FORMAT_VERSION,
        "operator_dispatch_review_mechanism": REVIEW_MECHANISM,
        "operator_dispatch_review_recorded_at": recorded_at,
        "source_credential_authorization_evaluation_id": (
            source.live_adapter_dry_run_credential_authorization_evaluation_id
        ),
        "source_credential_authorization_evaluation_hash": (
            source.live_adapter_dry_run_credential_authorization_evaluation_hash
        ),
        "source_credential_authorization_evaluation_packet": source_raw,
        "source_endpoint_allowlist_evaluation_hash": (
            source.source_endpoint_allowlist_evaluation_hash
        ),
        "source_dispatch_readiness_hash": source.source_dispatch_readiness_hash,
        "source_live_adapter_dry_run_request_hash": (
            source.source_live_adapter_dry_run_request_hash
        ),
        **{field: source_raw[field] for field in COPIED_FIELDS},
        "operator_review_decision": decision_raw,
        "operator_review_decision_digest": decision_digest,
        "operator_review_binding": binding,
        "operator_review_binding_digest": _digest(BINDING_DOMAIN, binding),
        "operator_dispatch_review_checks": checks,
        "operator_dispatch_review_check_digest": _digest(CHECKS_DOMAIN, checks),
        "future_bind_pre_dispatch_review_requirements": requirements,
        "future_bind_pre_dispatch_review_requirement_digest": _digest(
            REQUIREMENTS_DOMAIN, requirements
        ),
        "operator_dispatch_review_status": STATUS,
        "request_dispatch_state": "NOT_DISPATCHED",
        **{field: False for field in (
            "credential_resolved", "credential_material_accessed",
            "credential_material_embedded", "authorization_header_constructed",
            "token_embedded", "secret_embedded", "endpoint_resolved",
            "network_used", "live_adapter_instantiated", "webhook_called",
            "bind_invoked", "bind_receipt_created", "trustlog_written",
            "request_dispatched",
        )},
        "fail_closed": decision.review_decision != REVIEW_DECISIONS[0],
        "scope_limitations": SCOPE_LIMITATIONS,
    }
    digest = _packet_hash(raw)
    raw["live_adapter_dry_run_operator_dispatch_review_hash"] = digest
    raw["live_adapter_dry_run_operator_dispatch_review_id"] = (
        f"ladror:v1:sha256:{digest}"
    )
    return verify_live_adapter_dry_run_operator_dispatch_review_packet(raw)


def verify_live_adapter_dry_run_operator_dispatch_review_packet(
    raw: Any,
) -> CanonicalLiveAdapterDryRunOperatorDispatchReviewPacket:
    """Reverify source and recompute every binding, digest, hash, and ID."""
    try:
        value = raw.model_dump(mode="json") if isinstance(raw, BaseModel) else raw
        packet = CanonicalLiveAdapterDryRunOperatorDispatchReviewPacket.model_validate(
            _json_value(value)
        )
    except (ValidationError, TypeError,
            LiveAdapterDryRunOperatorDispatchReviewError) as exc:
        raise LiveAdapterDryRunOperatorDispatchReviewError(
            "LADROR_PACKET_INVALID"
        ) from exc
    actual = packet.model_dump(mode="json")
    source = _source(packet.source_credential_authorization_evaluation_packet)
    _validate_source(source)
    source_raw = source.model_dump(mode="json")
    if (
        packet.source_credential_authorization_evaluation_id
        != source.live_adapter_dry_run_credential_authorization_evaluation_id
        or packet.source_credential_authorization_evaluation_hash
        != source.live_adapter_dry_run_credential_authorization_evaluation_hash
    ):
        raise LiveAdapterDryRunOperatorDispatchReviewError(
            "LADROR_SOURCE_IDENTITY_MISMATCH"
        )
    lineage = (
        packet.source_endpoint_allowlist_evaluation_hash,
        packet.source_dispatch_readiness_hash,
        packet.source_live_adapter_dry_run_request_hash,
    )
    if lineage != (
        source.source_endpoint_allowlist_evaluation_hash,
        source.source_dispatch_readiness_hash,
        source.source_live_adapter_dry_run_request_hash,
    ):
        raise LiveAdapterDryRunOperatorDispatchReviewError(
            "LADROR_LINEAGE_MISMATCH"
        )
    for field in COPIED_FIELDS:
        if _json_value(getattr(packet, field)) != _json_value(source_raw[field]):
            raise LiveAdapterDryRunOperatorDispatchReviewError(
                "LADROR_SOURCE_FIELD_MISMATCH"
            )
    _validate_decision(source, packet.operator_review_decision)
    reviewed_at = _timestamp(packet.operator_review_decision.reviewed_at)
    recorded_at = _timestamp(packet.operator_dispatch_review_recorded_at)
    if datetime.fromisoformat(recorded_at) < datetime.fromisoformat(reviewed_at):
        raise LiveAdapterDryRunOperatorDispatchReviewError(
            "LADROR_RECORDED_TOO_EARLY"
        )
    decision_raw = packet.operator_review_decision.model_dump(mode="json")
    decision_raw["reviewed_at"] = reviewed_at
    decision_digest = _digest(DECISION_DOMAIN, decision_raw)
    if packet.operator_review_decision_digest != decision_digest:
        raise LiveAdapterDryRunOperatorDispatchReviewError(
            "LADROR_DECISION_DIGEST_MISMATCH"
        )
    binding = _binding(source, packet.operator_review_decision)
    if (
        packet.operator_review_binding != binding
        or packet.operator_review_binding_digest != _digest(BINDING_DOMAIN, binding)
    ):
        raise LiveAdapterDryRunOperatorDispatchReviewError(
            "LADROR_BINDING_MISMATCH"
        )
    checks = _checks(
        source.live_adapter_dry_run_credential_authorization_evaluation_hash,
        decision_digest,
    )
    if (
        _json_value(packet.operator_dispatch_review_checks) != checks
        or packet.operator_dispatch_review_check_digest
        != _digest(CHECKS_DOMAIN, checks)
    ):
        raise LiveAdapterDryRunOperatorDispatchReviewError(
            "LADROR_CHECKS_MISMATCH"
        )
    requirements = _requirements()
    if (
        _json_value(packet.future_bind_pre_dispatch_review_requirements)
        != requirements
        or packet.future_bind_pre_dispatch_review_requirement_digest
        != _digest(REQUIREMENTS_DOMAIN, requirements)
    ):
        raise LiveAdapterDryRunOperatorDispatchReviewError(
            "LADROR_REQUIREMENTS_MISMATCH"
        )
    expected_fail_closed = packet.operator_review_decision.review_decision != (
        "APPROVE_FOR_BIND_PRE_DISPATCH_REVIEW"
    ) or not all(check.passed for check in packet.operator_dispatch_review_checks)
    if packet.fail_closed != expected_fail_closed:
        raise LiveAdapterDryRunOperatorDispatchReviewError(
            "LADROR_FAIL_CLOSED_MISMATCH"
        )
    if packet.scope_limitations != SCOPE_LIMITATIONS:
        raise LiveAdapterDryRunOperatorDispatchReviewError(
            "LADROR_SCOPE_LIMITATIONS_MISMATCH"
        )
    digest = _packet_hash(actual)
    if packet.live_adapter_dry_run_operator_dispatch_review_hash != digest:
        raise LiveAdapterDryRunOperatorDispatchReviewError(
            "LADROR_PACKET_HASH_MISMATCH"
        )
    if packet.live_adapter_dry_run_operator_dispatch_review_id != (
        f"ladror:v1:sha256:{digest}"
    ):
        raise LiveAdapterDryRunOperatorDispatchReviewError(
            "LADROR_PACKET_ID_MISMATCH"
        )
    return packet
