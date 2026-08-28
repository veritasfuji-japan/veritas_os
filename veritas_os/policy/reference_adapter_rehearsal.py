"""Deterministic, no-effect reference-adapter rehearsal boundary.

This module deliberately owns a tiny in-memory rehearsal adapter rather than
using the execution-side reference adapter.  It performs seven descriptive
calls and cannot commit, persist, communicate, or construct execution receipts.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from veritas_os.policy.adapter_dry_run_plan import STEPS_DOMAIN, _digest as plan_digest
from veritas_os.policy.adapter_dry_run_result import (
    RESULTS_DOMAIN as FIXTURE_RESULTS_DOMAIN,
    AdapterDryRunFixtureResultError,
    CanonicalAdapterDryRunFixtureResultPacket,
    verify_adapter_dry_run_fixture_result_packet,
)
from veritas_os.policy.bind_artifacts import (
    ExecutionIntent,
    canonical_execution_intent_json,
    hash_execution_intent,
)

FORMAT_VERSION = "canonical-reference-adapter-in-memory-rehearsal/v1"
REHEARSAL_MECHANISM = "run_reference_adapter_in_memory_rehearsal_without_bind/v1"
OUTPUT_DOMAIN = "veritas.reference-adapter-in-memory-rehearsal.output/v1"
RESULTS_DOMAIN = "veritas.reference-adapter-in-memory-rehearsal.results/v1"
LOCAL_CHECKS_DOMAIN = "veritas.reference-adapter-in-memory-rehearsal.local-checks/v1"
FUTURE_REQUIREMENTS_DOMAIN = (
    "veritas.reference-adapter-in-memory-rehearsal.future-requirements/v1"
)
PACKET_DOMAIN = "veritas.reference-adapter-in-memory-rehearsal.packet/v1"
SOURCE_SUMMARY_KEYS = (
    "adapter_dry_run_result_id",
    "adapter_dry_run_result_hash",
    "format_version",
    "result_mechanism",
    "resulted_at",
    "execution_intent_id",
    "execution_intent_hash",
    "dry_run_fixture_result_status",
    "ready_for_reference_adapter_rehearsal",
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
STEP_LIMITATIONS = (
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
LOCAL_REHEARSAL_CHECKS = {
    key: True
    for key in (
        "adapter_dry_run_fixture_result_verified",
        "execution_intent_hash_verified",
        "execution_intent_id_verified",
        "adapter_descriptor_preserved",
        "planned_steps_preserved",
        "fixture_results_preserved",
        "planned_step_digest_verified",
        "fixture_result_digest_verified",
        "reference_rehearsal_results_ordered",
        "reference_rehearsal_results_match_planned_steps",
        "reference_outputs_digest_verified",
        "no_apply_rehearsal",
        "no_postcondition_rehearsal",
        "no_revert_rehearsal",
        "rehearsed_after_fixture_result",
        "reference_adapter_instance_created",
        "reference_adapter_methods_called",
        "no_live_adapter_instance",
        "no_live_adapter_invocation",
        "no_bind_invocation",
        "no_bind_receipt_created",
        "no_trustlog_write",
        "no_network",
        "no_filesystem",
        "no_external_effect",
        "no_live_state_claim",
        "no_live_authority_revalidation_claim",
        "no_live_constraint_revalidation_claim",
        "no_runtime_risk_acceptance_claim",
    )
}
FUTURE_LIVE_ADAPTER_DRY_RUN_REQUIREMENTS = {
    key: True
    for key in (
        "live_adapter_instance_required",
        "live_describe_target_required",
        "live_idempotency_key_required",
        "live_snapshot_required",
        "live_state_fingerprint_required",
        "live_authority_revalidation_required",
        "live_constraint_validation_required",
        "live_runtime_risk_assessment_required",
        "live_dry_run_result_packet_required",
        "human_approval_still_required",
        "authority_evidence_still_required",
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
    "NOT_LIVE_ADAPTER_INSTANCE",
    "NOT_LIVE_ADAPTER_INVOCATION",
    "NOT_LIVE_ADAPTER_RESULT",
    "NOT_EXTERNAL_EFFECT",
    "NOT_OPERATION_COMMIT",
    "NOT_TRUSTLOG_WRITE",
    "NOT_LIVE_STATE_CHECK",
    "NOT_RUNTIME_RISK_ACCEPTANCE",
    "NOT_LIVE_AUTHORITY_REVALIDATION",
    "NOT_LIVE_CONSTRAINT_REVALIDATION",
    "NOT_POSTCONDITION_VERIFICATION",
    "NOT_ROLLBACK_PROOF",
    "NOT_AUTHORITY_EVIDENCE",
    "NOT_HUMAN_APPROVAL",
)


class ReferenceAdapterRehearsalError(ValueError):
    """Stable fail-closed refusal for reference rehearsal processing."""


class ReferenceAdapterInMemoryStepResult(BaseModel):
    """Immutable pure-data observation of one permitted rehearsal call."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    rehearsal_step_result_id: str = Field(
        pattern=r"^reference-rehearsal-result:v1:[1-9][0-9]*:[a-z0-9-]+$"
    )
    planned_step_id: str
    fixture_step_result_id: str
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
    rehearsal_mode: Literal["reference_in_memory_no_effect"]
    reference_adapter_instance_created: Literal[True]
    reference_adapter_method_called: Literal[True]
    live_adapter_instance_created: Literal[False]
    live_adapter_method_called: Literal[False]
    network_used: Literal[False]
    filesystem_used: Literal[False]
    external_effect_used: Literal[False]
    trustlog_written: Literal[False]
    bind_receipt_created: Literal[False]
    bind_invoked: Literal[False]
    output_summary: dict[str, Any]
    output_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    matched_expected_output_ref: str
    rehearsal_scope_limitations: tuple[str, ...]


