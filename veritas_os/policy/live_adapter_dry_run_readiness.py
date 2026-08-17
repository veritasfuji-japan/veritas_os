"""Deterministic readiness boundary before any live-adapter request.

The helpers in this module only verify and copy a canonical reference rehearsal.
They deliberately have no adapter, execution, persistence, or I/O capability.
"""

from __future__ import annotations

import hashlib
import json
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
from veritas_os.policy.reference_adapter_rehearsal import (
    RESULTS_DOMAIN as REHEARSAL_DOMAIN,
    CanonicalReferenceAdapterInMemoryRehearsalPacket,
    ReferenceAdapterRehearsalError,
    verify_reference_adapter_in_memory_rehearsal_packet,
)

FORMAT_VERSION = "canonical-live-adapter-dry-run-request-readiness/v1"
READINESS_MECHANISM = (
    "evaluate_live_adapter_dry_run_request_readiness_without_request/v1"
)
CHECKS_DOMAIN = "veritas.live-adapter-dry-run-readiness.checks/v1"
LOCAL_CHECKS_DOMAIN = "veritas.live-adapter-dry-run-readiness.local-checks/v1"
FUTURE_REQUIREMENTS_DOMAIN = (
    "veritas.live-adapter-dry-run-readiness.future-requirements/v1"
)
PACKET_DOMAIN = "veritas.live-adapter-dry-run-readiness.packet/v1"

CHECK_NAMES = (
    "source_reference_rehearsal_verified",
    "execution_intent_identity_verified",
    "adapter_contract_descriptor_preserved",
    "planned_steps_preserved",
    "fixture_results_preserved",
    "reference_rehearsal_results_preserved",
    "no_live_adapter_already_called",
    "no_webhook_already_called",
    "no_bind_already_invoked",
    "no_bind_receipt_created",
    "no_trustlog_written",
    "no_external_effect_observed",
    "live_dry_run_request_not_yet_created",
    "apply_still_forbidden",
    "postconditions_still_deferred",
    "rollback_still_deferred",
)
CHECK_LIMITATIONS = (
    "NOT_LIVE_ADAPTER_RESULT",
    "NOT_LIVE_STATE",
    "NOT_LIVE_AUTHORITY_REVALIDATION",
    "NOT_LIVE_CONSTRAINT_REVALIDATION",
    "NOT_RUNTIME_RISK_ACCEPTANCE",
    "NOT_BIND_AUTHORIZATION",
    "NOT_BIND_RECEIPT",
    "NOT_TRUSTLOG_WRITE",
    "NOT_OPERATION_COMMIT",
)
LOCAL_READINESS_CHECKS = {
    key: True
    for key in (
        "source_reference_rehearsal_verified", "execution_intent_hash_verified",
        "execution_intent_id_verified", "adapter_descriptor_preserved",
        "planned_steps_preserved", "fixture_results_preserved",
        "reference_rehearsal_results_preserved", "planned_step_digest_verified",
        "fixture_result_digest_verified", "reference_rehearsal_result_digest_verified",
        "readiness_checks_ordered", "readiness_checks_digest_verified",
        "evaluated_after_reference_rehearsal", "no_live_adapter_instance",
        "no_live_adapter_invocation", "no_webhook_invocation",
        "no_live_dry_run_request_created", "no_bind_invocation",
        "no_bind_receipt_created", "no_trustlog_write", "no_network",
        "no_filesystem", "no_credential_access", "no_external_effect", "no_apply",
        "no_postcondition_verification", "no_revert", "semantic_match_not_authority",
    )
}
FUTURE_REQUIREMENTS = {
    key: True
    for key in (
        "explicit_live_dry_run_request_packet_required", "live_adapter_descriptor_required",
        "live_adapter_endpoint_allowlist_required", "live_adapter_read_only_scope_required",
        "live_adapter_credentials_review_required", "live_adapter_timeout_required",
        "live_adapter_rate_limit_required", "live_adapter_idempotency_key_required",
        "live_adapter_no_apply_policy_required", "live_adapter_no_commit_policy_required",
        "live_adapter_no_trustlog_write_before_policy_required",
        "bind_receipt_still_deferred", "human_approval_still_required_when_policy_requires",
        "authority_evidence_still_required", "apply_still_forbidden",
        "verify_postconditions_still_deferred", "rollback_or_revert_still_deferred",
    )
}
SCOPE_LIMITATIONS = (
    "NOT_EXECUTION_AUTHORITY", "NOT_BIND_AUTHORIZATION", "NOT_BIND_RECEIPT",
    "NOT_BIND_INVOCATION", "NOT_LIVE_ADAPTER_INSTANCE", "NOT_LIVE_ADAPTER_INVOCATION",
    "NOT_LIVE_ADAPTER_RESULT", "NOT_LIVE_DRY_RUN_REQUEST", "NOT_WEBHOOK_INVOCATION",
    "NOT_EXTERNAL_EFFECT", "NOT_OPERATION_COMMIT", "NOT_TRUSTLOG_WRITE",
    "NOT_LIVE_STATE_CHECK", "NOT_RUNTIME_RISK_ACCEPTANCE",
    "NOT_LIVE_AUTHORITY_REVALIDATION", "NOT_LIVE_CONSTRAINT_REVALIDATION",
    "NOT_POSTCONDITION_VERIFICATION", "NOT_ROLLBACK_PROOF", "NOT_AUTHORITY_EVIDENCE",
    "NOT_HUMAN_APPROVAL",
)
SOURCE_SUMMARY_KEYS = (
    "reference_rehearsal_id", "reference_rehearsal_hash", "format_version",
    "rehearsal_mechanism", "rehearsed_at", "execution_intent_id",
    "execution_intent_hash", "reference_rehearsal_status",
    "ready_for_live_adapter_dry_run_request",
)
COPIED_FIELDS = (
    "adapter_contract_descriptor", "adapter_contract_id", "adapter_contract_hash",
    "adapter_contract_version", "execution_intent", "execution_intent_id",
    "execution_intent_hash", "source_adapter_dry_run_fixture_result_hash",
    "source_adapter_dry_run_plan_hash", "source_adapter_contract_selection_hash",
    "source_bind_preflight_adjudication_hash", "source_formation_hash",
    "source_readiness_hash", "source_eligibility_hash", "source_handoff_hash",
    "trusted_validation_context_hash", "validation_result_hash", "mapping_value_digest",
    "execution_intent_contract_version", "source_to_execution_intent_mapping",
    "field_mapping_proof", "required_field_presence", "source_decision_identity",
    "candidate_identity", "evidence_lineage", "replay_summary",
)


