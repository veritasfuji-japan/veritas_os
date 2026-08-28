"""Promotion-native canonical adapter dry-run planning without effects.

The packet produced here describes future adapter calls.  It does not create an
adapter, invoke any method, prove approval or authority, write a TrustLog, or
authorize Bind.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from veritas_os.policy.adapter_dry_run_plan import (
    AdapterDryRunStepDescriptor,
    build_canonical_adapter_dry_run_step_descriptors,
)
from veritas_os.policy.bind_adapter_contract_selection import (
    BindAdapterContractSelectionError,
    verify_bind_adapter_contract_descriptor,
)
from veritas_os.policy.bind_artifacts import ExecutionIntent, hash_execution_intent
from veritas_os.policy.canonical_promotion_bind_adapter_contract_selection import (
    CanonicalPromotionBindAdapterContractSelectionError,
    CanonicalPromotionBindAdapterContractSelectionPacket,
    verify_canonical_promotion_bind_adapter_contract_selection_packet,
)

FORMAT_VERSION = "canonical-promotion-adapter-dry-run-plan/v1"
PLAN_MECHANISM = "plan_promotion_adapter_dry_run_without_invocation/v1"
STEPS_DOMAIN = "veritas.promotion-adapter-dry-run-plan.steps/v1"
LOCAL_CHECKS_DOMAIN = "veritas.promotion-adapter-dry-run-plan.local-checks/v1"
FUTURE_REQUIREMENTS_DOMAIN = (
    "veritas.promotion-adapter-dry-run-plan.future-requirements/v1"
)
PACKET_DOMAIN = "veritas.promotion-adapter-dry-run-plan.packet/v1"
PLAN_STATUS = "PROMOTION_NATIVE_ADAPTER_DRY_RUN_PLANNED_NO_EFFECT"

LOCAL_PLAN_CHECKS = {
    key: True
    for key in (
        "promotion_adapter_selection_verified",
        "execution_intent_object_verified",
        "execution_intent_id_verified",
        "execution_intent_hash_verified",
        "adapter_descriptor_verified",
        "adapter_descriptor_hash_verified",
        "adapter_descriptor_scope_matches_intent",
        "planned_steps_ordered",
        "planned_methods_declared",
        "no_apply_step",
        "no_postcondition_execution",
        "no_revert_execution",
        "planned_after_adapter_contract_selection",
        "approval_context_preserved",
        "policy_lineage_preserved",
        "no_adapter_instance",
        "no_adapter_invocation",
        "no_bind_invocation",
        "no_bind_receipt_created",
        "no_trustlog_write",
        "no_network",
        "no_filesystem",
        "no_external_effect",
        "no_human_approval_proof",
        "no_authority_evidence_proof",
    )
}
FUTURE_DRY_RUN_EXECUTION_REQUIREMENTS = {
    key: True
    for key in (
        "adapter_instance_required",
        "describe_target_call_required",
        "idempotency_key_plan_required",
        "snapshot_call_required",
        "state_fingerprint_call_required",
        "authority_revalidation_call_required",
        "constraint_validation_call_required",
        "runtime_risk_assessment_call_required",
        "dry_run_result_packet_required",
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
    "NOT_HUMAN_APPROVAL_PROOF",
    "NOT_AUTHORITY_EVIDENCE_PROOF",
    "NOT_EXTERNAL_EFFECT",
    "NOT_OPERATION_COMMIT",
    "NOT_TRUSTLOG_WRITE",
    "NOT_LIVE_STATE_CHECK",
    "NOT_RUNTIME_RISK_ACCEPTANCE",
    "NOT_AUTHORITY_REVALIDATION",
    "NOT_CONSTRAINT_REVALIDATION",
    "NOT_POSTCONDITION_VERIFICATION",
    "NOT_ROLLBACK_PROOF",
)


class CanonicalPromotionAdapterDryRunPlanError(ValueError):
    """Stable fail-closed refusal for promotion-native plan processing."""


class CanonicalPromotionAdapterDryRunPlanPacket(BaseModel):
    """Immutable promotion-native plan containing no executable operation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format_version: Literal["canonical-promotion-adapter-dry-run-plan/v1"]
    adapter_dry_run_plan_id: str = Field(pattern=r"^padp:v1:sha256:[0-9a-f]{64}$")
    adapter_dry_run_plan_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_mechanism: Literal["plan_promotion_adapter_dry_run_without_invocation/v1"]
    planned_at: str
    source_adapter_contract_selection_id: str
    source_adapter_contract_selection_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_adapter_contract_selection_packet: dict[str, Any]
    source_bind_preflight_adjudication_id: str
    source_bind_preflight_adjudication_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_pre_bind_validation_id: str
    source_pre_bind_validation_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_readiness_id: str
    source_readiness_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_promotion_id: str
    source_promotion_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_decision_identity: dict[str, Any]
    candidate_identity: dict[str, Any]
    selected_action_lineage: dict[str, Any]
    policy_snapshot_lineage: dict[str, Any]
    execution_intent: dict[str, Any]
    execution_intent_id: str
    execution_intent_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    adapter_contract_descriptor: dict[str, Any]
    adapter_contract_id: str
    adapter_contract_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    adapter_contract_version: Literal["bind-adapter-contract/v1"]
    approval_context: dict[str, Any]
    policy_lineage: dict[str, Any]
    planned_steps: tuple[AdapterDryRunStepDescriptor, ...]
    planned_step_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    local_plan_checks: dict[str, bool]
    local_plan_checks_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    future_dry_run_execution_requirements: dict[str, bool]
    future_dry_run_execution_requirements_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    dry_run_plan_status: Literal["PROMOTION_NATIVE_ADAPTER_DRY_RUN_PLANNED_NO_EFFECT"]
    ready_for_promotion_native_adapter_dry_run_execution: Literal[True]
    scope_limitations: tuple[str, ...]


