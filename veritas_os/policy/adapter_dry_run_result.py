"""Bind an adapter dry-run plan to inert caller-supplied fixture results.

The module is a deterministic, local data boundary.  It neither creates nor
invokes adapters, invokes Bind, constructs receipts, writes TrustLog, nor
performs I/O.  A fixture result is explicitly not a live adapter result.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from veritas_os.policy.adapter_dry_run_plan import (
    AdapterDryRunPlanError,
    CanonicalAdapterDryRunPlanPacket,
    STEPS_DOMAIN,
    _digest as _plan_digest,
    verify_adapter_dry_run_plan_packet,
)
from veritas_os.policy.bind_artifacts import (
    ExecutionIntent,
    canonical_execution_intent_json,
    hash_execution_intent,
)

FORMAT_VERSION = "canonical-adapter-dry-run-fixture-result/v1"
RESULT_MECHANISM = "record_adapter_dry_run_fixture_result_without_invocation/v1"
VALUE_DOMAIN = "veritas.adapter-dry-run-fixture-result.value/v1"
RESULTS_DOMAIN = "veritas.adapter-dry-run-fixture-result.results/v1"
LOCAL_CHECKS_DOMAIN = "veritas.adapter-dry-run-fixture-result.local-checks/v1"
FUTURE_REQUIREMENTS_DOMAIN = (
    "veritas.adapter-dry-run-fixture-result.future-requirements/v1"
)
PACKET_DOMAIN = "veritas.adapter-dry-run-fixture-result.packet/v1"
SOURCE_SUMMARY_KEYS = (
    "adapter_dry_run_plan_id",
    "adapter_dry_run_plan_hash",
    "format_version",
    "plan_mechanism",
    "planned_at",
    "execution_intent_id",
    "execution_intent_hash",
    "dry_run_plan_status",
    "ready_for_adapter_dry_run_execution",
)
RESULT_LIMITATIONS = (
    "NOT_LIVE_RESULT",
    "NOT_ADAPTER_INVOCATION",
    "NOT_LIVE_STATE",
    "NOT_AUTHORITY_REVALIDATION",
    "NOT_CONSTRAINT_REVALIDATION",
    "NOT_RUNTIME_RISK_ACCEPTANCE",
    "NOT_BIND_AUTHORIZATION",
    "NOT_BIND_RECEIPT",
    "NOT_TRUSTLOG_WRITE",
    "NOT_OPERATION_COMMIT",
)
LOCAL_RESULT_CHECKS = {
    key: True
    for key in (
        "adapter_dry_run_plan_verified",
        "execution_intent_hash_verified",
        "execution_intent_id_verified",
        "adapter_descriptor_preserved",
        "planned_steps_preserved",
        "planned_step_digest_verified",
        "fixture_results_ordered",
        "fixture_results_match_planned_steps",
        "fixture_values_digest_verified",
        "no_apply_result",
        "no_postcondition_result",
        "no_revert_result",
        "resulted_after_adapter_dry_run_plan",
        "no_adapter_instance",
        "no_adapter_invocation",
        "no_bind_invocation",
        "no_bind_receipt_created",
        "no_trustlog_write",
        "no_network",
        "no_filesystem",
        "no_external_effect",
        "no_live_state_claim",
        "no_authority_revalidation_claim",
        "no_constraint_revalidation_claim",
        "no_runtime_risk_acceptance_claim",
    )
}
FUTURE_REFERENCE_ADAPTER_REHEARSAL_REQUIREMENTS = {
    key: True
    for key in (
        "adapter_instance_required",
        "describe_target_call_required",
        "idempotency_key_call_required",
        "snapshot_call_required",
        "state_fingerprint_call_required",
        "authority_revalidation_call_required",
        "constraint_validation_call_required",
        "runtime_risk_assessment_call_required",
        "live_result_packet_required",
        "fixture_result_must_not_be_treated_as_live",
        "trustlog_policy_still_deferred",
        "bind_receipt_still_deferred",
        "apply_still_forbidden",
    )
}
SCOPE_LIMITATIONS = (
    "NOT_EXECUTION_AUTHORITY",
    "NOT_BIND_AUTHORIZATION",
    "NOT_BIND_RECEIPT",
    "NOT_BIND_INVOCATION",
    "NOT_ADAPTER_INSTANCE",
    "NOT_ADAPTER_INVOCATION",
    "NOT_ADAPTER_DRY_RUN_EXECUTION",
    "NOT_LIVE_ADAPTER_RESULT",
    "NOT_EXTERNAL_EFFECT",
    "NOT_OPERATION_COMMIT",
    "NOT_TRUSTLOG_WRITE",
    "NOT_LIVE_STATE_CHECK",
    "NOT_RUNTIME_RISK_ACCEPTANCE",
    "NOT_AUTHORITY_REVALIDATION",
    "NOT_CONSTRAINT_REVALIDATION",
    "NOT_POSTCONDITION_VERIFICATION",
    "NOT_ROLLBACK_PROOF",
    "NOT_AUTHORITY_EVIDENCE",
    "NOT_HUMAN_APPROVAL",
)
PLANNED_METHODS = (
    "describe_target",
    "build_idempotency_key",
    "snapshot",
    "fingerprint_state",
    "validate_authority",
    "validate_constraints",
    "assess_runtime_risk",
)
FIXTURE_VALUE_SUMMARY = {
    "status": "FIXTURE_RESULT_AVAILABLE",
    "semantic": "no_effect_fixture",
    "live_system_claim": False,
}


class AdapterDryRunFixtureResultError(ValueError):
    """Stable fail-closed refusal for fixture-result packet processing."""


class AdapterDryRunFixtureStepResult(BaseModel):
    """Immutable pure-data result associated with one planned dry-run step."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    step_result_id: str = Field(
        pattern=r"^dry-run-fixture-result:v1:[1-9][0-9]*:[a-z0-9-]+$"
    )
    planned_step_id: str
    ordinal: int = Field(ge=1)
    planned_adapter_method: Literal[
        "describe_target",
        "build_idempotency_key",
        "snapshot",
        "fingerprint_state",
        "validate_authority",
        "validate_constraints",
        "assess_runtime_risk",
    ]
    result_mode: Literal["fixture_no_effect"]
    result_source_kind: Literal[
        "in_memory_fixture",
        "unit_test_fixture",
        "operator_supplied_fixture",
    ]
    live_observed: Literal[False]
    adapter_instance_created: Literal[False]
    adapter_method_called: Literal[False]
    network_used: Literal[False]
    filesystem_used: Literal[False]
    external_effect_used: Literal[False]
    trustlog_written: Literal[False]
    bind_receipt_created: Literal[False]
    fixture_input_ref: str = Field(min_length=1)
    fixture_value_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    fixture_value_summary: dict[str, Any]
    matched_expected_output_ref: str
    refusal_if_missing_later: str
    result_scope_limitations: tuple[str, ...]


