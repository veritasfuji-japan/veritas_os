"""Evaluate dry-run dispatch readiness without dispatching or external effects.

The packet produced here is local, deterministic evidence about a previously
verified request packet.  It deliberately has no endpoint, credential,
adapter, network, Bind, receipt, persistence, or commit capability.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from veritas_os.policy.live_adapter_dry_run_request import (
    CanonicalLiveAdapterDryRunRequestPacket,
    LiveAdapterDryRunRequestError,
    verify_live_adapter_dry_run_request_packet,
)

FORMAT_VERSION = "canonical-live-adapter-dry-run-dispatch-readiness/v1"
DISPATCH_READINESS_MECHANISM = (
    "evaluate_live_adapter_dry_run_dispatch_readiness_without_dispatch/v1"
)
CHECKS_DOMAIN = "veritas.live-adapter-dry-run-dispatch-readiness.checks/v1"
FUTURE_REQUIREMENTS_DOMAIN = (
    "veritas.live-adapter-dry-run-dispatch-readiness.future-requirements/v1"
)
PACKET_DOMAIN = "veritas.live-adapter-dry-run-dispatch-readiness.packet/v1"

CHECK_NAMES = (
    "source_request_packet_verified",
    "request_packet_not_dispatched",
    "request_descriptor_preserved",
    "dispatch_preconditions_preserved",
    "execution_intent_identity_preserved",
    "adapter_contract_identity_preserved",
    "source_lineage_preserved",
    "no_endpoint_material_present",
    "no_credential_material_present",
    "no_network_material_present",
    "no_webhook_material_present",
    "no_live_adapter_instance_present",
    "no_bind_invocation_present",
    "no_bind_receipt_present",
    "no_trustlog_write_present",
    "endpoint_allowlist_evaluation_required",
    "credential_resolution_evaluation_required",
    "live_adapter_instance_evaluation_required",
    "operator_dispatch_review_required",
    "bind_pre_dispatch_review_required",
    "future_dispatch_gate_required",
)
EFFECT_FIELDS = (
    "endpoint_resolved", "credential_resolved", "credential_material_accessed",
    "credential_material_embedded", "network_used", "webhook_called",
    "live_adapter_instantiated", "live_adapter_method_called",
    "request_dispatched", "bind_invoked", "bind_receipt_created",
    "trustlog_written", "external_effect_used", "filesystem_used",
    "database_used", "provider_used", "subprocess_used", "operation_committed",
)
FUTURE_REQUIREMENT_NAMES = (
    "endpoint_allowlist_evaluation", "endpoint_identity_binding",
    "credential_resolution_authorization", "credential_material_non_embedding",
    "live_adapter_instance_construction_boundary",
    "operator_human_dispatch_review", "bind_pre_dispatch_review",
    "network_dispatch_boundary", "external_effect_scope_declaration",
    "trustlog_write_boundary_after_proper_authorization",
    "bind_receipt_boundary_only_after_bind",
    "rollback_postcondition_requirements_for_later_apply_path",
)
SCOPE_LIMITATIONS = (
    "NOT_DISPATCHED", "NOT_LIVE_ADAPTER_RESULT", "NOT_LIVE_STATE",
    "NOT_ENDPOINT_RESOLUTION", "NOT_CREDENTIAL_RESOLUTION",
    "NOT_CREDENTIAL_ACCESS", "NOT_NETWORK_CALL", "NOT_WEBHOOK_CALL",
    "NOT_LIVE_ADAPTER_INSTANCE", "NOT_BIND_AUTHORIZATION",
    "NOT_BIND_RECEIPT", "NOT_TRUSTLOG_WRITE", "NOT_OPERATION_COMMIT",
    "NOT_PRODUCTION_CLAIM", "NOT_CUSTOMER_CLAIM",
    "NOT_REGULATORY_CERTIFICATION",
)
COPIED_FIELDS = (
    "request_descriptor", "dispatch_preconditions", "dispatch_precondition_digest",
    "execution_intent", "execution_intent_id", "execution_intent_hash",
    "adapter_contract_descriptor", "adapter_contract_id", "adapter_contract_hash",
    "adapter_contract_version", "source_live_adapter_dry_run_readiness_hash",
    "source_reference_rehearsal_hash", "source_adapter_dry_run_fixture_result_hash",
    "source_adapter_dry_run_plan_hash", "source_adapter_contract_selection_hash",
    "source_bind_preflight_adjudication_hash", "source_formation_hash",
    "source_readiness_hash", "source_eligibility_hash", "source_handoff_hash",
    "trusted_validation_context_hash", "validation_result_hash",
    "mapping_value_digest", "execution_intent_contract_version",
    "source_to_execution_intent_mapping", "field_mapping_proof",
    "required_field_presence", "source_decision_identity", "candidate_identity",
    "evidence_lineage", "replay_summary",
)


class LiveAdapterDryRunDispatchReadinessError(ValueError):
    """Stable fail-closed refusal for invalid dispatch-readiness evidence."""


class DispatchReadinessCheck(BaseModel):
    """One ordered, local, non-effecting readiness assertion."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    check_id: str = Field(pattern=r"^ladrdr-check:v1:[1-9][0-9]*:[a-z0-9-]+$")
    ordinal: int = Field(ge=1, le=21)
    name: Literal[*CHECK_NAMES]
    mode: Literal["deterministic_local_dispatch_readiness_evaluation_only"]
    passed: Literal[True]
    evidence_ref: str = Field(min_length=1)
    endpoint_resolved: Literal[False]
    credential_resolved: Literal[False]
    credential_material_accessed: Literal[False]
    credential_material_embedded: Literal[False]
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