def _json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise CanonicalPromotionAdapterDryRunPlanError("PADP_PACKET_INVALID")
        return value
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, Mapping) and all(isinstance(key, str) for key in value):
        return {key: _json_value(item) for key, item in value.items()}
    raise CanonicalPromotionAdapterDryRunPlanError("PADP_PACKET_INVALID")


def _aware(value: Any, code: str) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise CanonicalPromotionAdapterDryRunPlanError(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CanonicalPromotionAdapterDryRunPlanError(code)
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
            if key not in {"adapter_dry_run_plan_id", "adapter_dry_run_plan_hash"}
        },
    )


def _verified_source(
    value: Any,
) -> CanonicalPromotionBindAdapterContractSelectionPacket:
    try:
        return verify_canonical_promotion_bind_adapter_contract_selection_packet(value)
    except (
        CanonicalPromotionBindAdapterContractSelectionError,
        TypeError,
        ValueError,
    ) as exc:
        raise CanonicalPromotionAdapterDryRunPlanError(
            "PADP_ADAPTER_SELECTION_INVALID"
        ) from exc


def _verified_intent(
    source: CanonicalPromotionBindAdapterContractSelectionPacket,
) -> ExecutionIntent:
    try:
        intent = ExecutionIntent(**source.execution_intent)
    except (TypeError, ValueError) as exc:
        raise CanonicalPromotionAdapterDryRunPlanError(
            "PADP_EXECUTION_INTENT_INVALID"
        ) from exc
    if intent.to_dict() != source.execution_intent:
        raise CanonicalPromotionAdapterDryRunPlanError(
            "PADP_EXECUTION_INTENT_OBJECT_MISMATCH"
        )
    if intent.execution_intent_id != source.execution_intent_id:
        raise CanonicalPromotionAdapterDryRunPlanError(
            "PADP_EXECUTION_INTENT_ID_MISMATCH"
        )
    if hash_execution_intent(intent) != source.execution_intent_hash:
        raise CanonicalPromotionAdapterDryRunPlanError(
            "PADP_EXECUTION_INTENT_HASH_MISMATCH"
        )
    return intent


def _source_bindings(
    source: CanonicalPromotionBindAdapterContractSelectionPacket,
) -> dict[str, Any]:
    keys = (
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
    )
    return {key: getattr(source, key) for key in keys}


