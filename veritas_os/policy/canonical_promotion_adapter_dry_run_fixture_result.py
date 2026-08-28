"""Record promotion-native adapter dry-run fixture evidence without effects.

This boundary accepts only a verified promotion-native dry-run plan and inert
fixture values.  It never creates or invokes an adapter, authorizes Bind,
proves human approval, observes live state, or writes TrustLog.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from veritas_os.policy.adapter_dry_run_result import (
    AdapterDryRunFixtureStepResult,
    FIXTURE_VALUE_SUMMARY,
    validate_fixture_step_results,
)
from veritas_os.policy.bind_adapter_contract_selection import (
    BindAdapterContractSelectionError,
    verify_bind_adapter_contract_descriptor,
)
from veritas_os.policy.bind_artifacts import ExecutionIntent, hash_execution_intent
from veritas_os.policy.canonical_promotion_adapter_dry_run_plan import (
    STEPS_DOMAIN as PLAN_STEPS_DOMAIN,
    CanonicalPromotionAdapterDryRunPlanError,
    CanonicalPromotionAdapterDryRunPlanPacket,
    _digest as _plan_digest,
    verify_canonical_promotion_adapter_dry_run_plan_packet,
)

FORMAT_VERSION = "canonical-promotion-adapter-dry-run-fixture-result/v1"
RESULT_MECHANISM = (
    "record_promotion_adapter_dry_run_fixture_result_without_invocation/v1"
)
VALUE_DOMAIN = "veritas.promotion-adapter-dry-run-fixture-result.value/v1"
RESULTS_DOMAIN = "veritas.promotion-adapter-dry-run-fixture-result.results/v1"
LOCAL_CHECKS_DOMAIN = (
    "veritas.promotion-adapter-dry-run-fixture-result.local-checks/v1"
)
FUTURE_REQUIREMENTS_DOMAIN = (
    "veritas.promotion-adapter-dry-run-fixture-result.future-requirements/v1"
)
PACKET_DOMAIN = "veritas.promotion-adapter-dry-run-fixture-result.packet/v1"
RESULT_STATUS = "PROMOTION_NATIVE_ADAPTER_DRY_RUN_FIXTURE_RESULT_RECORDED_NO_EFFECT"

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
SCOPE_LIMITATIONS = (
    "NOT_EXECUTION_AUTHORITY",
    "NOT_BIND_AUTHORIZATION",
    "NOT_BIND_RECEIPT",
    "NOT_BIND_INVOCATION",
    "NOT_LIVE_ADAPTER_RESULT",
    "NOT_LIVE_STATE_CHECK",
    "NOT_HUMAN_APPROVAL_PROOF",
    "NOT_AUTHORITY_EVIDENCE_PROOF",
    "NOT_RUNTIME_RISK_ACCEPTANCE",
    "NOT_EXTERNAL_EFFECT",
    "NOT_OPERATION_COMMIT",
    "NOT_TRUSTLOG_WRITE",
)
LOCAL_RESULT_CHECKS = {
    key: True
    for key in (
        "promotion_adapter_dry_run_plan_verified",
        "execution_intent_object_verified",
        "execution_intent_id_verified",
        "execution_intent_hash_verified",
        "adapter_descriptor_verified",
        "adapter_descriptor_target_verified",
        "planned_steps_preserved",
        "fixture_results_ordered",
        "fixture_results_match_planned_steps",
        "fixture_values_digest_verified",
        "no_apply_result",
        "no_postcondition_result",
        "no_revert_result",
        "resulted_after_plan",
        "no_adapter_instance",
        "no_adapter_invocation",
        "no_network",
        "no_filesystem",
        "no_external_effect",
        "no_live_state_claim",
        "no_human_approval_proof",
        "no_authority_evidence_proof",
    )
}
FUTURE_REFERENCE_REHEARSAL_REQUIREMENTS = {
    key: True
    for key in (
        "fresh_verified_source_gate_required",
        "adapter_instance_required",
        "all_seven_adapter_calls_required",
        "live_result_packet_required",
        "fixture_result_must_not_be_treated_as_live",
        "human_approval_proof_still_deferred",
        "authority_evidence_proof_still_deferred",
        "trustlog_policy_still_deferred",
        "bind_receipt_still_deferred",
        "apply_still_forbidden",
    )
}


class CanonicalPromotionAdapterDryRunFixtureResultError(ValueError):
    """Stable fail-closed promotion fixture-result refusal."""


class CanonicalPromotionAdapterDryRunFixtureResultPacket(BaseModel):
    """Immutable promotion-native binding to seven inert fixture results."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format_version: Literal[
        "canonical-promotion-adapter-dry-run-fixture-result/v1"
    ]
    adapter_dry_run_fixture_result_id: str = Field(
        pattern=r"^padr:v1:sha256:[0-9a-f]{64}$"
    )
    adapter_dry_run_fixture_result_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_mechanism: Literal[
        "record_promotion_adapter_dry_run_fixture_result_without_invocation/v1"
    ]
    resulted_at: str
    source_adapter_dry_run_plan_id: str
    source_adapter_dry_run_plan_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_adapter_dry_run_plan_packet: dict[str, Any]
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
    execution_intent: dict[str, Any]
    execution_intent_id: str
    execution_intent_hash: str
    adapter_contract_descriptor: dict[str, Any]
    adapter_contract_id: str
    adapter_contract_hash: str
    adapter_contract_version: Literal["bind-adapter-contract/v1"]
    approval_context: dict[str, Any]
    policy_lineage: dict[str, Any]
    planned_steps: tuple[dict[str, Any], ...]
    planned_step_digest: str
    fixture_step_results: tuple[AdapterDryRunFixtureStepResult, ...]
    fixture_result_digest: str
    local_result_checks: dict[str, bool]
    local_result_checks_digest: str
    future_reference_rehearsal_requirements: dict[str, bool]
    future_reference_rehearsal_requirements_digest: str
    dry_run_fixture_result_status: Literal[
        "PROMOTION_NATIVE_ADAPTER_DRY_RUN_FIXTURE_RESULT_RECORDED_NO_EFFECT"
    ]
    ready_for_promotion_native_reference_rehearsal: Literal[True]
    scope_limitations: tuple[str, ...]