class LiveAdapterDryRunReadinessError(ValueError):
    """Stable fail-closed refusal for readiness packet processing."""


class LiveAdapterDryRunReadinessCheck(BaseModel):
    """Immutable evidence descriptor for one local readiness assertion."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    readiness_check_id: str = Field(pattern=r"^live-adapter-dry-run-readiness-check:v1:[1-9][0-9]*:[a-z0-9-]+$")
    ordinal: int = Field(ge=1, le=16)
    check_name: Literal[*CHECK_NAMES]
    check_mode: Literal["deterministic_local_readiness_only"]
    passed: Literal[True]
    evidence_ref: str = Field(min_length=1)
    live_observation_used: Literal[False]
    network_used: Literal[False]
    filesystem_used: Literal[False]
    credential_accessed: Literal[False]
    adapter_instance_created: Literal[False]
    adapter_method_called: Literal[False]
    bind_invoked: Literal[False]
    bind_receipt_created: Literal[False]
    trustlog_written: Literal[False]
    external_effect_used: Literal[False]
    check_scope_limitations: tuple[str, ...]


class CanonicalLiveAdapterDryRunRequestReadinessPacket(BaseModel):
    """Strict immutable content-addressed readiness-only packet."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    format_version: Literal[FORMAT_VERSION]
    live_adapter_dry_run_readiness_id: str = Field(pattern=r"^ladr:v1:sha256:[0-9a-f]{64}$")
    live_adapter_dry_run_readiness_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    readiness_mechanism: Literal[READINESS_MECHANISM]
    readiness_evaluated_at: str
    source_reference_rehearsal: dict[str, Any]
    source_reference_rehearsal_hash: str
    source_reference_rehearsal_packet: dict[str, Any]
    adapter_contract_descriptor: dict[str, Any]
    adapter_contract_id: str
    adapter_contract_hash: str
    adapter_contract_version: str
    execution_intent: dict[str, Any]
    execution_intent_id: str
    execution_intent_hash: str
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
    live_adapter_dry_run_request_readiness_status: Literal["LIVE_ADAPTER_DRY_RUN_REQUEST_READY_BUT_NOT_REQUESTED"]
    ready_for_live_adapter_dry_run_request_packet: Literal[True]
    fail_closed: Literal[False]
    planned_steps: tuple[dict[str, Any], ...]
    planned_step_digest: str
    fixture_step_results: tuple[dict[str, Any], ...]
    fixture_result_digest: str
    reference_rehearsal_results: tuple[dict[str, Any], ...]
    reference_rehearsal_result_digest: str
    readiness_checks: tuple[LiveAdapterDryRunReadinessCheck, ...]
    readiness_check_digest: str
    local_readiness_checks: dict[str, bool]
    future_live_adapter_dry_run_request_packet_requirements: dict[str, bool]
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
            raise LiveAdapterDryRunReadinessError("LADR_PACKET_INVALID")
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise LiveAdapterDryRunReadinessError("LADR_EVALUATED_AT_INVALID")
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _json_value(item) for key, item in value.items()}
    raise LiveAdapterDryRunReadinessError("LADR_PACKET_INVALID")