class CanonicalReferenceAdapterInMemoryRehearsalPacket(BaseModel):
    """Strict content-addressed packet for a verified local rehearsal."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    format_version: Literal["canonical-reference-adapter-in-memory-rehearsal/v1"]
    reference_rehearsal_id: str = Field(pattern=r"^rar:v1:sha256:[0-9a-f]{64}$")
    reference_rehearsal_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    rehearsal_mechanism: Literal[
        "run_reference_adapter_in_memory_rehearsal_without_bind/v1"
    ]
    rehearsed_at: str
    source_adapter_dry_run_fixture_result: dict[str, Any]
    source_adapter_dry_run_fixture_result_hash: str
    source_adapter_dry_run_fixture_result_packet: dict[str, Any]
    adapter_contract_descriptor: dict[str, Any]
    adapter_contract_id: str
    adapter_contract_hash: str
    adapter_contract_version: str
    execution_intent: dict[str, Any]
    execution_intent_id: str
    execution_intent_hash: str
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
    reference_rehearsal_status: Literal[
        "REFERENCE_ADAPTER_IN_MEMORY_REHEARSAL_COMPLETED_NO_EFFECT"
    ]
    ready_for_live_adapter_dry_run_request: Literal[True]
    fail_closed: Literal[False]
    planned_steps: tuple[dict[str, Any], ...]
    planned_step_digest: str
    fixture_step_results: tuple[dict[str, Any], ...]
    fixture_result_digest: str
    reference_rehearsal_results: tuple[ReferenceAdapterInMemoryStepResult, ...]
    reference_rehearsal_result_digest: str
    local_rehearsal_checks: dict[str, bool]
    future_live_adapter_dry_run_requirements: dict[str, bool]
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
            raise ReferenceAdapterRehearsalError("RAR_PACKET_INVALID")
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ReferenceAdapterRehearsalError("RAR_REHEARSED_AT_INVALID")
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _json_value(item) for key, item in value.items()}
    raise ReferenceAdapterRehearsalError("RAR_PACKET_INVALID")


def _aware(value: Any, code: str) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ReferenceAdapterRehearsalError(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ReferenceAdapterRehearsalError(code)
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
            if key not in {"reference_rehearsal_id", "reference_rehearsal_hash"}
        },
    )


def _verified_source(value: Any) -> CanonicalAdapterDryRunFixtureResultPacket:
    try:
        return verify_adapter_dry_run_fixture_result_packet(value)
    except (AdapterDryRunFixtureResultError, TypeError, ValueError) as exc:
        raise ReferenceAdapterRehearsalError("RAR_FIXTURE_RESULT_INVALID") from exc


def _intent(raw: dict[str, Any]) -> ExecutionIntent:
    try:
        intent = ExecutionIntent(**raw)
        canonical_execution_intent_json(intent)
    except (TypeError, ValueError) as exc:
        raise ReferenceAdapterRehearsalError("RAR_PACKET_INVALID") from exc
    if intent.to_dict() != raw:
        raise ReferenceAdapterRehearsalError("RAR_PACKET_INVALID")
    return intent


class InMemoryReferenceRehearsalAdapter:
    """Seven-method local adapter with no execution or I/O capabilities."""

    def __init__(
        self,
        intent: ExecutionIntent,
        fixture: dict[str, Any],
        *,
        output_domain: str = OUTPUT_DOMAIN,
    ) -> None:
        self._intent = intent.to_dict()
        self._fixture = fixture
        self._output_domain = output_domain

    def rehearse(self, method: str, ordinal: int) -> dict[str, Any]:
        """Return a deterministic JSON descriptor for one allowlisted method."""
        if method not in PLANNED_METHODS:
            raise ReferenceAdapterRehearsalError("RAR_FORBIDDEN_EXECUTION_STEP")
        return {
            "method": method,
            "ordinal": ordinal,
            "mode": "reference_in_memory_no_effect",
            "intent_digest": _digest(self._output_domain, self._intent),
            "fixture_digest": _digest(self._output_domain, self._fixture),
            "target_system": self._intent["target_system"],
            "target_resource": self._intent["target_resource"],
        }


def _results(
    source: CanonicalAdapterDryRunFixtureResultPacket, fixture: dict[str, Any]
) -> list[dict[str, Any]]:
    adapter = InMemoryReferenceRehearsalAdapter(
        _intent(source.execution_intent), fixture
    )
    results = []
    for step, fixture_result in zip(
        source.planned_steps, source.fixture_step_results, strict=True
    ):
        step_json = _json_value(step)
        fixture_result_json = _json_value(fixture_result)
        if not isinstance(step_json, dict) or not isinstance(
            fixture_result_json, dict
        ):
            raise ReferenceAdapterRehearsalError("RAR_PACKET_INVALID")
        method = step_json["planned_adapter_method"]
        ordinal = step_json["ordinal"]
        summary = adapter.rehearse(method, ordinal)
        results.append(
            {
                "rehearsal_step_result_id": (
                    f"reference-rehearsal-result:v1:{ordinal}:"
                    f"{method.replace('_', '-')}"
                ),
                "planned_step_id": step_json["step_id"],
                "fixture_step_result_id": fixture_result_json["step_result_id"],
                "ordinal": ordinal,
                "planned_adapter_method": method,
                "rehearsal_mode": "reference_in_memory_no_effect",
                "reference_adapter_instance_created": True,
                "reference_adapter_method_called": True,
                "live_adapter_instance_created": False,
                "live_adapter_method_called": False,
                "network_used": False,
                "filesystem_used": False,
                "external_effect_used": False,
                "trustlog_written": False,
                "bind_receipt_created": False,
                "bind_invoked": False,
                "output_summary": summary,
                "output_digest": _digest(OUTPUT_DOMAIN, summary),
                "matched_expected_output_ref": step_json["expected_output_ref"],
                "rehearsal_scope_limitations": STEP_LIMITATIONS,
            }
        )
    return results


_COPIED_FIELDS = (
    "adapter_contract_descriptor",
    "adapter_contract_id",
    "adapter_contract_hash",
    "adapter_contract_version",
    "execution_intent",
    "execution_intent_id",
    "execution_intent_hash",
    "source_adapter_dry_run_plan_hash",
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


def build_reference_adapter_in_memory_rehearsal_packet(
    adapter_dry_run_fixture_result_packet: Any,
    reference_rehearsal_fixture: Any,
    rehearsed_at: datetime,
) -> CanonicalReferenceAdapterInMemoryRehearsalPacket:
    """Build and reverify a no-effect rehearsal packet from verified input."""
    rehearsed = _aware(rehearsed_at, "RAR_REHEARSED_AT_INVALID")
    fixture = _json_value(reference_rehearsal_fixture)
    if not isinstance(fixture, dict):
        raise ReferenceAdapterRehearsalError("RAR_PACKET_INVALID")
    source_packet = _verified_source(_json_value(adapter_dry_run_fixture_result_packet))
    source = source_packet.model_dump(mode="json")
    if rehearsed < _aware(source_packet.resulted_at, "RAR_FIXTURE_RESULT_INVALID"):
        raise ReferenceAdapterRehearsalError("RAR_REHEARSED_BEFORE_FIXTURE_RESULT")
    intent = _intent(source_packet.execution_intent)
    if intent.execution_intent_id != source_packet.execution_intent_id:
        raise ReferenceAdapterRehearsalError("RAR_EXECUTION_INTENT_ID_MISMATCH")
    if hash_execution_intent(intent) != source_packet.execution_intent_hash:
        raise ReferenceAdapterRehearsalError("RAR_EXECUTION_INTENT_HASH_MISMATCH")
    descriptor = source_packet.adapter_contract_descriptor
    if (
        descriptor["target_system"] != intent.target_system
        or descriptor["target_resource_scope"] != intent.target_resource
    ):
        raise ReferenceAdapterRehearsalError("RAR_DESCRIPTOR_MISMATCH")
    steps = [_json_value(item) for item in source_packet.planned_steps]
    fixtures = [_json_value(item) for item in source_packet.fixture_step_results]
    results = _results(source_packet, fixture)
    raw = {
        "format_version": FORMAT_VERSION,
        "rehearsal_mechanism": REHEARSAL_MECHANISM,
        "rehearsed_at": rehearsed.isoformat(),
        "source_adapter_dry_run_fixture_result": {
            key: source[key] for key in SOURCE_SUMMARY_KEYS
        },
        "source_adapter_dry_run_fixture_result_hash": source_packet.adapter_dry_run_result_hash,
        "source_adapter_dry_run_fixture_result_packet": source,
        **{key: source[key] for key in _COPIED_FIELDS},
        "reference_rehearsal_status": "REFERENCE_ADAPTER_IN_MEMORY_REHEARSAL_COMPLETED_NO_EFFECT",
        "ready_for_live_adapter_dry_run_request": True,
        "fail_closed": False,
        "planned_steps": steps,
        "planned_step_digest": source_packet.planned_step_digest,
        "fixture_step_results": fixtures,
        "fixture_result_digest": source_packet.fixture_result_digest,
        "reference_rehearsal_results": results,
        "reference_rehearsal_result_digest": _digest(RESULTS_DOMAIN, results),
        "local_rehearsal_checks": LOCAL_REHEARSAL_CHECKS,
        "future_live_adapter_dry_run_requirements": FUTURE_LIVE_ADAPTER_DRY_RUN_REQUIREMENTS,
        "scope_limitations": SCOPE_LIMITATIONS,
    }
    digest = _packet_hash(raw)
    raw.update(
        reference_rehearsal_hash=digest,
        reference_rehearsal_id=f"rar:v1:sha256:{digest}",
    )
    return verify_reference_adapter_in_memory_rehearsal_packet(raw)


def verify_reference_adapter_in_memory_rehearsal_packet(
    packet: Any,
) -> CanonicalReferenceAdapterInMemoryRehearsalPacket:
    """Independently revalidate all source, result, and identity bindings."""
    try:
        value = (
            packet.model_dump(mode="json")
            if isinstance(packet, BaseModel)
            else _json_value(packet)
        )
        candidate = CanonicalReferenceAdapterInMemoryRehearsalPacket.model_validate(
            value
        )
    except (ValidationError, ReferenceAdapterRehearsalError, TypeError) as exc:
        raise ReferenceAdapterRehearsalError("RAR_PACKET_INVALID") from exc
    raw = candidate.model_dump(mode="json")
    source_packet = _verified_source(
        candidate.source_adapter_dry_run_fixture_result_packet
    )
    source = source_packet.model_dump(mode="json")
    if (
        set(candidate.source_adapter_dry_run_fixture_result) != set(SOURCE_SUMMARY_KEYS)
        or candidate.source_adapter_dry_run_fixture_result
        != {key: source[key] for key in SOURCE_SUMMARY_KEYS}
        or candidate.source_adapter_dry_run_fixture_result_hash
        != source_packet.adapter_dry_run_result_hash
    ):
        raise ReferenceAdapterRehearsalError("RAR_SOURCE_SUMMARY_MISMATCH")
    if _aware(candidate.rehearsed_at, "RAR_REHEARSED_AT_INVALID") < _aware(
        source_packet.resulted_at, "RAR_FIXTURE_RESULT_INVALID"
    ):
        raise ReferenceAdapterRehearsalError("RAR_REHEARSED_BEFORE_FIXTURE_RESULT")
    if any(
        getattr(candidate, key) != getattr(source_packet, key) for key in _COPIED_FIELDS
    ):
        raise ReferenceAdapterRehearsalError("RAR_SOURCE_SUMMARY_MISMATCH")
    intent = _intent(candidate.execution_intent)
    if intent.execution_intent_id != candidate.execution_intent_id:
        raise ReferenceAdapterRehearsalError("RAR_EXECUTION_INTENT_ID_MISMATCH")
    if hash_execution_intent(intent) != candidate.execution_intent_hash:
        raise ReferenceAdapterRehearsalError("RAR_EXECUTION_INTENT_HASH_MISMATCH")
    descriptor = candidate.adapter_contract_descriptor
    if (
        descriptor["target_system"] != intent.target_system
        or descriptor["target_resource_scope"] != intent.target_resource
    ):
        raise ReferenceAdapterRehearsalError("RAR_DESCRIPTOR_MISMATCH")
    steps = [_json_value(item) for item in source_packet.planned_steps]
    fixtures = [_json_value(item) for item in source_packet.fixture_step_results]
    if list(candidate.planned_steps) != steps:
        raise ReferenceAdapterRehearsalError("RAR_PLANNED_STEPS_MISMATCH")
    if (
        candidate.planned_step_digest != source_packet.planned_step_digest
        or candidate.planned_step_digest != plan_digest(STEPS_DOMAIN, steps)
    ):
        raise ReferenceAdapterRehearsalError("RAR_PLANNED_STEPS_MISMATCH")
    if list(candidate.fixture_step_results) != fixtures:
        raise ReferenceAdapterRehearsalError("RAR_FIXTURE_RESULTS_MISMATCH")
    if (
        candidate.fixture_result_digest != source_packet.fixture_result_digest
        or candidate.fixture_result_digest != _digest(FIXTURE_RESULTS_DOMAIN, fixtures)
    ):
        raise ReferenceAdapterRehearsalError("RAR_FIXTURE_RESULTS_MISMATCH")
    results = [_json_value(item) for item in candidate.reference_rehearsal_results]
    if len(results) != 7 or [
        item["planned_adapter_method"] for item in results
    ] != list(PLANNED_METHODS):
        raise ReferenceAdapterRehearsalError("RAR_REHEARSAL_RESULTS_INVALID")
    for result, step, fixture in zip(results, steps, fixtures, strict=True):
        expected_id = f"reference-rehearsal-result:v1:{step['ordinal']}:{step['planned_adapter_method'].replace('_', '-')}"
        if (
            result["rehearsal_step_result_id"] != expected_id
            or result["planned_step_id"] != step["step_id"]
            or result["fixture_step_result_id"] != fixture["step_result_id"]
            or result["ordinal"] != step["ordinal"]
            or result["matched_expected_output_ref"] != step["expected_output_ref"]
            or tuple(result["rehearsal_scope_limitations"]) != STEP_LIMITATIONS
        ):
            raise ReferenceAdapterRehearsalError("RAR_REHEARSAL_RESULTS_INVALID")
        flags = (
            result["reference_adapter_instance_created"],
            result["reference_adapter_method_called"],
            not result["live_adapter_instance_created"],
            not result["live_adapter_method_called"],
            not result["network_used"],
            not result["filesystem_used"],
            not result["external_effect_used"],
            not result["trustlog_written"],
            not result["bind_receipt_created"],
            not result["bind_invoked"],
        )
        if not all(flags):
            raise ReferenceAdapterRehearsalError("RAR_EXTERNAL_EFFECT_FORBIDDEN")
        if result["output_digest"] != _digest(OUTPUT_DOMAIN, result["output_summary"]):
            raise ReferenceAdapterRehearsalError("RAR_OUTPUT_DIGEST_MISMATCH")
    if candidate.reference_rehearsal_result_digest != _digest(RESULTS_DOMAIN, results):
        raise ReferenceAdapterRehearsalError("RAR_REHEARSAL_RESULTS_INVALID")
    if candidate.local_rehearsal_checks != LOCAL_REHEARSAL_CHECKS:
        raise ReferenceAdapterRehearsalError("RAR_LOCAL_CHECKS_MISMATCH")
    if (
        candidate.future_live_adapter_dry_run_requirements
        != FUTURE_LIVE_ADAPTER_DRY_RUN_REQUIREMENTS
    ):
        raise ReferenceAdapterRehearsalError("RAR_FUTURE_REQUIREMENTS_MISMATCH")
    _digest(LOCAL_CHECKS_DOMAIN, candidate.local_rehearsal_checks)
    _digest(
        FUTURE_REQUIREMENTS_DOMAIN, candidate.future_live_adapter_dry_run_requirements
    )
    if candidate.scope_limitations != SCOPE_LIMITATIONS:
        raise ReferenceAdapterRehearsalError("RAR_SCOPE_LIMITATIONS_MISSING")
    digest = _packet_hash(raw)
    if candidate.reference_rehearsal_hash != digest:
        raise ReferenceAdapterRehearsalError("RAR_PACKET_HASH_MISMATCH")
    if candidate.reference_rehearsal_id != f"rar:v1:sha256:{digest}":
        raise ReferenceAdapterRehearsalError("RAR_PACKET_ID_MISMATCH")
    return candidate
