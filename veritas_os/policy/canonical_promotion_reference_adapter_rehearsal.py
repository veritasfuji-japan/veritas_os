"""Promotion-native deterministic reference-adapter rehearsal boundary.

The boundary invokes only the shared seven-method in-memory rehearsal adapter.
It independently binds a verified promotion-native fixture-result packet and
cannot perform Bind, live adapter calls, I/O, or external effects.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from veritas_os.policy.bind_adapter_contract_selection import (
    BindAdapterContractSelectionError,
    verify_bind_adapter_contract_descriptor,
)
from veritas_os.policy.bind_artifacts import ExecutionIntent, hash_execution_intent
from veritas_os.policy.canonical_promotion_adapter_dry_run_fixture_result import (
    RESULTS_DOMAIN as FIXTURE_RESULTS_DOMAIN,
    CanonicalPromotionAdapterDryRunFixtureResultError,
    CanonicalPromotionAdapterDryRunFixtureResultPacket,
    _digest as fixture_digest,
    verify_canonical_promotion_adapter_dry_run_fixture_result_packet,
)
from veritas_os.policy.canonical_promotion_adapter_dry_run_plan import (
    STEPS_DOMAIN,
    _digest as plan_digest,
)
from veritas_os.policy.reference_adapter_rehearsal import (
    InMemoryReferenceRehearsalAdapter,
    PLANNED_METHODS,
)

FORMAT_VERSION = "canonical-promotion-reference-adapter-in-memory-rehearsal/v1"
REHEARSAL_MECHANISM = (
    "run_promotion_reference_adapter_in_memory_rehearsal_without_bind/v1"
)
OUTPUT_DOMAIN = "veritas.promotion-reference-adapter-rehearsal.output/v1"
RESULTS_DOMAIN = "veritas.promotion-reference-adapter-rehearsal.results/v1"
LOCAL_CHECKS_DOMAIN = "veritas.promotion-reference-adapter-rehearsal.local-checks/v1"
FUTURE_REQUIREMENTS_DOMAIN = (
    "veritas.promotion-reference-adapter-rehearsal.future-requirements/v1"
)
PACKET_DOMAIN = "veritas.promotion-reference-adapter-rehearsal.packet/v1"
STATUS = "PROMOTION_NATIVE_REFERENCE_ADAPTER_IN_MEMORY_REHEARSAL_COMPLETED_NO_EFFECT"
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
    "NOT_AUTHORITY_EVIDENCE_PROOF",
    "NOT_HUMAN_APPROVAL_PROOF",
)
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
    "NOT_AUTHORITY_EVIDENCE_PROOF",
    "NOT_HUMAN_APPROVAL_PROOF",
)
LOCAL_CHECKS = {
    key: True
    for key in (
        "promotion_fixture_result_verified",
        "execution_intent_object_verified",
        "execution_intent_id_verified",
        "execution_intent_hash_verified",
        "adapter_descriptor_verified",
        "adapter_descriptor_target_verified",
        "planned_steps_verified",
        "fixture_results_verified",
        "seven_reference_methods_called",
        "rehearsal_outputs_reconstructed",
        "no_apply_rehearsal",
        "no_postcondition_rehearsal",
        "no_revert_rehearsal",
        "no_live_adapter_instance",
        "no_live_adapter_invocation",
        "no_network",
        "no_filesystem",
        "no_external_effect",
        "no_bind_invocation",
        "no_bind_receipt",
        "no_trustlog_write",
        "no_authority_evidence_proof",
        "no_human_approval_proof",
        "rehearsed_after_fixture_result",
    )
}
FUTURE_REQUIREMENTS = {
    key: True
    for key in (
        "fresh_verified_source_gate_required",
        "live_adapter_dry_run_request_required",
        "live_authority_revalidation_required",
        "live_constraint_revalidation_required",
        "runtime_risk_acceptance_required",
        "human_approval_proof_still_deferred",
        "authority_evidence_proof_still_deferred",
        "bind_authorization_still_deferred",
        "trustlog_policy_still_deferred",
        "apply_still_forbidden",
    )
}
LINEAGE_FIELDS = (
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


class CanonicalPromotionReferenceAdapterRehearsalError(ValueError):
    """Stable fail-closed refusal for promotion-native rehearsal packets."""


class PromotionReferenceAdapterStepResult(BaseModel):
    """Immutable evidence for one allowlisted local adapter call."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    rehearsal_step_result_id: str = Field(
        pattern=r"^promotion-reference-rehearsal-result:v1:[1-9][0-9]*:[a-z0-9-]+$"
    )
    planned_step_id: str
    fixture_step_result_id: str
    ordinal: int = Field(ge=1)
    planned_adapter_method: Literal[
        "describe_target", "build_idempotency_key", "snapshot",
        "fingerprint_state", "validate_authority", "validate_constraints",
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
    authority_evidence_proven: Literal[False]
    human_approval_proven: Literal[False]
    output_summary: dict[str, Any]
    output_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    matched_expected_output_ref: str
    rehearsal_scope_limitations: tuple[str, ...]


class CanonicalPromotionReferenceAdapterInMemoryRehearsalPacket(BaseModel):
    """Content-addressed promotion-native in-memory rehearsal evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    format_version: Literal[
        "canonical-promotion-reference-adapter-in-memory-rehearsal/v1"
    ]
    promotion_reference_rehearsal_id: str = Field(
        pattern=r"^prar:v1:sha256:[0-9a-f]{64}$"
    )
    promotion_reference_rehearsal_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    rehearsal_mechanism: Literal[
        "run_promotion_reference_adapter_in_memory_rehearsal_without_bind/v1"
    ]
    rehearsed_at: str
    reference_rehearsal_fixture: dict[str, Any]
    source_adapter_dry_run_fixture_result_id: str
    source_adapter_dry_run_fixture_result_hash: str
    source_adapter_dry_run_fixture_result_packet: dict[str, Any]
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
    execution_intent: dict[str, Any]
    execution_intent_id: str
    execution_intent_hash: str
    adapter_contract_descriptor: dict[str, Any]
    adapter_contract_id: str
    adapter_contract_hash: str
    adapter_contract_version: Literal["bind-adapter-contract/v1"]
    planned_steps: tuple[dict[str, Any], ...]
    planned_step_digest: str
    fixture_step_results: tuple[dict[str, Any], ...]
    fixture_result_digest: str
    reference_rehearsal_results: tuple[PromotionReferenceAdapterStepResult, ...]
    reference_rehearsal_result_digest: str
    local_rehearsal_checks: dict[str, bool]
    local_rehearsal_checks_digest: str
    future_requirements: dict[str, bool]
    future_requirements_digest: str
    reference_rehearsal_status: Literal[
        "PROMOTION_NATIVE_REFERENCE_ADAPTER_IN_MEMORY_REHEARSAL_COMPLETED_NO_EFFECT"
    ]
    ready_for_promotion_native_live_adapter_dry_run_request: Literal[True]
    scope_limitations: tuple[str, ...]


def _json(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and value == value and value not in (
        float("inf"), float("-inf")
    ):
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise CanonicalPromotionReferenceAdapterRehearsalError(
                "PRAR_REHEARSED_AT_INVALID"
            )
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    if isinstance(value, Mapping) and all(isinstance(key, str) for key in value):
        return {key: _json(item) for key, item in value.items()}
    raise CanonicalPromotionReferenceAdapterRehearsalError("PRAR_PACKET_INVALID")


def _digest(domain: str, value: Any) -> str:
    encoded = json.dumps(
        {"domain": domain, "value": _json(value)}, allow_nan=False,
        ensure_ascii=False, separators=(",", ":"), sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _aware(value: Any, code: str) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise CanonicalPromotionReferenceAdapterRehearsalError(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CanonicalPromotionReferenceAdapterRehearsalError(code)
    return parsed


def _packet_hash(raw: dict[str, Any]) -> str:
    return _digest(PACKET_DOMAIN, {key: value for key, value in raw.items() if key not in {
        "promotion_reference_rehearsal_id", "promotion_reference_rehearsal_hash"
    }})


def _source(value: Any) -> CanonicalPromotionAdapterDryRunFixtureResultPacket:
    try:
        return verify_canonical_promotion_adapter_dry_run_fixture_result_packet(value)
    except (CanonicalPromotionAdapterDryRunFixtureResultError, TypeError, ValueError) as exc:
        raise CanonicalPromotionReferenceAdapterRehearsalError(
            "PRAR_SOURCE_FIXTURE_RESULT_INVALID"
        ) from exc


def _intent(source: CanonicalPromotionAdapterDryRunFixtureResultPacket) -> ExecutionIntent:
    try:
        intent = ExecutionIntent(**source.execution_intent)
    except (TypeError, ValueError) as exc:
        raise CanonicalPromotionReferenceAdapterRehearsalError(
            "PRAR_EXECUTION_INTENT_INVALID"
        ) from exc
    if (intent.to_dict() != source.execution_intent
            or intent.execution_intent_id != source.execution_intent_id
            or hash_execution_intent(intent) != source.execution_intent_hash):
        raise CanonicalPromotionReferenceAdapterRehearsalError(
            "PRAR_EXECUTION_INTENT_MISMATCH"
        )
    return intent


def _descriptor(source, intent: ExecutionIntent) -> None:
    try:
        descriptor = verify_bind_adapter_contract_descriptor(
            source.adapter_contract_descriptor, intent
        )
    except (BindAdapterContractSelectionError, TypeError, ValueError) as exc:
        raise CanonicalPromotionReferenceAdapterRehearsalError(
            "PRAR_DESCRIPTOR_INVALID"
        ) from exc
    if (descriptor.model_dump(mode="json") != source.adapter_contract_descriptor
            or descriptor.adapter_contract_id != source.adapter_contract_id
            or descriptor.adapter_contract_hash != source.adapter_contract_hash
            or descriptor.adapter_contract_version != source.adapter_contract_version):
        raise CanonicalPromotionReferenceAdapterRehearsalError(
            "PRAR_DESCRIPTOR_MISMATCH"
        )


def _results(source, fixture: dict[str, Any]) -> list[dict[str, Any]]:
    adapter = InMemoryReferenceRehearsalAdapter(
        _intent(source), fixture, output_domain=OUTPUT_DOMAIN
    )
    results = []
    for step, fixture_result in zip(
        source.planned_steps, source.fixture_step_results, strict=True
    ):
        step_raw = _json(step)
        fixture_raw = _json(fixture_result)
        method = step_raw["planned_adapter_method"]
        ordinal = step_raw["ordinal"]
        summary = adapter.rehearse(method, ordinal)
        raw_result = {
            "rehearsal_step_result_id": (
                f"promotion-reference-rehearsal-result:v1:{ordinal}:"
                f"{method.replace('_', '-')}"
            ),
            "planned_step_id": step_raw["step_id"],
            "fixture_step_result_id": fixture_raw["step_result_id"],
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
            "authority_evidence_proven": False,
            "human_approval_proven": False,
            "output_summary": summary,
            "output_digest": _digest(OUTPUT_DOMAIN, summary),
            "matched_expected_output_ref": step_raw["expected_output_ref"],
            "rehearsal_scope_limitations": STEP_LIMITATIONS,
        }
        results.append(
            PromotionReferenceAdapterStepResult.model_validate(
                raw_result
            ).model_dump(mode="json")
        )
    return results


def build_canonical_promotion_reference_adapter_in_memory_rehearsal_packet(
    adapter_dry_run_fixture_result_packet: CanonicalPromotionAdapterDryRunFixtureResultPacket | Mapping[str, Any],
    reference_rehearsal_fixture: Any,
    rehearsed_at: datetime,
) -> CanonicalPromotionReferenceAdapterInMemoryRehearsalPacket:
    """Build and independently reverify one promotion-native rehearsal packet."""
    source = _source(_json(adapter_dry_run_fixture_result_packet))
    fixture = _json(reference_rehearsal_fixture)
    if not isinstance(fixture, dict):
        raise CanonicalPromotionReferenceAdapterRehearsalError("PRAR_FIXTURE_INVALID")
    rehearsed = _aware(rehearsed_at, "PRAR_REHEARSED_AT_INVALID")
    if rehearsed < _aware(source.resulted_at, "PRAR_SOURCE_FIXTURE_RESULT_INVALID"):
        raise CanonicalPromotionReferenceAdapterRehearsalError(
            "PRAR_REHEARSED_BEFORE_RESULT"
        )
    intent = _intent(source)
    _descriptor(source, intent)
    source_raw = source.model_dump(mode="json")
    steps = [_json(item) for item in source.planned_steps]
    fixtures = [_json(item) for item in source.fixture_step_results]
    results = _results(source, fixture)
    raw = {
        "format_version": FORMAT_VERSION,
        "rehearsal_mechanism": REHEARSAL_MECHANISM,
        "rehearsed_at": rehearsed.isoformat(),
        "reference_rehearsal_fixture": fixture,
        "source_adapter_dry_run_fixture_result_id": source.adapter_dry_run_fixture_result_id,
        "source_adapter_dry_run_fixture_result_hash": source.adapter_dry_run_fixture_result_hash,
        "source_adapter_dry_run_fixture_result_packet": source_raw,
        **{field: source_raw[field] for field in LINEAGE_FIELDS},
        "execution_intent": source.execution_intent,
        "execution_intent_id": source.execution_intent_id,
        "execution_intent_hash": source.execution_intent_hash,
        "adapter_contract_descriptor": source.adapter_contract_descriptor,
        "adapter_contract_id": source.adapter_contract_id,
        "adapter_contract_hash": source.adapter_contract_hash,
        "adapter_contract_version": source.adapter_contract_version,
        "planned_steps": steps,
        "planned_step_digest": source.planned_step_digest,
        "fixture_step_results": fixtures,
        "fixture_result_digest": source.fixture_result_digest,
        "reference_rehearsal_results": results,
        "reference_rehearsal_result_digest": _digest(RESULTS_DOMAIN, results),
        "local_rehearsal_checks": LOCAL_CHECKS,
        "local_rehearsal_checks_digest": _digest(LOCAL_CHECKS_DOMAIN, LOCAL_CHECKS),
        "future_requirements": FUTURE_REQUIREMENTS,
        "future_requirements_digest": _digest(FUTURE_REQUIREMENTS_DOMAIN, FUTURE_REQUIREMENTS),
        "reference_rehearsal_status": STATUS,
        "ready_for_promotion_native_live_adapter_dry_run_request": True,
        "scope_limitations": SCOPE_LIMITATIONS,
    }
    digest = _packet_hash(raw)
    raw["promotion_reference_rehearsal_hash"] = digest
    raw["promotion_reference_rehearsal_id"] = f"prar:v1:sha256:{digest}"
    return verify_canonical_promotion_reference_adapter_in_memory_rehearsal_packet(raw)


def verify_canonical_promotion_reference_adapter_in_memory_rehearsal_packet(
    packet: Any,
) -> CanonicalPromotionReferenceAdapterInMemoryRehearsalPacket:
    """Fail closed while independently reconstructing every rehearsal binding."""
    try:
        candidate = CanonicalPromotionReferenceAdapterInMemoryRehearsalPacket.model_validate(_json(packet))
        raw = candidate.model_dump(mode="json")
        source = _source(candidate.source_adapter_dry_run_fixture_result_packet)
        intent = _intent(source)
        _descriptor(source, intent)
        if (candidate.source_adapter_dry_run_fixture_result_id != source.adapter_dry_run_fixture_result_id
                or candidate.source_adapter_dry_run_fixture_result_hash != source.adapter_dry_run_fixture_result_hash
                or any(getattr(candidate, field) != getattr(source, field) for field in LINEAGE_FIELDS)
                or candidate.execution_intent != intent.to_dict()
                or candidate.execution_intent_id != intent.execution_intent_id
                or candidate.execution_intent_hash != hash_execution_intent(intent)
                or candidate.adapter_contract_descriptor != source.adapter_contract_descriptor
                or candidate.adapter_contract_id != source.adapter_contract_id
                or candidate.adapter_contract_hash != source.adapter_contract_hash
                or candidate.adapter_contract_version != source.adapter_contract_version):
            raise CanonicalPromotionReferenceAdapterRehearsalError("PRAR_SOURCE_BINDING_MISMATCH")
        if _aware(candidate.rehearsed_at, "PRAR_REHEARSED_AT_INVALID") < _aware(source.resulted_at, "PRAR_SOURCE_FIXTURE_RESULT_INVALID"):
            raise CanonicalPromotionReferenceAdapterRehearsalError("PRAR_REHEARSED_BEFORE_RESULT")
        steps = [_json(item) for item in source.planned_steps]
        fixtures = [_json(item) for item in source.fixture_step_results]
        if (list(candidate.planned_steps) != steps
                or candidate.planned_step_digest != source.planned_step_digest
                or candidate.planned_step_digest != plan_digest(STEPS_DOMAIN, steps)):
            raise CanonicalPromotionReferenceAdapterRehearsalError("PRAR_PLANNED_STEPS_MISMATCH")
        if (list(candidate.fixture_step_results) != fixtures
                or candidate.fixture_result_digest != source.fixture_result_digest
                or candidate.fixture_result_digest != fixture_digest(FIXTURE_RESULTS_DOMAIN, fixtures)):
            raise CanonicalPromotionReferenceAdapterRehearsalError("PRAR_FIXTURE_RESULTS_MISMATCH")
        expected = _results(source, candidate.reference_rehearsal_fixture)
        results = [_json(item) for item in candidate.reference_rehearsal_results]
        if len(results) != 7 or [item["planned_adapter_method"] for item in results] != list(PLANNED_METHODS):
            raise CanonicalPromotionReferenceAdapterRehearsalError("PRAR_REHEARSAL_RESULTS_INVALID")
        for result, template, step, fixture in zip(results, expected, steps, fixtures, strict=True):
            if result != template or result["fixture_step_result_id"] != fixture["step_result_id"] or result["planned_step_id"] != step["step_id"]:
                raise CanonicalPromotionReferenceAdapterRehearsalError("PRAR_REHEARSAL_RESULTS_INVALID")
        if candidate.reference_rehearsal_result_digest != _digest(RESULTS_DOMAIN, results):
            raise CanonicalPromotionReferenceAdapterRehearsalError("PRAR_REHEARSAL_RESULTS_INVALID")
        if (candidate.local_rehearsal_checks != LOCAL_CHECKS
                or candidate.local_rehearsal_checks_digest != _digest(LOCAL_CHECKS_DOMAIN, LOCAL_CHECKS)
                or candidate.future_requirements != FUTURE_REQUIREMENTS
                or candidate.future_requirements_digest != _digest(FUTURE_REQUIREMENTS_DOMAIN, FUTURE_REQUIREMENTS)
                or candidate.scope_limitations != SCOPE_LIMITATIONS):
            raise CanonicalPromotionReferenceAdapterRehearsalError("PRAR_CANONICAL_CHECKS_MISMATCH")
        digest = _packet_hash(raw)
        if candidate.promotion_reference_rehearsal_hash != digest or candidate.promotion_reference_rehearsal_id != f"prar:v1:sha256:{digest}":
            raise CanonicalPromotionReferenceAdapterRehearsalError("PRAR_PACKET_IDENTITY_MISMATCH")
        return candidate
    except CanonicalPromotionReferenceAdapterRehearsalError:
        raise
    except (TypeError, ValueError, ValidationError, KeyError) as exc:
        raise CanonicalPromotionReferenceAdapterRehearsalError("PRAR_PACKET_INVALID") from exc