class CanonicalAdapterDryRunFixtureResultPacket(BaseModel):
    """Strict immutable binding of a verified plan to inert fixture data."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    format_version: Literal["canonical-adapter-dry-run-fixture-result/v1"]
    adapter_dry_run_result_id: str = Field(
        pattern=r"^adr:v1:sha256:[0-9a-f]{64}$"
    )
    adapter_dry_run_result_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_mechanism: Literal[
        "record_adapter_dry_run_fixture_result_without_invocation/v1"
    ]
    resulted_at: str
    source_adapter_dry_run_plan: dict[str, Any]
    source_adapter_dry_run_plan_hash: str
    source_adapter_dry_run_plan_packet: dict[str, Any]
    adapter_contract_descriptor: dict[str, Any]
    adapter_contract_id: str
    adapter_contract_hash: str
    adapter_contract_version: Literal["bind-adapter-contract/v1"]
    execution_intent: dict[str, Any]
    execution_intent_id: str
    execution_intent_hash: str
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
    dry_run_fixture_result_status: Literal[
        "ADAPTER_DRY_RUN_FIXTURE_RESULT_RECORDED_NO_EFFECT"
    ]
    ready_for_reference_adapter_rehearsal: Literal[True]
    fail_closed: Literal[False]
    planned_steps: tuple[dict[str, Any], ...]
    planned_step_digest: str
    fixture_step_results: tuple[AdapterDryRunFixtureStepResult, ...]
    fixture_result_digest: str
    local_result_checks: dict[str, bool]
    future_reference_adapter_rehearsal_requirements: dict[str, bool]
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
            raise AdapterDryRunFixtureResultError("ADR_PACKET_INVALID")
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise AdapterDryRunFixtureResultError("ADR_RESULTED_AT_INVALID")
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _json_value(item) for key, item in value.items()}
    raise AdapterDryRunFixtureResultError("ADR_PACKET_INVALID")


def _aware(value: Any, code: str) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise AdapterDryRunFixtureResultError(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AdapterDryRunFixtureResultError(code)
    return parsed


def _digest(domain: str, value: Any) -> str:
    encoded = json.dumps(
        {"domain": domain, "value": _json_value(value)},
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _packet_hash(raw: dict[str, Any]) -> str:
    return _digest(
        PACKET_DOMAIN,
        {
            key: value
            for key, value in raw.items()
            if key
            not in {"adapter_dry_run_result_id", "adapter_dry_run_result_hash"}
        },
    )


def _verified_plan(value: Any) -> CanonicalAdapterDryRunPlanPacket:
    try:
        return verify_adapter_dry_run_plan_packet(value)
    except (AdapterDryRunPlanError, TypeError, ValueError) as exc:
        raise AdapterDryRunFixtureResultError("ADR_DRY_RUN_PLAN_INVALID") from exc


def _intent(raw: dict[str, Any]) -> ExecutionIntent:
    try:
        intent = ExecutionIntent(**raw)
        canonical_execution_intent_json(intent)
    except (TypeError, ValueError) as exc:
        raise AdapterDryRunFixtureResultError("ADR_PACKET_INVALID") from exc
    if intent.to_dict() != raw:
        raise AdapterDryRunFixtureResultError("ADR_PACKET_INVALID")
    return intent


def _fixture_results(
    supplied: Any,
    planned_steps: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    raw_results = _json_value(supplied)
    if not isinstance(raw_results, list) or len(raw_results) != len(planned_steps):
        raise AdapterDryRunFixtureResultError("ADR_FIXTURE_RESULTS_INVALID")
    results = []
    for raw, step in zip(raw_results, planned_steps, strict=True):
        if not isinstance(raw, dict):
            raise AdapterDryRunFixtureResultError("ADR_FIXTURE_RESULTS_INVALID")
        value = dict(raw)
        if value.get("fixture_value_summary") != FIXTURE_VALUE_SUMMARY:
            raise AdapterDryRunFixtureResultError("ADR_LIVE_RESULT_FORBIDDEN")
        expected_digest = _digest(VALUE_DOMAIN, value.get("fixture_value_summary"))
        supplied_digest = value.get("fixture_value_digest")
        if supplied_digest is not None and supplied_digest != expected_digest:
            raise AdapterDryRunFixtureResultError("ADR_FIXTURE_RESULTS_INVALID")
        value["fixture_value_digest"] = expected_digest
        try:
            result = AdapterDryRunFixtureStepResult.model_validate(value)
        except ValidationError as exc:
            raise AdapterDryRunFixtureResultError(
                "ADR_FIXTURE_RESULTS_INVALID"
            ) from exc
        expected_id = (
            f"dry-run-fixture-result:v1:{step['ordinal']}:"
            f"{step['planned_adapter_method'].replace('_', '-')}"
        )
        if (
            result.step_result_id != expected_id
            or result.planned_step_id != step["step_id"]
            or result.ordinal != step["ordinal"]
            or result.planned_adapter_method != step["planned_adapter_method"]
            or result.matched_expected_output_ref != step["expected_output_ref"]
            or result.refusal_if_missing_later != step["refusal_if_missing_later"]
            or result.result_scope_limitations != RESULT_LIMITATIONS
        ):
            raise AdapterDryRunFixtureResultError("ADR_FIXTURE_RESULTS_INVALID")
        results.append(result.model_dump(mode="json"))
    if [item["planned_adapter_method"] for item in results] != list(
        PLANNED_METHODS
    ):
        raise AdapterDryRunFixtureResultError("ADR_FORBIDDEN_EXECUTION_RESULT")
    return results


def build_adapter_dry_run_fixture_result_packet(
    adapter_dry_run_plan_packet: Any,
    fixture_step_results: Any,
    resulted_at: datetime,
) -> CanonicalAdapterDryRunFixtureResultPacket:
    """Build an inert fixture-result binding from an independently verified plan."""
    resulted = _aware(resulted_at, "ADR_RESULTED_AT_INVALID")
    source_packet = _verified_plan(_json_value(adapter_dry_run_plan_packet))
    source = source_packet.model_dump(mode="json")
    if resulted < _aware(source_packet.planned_at, "ADR_DRY_RUN_PLAN_INVALID"):
        raise AdapterDryRunFixtureResultError("ADR_RESULTED_BEFORE_PLAN")
    intent = _intent(source_packet.execution_intent)
    if intent.execution_intent_id != source_packet.execution_intent_id:
        raise AdapterDryRunFixtureResultError("ADR_EXECUTION_INTENT_ID_MISMATCH")
    if hash_execution_intent(intent) != source_packet.execution_intent_hash:
        raise AdapterDryRunFixtureResultError("ADR_EXECUTION_INTENT_HASH_MISMATCH")
    descriptor = source_packet.adapter_contract_descriptor
    if (
        descriptor["target_system"] != intent.target_system
        or descriptor["target_resource_scope"] != intent.target_resource
    ):
        raise AdapterDryRunFixtureResultError("ADR_DESCRIPTOR_MISMATCH")
    steps = [step.model_dump(mode="json") for step in source_packet.planned_steps]
    if source_packet.planned_step_digest != _plan_digest(STEPS_DOMAIN, steps):
        raise AdapterDryRunFixtureResultError("ADR_PLANNED_STEP_DIGEST_MISMATCH")
    results = _fixture_results(fixture_step_results, steps)
    copied = (
        "adapter_contract_descriptor",
        "adapter_contract_id",
        "adapter_contract_hash",
        "adapter_contract_version",
        "execution_intent",
        "execution_intent_id",
        "execution_intent_hash",
        "source_adapter_contract_selection_hash",
        "source_bind_preflight_adjudication_hash",
        "source_formation_hash",
        "source_readiness_hash",
        "source_eligibility_hash",
        "source_handoff_hash",
        "trusted_validation_context_hash",
        "validation_result_hash",
        "mapping_value_digest",
        "execution_intent_contract_version",
        "source_to_execution_intent_mapping",
        "field_mapping_proof",
        "required_field_presence",
        "source_decision_identity",
        "candidate_identity",
        "evidence_lineage",
        "replay_summary",
    )
    raw = {
        "format_version": FORMAT_VERSION,
        "result_mechanism": RESULT_MECHANISM,
        "resulted_at": resulted.isoformat(),
        "source_adapter_dry_run_plan": {
            key: source[key] for key in SOURCE_SUMMARY_KEYS
        },
        "source_adapter_dry_run_plan_hash": source_packet.adapter_dry_run_plan_hash,
        "source_adapter_dry_run_plan_packet": source,
        **{key: source[key] for key in copied},
        "dry_run_fixture_result_status": (
            "ADAPTER_DRY_RUN_FIXTURE_RESULT_RECORDED_NO_EFFECT"
        ),
        "ready_for_reference_adapter_rehearsal": True,
        "fail_closed": False,
        "planned_steps": steps,
        "planned_step_digest": source_packet.planned_step_digest,
        "fixture_step_results": results,
        "fixture_result_digest": _digest(RESULTS_DOMAIN, results),
        "local_result_checks": LOCAL_RESULT_CHECKS,
        "future_reference_adapter_rehearsal_requirements": (
            FUTURE_REFERENCE_ADAPTER_REHEARSAL_REQUIREMENTS
        ),
        "scope_limitations": SCOPE_LIMITATIONS,
    }
    digest = _packet_hash(raw)
    raw.update(
        adapter_dry_run_result_hash=digest,
        adapter_dry_run_result_id=f"adr:v1:sha256:{digest}",
    )
    return verify_adapter_dry_run_fixture_result_packet(raw)


def verify_adapter_dry_run_fixture_result_packet(
    packet: Any,
) -> CanonicalAdapterDryRunFixtureResultPacket:
    """Dump and independently verify every source and fixture-result binding."""
    try:
        value = (
            packet.model_dump(mode="json")
            if isinstance(packet, BaseModel)
            else _json_value(packet)
        )
        candidate = CanonicalAdapterDryRunFixtureResultPacket.model_validate(value)
    except (ValidationError, AdapterDryRunFixtureResultError, TypeError) as exc:
        raise AdapterDryRunFixtureResultError("ADR_PACKET_INVALID") from exc
    raw = candidate.model_dump(mode="json")
    source_packet = _verified_plan(candidate.source_adapter_dry_run_plan_packet)
    source = source_packet.model_dump(mode="json")
    if (
        set(candidate.source_adapter_dry_run_plan) != set(SOURCE_SUMMARY_KEYS)
        or candidate.source_adapter_dry_run_plan
        != {key: source[key] for key in SOURCE_SUMMARY_KEYS}
        or candidate.source_adapter_dry_run_plan_hash
        != source_packet.adapter_dry_run_plan_hash
    ):
        raise AdapterDryRunFixtureResultError("ADR_SOURCE_SUMMARY_MISMATCH")
    if _aware(candidate.resulted_at, "ADR_RESULTED_AT_INVALID") < _aware(
        source_packet.planned_at, "ADR_DRY_RUN_PLAN_INVALID"
    ):
        raise AdapterDryRunFixtureResultError("ADR_RESULTED_BEFORE_PLAN")
    copied = (
        "adapter_contract_descriptor",
        "adapter_contract_id",
        "adapter_contract_hash",
        "adapter_contract_version",
        "execution_intent",
        "execution_intent_id",
        "execution_intent_hash",
        "source_adapter_contract_selection_hash",
        "source_bind_preflight_adjudication_hash",
        "source_formation_hash",
        "source_readiness_hash",
        "source_eligibility_hash",
        "source_handoff_hash",
        "trusted_validation_context_hash",
        "validation_result_hash",
        "mapping_value_digest",
        "execution_intent_contract_version",
        "source_to_execution_intent_mapping",
        "field_mapping_proof",
        "required_field_presence",
        "source_decision_identity",
        "candidate_identity",
        "evidence_lineage",
        "replay_summary",
    )
    if any(getattr(candidate, key) != getattr(source_packet, key) for key in copied):
        raise AdapterDryRunFixtureResultError("ADR_SOURCE_SUMMARY_MISMATCH")
    intent = _intent(candidate.execution_intent)
    if intent.execution_intent_id != candidate.execution_intent_id:
        raise AdapterDryRunFixtureResultError("ADR_EXECUTION_INTENT_ID_MISMATCH")
    if hash_execution_intent(intent) != candidate.execution_intent_hash:
        raise AdapterDryRunFixtureResultError("ADR_EXECUTION_INTENT_HASH_MISMATCH")
    descriptor = candidate.adapter_contract_descriptor
    if (
        descriptor["target_system"] != intent.target_system
        or descriptor["target_resource_scope"] != intent.target_resource
    ):
        raise AdapterDryRunFixtureResultError("ADR_DESCRIPTOR_MISMATCH")
    source_steps = [
        step.model_dump(mode="json") for step in source_packet.planned_steps
    ]
    if list(candidate.planned_steps) != source_steps:
        raise AdapterDryRunFixtureResultError("ADR_PLANNED_STEPS_MISMATCH")
    if (
        candidate.planned_step_digest != source_packet.planned_step_digest
        or candidate.planned_step_digest != _plan_digest(STEPS_DOMAIN, source_steps)
    ):
        raise AdapterDryRunFixtureResultError("ADR_PLANNED_STEP_DIGEST_MISMATCH")
    results = _fixture_results(
        [item.model_dump(mode="json") for item in candidate.fixture_step_results],
        source_steps,
    )
    if candidate.fixture_result_digest != _digest(RESULTS_DOMAIN, results):
        raise AdapterDryRunFixtureResultError("ADR_FIXTURE_RESULT_DIGEST_MISMATCH")
    if candidate.local_result_checks != LOCAL_RESULT_CHECKS:
        raise AdapterDryRunFixtureResultError("ADR_LOCAL_CHECKS_MISMATCH")
    if (
        candidate.future_reference_adapter_rehearsal_requirements
        != FUTURE_REFERENCE_ADAPTER_REHEARSAL_REQUIREMENTS
    ):
        raise AdapterDryRunFixtureResultError("ADR_FUTURE_REQUIREMENTS_MISMATCH")
    _digest(LOCAL_CHECKS_DOMAIN, candidate.local_result_checks)
    _digest(
        FUTURE_REQUIREMENTS_DOMAIN,
        candidate.future_reference_adapter_rehearsal_requirements,
    )
    if candidate.scope_limitations != SCOPE_LIMITATIONS:
        raise AdapterDryRunFixtureResultError("ADR_SCOPE_LIMITATIONS_MISSING")
    digest = _packet_hash(raw)
    if candidate.adapter_dry_run_result_hash != digest:
        raise AdapterDryRunFixtureResultError("ADR_PACKET_HASH_MISMATCH")
    if candidate.adapter_dry_run_result_id != f"adr:v1:sha256:{digest}":
        raise AdapterDryRunFixtureResultError("ADR_PACKET_ID_MISMATCH")
    return candidate