def build_canonical_promotion_adapter_dry_run_plan_packet(
    adapter_contract_selection_packet: (
        CanonicalPromotionBindAdapterContractSelectionPacket | Mapping[str, Any]
    ),
    planned_at: datetime,
) -> CanonicalPromotionAdapterDryRunPlanPacket:
    """Build a canonical inert plan from one verified promotion selection."""
    planned = _aware(planned_at, "PADP_PLANNED_AT_INVALID")
    source = _verified_source(_json_value(adapter_contract_selection_packet))
    if planned < _aware(source.selected_at, "PADP_SOURCE_TIME_INVALID"):
        raise CanonicalPromotionAdapterDryRunPlanError("PADP_PLANNED_BEFORE_SELECTION")
    intent = _verified_intent(source)
    try:
        descriptor = verify_bind_adapter_contract_descriptor(
            source.adapter_contract_descriptor, intent
        )
    except (BindAdapterContractSelectionError, TypeError, ValueError) as exc:
        raise CanonicalPromotionAdapterDryRunPlanError(
            "PADP_DESCRIPTOR_INVALID"
        ) from exc
    steps = build_canonical_adapter_dry_run_step_descriptors()
    raw = {
        "format_version": FORMAT_VERSION,
        "adapter_dry_run_plan_id": "padp:v1:sha256:" + "0" * 64,
        "adapter_dry_run_plan_hash": "0" * 64,
        "plan_mechanism": PLAN_MECHANISM,
        "planned_at": planned.isoformat(),
        "source_adapter_contract_selection_id": source.adapter_contract_selection_id,
        "source_adapter_contract_selection_hash": source.adapter_contract_selection_hash,
        "source_adapter_contract_selection_packet": source.model_dump(mode="json"),
        **_source_bindings(source),
        "execution_intent": intent.to_dict(),
        "execution_intent_id": intent.execution_intent_id,
        "execution_intent_hash": hash_execution_intent(intent),
        "adapter_contract_descriptor": descriptor.model_dump(mode="json"),
        "adapter_contract_id": descriptor.adapter_contract_id,
        "adapter_contract_hash": descriptor.adapter_contract_hash,
        "adapter_contract_version": descriptor.adapter_contract_version,
        "approval_context": source.approval_context,
        "policy_lineage": source.policy_lineage,
        "planned_steps": steps,
        "planned_step_digest": _digest(STEPS_DOMAIN, steps),
        "local_plan_checks": LOCAL_PLAN_CHECKS,
        "local_plan_checks_digest": _digest(LOCAL_CHECKS_DOMAIN, LOCAL_PLAN_CHECKS),
        "future_dry_run_execution_requirements": FUTURE_DRY_RUN_EXECUTION_REQUIREMENTS,
        "future_dry_run_execution_requirements_digest": _digest(
            FUTURE_REQUIREMENTS_DOMAIN, FUTURE_DRY_RUN_EXECUTION_REQUIREMENTS
        ),
        "dry_run_plan_status": PLAN_STATUS,
        "ready_for_promotion_native_adapter_dry_run_execution": True,
        "scope_limitations": SCOPE_LIMITATIONS,
    }
    digest = _packet_hash(raw)
    raw["adapter_dry_run_plan_hash"] = digest
    raw["adapter_dry_run_plan_id"] = f"padp:v1:sha256:{digest}"
    return verify_canonical_promotion_adapter_dry_run_plan_packet(raw)