def _aware(value: Any, code: str) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise LiveAdapterDryRunReadinessError(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LiveAdapterDryRunReadinessError(code)
    return parsed


def _digest(domain: str, value: Any) -> str:
    encoded = json.dumps(
        {"domain": domain, "value": _json_value(value)}, allow_nan=False,
        ensure_ascii=False, separators=(",", ":"), sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _packet_hash(raw: dict[str, Any]) -> str:
    return _digest(PACKET_DOMAIN, {key: value for key, value in raw.items() if key not in {"live_adapter_dry_run_readiness_id", "live_adapter_dry_run_readiness_hash"}})


def _source(value: Any) -> CanonicalReferenceAdapterInMemoryRehearsalPacket:
    try:
        return verify_reference_adapter_in_memory_rehearsal_packet(value)
    except (ReferenceAdapterRehearsalError, TypeError, ValueError) as exc:
        raise LiveAdapterDryRunReadinessError("LADR_REFERENCE_REHEARSAL_INVALID") from exc


def _intent(raw: dict[str, Any]) -> ExecutionIntent:
    try:
        intent = ExecutionIntent(**raw)
        canonical_execution_intent_json(intent)
    except (TypeError, ValueError) as exc:
        raise LiveAdapterDryRunReadinessError("LADR_PACKET_INVALID") from exc
    if intent.to_dict() != raw:
        raise LiveAdapterDryRunReadinessError("LADR_PACKET_INVALID")
    return intent


def _checks(source_hash: str) -> list[dict[str, Any]]:
    return [
        {
            "readiness_check_id": f"live-adapter-dry-run-readiness-check:v1:{ordinal}:{name.replace('_', '-')}",
            "ordinal": ordinal, "check_name": name,
            "check_mode": "deterministic_local_readiness_only", "passed": True,
            "evidence_ref": f"reference_rehearsal_hash:{source_hash}:{name}",
            "live_observation_used": False, "network_used": False,
            "filesystem_used": False, "credential_accessed": False,
            "adapter_instance_created": False, "adapter_method_called": False,
            "bind_invoked": False, "bind_receipt_created": False,
            "trustlog_written": False, "external_effect_used": False,
            "check_scope_limitations": CHECK_LIMITATIONS,
        }
        for ordinal, name in enumerate(CHECK_NAMES, 1)
    ]


def _validate_source(source: CanonicalReferenceAdapterInMemoryRehearsalPacket) -> ExecutionIntent:
    intent = _intent(source.execution_intent)
    if intent.execution_intent_id != source.execution_intent_id:
        raise LiveAdapterDryRunReadinessError("LADR_EXECUTION_INTENT_ID_MISMATCH")
    if hash_execution_intent(intent) != source.execution_intent_hash:
        raise LiveAdapterDryRunReadinessError("LADR_EXECUTION_INTENT_HASH_MISMATCH")
    descriptor = source.adapter_contract_descriptor
    if descriptor.get("target_system") != intent.target_system or descriptor.get("target_resource_scope") != intent.target_resource:
        raise LiveAdapterDryRunReadinessError("LADR_DESCRIPTOR_MISMATCH")
    for result in source.reference_rehearsal_results:
        if any((result.live_adapter_instance_created, result.live_adapter_method_called,
                result.network_used, result.filesystem_used, result.external_effect_used,
                result.bind_invoked, result.bind_receipt_created, result.trustlog_written)):
            raise LiveAdapterDryRunReadinessError("LADR_EXTERNAL_EFFECT_FORBIDDEN")
    return intent


def build_live_adapter_dry_run_request_readiness_packet(
    reference_rehearsal_packet: Any,
    readiness_evaluated_at: datetime,
) -> CanonicalLiveAdapterDryRunRequestReadinessPacket:
    """Build readiness evidence while stopping before any live request."""
    evaluated = _aware(readiness_evaluated_at, "LADR_EVALUATED_AT_INVALID")
    source = _source(_json_value(reference_rehearsal_packet))
    _validate_source(source)
    if evaluated < _aware(source.rehearsed_at, "LADR_REFERENCE_REHEARSAL_INVALID"):
        raise LiveAdapterDryRunReadinessError("LADR_EVALUATED_BEFORE_REHEARSAL")
    source_raw = source.model_dump(mode="json")
    steps = _json_value(source.planned_steps)
    fixtures = _json_value(source.fixture_step_results)
    results = _json_value(source.reference_rehearsal_results)
    checks = _checks(source.reference_rehearsal_hash)
    raw = {
        "format_version": FORMAT_VERSION, "readiness_mechanism": READINESS_MECHANISM,
        "readiness_evaluated_at": evaluated.isoformat(),
        "source_reference_rehearsal": {key: source_raw[key] for key in SOURCE_SUMMARY_KEYS},
        "source_reference_rehearsal_hash": source.reference_rehearsal_hash,
        "source_reference_rehearsal_packet": source_raw,
        **{key: source_raw[key] for key in COPIED_FIELDS},
        "live_adapter_dry_run_request_readiness_status": "LIVE_ADAPTER_DRY_RUN_REQUEST_READY_BUT_NOT_REQUESTED",
        "ready_for_live_adapter_dry_run_request_packet": True, "fail_closed": False,
        "planned_steps": steps, "planned_step_digest": source.planned_step_digest,
        "fixture_step_results": fixtures, "fixture_result_digest": source.fixture_result_digest,
        "reference_rehearsal_results": results,
        "reference_rehearsal_result_digest": source.reference_rehearsal_result_digest,
        "readiness_checks": checks, "readiness_check_digest": _digest(CHECKS_DOMAIN, checks),
        "local_readiness_checks": LOCAL_READINESS_CHECKS,
        "future_live_adapter_dry_run_request_packet_requirements": FUTURE_REQUIREMENTS,
        "scope_limitations": SCOPE_LIMITATIONS,
    }
    digest = _packet_hash(raw)
    raw.update(live_adapter_dry_run_readiness_hash=digest,
               live_adapter_dry_run_readiness_id=f"ladr:v1:sha256:{digest}")
    return verify_live_adapter_dry_run_request_readiness_packet(raw)


def verify_live_adapter_dry_run_request_readiness_packet(
    packet: Any,
) -> CanonicalLiveAdapterDryRunRequestReadinessPacket:
    """Independently reverify every readiness and source binding."""
    try:
        value = packet.model_dump(mode="json") if isinstance(packet, BaseModel) else _json_value(packet)
        candidate = CanonicalLiveAdapterDryRunRequestReadinessPacket.model_validate(value)
    except (ValidationError, LiveAdapterDryRunReadinessError, TypeError) as exc:
        raise LiveAdapterDryRunReadinessError("LADR_PACKET_INVALID") from exc
    raw = candidate.model_dump(mode="json")
    source = _source(candidate.source_reference_rehearsal_packet)
    source_raw = source.model_dump(mode="json")
    _validate_source(source)
    if set(candidate.source_reference_rehearsal) != set(SOURCE_SUMMARY_KEYS) or candidate.source_reference_rehearsal != {key: source_raw[key] for key in SOURCE_SUMMARY_KEYS} or candidate.source_reference_rehearsal_hash != source.reference_rehearsal_hash:
        raise LiveAdapterDryRunReadinessError("LADR_SOURCE_SUMMARY_MISMATCH")
    if _aware(candidate.readiness_evaluated_at, "LADR_EVALUATED_AT_INVALID") < _aware(source.rehearsed_at, "LADR_REFERENCE_REHEARSAL_INVALID"):
        raise LiveAdapterDryRunReadinessError("LADR_EVALUATED_BEFORE_REHEARSAL")
    if any(_json_value(getattr(candidate, key)) != _json_value(getattr(source, key)) for key in COPIED_FIELDS):
        raise LiveAdapterDryRunReadinessError("LADR_SOURCE_SUMMARY_MISMATCH")
    steps, fixtures, results = (_json_value(source.planned_steps), _json_value(source.fixture_step_results), _json_value(source.reference_rehearsal_results))
    if _json_value(candidate.planned_steps) != steps or candidate.planned_step_digest != source.planned_step_digest or candidate.planned_step_digest != source_digest(STEPS_DOMAIN, steps):
        raise LiveAdapterDryRunReadinessError("LADR_PLANNED_STEPS_MISMATCH")
    if _json_value(candidate.fixture_step_results) != fixtures or candidate.fixture_result_digest != source.fixture_result_digest or candidate.fixture_result_digest != _digest(FIXTURE_DOMAIN, fixtures):
        raise LiveAdapterDryRunReadinessError("LADR_FIXTURE_RESULTS_MISMATCH")
    if _json_value(candidate.reference_rehearsal_results) != results or candidate.reference_rehearsal_result_digest != source.reference_rehearsal_result_digest or candidate.reference_rehearsal_result_digest != _digest(REHEARSAL_DOMAIN, results):
        raise LiveAdapterDryRunReadinessError("LADR_REFERENCE_REHEARSAL_RESULTS_MISMATCH")
    checks = _json_value(_checks(source.reference_rehearsal_hash))
    if _json_value(candidate.readiness_checks) != checks:
        raise LiveAdapterDryRunReadinessError("LADR_READINESS_CHECKS_INVALID")
    if candidate.readiness_check_digest != _digest(CHECKS_DOMAIN, checks):
        raise LiveAdapterDryRunReadinessError("LADR_READINESS_CHECK_DIGEST_MISMATCH")
    if candidate.local_readiness_checks != LOCAL_READINESS_CHECKS:
        raise LiveAdapterDryRunReadinessError("LADR_LOCAL_CHECKS_MISMATCH")
    if candidate.future_live_adapter_dry_run_request_packet_requirements != FUTURE_REQUIREMENTS:
        raise LiveAdapterDryRunReadinessError("LADR_FUTURE_REQUIREMENTS_MISMATCH")
    _digest(LOCAL_CHECKS_DOMAIN, candidate.local_readiness_checks)
    _digest(FUTURE_REQUIREMENTS_DOMAIN, candidate.future_live_adapter_dry_run_request_packet_requirements)
    if candidate.scope_limitations != SCOPE_LIMITATIONS:
        raise LiveAdapterDryRunReadinessError("LADR_SCOPE_LIMITATIONS_MISSING")
    digest = _packet_hash(raw)
    if candidate.live_adapter_dry_run_readiness_hash != digest:
        raise LiveAdapterDryRunReadinessError("LADR_PACKET_HASH_MISMATCH")
    if candidate.live_adapter_dry_run_readiness_id != f"ladr:v1:sha256:{digest}":
        raise LiveAdapterDryRunReadinessError("LADR_PACKET_ID_MISMATCH")
    return candidate
