"""Plan a future adapter dry run without creating or invoking an adapter.

This module is deliberately pure data: it verifies an exact adapter contract
selection and records seven inert method-name descriptors.  It performs no I/O,
Bind activity, adapter activity, receipt construction, or TrustLog write.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from veritas_os.policy.bind_adapter_contract_selection import (
    BindAdapterContractSelectionError,
    CanonicalBindAdapterContractSelectionPacket,
    verify_bind_adapter_contract_selection_packet,
)
from veritas_os.policy.bind_artifacts import (
    ExecutionIntent,
    canonical_execution_intent_json,
    hash_execution_intent,
)

FORMAT_VERSION = "canonical-adapter-dry-run-plan/v1"
PLAN_MECHANISM = "plan_adapter_dry_run_without_invocation/v1"
STEPS_DOMAIN = "veritas.adapter-dry-run-plan.steps/v1"
LOCAL_CHECKS_DOMAIN = "veritas.adapter-dry-run-plan.local-checks/v1"
FUTURE_REQUIREMENTS_DOMAIN = "veritas.adapter-dry-run-plan.future-requirements/v1"
PACKET_DOMAIN = "veritas.adapter-dry-run-plan.packet/v1"
SOURCE_SUMMARY_KEYS = (
    "adapter_contract_selection_id", "adapter_contract_selection_hash",
    "format_version", "selection_mechanism", "selected_at",
    "adapter_contract_id", "adapter_contract_hash", "execution_intent_id",
    "execution_intent_hash", "selection_status", "ready_for_adapter_dry_run",
)
STEP_LIMITATIONS = (
    "NOT_EXECUTED", "NOT_ADAPTER_INVOCATION", "NOT_LIVE_STATE",
    "NOT_AUTHORITY_REVALIDATION", "NOT_CONSTRAINT_REVALIDATION",
    "NOT_RUNTIME_RISK_ACCEPTANCE", "NOT_BIND_AUTHORIZATION",
    "NOT_BIND_RECEIPT", "NOT_TRUSTLOG_WRITE",
)
EFFECT_POLICY = {
    "adapter_instance_required_later": True,
    "adapter_method_call_allowed_now": False,
    "network_allowed": False,
    "filesystem_allowed": False,
    "external_effect_allowed": False,
    "trustlog_write_allowed": False,
    "bind_receipt_allowed": False,
}
STEP_SPECS = (
    ("prepare", "describe_target", "planned_target_description_ref",
     "DRY_RUN_TARGET_DESCRIPTION_MISSING"),
    ("prepare", "build_idempotency_key", "planned_idempotency_key_ref",
     "DRY_RUN_IDEMPOTENCY_KEY_MISSING"),
    ("observe", "snapshot", "planned_snapshot_ref",
     "DRY_RUN_SNAPSHOT_MISSING"),
    ("observe", "fingerprint_state", "planned_state_fingerprint_ref",
     "DRY_RUN_STATE_FINGERPRINT_MISSING"),
    ("validate", "validate_authority", "planned_authority_signal_ref",
     "DRY_RUN_AUTHORITY_SIGNAL_MISSING"),
    ("validate", "validate_constraints", "planned_constraint_signal_ref",
     "DRY_RUN_CONSTRAINT_SIGNAL_MISSING"),
    ("assess", "assess_runtime_risk", "planned_runtime_risk_signal_ref",
     "DRY_RUN_RUNTIME_RISK_SIGNAL_MISSING"),
)
LOCAL_PLAN_CHECKS = {key: True for key in (
    "adapter_contract_selection_verified", "execution_intent_hash_verified",
    "execution_intent_id_verified", "adapter_descriptor_hash_verified",
    "adapter_descriptor_scope_matches_intent", "planned_steps_ordered",
    "planned_methods_declared", "no_apply_step", "no_postcondition_step",
    "no_revert_step", "planned_after_adapter_contract_selection",
    "no_adapter_instance", "no_adapter_invocation", "no_bind_invocation",
    "no_bind_receipt_created", "no_trustlog_write", "no_network",
    "no_filesystem", "no_external_effect",
)}
FUTURE_DRY_RUN_EXECUTION_REQUIREMENTS = {key: True for key in (
    "adapter_instance_required", "describe_target_call_required",
    "idempotency_key_plan_required", "snapshot_call_required",
    "state_fingerprint_call_required", "authority_revalidation_call_required",
    "constraint_validation_call_required", "runtime_risk_assessment_call_required",
    "dry_run_result_packet_required", "trustlog_policy_still_deferred",
    "bind_receipt_still_deferred", "apply_still_forbidden",
)}
SCOPE_LIMITATIONS = (
    "NOT_EXECUTION_AUTHORITY", "NOT_BIND_AUTHORIZATION", "NOT_BIND_RECEIPT",
    "NOT_BIND_INVOCATION", "NOT_ADAPTER_INSTANCE", "NOT_ADAPTER_INVOCATION",
    "NOT_ADAPTER_DRY_RUN_EXECUTION", "NOT_EXTERNAL_EFFECT",
    "NOT_OPERATION_COMMIT", "NOT_TRUSTLOG_WRITE", "NOT_LIVE_STATE_CHECK",
    "NOT_RUNTIME_RISK_ACCEPTANCE", "NOT_AUTHORITY_REVALIDATION",
    "NOT_CONSTRAINT_REVALIDATION", "NOT_POSTCONDITION_VERIFICATION",
    "NOT_ROLLBACK_PROOF", "NOT_AUTHORITY_EVIDENCE", "NOT_HUMAN_APPROVAL",
)


class AdapterDryRunPlanError(ValueError):
    """Stable fail-closed refusal for dry-run plan processing."""


class AdapterDryRunStepDescriptor(BaseModel):
    """Immutable description of a future call, never an executable call."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    step_id: str = Field(pattern=r"^dry-run-step:v1:[1-9][0-9]*:[a-z0-9-]+$")
    ordinal: int = Field(ge=1)
    phase: Literal["prepare", "observe", "validate", "assess", "finalize"]
    planned_adapter_method: Literal[
        "snapshot", "fingerprint_state", "validate_authority",
        "validate_constraints", "assess_runtime_risk", "describe_target",
        "build_idempotency_key",
    ]
    execution_mode: Literal["planned_no_effect"]
    required_input_refs: tuple[str, ...]
    expected_output_ref: str
    effect_policy: dict[str, bool]
    refusal_if_missing_later: str
    step_scope_limitations: tuple[str, ...]