def verify_canonical_promotion_adapter_dry_run_plan_packet(
    packet: CanonicalPromotionAdapterDryRunPlanPacket | Mapping[str, Any],
) -> CanonicalPromotionAdapterDryRunPlanPacket:
    """Strictly reverify the source and every content-addressed plan binding."""
    try:
        parsed = CanonicalPromotionAdapterDryRunPlanPacket.model_validate(
            _json_value(packet)
        )
        raw = parsed.model_dump(mode="json")
        source = _verified_source(parsed.source_adapter_contract_selection_packet)
        intent = _verified_intent(source)
        descriptor = verify_bind_adapter_contract_descriptor(
            parsed.adapter_contract_descriptor, intent
        )
        if _aware(parsed.planned_at, "PADP_PLANNED_AT_INVALID") < _aware(
            source.selected_at, "PADP_SOURCE_TIME_INVALID"
        ):
            raise CanonicalPromotionAdapterDryRunPlanError(
                "PADP_PLANNED_BEFORE_SELECTION"
            )
        if (
            parsed.source_adapter_contract_selection_id
            != source.adapter_contract_selection_id
            or parsed.source_adapter_contract_selection_hash
            != source.adapter_contract_selection_hash
            or any(
                getattr(parsed, key) != value
                for key, value in _source_bindings(source).items()
            )
            or parsed.execution_intent != source.execution_intent
            or parsed.execution_intent != intent.to_dict()
            or parsed.execution_intent_id != source.execution_intent_id
            or parsed.execution_intent_id != intent.execution_intent_id
            or parsed.execution_intent_hash != source.execution_intent_hash
            or parsed.execution_intent_hash != hash_execution_intent(intent)
            or parsed.approval_context != source.approval_context
            or parsed.approval_context != intent.approval_context
            or parsed.policy_lineage != source.policy_lineage
            or parsed.policy_lineage != intent.policy_lineage
        ):
            raise CanonicalPromotionAdapterDryRunPlanError(
                "PADP_SOURCE_BINDING_MISMATCH"
            )
        descriptor_raw = descriptor.model_dump(mode="json")
        if (
            parsed.adapter_contract_descriptor != descriptor_raw
            or parsed.adapter_contract_descriptor != source.adapter_contract_descriptor
            or parsed.adapter_contract_id != descriptor.adapter_contract_id
            or parsed.adapter_contract_id != source.adapter_contract_id
            or parsed.adapter_contract_hash != descriptor.adapter_contract_hash
            or parsed.adapter_contract_hash != source.adapter_contract_hash
            or parsed.adapter_contract_version != descriptor.adapter_contract_version
            or parsed.adapter_contract_version != source.adapter_contract_version
        ):
            raise CanonicalPromotionAdapterDryRunPlanError(
                "PADP_DESCRIPTOR_BINDING_MISMATCH"
            )
        expected_steps = tuple(
            AdapterDryRunStepDescriptor.model_validate(item)
            for item in build_canonical_adapter_dry_run_step_descriptors()
        )
        if parsed.planned_steps != expected_steps:
            raise CanonicalPromotionAdapterDryRunPlanError("PADP_STEPS_MISMATCH")
        steps_raw = [step.model_dump(mode="json") for step in parsed.planned_steps]
        if parsed.planned_step_digest != _digest(STEPS_DOMAIN, steps_raw):
            raise CanonicalPromotionAdapterDryRunPlanError("PADP_STEP_DIGEST_MISMATCH")
        if any(
            step.planned_adapter_method in {"apply", "verify_postconditions", "revert"}
            for step in parsed.planned_steps
        ):
            raise CanonicalPromotionAdapterDryRunPlanError("PADP_EFFECT_STEP_FORBIDDEN")
        if (
            parsed.local_plan_checks != LOCAL_PLAN_CHECKS
            or parsed.local_plan_checks_digest
            != _digest(LOCAL_CHECKS_DOMAIN, LOCAL_PLAN_CHECKS)
        ):
            raise CanonicalPromotionAdapterDryRunPlanError("PADP_LOCAL_CHECKS_MISMATCH")
        if (
            parsed.future_dry_run_execution_requirements
            != FUTURE_DRY_RUN_EXECUTION_REQUIREMENTS
            or parsed.future_dry_run_execution_requirements_digest
            != _digest(
                FUTURE_REQUIREMENTS_DOMAIN, FUTURE_DRY_RUN_EXECUTION_REQUIREMENTS
            )
        ):
            raise CanonicalPromotionAdapterDryRunPlanError(
                "PADP_FUTURE_REQUIREMENTS_MISMATCH"
            )
        if parsed.scope_limitations != SCOPE_LIMITATIONS:
            raise CanonicalPromotionAdapterDryRunPlanError(
                "PADP_SCOPE_LIMITATIONS_MISMATCH"
            )
        digest = _packet_hash(raw)
        if parsed.adapter_dry_run_plan_hash != digest:
            raise CanonicalPromotionAdapterDryRunPlanError("PADP_PACKET_HASH_MISMATCH")
        if parsed.adapter_dry_run_plan_id != f"padp:v1:sha256:{digest}":
            raise CanonicalPromotionAdapterDryRunPlanError("PADP_PACKET_ID_MISMATCH")
        return parsed
    except CanonicalPromotionAdapterDryRunPlanError:
        raise
    except (
        BindAdapterContractSelectionError,
        TypeError,
        ValueError,
        ValidationError,
    ) as exc:
        raise CanonicalPromotionAdapterDryRunPlanError("PADP_PACKET_INVALID") from exc
