"""Construct a deterministic live-adapter dry-run request without dispatch.

This module is an intentionally local, pure-data boundary.  It verifies the
readiness artifact and constructs content-addressed evidence for a *future*
dispatch; it has no capability to instantiate or call an adapter.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from veritas_os.policy.adapter_dry_run_plan import STEPS_DOMAIN, _digest as source_digest
from veritas_os.policy.adapter_dry_run_result import RESULTS_DOMAIN as FIXTURE_DOMAIN
from veritas_os.policy.bind_artifacts import (
    ExecutionIntent,
    canonical_execution_intent_json,
    hash_execution_intent,
)
from veritas_os.policy.live_adapter_dry_run_readiness import (
    CHECKS_DOMAIN as READINESS_CHECKS_DOMAIN,
    CanonicalLiveAdapterDryRunRequestReadinessPacket,
    LiveAdapterDryRunReadinessError,
    _digest as readiness_digest,
    verify_live_adapter_dry_run_request_readiness_packet,
)
from veritas_os.policy.reference_adapter_rehearsal import (
    RESULTS_DOMAIN as REHEARSAL_DOMAIN,
)

FORMAT_VERSION = "canonical-live-adapter-dry-run-request/v1"
REQUEST_MECHANISM = "construct_live_adapter_dry_run_request_without_dispatch/v1"
DESCRIPTOR_DOMAIN = "veritas.live-adapter-dry-run-request.descriptor/v1"
DISPATCH_PRECONDITIONS_DOMAIN = (
    "veritas.live-adapter-dry-run-request.dispatch-preconditions/v1"
)
CONSTRUCTION_CHECKS_DOMAIN = (
    "veritas.live-adapter-dry-run-request.construction-checks/v1"
)
FUTURE_REQUIREMENTS_DOMAIN = (
    "veritas.live-adapter-dry-run-request.future-requirements/v1"
)
PACKET_DOMAIN = "veritas.live-adapter-dry-run-request.packet/v1"

PRECONDITION_NAMES = (
    "readiness_packet_verified", "execution_intent_identity_verified",
    "adapter_descriptor_preserved", "request_descriptor_constructed",
    "dry_run_only_policy_declared", "read_only_scope_declared",
    "no_apply_policy_declared", "no_commit_policy_declared",
    "no_credential_material_embedded", "no_endpoint_material_embedded",
    "dispatch_not_performed", "webhook_not_called",
    "live_adapter_not_instantiated", "bind_not_invoked",
    "bind_receipt_not_created", "trustlog_not_written",
    "external_effect_not_used", "future_dispatch_gate_required",
)
PRECONDITION_LIMITATIONS = (
    "NOT_DISPATCHED", "NOT_LIVE_ADAPTER_RESULT", "NOT_LIVE_STATE",
    "NOT_LIVE_AUTHORITY_REVALIDATION", "NOT_LIVE_CONSTRAINT_REVALIDATION",
    "NOT_RUNTIME_RISK_ACCEPTANCE", "NOT_BIND_AUTHORIZATION",
    "NOT_BIND_RECEIPT", "NOT_TRUSTLOG_WRITE", "NOT_OPERATION_COMMIT",
)
DESCRIPTOR_LIMITATIONS = (
    "NOT_DISPATCHED", "NOT_LIVE_ADAPTER_INVOCATION",
    "NOT_WEBHOOK_INVOCATION", "NOT_NETWORK_CALL", "NOT_CREDENTIAL_ACCESS",
    "NOT_LIVE_STATE", "NOT_BIND_AUTHORIZATION", "NOT_BIND_RECEIPT",
    "NOT_TRUSTLOG_WRITE", "NOT_OPERATION_COMMIT",
)
SCOPE_LIMITATIONS = (
    "NOT_EXECUTION_AUTHORITY", "NOT_BIND_AUTHORIZATION", "NOT_BIND_RECEIPT",
    "NOT_BIND_INVOCATION", "NOT_LIVE_ADAPTER_INSTANCE",
    "NOT_LIVE_ADAPTER_INVOCATION", "NOT_LIVE_ADAPTER_RESULT",
    "NOT_LIVE_DRY_RUN_DISPATCH", "NOT_WEBHOOK_INVOCATION",
    "NOT_NETWORK_CALL", "NOT_CREDENTIAL_ACCESS", "NOT_EXTERNAL_EFFECT",
    "NOT_OPERATION_COMMIT", "NOT_TRUSTLOG_WRITE", "NOT_LIVE_STATE_CHECK",
    "NOT_RUNTIME_RISK_ACCEPTANCE", "NOT_LIVE_AUTHORITY_REVALIDATION",
    "NOT_LIVE_CONSTRAINT_REVALIDATION", "NOT_POSTCONDITION_VERIFICATION",
    "NOT_ROLLBACK_PROOF", "NOT_AUTHORITY_EVIDENCE", "NOT_HUMAN_APPROVAL",
)
SOURCE_SUMMARY_KEYS = (
    "live_adapter_dry_run_readiness_id", "live_adapter_dry_run_readiness_hash",
    "format_version", "readiness_mechanism", "readiness_evaluated_at",
    "execution_intent_id", "execution_intent_hash",
    "live_adapter_dry_run_request_readiness_status",
    "ready_for_live_adapter_dry_run_request_packet",
)
COPIED_FIELDS = (
    "source_reference_rehearsal_hash",
    "source_adapter_dry_run_fixture_result_hash", "source_adapter_dry_run_plan_hash",
    "source_adapter_contract_selection_hash",
    "source_bind_preflight_adjudication_hash", "source_formation_hash",
    "source_readiness_hash", "source_eligibility_hash", "source_handoff_hash",
    "trusted_validation_context_hash", "validation_result_hash",
    "mapping_value_digest", "execution_intent_contract_version",
    "source_to_execution_intent_mapping", "field_mapping_proof",
    "required_field_presence", "source_decision_identity", "candidate_identity",
    "evidence_lineage", "replay_summary",
)
CONSTRUCTION_CHECKS = {key: True for key in (
    "readiness_packet_verified", "execution_intent_hash_verified",
    "execution_intent_id_verified", "adapter_descriptor_preserved",
    "planned_steps_preserved", "fixture_results_preserved",
    "reference_rehearsal_results_preserved", "readiness_checks_preserved",
    "planned_step_digest_verified", "fixture_result_digest_verified",
    "reference_rehearsal_result_digest_verified", "readiness_check_digest_verified",
    "request_descriptor_constructed", "dispatch_preconditions_ordered",
    "dispatch_precondition_digest_verified", "requested_after_readiness_evaluation",
    "no_live_adapter_instance", "no_live_adapter_invocation",
    "no_webhook_invocation", "no_live_dry_run_dispatch", "no_bind_invocation",
    "no_bind_receipt_created", "no_trustlog_write", "no_network",
    "no_filesystem", "no_credential_access", "no_endpoint_contact",
    "no_external_effect", "no_apply", "no_postcondition_verification",
    "no_revert", "semantic_match_not_authority",
)}
FUTURE_REQUIREMENTS = {key: True for key in (
    "dispatch_readiness_packet_required", "endpoint_allowlist_resolution_required",
    "credential_resolution_required", "credential_scope_review_required",
    "live_adapter_instance_policy_required", "live_adapter_timeout_required",
    "live_adapter_rate_limit_required", "live_adapter_idempotency_key_required",
    "dry_run_only_enforcement_required", "no_apply_runtime_guard_required",
    "no_commit_runtime_guard_required", "network_egress_policy_required",
    "webhook_dispatch_policy_required", "live_result_packet_required",
    "bind_receipt_still_deferred", "human_approval_still_required_when_policy_requires",
    "authority_evidence_still_required", "apply_still_forbidden",
    "verify_postconditions_still_deferred", "rollback_or_revert_still_deferred",
)}


class LiveAdapterDryRunRequestError(ValueError):
    """Stable fail-closed refusal for request packet processing."""


class LiveAdapterDryRunRequestDescriptor(BaseModel):
    """Immutable non-secret description of a future dry-run request."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    request_descriptor_id: str = Field(
        pattern=r"^live-adapter-dry-run-request-descriptor:v1:[a-z0-9-]+$"
    )
    request_kind: Literal["live_adapter_dry_run"]
    dispatch_mode: Literal["not_dispatched"]
    adapter_contract_id: str
    adapter_contract_hash: str
    adapter_contract_version: str
    target_system: str
    target_resource_scope: str
    action_name: str
    dry_run_only: Literal[True]
    read_only_scope_required: Literal[True]
    no_apply: Literal[True]
    no_commit: Literal[True]
    no_state_mutation: Literal[True]
    no_trustlog_write_before_policy: Literal[True]
    no_bind_receipt_before_bind: Literal[True]
    credential_material_included: Literal[False]
    credential_accessed: Literal[False]
    endpoint_material_included: Literal[False]
    endpoint_contacted: Literal[False]
    webhook_contacted: Literal[False]
    network_used: Literal[False]
    external_effect_used: Literal[False]
    descriptor_scope_limitations: tuple[str, ...]