class FutureDispatchRequirement(BaseModel):
    """A requirement explicitly deferred to a separate future artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    ordinal: int = Field(ge=1, le=12)
    name: Literal[*FUTURE_REQUIREMENT_NAMES]
    separate_future_artifact_required: Literal[True]
    satisfied_by_this_packet: Literal[False]


class CanonicalLiveAdapterDryRunDispatchReadinessPacket(BaseModel):
    """Closed, immutable, content-addressed dispatch-readiness packet."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    format_version: Literal[FORMAT_VERSION]
    live_adapter_dry_run_dispatch_readiness_id: str = Field(
        pattern=r"^ladrdr:v1:sha256:[0-9a-f]{64}$"
    )
    live_adapter_dry_run_dispatch_readiness_hash: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )
    dispatch_readiness_mechanism: Literal[DISPATCH_READINESS_MECHANISM]
    dispatch_readiness_evaluated_at: str
    source_live_adapter_dry_run_request_id: str
    source_live_adapter_dry_run_request_hash: str
    source_live_adapter_dry_run_request_packet: dict[str, Any]
    request_descriptor: dict[str, Any]
    dispatch_preconditions: tuple[dict[str, Any], ...]
    dispatch_precondition_digest: str
    execution_intent: dict[str, Any]
    execution_intent_id: str
    execution_intent_hash: str
    adapter_contract_descriptor: dict[str, Any]
    adapter_contract_id: str
    adapter_contract_hash: str
    adapter_contract_version: str
    source_live_adapter_dry_run_readiness_hash: str
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
    dispatch_readiness_status: Literal[
        "LIVE_ADAPTER_DRY_RUN_DISPATCH_READINESS_EVALUATED_NOT_DISPATCHED"
    ]
    request_dispatch_state: Literal["NOT_DISPATCHED"]
    ready_for_endpoint_allowlist_evaluation: Literal[True]
    ready_for_credential_resolution_evaluation: Literal[True]
    ready_for_live_adapter_instance_evaluation: Literal[True]
    ready_for_operator_dispatch_review: Literal[True]
    ready_for_bind_pre_dispatch_review: Literal[True]
    fail_closed: Literal[False]
    dispatch_readiness_checks: tuple[DispatchReadinessCheck, ...]
    dispatch_readiness_check_digest: str
    future_dispatch_requirements: tuple[FutureDispatchRequirement, ...]
    future_dispatch_requirement_digest: str
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
            raise LiveAdapterDryRunDispatchReadinessError("LADRDR_PACKET_INVALID")
        return value
    if isinstance(value, datetime):
        return _normalized_timestamp(value)
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _json_value(item) for key, item in value.items()}
    raise LiveAdapterDryRunDispatchReadinessError("LADRDR_PACKET_INVALID")