def _json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise CanonicalPromotionAdapterDryRunFixtureResultError(
                "PADR_PACKET_INVALID"
            )
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise CanonicalPromotionAdapterDryRunFixtureResultError(
                "PADR_RESULTED_AT_INVALID"
            )
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, Mapping) and all(isinstance(key, str) for key in value):
        return {key: _json_value(item) for key, item in value.items()}
    raise CanonicalPromotionAdapterDryRunFixtureResultError("PADR_PACKET_INVALID")


def _aware(value: Any, code: str) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise CanonicalPromotionAdapterDryRunFixtureResultError(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CanonicalPromotionAdapterDryRunFixtureResultError(code)
    return parsed


def _digest(domain: str, value: Any) -> str:
    encoded = json.dumps(
        {"domain": domain, "value": _json_value(value)},
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _packet_hash(raw: dict[str, Any]) -> str:
    return _digest(
        PACKET_DOMAIN,
        {
            key: value
            for key, value in raw.items()
            if key
            not in {
                "adapter_dry_run_fixture_result_id",
                "adapter_dry_run_fixture_result_hash",
            }
        },
    )


def _verified_plan(value: Any) -> CanonicalPromotionAdapterDryRunPlanPacket:
    try:
        return verify_canonical_promotion_adapter_dry_run_plan_packet(value)
    except (CanonicalPromotionAdapterDryRunPlanError, TypeError, ValueError) as exc:
        raise CanonicalPromotionAdapterDryRunFixtureResultError(
            "PADR_SOURCE_PLAN_INVALID"
        ) from exc


def _intent(source: CanonicalPromotionAdapterDryRunPlanPacket) -> ExecutionIntent:
    try:
        intent = ExecutionIntent(**source.execution_intent)
    except (TypeError, ValueError) as exc:
        raise CanonicalPromotionAdapterDryRunFixtureResultError(
            "PADR_EXECUTION_INTENT_INVALID"
        ) from exc
    if intent.to_dict() != source.execution_intent:
        raise CanonicalPromotionAdapterDryRunFixtureResultError(
            "PADR_EXECUTION_INTENT_OBJECT_MISMATCH"
        )
    if intent.execution_intent_id != source.execution_intent_id:
        raise CanonicalPromotionAdapterDryRunFixtureResultError(
            "PADR_EXECUTION_INTENT_ID_MISMATCH"
        )
    if hash_execution_intent(intent) != source.execution_intent_hash:
        raise CanonicalPromotionAdapterDryRunFixtureResultError(
            "PADR_EXECUTION_INTENT_HASH_MISMATCH"
        )
    return intent


def _descriptor(source: CanonicalPromotionAdapterDryRunPlanPacket, intent: ExecutionIntent):
    try:
        descriptor = verify_bind_adapter_contract_descriptor(
            source.adapter_contract_descriptor, intent
        )
    except (BindAdapterContractSelectionError, TypeError, ValueError) as exc:
        raise CanonicalPromotionAdapterDryRunFixtureResultError(
            "PADR_DESCRIPTOR_INVALID"
        ) from exc
    if (
        descriptor.model_dump(mode="json") != source.adapter_contract_descriptor
        or descriptor.adapter_contract_id != source.adapter_contract_id
        or descriptor.adapter_contract_hash != source.adapter_contract_hash
        or descriptor.adapter_contract_version != source.adapter_contract_version
    ):
        raise CanonicalPromotionAdapterDryRunFixtureResultError(
            "PADR_DESCRIPTOR_MISMATCH"
        )
    return descriptor


LINEAGE_FIELDS = (
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


def _fixture_results(supplied: Any, steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return validate_fixture_step_results(
        _json_value(supplied),
        steps,
        value_domain=VALUE_DOMAIN,
        result_limitations=RESULT_LIMITATIONS,
        error_type=CanonicalPromotionAdapterDryRunFixtureResultError,
        error_code="PADR_FIXTURE_RESULTS_INVALID",
        live_error_code="PADR_LIVE_RESULT_FORBIDDEN",
        forbidden_error_code="PADR_EFFECT_RESULT_FORBIDDEN",
    )


def build_canonical_promotion_adapter_dry_run_fixture_result_packet(
    adapter_dry_run_plan_packet: CanonicalPromotionAdapterDryRunPlanPacket
    | Mapping[str, Any],
    fixture_step_results: Any,
    resulted_at: datetime,
) -> CanonicalPromotionAdapterDryRunFixtureResultPacket:
    """Build deterministic no-effect evidence from one verified native plan."""
    resulted = _aware(resulted_at, "PADR_RESULTED_AT_INVALID")
    source = _verified_plan(_json_value(adapter_dry_run_plan_packet))
    if resulted < _aware(source.planned_at, "PADR_SOURCE_PLAN_INVALID"):
        raise CanonicalPromotionAdapterDryRunFixtureResultError(
            "PADR_RESULTED_BEFORE_PLAN"
        )
    intent = _intent(source)
    _descriptor(source, intent)
    steps = [step.model_dump(mode="json") for step in source.planned_steps]
    if source.planned_step_digest != _plan_digest(PLAN_STEPS_DOMAIN, steps):
        raise CanonicalPromotionAdapterDryRunFixtureResultError(
            "PADR_PLANNED_STEP_DIGEST_MISMATCH"
        )
    results = _fixture_results(fixture_step_results, steps)
    source_raw = source.model_dump(mode="json")
    raw = {
        "format_version": FORMAT_VERSION,
        "result_mechanism": RESULT_MECHANISM,
        "resulted_at": resulted.isoformat(),
        "source_adapter_dry_run_plan_id": source.adapter_dry_run_plan_id,
        "source_adapter_dry_run_plan_hash": source.adapter_dry_run_plan_hash,
        "source_adapter_dry_run_plan_packet": source_raw,
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
        "fixture_step_results": results,
        "fixture_result_digest": _digest(RESULTS_DOMAIN, results),
        "local_result_checks": LOCAL_RESULT_CHECKS,
        "local_result_checks_digest": _digest(
            LOCAL_CHECKS_DOMAIN, LOCAL_RESULT_CHECKS
        ),
        "future_reference_rehearsal_requirements": (
            FUTURE_REFERENCE_REHEARSAL_REQUIREMENTS
        ),
        "future_reference_rehearsal_requirements_digest": _digest(
            FUTURE_REQUIREMENTS_DOMAIN, FUTURE_REFERENCE_REHEARSAL_REQUIREMENTS
        ),
        "dry_run_fixture_result_status": RESULT_STATUS,
        "ready_for_promotion_native_reference_rehearsal": True,
        "scope_limitations": SCOPE_LIMITATIONS,
    }
    digest = _packet_hash(raw)
    raw["adapter_dry_run_fixture_result_hash"] = digest
    raw["adapter_dry_run_fixture_result_id"] = f"padr:v1:sha256:{digest}"
    return verify_canonical_promotion_adapter_dry_run_fixture_result_packet(raw)


def verify_canonical_promotion_adapter_dry_run_fixture_result_packet(
    packet: Any,
) -> CanonicalPromotionAdapterDryRunFixtureResultPacket:
    """Independently reverify every source, semantic, lineage, and digest."""
    try:
        value = _json_value(packet)
        candidate = CanonicalPromotionAdapterDryRunFixtureResultPacket.model_validate(
            value
        )
        raw = candidate.model_dump(mode="json")
        source = _verified_plan(candidate.source_adapter_dry_run_plan_packet)
        intent = _intent(source)
        descriptor = _descriptor(source, intent)
        if (
            candidate.source_adapter_dry_run_plan_id != source.adapter_dry_run_plan_id
            or candidate.source_adapter_dry_run_plan_hash
            != source.adapter_dry_run_plan_hash
            or any(
                getattr(candidate, field) != getattr(source, field)
                for field in LINEAGE_FIELDS
            )
            or candidate.execution_intent != source.execution_intent
            or candidate.execution_intent != intent.to_dict()
            or candidate.execution_intent_id != source.execution_intent_id
            or candidate.execution_intent_id != intent.execution_intent_id
            or candidate.execution_intent_hash != source.execution_intent_hash
            or candidate.execution_intent_hash != hash_execution_intent(intent)
            or candidate.adapter_contract_descriptor
            != descriptor.model_dump(mode="json")
            or candidate.adapter_contract_id != source.adapter_contract_id
            or candidate.adapter_contract_hash != source.adapter_contract_hash
            or candidate.adapter_contract_version != source.adapter_contract_version
        ):
            raise CanonicalPromotionAdapterDryRunFixtureResultError(
                "PADR_SOURCE_BINDING_MISMATCH"
            )
        if _aware(candidate.resulted_at, "PADR_RESULTED_AT_INVALID") < _aware(
            source.planned_at, "PADR_SOURCE_PLAN_INVALID"
        ):
            raise CanonicalPromotionAdapterDryRunFixtureResultError(
                "PADR_RESULTED_BEFORE_PLAN"
            )
        steps = [step.model_dump(mode="json") for step in source.planned_steps]
        if (
            list(candidate.planned_steps) != steps
            or candidate.planned_step_digest != source.planned_step_digest
            or candidate.planned_step_digest
            != _plan_digest(PLAN_STEPS_DOMAIN, steps)
        ):
            raise CanonicalPromotionAdapterDryRunFixtureResultError(
                "PADR_PLANNED_STEPS_MISMATCH"
            )
        results = _fixture_results(
            [item.model_dump(mode="json") for item in candidate.fixture_step_results],
            steps,
        )
        if candidate.fixture_result_digest != _digest(RESULTS_DOMAIN, results):
            raise CanonicalPromotionAdapterDryRunFixtureResultError(
                "PADR_FIXTURE_RESULT_DIGEST_MISMATCH"
            )
        if (
            candidate.local_result_checks != LOCAL_RESULT_CHECKS
            or candidate.local_result_checks_digest
            != _digest(LOCAL_CHECKS_DOMAIN, LOCAL_RESULT_CHECKS)
            or candidate.future_reference_rehearsal_requirements
            != FUTURE_REFERENCE_REHEARSAL_REQUIREMENTS
            or candidate.future_reference_rehearsal_requirements_digest
            != _digest(
                FUTURE_REQUIREMENTS_DOMAIN,
                FUTURE_REFERENCE_REHEARSAL_REQUIREMENTS,
            )
            or candidate.scope_limitations != SCOPE_LIMITATIONS
        ):
            raise CanonicalPromotionAdapterDryRunFixtureResultError(
                "PADR_CANONICAL_CHECKS_MISMATCH"
            )
        digest = _packet_hash(raw)
        if candidate.adapter_dry_run_fixture_result_hash != digest:
            raise CanonicalPromotionAdapterDryRunFixtureResultError(
                "PADR_PACKET_HASH_MISMATCH"
            )
        if candidate.adapter_dry_run_fixture_result_id != f"padr:v1:sha256:{digest}":
            raise CanonicalPromotionAdapterDryRunFixtureResultError(
                "PADR_PACKET_ID_MISMATCH"
            )
        return candidate
    except CanonicalPromotionAdapterDryRunFixtureResultError:
        raise
    except (TypeError, ValueError, ValidationError) as exc:
        raise CanonicalPromotionAdapterDryRunFixtureResultError(
            "PADR_PACKET_INVALID"
        ) from exc