class LiveAdapterDryRunDispatchPrecondition(BaseModel):
    """Immutable local assertion that precedes any future dispatch gate."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    precondition_id: str = Field(
        pattern=(
            r"^live-adapter-dry-run-dispatch-precondition:v1:"
            r"[1-9][0-9]*:[a-z0-9-]+$"
        )
    )
    ordinal: int = Field(ge=1, le=18)
    precondition_name: Literal[*PRECONDITION_NAMES]
    precondition_mode: Literal["deterministic_local_request_construction_only"]
    passed: Literal[True]
    evidence_ref: str = Field(min_length=1)
    live_observation_used: Literal[False]
    network_used: Literal[False]
    filesystem_used: Literal[False]
    credential_accessed: Literal[False]
    adapter_instance_created: Literal[False]
    adapter_method_called: Literal[False]
    request_dispatched: Literal[False]
    webhook_called: Literal[False]
    bind_invoked: Literal[False]
    bind_receipt_created: Literal[False]
    trustlog_written: Literal[False]
    external_effect_used: Literal[False]
    precondition_scope_limitations: tuple[str, ...]


class CanonicalLiveAdapterDryRunRequestPacket(BaseModel):
    """Strict immutable content-addressed, non-dispatched request packet."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    format_version: Literal[FORMAT_VERSION]
    live_adapter_dry_run_request_id: str = Field(pattern=r"^ladrq:v1:sha256:[0-9a-f]{64}$")
    live_adapter_dry_run_request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_mechanism: Literal[REQUEST_MECHANISM]
    requested_at: str
    source_live_adapter_dry_run_readiness: dict[str, Any]
    source_live_adapter_dry_run_readiness_hash: str
    source_live_adapter_dry_run_readiness_packet: dict[str, Any]
    request_descriptor: LiveAdapterDryRunRequestDescriptor
    adapter_contract_descriptor: dict[str, Any]
    adapter_contract_id: str
    adapter_contract_hash: str
    adapter_contract_version: str
    execution_intent: dict[str, Any]
    execution_intent_id: str
    execution_intent_hash: str
    source_reference_rehearsal_hash: str
    source_adapter_dry_run_fixture_result_hash: str
    source_adapter_dry_run_plan_hash: str
    source_adapter_contract_selection_hash: str
    source_bind_preflight_adjudication_hash: str
    source_formation_hash: str
    source_readiness_hash: str
    source_eligibility_hash: str
    source_handoff_hash: str
    trusted_validation_context_hash: str
    validation_result_hash: str
    mapping_value_digest: str
    execution_intent_contract_version: str
    live_adapter_dry_run_request_status: Literal[
        "LIVE_ADAPTER_DRY_RUN_REQUEST_CREATED_NOT_DISPATCHED"
    ]
    request_dispatch_state: Literal["NOT_DISPATCHED"]
    ready_for_live_adapter_dry_run_dispatch_readiness: Literal[True]
    fail_closed: Literal[False]
    planned_steps: tuple[dict[str, Any], ...]
    planned_step_digest: str
    fixture_step_results: tuple[dict[str, Any], ...]
    fixture_result_digest: str
    reference_rehearsal_results: tuple[dict[str, Any], ...]
    reference_rehearsal_result_digest: str
    readiness_checks: tuple[dict[str, Any], ...]
    readiness_check_digest: str
    dispatch_preconditions: tuple[LiveAdapterDryRunDispatchPrecondition, ...]
    dispatch_precondition_digest: str
    request_construction_checks: dict[str, bool]
    future_live_adapter_dry_run_dispatch_requirements: dict[str, bool]
    source_to_execution_intent_mapping: dict[str, Any]
    field_mapping_proof: dict[str, Any]
    required_field_presence: dict[str, str]
    source_decision_identity: dict[str, Any]
    candidate_identity: dict[str, Any]
    evidence_lineage: dict[str, Any]
    replay_summary: dict[str, Any]
    scope_limitations: tuple[str, ...]