def _normalized_timestamp(value: Any) -> str:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise LiveAdapterDryRunDispatchReadinessError(
            "LADRDR_EVALUATED_AT_INVALID"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LiveAdapterDryRunDispatchReadinessError("LADRDR_EVALUATED_AT_INVALID")
    return parsed.astimezone(timezone.utc).isoformat()


def _digest(domain: str, value: Any) -> str:
    encoded = json.dumps(
        {"domain": domain, "value": _json_value(value)},
        allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _packet_hash(raw: dict[str, Any]) -> str:
    omitted = {
        "live_adapter_dry_run_dispatch_readiness_id",
        "live_adapter_dry_run_dispatch_readiness_hash",
    }
    return _digest(PACKET_DOMAIN, {key: value for key, value in raw.items()
                                   if key not in omitted})


def _source(value: Any) -> CanonicalLiveAdapterDryRunRequestPacket:
    try:
        return verify_live_adapter_dry_run_request_packet(value)
    except (LiveAdapterDryRunRequestError, TypeError, ValueError) as exc:
        raise LiveAdapterDryRunDispatchReadinessError(
            "LADRDR_SOURCE_REQUEST_INVALID"
        ) from exc


def _checks(source: CanonicalLiveAdapterDryRunRequestPacket) -> list[dict[str, Any]]:
    return [{
        "check_id": f"ladrdr-check:v1:{ordinal}:{name.replace('_', '-')}",
        "ordinal": ordinal,
        "name": name,
        "mode": "deterministic_local_dispatch_readiness_evaluation_only",
        "passed": True,
        "evidence_ref": f"source_request_hash:{source.live_adapter_dry_run_request_hash}:{name}",
        **{field: False for field in EFFECT_FIELDS},
    } for ordinal, name in enumerate(CHECK_NAMES, 1)]


def _future_requirements() -> list[dict[str, Any]]:
    return [{
        "ordinal": ordinal,
        "name": name,
        "separate_future_artifact_required": True,
        "satisfied_by_this_packet": False,
    } for ordinal, name in enumerate(FUTURE_REQUIREMENT_NAMES, 1)]


def build_live_adapter_dry_run_dispatch_readiness_packet(
    source_live_adapter_dry_run_request_packet: Any,
    dispatch_readiness_evaluated_at: datetime,
) -> CanonicalLiveAdapterDryRunDispatchReadinessPacket:
    """Evaluate a verified request locally, without performing dispatch."""
    evaluated_at = _normalized_timestamp(dispatch_readiness_evaluated_at)
    source = _source(_json_value(source_live_adapter_dry_run_request_packet))
    if source.request_dispatch_state != "NOT_DISPATCHED":
        raise LiveAdapterDryRunDispatchReadinessError("LADRDR_SOURCE_DISPATCHED")
    if source.live_adapter_dry_run_request_status != (
        "LIVE_ADAPTER_DRY_RUN_REQUEST_CREATED_NOT_DISPATCHED"
    ):
        raise LiveAdapterDryRunDispatchReadinessError("LADRDR_SOURCE_STATUS_INVALID")
    if datetime.fromisoformat(evaluated_at) < datetime.fromisoformat(
        _normalized_timestamp(source.requested_at)
    ):
        raise LiveAdapterDryRunDispatchReadinessError("LADRDR_EVALUATED_BEFORE_REQUEST")
    source_raw = source.model_dump(mode="json")
    checks = _checks(source)
    requirements = _future_requirements()
    raw = {
        "format_version": FORMAT_VERSION,
        "dispatch_readiness_mechanism": DISPATCH_READINESS_MECHANISM,
        "dispatch_readiness_evaluated_at": evaluated_at,
        "source_live_adapter_dry_run_request_id": source.live_adapter_dry_run_request_id,
        "source_live_adapter_dry_run_request_hash": source.live_adapter_dry_run_request_hash,
        "source_live_adapter_dry_run_request_packet": source_raw,
        **{field: source_raw[field] for field in COPIED_FIELDS},
        "dispatch_readiness_status": (
            "LIVE_ADAPTER_DRY_RUN_DISPATCH_READINESS_EVALUATED_NOT_DISPATCHED"
        ),
        "request_dispatch_state": "NOT_DISPATCHED",
        "ready_for_endpoint_allowlist_evaluation": True,
        "ready_for_credential_resolution_evaluation": True,
        "ready_for_live_adapter_instance_evaluation": True,
        "ready_for_operator_dispatch_review": True,
        "ready_for_bind_pre_dispatch_review": True,
        "fail_closed": False,
        "dispatch_readiness_checks": checks,
        "dispatch_readiness_check_digest": _digest(CHECKS_DOMAIN, checks),
        "future_dispatch_requirements": requirements,
        "future_dispatch_requirement_digest": _digest(
            FUTURE_REQUIREMENTS_DOMAIN, requirements
        ),
        "scope_limitations": SCOPE_LIMITATIONS,
    }
    digest = _packet_hash(raw)
    raw["live_adapter_dry_run_dispatch_readiness_hash"] = digest
    raw["live_adapter_dry_run_dispatch_readiness_id"] = (
        f"ladrdr:v1:sha256:{digest}"
    )
    return verify_live_adapter_dry_run_dispatch_readiness_packet(raw)


def verify_live_adapter_dry_run_dispatch_readiness_packet(
    raw: Any,
) -> CanonicalLiveAdapterDryRunDispatchReadinessPacket:
    """Fail closed unless every source, ordered claim, digest, and ID verifies."""
    try:
        value = raw.model_dump(mode="json") if isinstance(raw, BaseModel) else _json_value(raw)
        candidate = CanonicalLiveAdapterDryRunDispatchReadinessPacket.model_validate(value)
    except (ValidationError, TypeError, LiveAdapterDryRunDispatchReadinessError) as exc:
        raise LiveAdapterDryRunDispatchReadinessError("LADRDR_PACKET_INVALID") from exc
    candidate_raw = candidate.model_dump(mode="json")
    source = _source(candidate.source_live_adapter_dry_run_request_packet)
    source_raw = source.model_dump(mode="json")
    if candidate.source_live_adapter_dry_run_request_id != source.live_adapter_dry_run_request_id:
        raise LiveAdapterDryRunDispatchReadinessError("LADRDR_SOURCE_ID_MISMATCH")
    if candidate.source_live_adapter_dry_run_request_hash != source.live_adapter_dry_run_request_hash:
        raise LiveAdapterDryRunDispatchReadinessError("LADRDR_SOURCE_HASH_MISMATCH")
    if candidate.request_dispatch_state != source.request_dispatch_state:
        raise LiveAdapterDryRunDispatchReadinessError("LADRDR_SOURCE_DISPATCHED")
    if source.live_adapter_dry_run_request_status != (
        "LIVE_ADAPTER_DRY_RUN_REQUEST_CREATED_NOT_DISPATCHED"
    ):
        raise LiveAdapterDryRunDispatchReadinessError("LADRDR_SOURCE_STATUS_INVALID")
    if datetime.fromisoformat(_normalized_timestamp(candidate.dispatch_readiness_evaluated_at)) < datetime.fromisoformat(
        _normalized_timestamp(source.requested_at)
    ):
        raise LiveAdapterDryRunDispatchReadinessError("LADRDR_EVALUATED_BEFORE_REQUEST")
    for field in COPIED_FIELDS:
        if _json_value(getattr(candidate, field)) != _json_value(source_raw[field]):
            raise LiveAdapterDryRunDispatchReadinessError("LADRDR_SOURCE_FIELD_MISMATCH")
    checks = _checks(source)
    if _json_value(candidate.dispatch_readiness_checks) != checks:
        raise LiveAdapterDryRunDispatchReadinessError("LADRDR_CHECKS_MISMATCH")
    if candidate.dispatch_readiness_check_digest != _digest(CHECKS_DOMAIN, checks):
        raise LiveAdapterDryRunDispatchReadinessError("LADRDR_CHECK_DIGEST_MISMATCH")
    requirements = _future_requirements()
    if _json_value(candidate.future_dispatch_requirements) != requirements:
        raise LiveAdapterDryRunDispatchReadinessError("LADRDR_REQUIREMENTS_MISMATCH")
    if candidate.future_dispatch_requirement_digest != _digest(
        FUTURE_REQUIREMENTS_DOMAIN, requirements
    ):
        raise LiveAdapterDryRunDispatchReadinessError("LADRDR_REQUIREMENT_DIGEST_MISMATCH")
    if candidate.scope_limitations != SCOPE_LIMITATIONS:
        raise LiveAdapterDryRunDispatchReadinessError("LADRDR_SCOPE_MISMATCH")
    digest = _packet_hash(candidate_raw)
    if candidate.live_adapter_dry_run_dispatch_readiness_hash != digest:
        raise LiveAdapterDryRunDispatchReadinessError("LADRDR_PACKET_HASH_MISMATCH")
    if candidate.live_adapter_dry_run_dispatch_readiness_id != f"ladrdr:v1:sha256:{digest}":
        raise LiveAdapterDryRunDispatchReadinessError("LADRDR_PACKET_ID_MISMATCH")
    return candidate