class CanonicalAdapterDryRunPlanPacket(BaseModel):
    """Strict immutable packet representing only a no-effect plan."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    format_version: Literal["canonical-adapter-dry-run-plan/v1"]
    adapter_dry_run_plan_id: str = Field(pattern=r"^adp:v1:sha256:[0-9a-f]{64}$")
    adapter_dry_run_plan_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_mechanism: Literal["plan_adapter_dry_run_without_invocation/v1"]
    planned_at: str
    source_adapter_contract_selection: dict[str, Any]
    source_adapter_contract_selection_hash: str
    source_adapter_contract_selection_packet: dict[str, Any]
    adapter_contract_descriptor: dict[str, Any]
    adapter_contract_id: str
    adapter_contract_hash: str
    adapter_contract_version: Literal["bind-adapter-contract/v1"]
    execution_intent: dict[str, Any]
    execution_intent_id: str
    execution_intent_hash: str
    source_bind_preflight_adjudication_hash: str
    source_formation_hash: str
    source_readiness_hash: str
    source_eligibility_hash: str
    source_handoff_hash: str
    trusted_validation_context_hash: str
    validation_result_hash: str
    mapping_value_digest: str
    execution_intent_contract_version: str
    dry_run_plan_status: Literal["ADAPTER_DRY_RUN_PLANNED_NO_EFFECT"]
    ready_for_adapter_dry_run_execution: Literal[True]
    fail_closed: Literal[False]
    planned_steps: tuple[AdapterDryRunStepDescriptor, ...]
    planned_step_digest: str
    local_plan_checks: dict[str, bool]
    future_dry_run_execution_requirements: dict[str, bool]
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
            raise AdapterDryRunPlanError("ADP_PACKET_INVALID")
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise AdapterDryRunPlanError("ADP_PLANNED_AT_INVALID")
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _json_value(item) for key, item in value.items()}
    raise AdapterDryRunPlanError("ADP_PACKET_INVALID")


def _aware(value: Any, code: str) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise AdapterDryRunPlanError(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AdapterDryRunPlanError(code)
    return parsed


def _digest(domain: str, value: Any) -> str:
    encoded = json.dumps(
        {"domain": domain, "value": _json_value(value)}, allow_nan=False,
        ensure_ascii=False, separators=(",", ":"), sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _packet_hash(raw: dict[str, Any]) -> str:
    return _digest(PACKET_DOMAIN, {
        key: value for key, value in raw.items()
        if key not in {"adapter_dry_run_plan_id", "adapter_dry_run_plan_hash"}
    })


def _verified_source(value: Any) -> CanonicalBindAdapterContractSelectionPacket:
    try:
        return verify_bind_adapter_contract_selection_packet(value)
    except (BindAdapterContractSelectionError, TypeError, ValueError) as exc:
        raise AdapterDryRunPlanError("ADP_ADAPTER_SELECTION_INVALID") from exc


def _intent(raw: dict[str, Any]) -> ExecutionIntent:
    try:
        intent = ExecutionIntent(**raw)
        canonical_execution_intent_json(intent)
    except (TypeError, ValueError) as exc:
        raise AdapterDryRunPlanError("ADP_PACKET_INVALID") from exc
    if intent.to_dict() != raw:
        raise AdapterDryRunPlanError("ADP_PACKET_INVALID")
    return intent


def _planned_steps() -> list[dict[str, Any]]:
    result = []
    for ordinal, (phase, method, output, refusal) in enumerate(STEP_SPECS, 1):
        slug = method.replace("_", "-")
        inputs = ["execution_intent", "adapter_contract_descriptor",
                  "source_bind_preflight_adjudication_packet"]
        result.append({
            "step_id": f"dry-run-step:v1:{ordinal}:{slug}", "ordinal": ordinal,
            "phase": phase, "planned_adapter_method": method,
            "execution_mode": "planned_no_effect", "required_input_refs": inputs,
            "expected_output_ref": output, "effect_policy": EFFECT_POLICY,
            "refusal_if_missing_later": refusal,
            "step_scope_limitations": STEP_LIMITATIONS,
        })
    return result


def build_adapter_dry_run_plan_packet(
    adapter_contract_selection_packet: Any,
    planned_at: datetime,
) -> CanonicalAdapterDryRunPlanPacket:
    """Build an inert plan after verifying the complete selection packet."""
    planned = _aware(planned_at, "ADP_PLANNED_AT_INVALID")
    source_packet = _verified_source(_json_value(adapter_contract_selection_packet))
    source = source_packet.model_dump(mode="json")
    if planned < _aware(source_packet.selected_at, "ADP_ADAPTER_SELECTION_INVALID"):
        raise AdapterDryRunPlanError("ADP_PLANNED_BEFORE_SELECTION")
    intent = _intent(source_packet.execution_intent)
    if intent.execution_intent_id != source_packet.execution_intent_id:
        raise AdapterDryRunPlanError("ADP_EXECUTION_INTENT_ID_MISMATCH")
    if hash_execution_intent(intent) != source_packet.execution_intent_hash:
        raise AdapterDryRunPlanError("ADP_EXECUTION_INTENT_HASH_MISMATCH")
    descriptor = source_packet.adapter_contract_descriptor
    if (descriptor["target_system"] != intent.target_system or
            descriptor["target_resource_scope"] != intent.target_resource):
        raise AdapterDryRunPlanError("ADP_DESCRIPTOR_TARGET_MISMATCH")
    steps = _planned_steps()
    copied = (
        "adapter_contract_descriptor", "adapter_contract_id",
        "adapter_contract_hash", "adapter_contract_version", "execution_intent",
        "execution_intent_id", "execution_intent_hash",
        "source_bind_preflight_adjudication_hash", "source_formation_hash",
        "source_readiness_hash", "source_eligibility_hash", "source_handoff_hash",
        "trusted_validation_context_hash", "validation_result_hash",
        "mapping_value_digest", "execution_intent_contract_version",
        "source_to_execution_intent_mapping", "field_mapping_proof",
        "required_field_presence", "source_decision_identity", "candidate_identity",
        "evidence_lineage", "replay_summary",
    )
    raw = {
        "format_version": FORMAT_VERSION, "plan_mechanism": PLAN_MECHANISM,
        "planned_at": planned.isoformat(),
        "source_adapter_contract_selection": {
            key: source[key] for key in SOURCE_SUMMARY_KEYS
        },
        "source_adapter_contract_selection_hash": source_packet.adapter_contract_selection_hash,
        "source_adapter_contract_selection_packet": source,
        **{key: source[key] for key in copied},
        "dry_run_plan_status": "ADAPTER_DRY_RUN_PLANNED_NO_EFFECT",
        "ready_for_adapter_dry_run_execution": True, "fail_closed": False,
        "planned_steps": steps,
        "planned_step_digest": _digest(STEPS_DOMAIN, steps),
        "local_plan_checks": LOCAL_PLAN_CHECKS,
        "future_dry_run_execution_requirements": FUTURE_DRY_RUN_EXECUTION_REQUIREMENTS,
        "scope_limitations": SCOPE_LIMITATIONS,
    }
    digest = _packet_hash(raw)
    raw.update(adapter_dry_run_plan_hash=digest,
               adapter_dry_run_plan_id=f"adp:v1:sha256:{digest}")
    return verify_adapter_dry_run_plan_packet(raw)


def verify_adapter_dry_run_plan_packet(
    packet: Any,
) -> CanonicalAdapterDryRunPlanPacket:
    """Dump, revalidate, and independently recompute every packet binding."""
    try:
        value = packet.model_dump(mode="json") if isinstance(packet, BaseModel) else _json_value(packet)
        candidate = CanonicalAdapterDryRunPlanPacket.model_validate(value)
    except (ValidationError, AdapterDryRunPlanError, TypeError) as exc:
        raise AdapterDryRunPlanError("ADP_PACKET_INVALID") from exc
    raw = candidate.model_dump(mode="json")
    source_packet = _verified_source(candidate.source_adapter_contract_selection_packet)
    source = source_packet.model_dump(mode="json")
    if (set(candidate.source_adapter_contract_selection) != set(SOURCE_SUMMARY_KEYS) or
            candidate.source_adapter_contract_selection != {
                key: source[key] for key in SOURCE_SUMMARY_KEYS
            } or candidate.source_adapter_contract_selection_hash !=
            source_packet.adapter_contract_selection_hash):
        raise AdapterDryRunPlanError("ADP_SOURCE_SUMMARY_MISMATCH")
    if _aware(candidate.planned_at, "ADP_PLANNED_AT_INVALID") < _aware(
            source_packet.selected_at, "ADP_ADAPTER_SELECTION_INVALID"):
        raise AdapterDryRunPlanError("ADP_PLANNED_BEFORE_SELECTION")
    copied = (
        "adapter_contract_descriptor", "adapter_contract_id",
        "adapter_contract_hash", "adapter_contract_version", "execution_intent",
        "execution_intent_id", "execution_intent_hash",
        "source_bind_preflight_adjudication_hash", "source_formation_hash",
        "source_readiness_hash", "source_eligibility_hash", "source_handoff_hash",
        "trusted_validation_context_hash", "validation_result_hash",
        "mapping_value_digest", "execution_intent_contract_version",
        "source_to_execution_intent_mapping", "field_mapping_proof",
        "required_field_presence", "source_decision_identity", "candidate_identity",
        "evidence_lineage", "replay_summary",
    )
    if any(getattr(candidate, key) != getattr(source_packet, key) for key in copied):
        raise AdapterDryRunPlanError("ADP_SOURCE_SUMMARY_MISMATCH")
    intent = _intent(candidate.execution_intent)
    if intent.execution_intent_id != candidate.execution_intent_id:
        raise AdapterDryRunPlanError("ADP_EXECUTION_INTENT_ID_MISMATCH")
    if hash_execution_intent(intent) != candidate.execution_intent_hash:
        raise AdapterDryRunPlanError("ADP_EXECUTION_INTENT_HASH_MISMATCH")
    if candidate.planned_steps != tuple(
            AdapterDryRunStepDescriptor.model_validate(item)
            for item in _planned_steps()):
        raise AdapterDryRunPlanError("ADP_PLANNED_STEPS_INVALID")
    steps_raw = [step.model_dump(mode="json") for step in candidate.planned_steps]
    if candidate.planned_step_digest != _digest(STEPS_DOMAIN, steps_raw):
        raise AdapterDryRunPlanError("ADP_PLANNED_STEP_DIGEST_MISMATCH")
    if candidate.local_plan_checks != LOCAL_PLAN_CHECKS:
        raise AdapterDryRunPlanError("ADP_LOCAL_CHECKS_MISMATCH")
    if candidate.future_dry_run_execution_requirements != FUTURE_DRY_RUN_EXECUTION_REQUIREMENTS:
        raise AdapterDryRunPlanError("ADP_FUTURE_REQUIREMENTS_MISMATCH")
    _digest(LOCAL_CHECKS_DOMAIN, candidate.local_plan_checks)
    _digest(FUTURE_REQUIREMENTS_DOMAIN, candidate.future_dry_run_execution_requirements)
    if candidate.scope_limitations != SCOPE_LIMITATIONS:
        raise AdapterDryRunPlanError("ADP_SCOPE_LIMITATIONS_MISSING")
    digest = _packet_hash(raw)
    if candidate.adapter_dry_run_plan_hash != digest:
        raise AdapterDryRunPlanError("ADP_PACKET_HASH_MISMATCH")
    if candidate.adapter_dry_run_plan_id != f"adp:v1:sha256:{digest}":
        raise AdapterDryRunPlanError("ADP_PACKET_ID_MISMATCH")
    return candidate