def _json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise LiveAdapterDryRunRequestError("LADRQ_PACKET_INVALID")
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise LiveAdapterDryRunRequestError("LADRQ_REQUESTED_AT_INVALID")
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _json_value(item) for key, item in value.items()}
    raise LiveAdapterDryRunRequestError("LADRQ_PACKET_INVALID")


def _aware(value: Any, code: str) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise LiveAdapterDryRunRequestError(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LiveAdapterDryRunRequestError(code)
    return parsed


def _digest(domain: str, value: Any) -> str:
    encoded = json.dumps(
        {"domain": domain, "value": _json_value(value)}, allow_nan=False,
        ensure_ascii=False, separators=(",", ":"), sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _packet_hash(raw: dict[str, Any]) -> str:
    return _digest(PACKET_DOMAIN, {key: value for key, value in raw.items() if key not in {
        "live_adapter_dry_run_request_id", "live_adapter_dry_run_request_hash",
    }})


def _source(value: Any) -> CanonicalLiveAdapterDryRunRequestReadinessPacket:
    try:
        return verify_live_adapter_dry_run_request_readiness_packet(value)
    except (LiveAdapterDryRunReadinessError, TypeError, ValueError) as exc:
        raise LiveAdapterDryRunRequestError("LADRQ_READINESS_PACKET_INVALID") from exc


def _intent(raw: dict[str, Any]) -> ExecutionIntent:
    try:
        intent = ExecutionIntent(**raw)
        canonical_execution_intent_json(intent)
    except (TypeError, ValueError) as exc:
        raise LiveAdapterDryRunRequestError("LADRQ_PACKET_INVALID") from exc
    if intent.to_dict() != raw:
        raise LiveAdapterDryRunRequestError("LADRQ_PACKET_INVALID")
    return intent


def _build_expected_request_descriptor(
    source: CanonicalLiveAdapterDryRunRequestReadinessPacket,
) -> dict[str, Any]:
    """Return the canonical descriptor derived only from verified readiness.

    Normalizing the complete descriptor here ensures the builder and verifier
    compare the same JSON representation, including list-valued limitations.
    """
    intent = _intent(source.execution_intent)
    slug = re.sub(r"[^a-z0-9]+", "-", source.adapter_contract_id.lower()).strip("-")
    raw = {
        "request_descriptor_id": f"live-adapter-dry-run-request-descriptor:v1:{slug}",
        "request_kind": "live_adapter_dry_run", "dispatch_mode": "not_dispatched",
        "adapter_contract_id": source.adapter_contract_id,
        "adapter_contract_hash": source.adapter_contract_hash,
        "adapter_contract_version": source.adapter_contract_version,
        "target_system": intent.target_system,
        "target_resource_scope": intent.target_resource,
        "action_name": intent.intended_action,
        "dry_run_only": True, "read_only_scope_required": True,
        "no_apply": True, "no_commit": True, "no_state_mutation": True,
        "no_trustlog_write_before_policy": True,
        "no_bind_receipt_before_bind": True,
        "credential_material_included": False, "credential_accessed": False,
        "endpoint_material_included": False, "endpoint_contacted": False,
        "webhook_contacted": False, "network_used": False,
        "external_effect_used": False,
        "descriptor_scope_limitations": DESCRIPTOR_LIMITATIONS,
    }
    canonical = _json_value(raw)
    _digest(DESCRIPTOR_DOMAIN, canonical)
    return canonical


def _preconditions(source_hash: str) -> list[dict[str, Any]]:
    return [{
        "precondition_id": (
            "live-adapter-dry-run-dispatch-precondition:"
            f"v1:{ordinal}:{name.replace('_', '-')}"
        ),
        "ordinal": ordinal, "precondition_name": name,
        "precondition_mode": "deterministic_local_request_construction_only",
        "passed": True, "evidence_ref": f"readiness_hash:{source_hash}:{name}",
        "live_observation_used": False, "network_used": False,
        "filesystem_used": False, "credential_accessed": False,
        "adapter_instance_created": False, "adapter_method_called": False,
        "request_dispatched": False, "webhook_called": False,
        "bind_invoked": False, "bind_receipt_created": False,
        "trustlog_written": False, "external_effect_used": False,
        "precondition_scope_limitations": PRECONDITION_LIMITATIONS,
    } for ordinal, name in enumerate(PRECONDITION_NAMES, 1)]


def _validate_source(source: CanonicalLiveAdapterDryRunRequestReadinessPacket) -> None:
    intent = _intent(source.execution_intent)
    if intent.execution_intent_id != source.execution_intent_id:
        raise LiveAdapterDryRunRequestError("LADRQ_EXECUTION_INTENT_ID_MISMATCH")
    if hash_execution_intent(intent) != source.execution_intent_hash:
        raise LiveAdapterDryRunRequestError("LADRQ_EXECUTION_INTENT_HASH_MISMATCH")
    descriptor = source.adapter_contract_descriptor
    if (descriptor.get("target_system") != intent.target_system or
            descriptor.get("target_resource_scope") != intent.target_resource):
        raise LiveAdapterDryRunRequestError("LADRQ_DESCRIPTOR_MISMATCH")


def build_live_adapter_dry_run_request_packet(
    live_adapter_dry_run_readiness_packet: Any,
    requested_at: datetime,
) -> CanonicalLiveAdapterDryRunRequestPacket:
    """Verify readiness and construct a request packet without dispatching it."""
    requested = _aware(requested_at, "LADRQ_REQUESTED_AT_INVALID")
    source = _source(_json_value(live_adapter_dry_run_readiness_packet))
    _validate_source(source)
    if requested < _aware(source.readiness_evaluated_at, "LADRQ_READINESS_PACKET_INVALID"):
        raise LiveAdapterDryRunRequestError("LADRQ_REQUESTED_BEFORE_READINESS")
    source_raw = source.model_dump(mode="json")
    preconditions = _preconditions(source.live_adapter_dry_run_readiness_hash)
    raw = {
        "format_version": FORMAT_VERSION, "request_mechanism": REQUEST_MECHANISM,
        "requested_at": requested.isoformat(),
        "source_live_adapter_dry_run_readiness": {
            key: source_raw[key] for key in SOURCE_SUMMARY_KEYS
        },
        "source_live_adapter_dry_run_readiness_hash": source.live_adapter_dry_run_readiness_hash,
        "source_live_adapter_dry_run_readiness_packet": source_raw,
        "request_descriptor": _build_expected_request_descriptor(source),
        "adapter_contract_descriptor": source_raw["adapter_contract_descriptor"],
        "adapter_contract_id": source.adapter_contract_id,
        "adapter_contract_hash": source.adapter_contract_hash,
        "adapter_contract_version": source.adapter_contract_version,
        "execution_intent": source_raw["execution_intent"],
        "execution_intent_id": source.execution_intent_id,
        "execution_intent_hash": source.execution_intent_hash,
        **{key: source_raw[key] for key in COPIED_FIELDS},
        "live_adapter_dry_run_request_status": (
            "LIVE_ADAPTER_DRY_RUN_REQUEST_CREATED_NOT_DISPATCHED"
        ),
        "request_dispatch_state": "NOT_DISPATCHED",
        "ready_for_live_adapter_dry_run_dispatch_readiness": True,
        "fail_closed": False,
        "planned_steps": source_raw["planned_steps"],
        "planned_step_digest": source.planned_step_digest,
        "fixture_step_results": source_raw["fixture_step_results"],
        "fixture_result_digest": source.fixture_result_digest,
        "reference_rehearsal_results": source_raw["reference_rehearsal_results"],
        "reference_rehearsal_result_digest": source.reference_rehearsal_result_digest,
        "readiness_checks": source_raw["readiness_checks"],
        "readiness_check_digest": source.readiness_check_digest,
        "dispatch_preconditions": preconditions,
        "dispatch_precondition_digest": _digest(DISPATCH_PRECONDITIONS_DOMAIN, preconditions),
        "request_construction_checks": CONSTRUCTION_CHECKS,
        "future_live_adapter_dry_run_dispatch_requirements": FUTURE_REQUIREMENTS,
        "scope_limitations": SCOPE_LIMITATIONS,
    }
    digest = _packet_hash(raw)
    raw.update(live_adapter_dry_run_request_hash=digest,
               live_adapter_dry_run_request_id=f"ladrq:v1:sha256:{digest}")
    return verify_live_adapter_dry_run_request_packet(raw)


def verify_live_adapter_dry_run_request_packet(
    packet: Any,
) -> CanonicalLiveAdapterDryRunRequestPacket:
    """Independently reverify source, preserved data, claims, and identity."""
    try:
        value = (
            packet.model_dump(mode="json")
            if isinstance(packet, BaseModel)
            else _json_value(packet)
        )
        candidate = CanonicalLiveAdapterDryRunRequestPacket.model_validate(value)
    except (ValidationError, LiveAdapterDryRunRequestError, TypeError) as exc:
        raise LiveAdapterDryRunRequestError("LADRQ_PACKET_INVALID") from exc
    raw = candidate.model_dump(mode="json")
    source = _source(candidate.source_live_adapter_dry_run_readiness_packet)
    source_raw = source.model_dump(mode="json")
    _validate_source(source)
    expected_summary = {key: source_raw[key] for key in SOURCE_SUMMARY_KEYS}
    if (set(candidate.source_live_adapter_dry_run_readiness) != set(SOURCE_SUMMARY_KEYS)
            or candidate.source_live_adapter_dry_run_readiness != expected_summary
            or candidate.source_live_adapter_dry_run_readiness_hash
            != source.live_adapter_dry_run_readiness_hash):
        raise LiveAdapterDryRunRequestError("LADRQ_SOURCE_SUMMARY_MISMATCH")
    if _aware(candidate.requested_at, "LADRQ_REQUESTED_AT_INVALID") < _aware(
            source.readiness_evaluated_at, "LADRQ_READINESS_PACKET_INVALID"):
        raise LiveAdapterDryRunRequestError("LADRQ_REQUESTED_BEFORE_READINESS")
    intent = _intent(candidate.execution_intent)
    if candidate.execution_intent != source.execution_intent:
        raise LiveAdapterDryRunRequestError("LADRQ_EXECUTION_INTENT_HASH_MISMATCH")
    if (intent.execution_intent_id != candidate.execution_intent_id or
            candidate.execution_intent_id != source.execution_intent_id):
        raise LiveAdapterDryRunRequestError("LADRQ_EXECUTION_INTENT_ID_MISMATCH")
    if (hash_execution_intent(intent) != candidate.execution_intent_hash or
            candidate.execution_intent_hash != source.execution_intent_hash):
        raise LiveAdapterDryRunRequestError("LADRQ_EXECUTION_INTENT_HASH_MISMATCH")
    actual_descriptor = _json_value(candidate.request_descriptor)
    expected_descriptor = _build_expected_request_descriptor(source)
    if actual_descriptor != expected_descriptor:
        raise LiveAdapterDryRunRequestError("LADRQ_REQUEST_DESCRIPTOR_INVALID")
    for key in ("adapter_contract_descriptor", "adapter_contract_id",
                "adapter_contract_hash", "adapter_contract_version", *COPIED_FIELDS):
        if _json_value(getattr(candidate, key)) != _json_value(getattr(source, key)):
            raise LiveAdapterDryRunRequestError("LADRQ_DESCRIPTOR_MISMATCH")
    collections = (
        ("planned_steps", "planned_step_digest", STEPS_DOMAIN, source_digest,
         "LADRQ_PLANNED_STEPS_MISMATCH"),
        ("fixture_step_results", "fixture_result_digest", FIXTURE_DOMAIN, _digest,
         "LADRQ_FIXTURE_RESULTS_MISMATCH"),
        ("reference_rehearsal_results", "reference_rehearsal_result_digest",
         REHEARSAL_DOMAIN, _digest, "LADRQ_REFERENCE_REHEARSAL_RESULTS_MISMATCH"),
        ("readiness_checks", "readiness_check_digest", READINESS_CHECKS_DOMAIN,
         readiness_digest, "LADRQ_READINESS_CHECKS_MISMATCH"),
    )
    for field, digest_field, domain, digest_fn, code in collections:
        value = _json_value(getattr(candidate, field))
        if (value != _json_value(getattr(source, field)) or
                getattr(candidate, digest_field) != getattr(source, digest_field) or
                getattr(candidate, digest_field) != digest_fn(domain, value)):
            raise LiveAdapterDryRunRequestError(code)
    preconditions = _preconditions(source.live_adapter_dry_run_readiness_hash)
    if _json_value(candidate.dispatch_preconditions) != preconditions:
        raise LiveAdapterDryRunRequestError("LADRQ_DISPATCH_PRECONDITIONS_INVALID")
    if candidate.dispatch_precondition_digest != _digest(
            DISPATCH_PRECONDITIONS_DOMAIN, preconditions):
        raise LiveAdapterDryRunRequestError("LADRQ_DISPATCH_PRECONDITION_DIGEST_MISMATCH")
    if candidate.request_construction_checks != CONSTRUCTION_CHECKS:
        raise LiveAdapterDryRunRequestError("LADRQ_CONSTRUCTION_CHECKS_MISMATCH")
    if candidate.future_live_adapter_dry_run_dispatch_requirements != FUTURE_REQUIREMENTS:
        raise LiveAdapterDryRunRequestError("LADRQ_FUTURE_REQUIREMENTS_MISMATCH")
    _digest(CONSTRUCTION_CHECKS_DOMAIN, candidate.request_construction_checks)
    _digest(FUTURE_REQUIREMENTS_DOMAIN, candidate.future_live_adapter_dry_run_dispatch_requirements)
    if candidate.scope_limitations != SCOPE_LIMITATIONS:
        raise LiveAdapterDryRunRequestError("LADRQ_SCOPE_LIMITATIONS_MISSING")
    digest = _packet_hash(raw)
    if candidate.live_adapter_dry_run_request_hash != digest:
        raise LiveAdapterDryRunRequestError("LADRQ_PACKET_HASH_MISMATCH")
    if candidate.live_adapter_dry_run_request_id != f"ladrq:v1:sha256:{digest}":
        raise LiveAdapterDryRunRequestError("LADRQ_PACKET_ID_MISMATCH")
    return candidate
