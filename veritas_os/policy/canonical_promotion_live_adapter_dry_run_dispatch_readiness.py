"""Evaluate promotion-native dispatch readiness without performing effects.

This pure-data boundary proves only that a verified promotion-native dry-run
request may proceed to a separate, local endpoint-allowlist evaluation.  It
cannot resolve endpoints or credentials, instantiate adapters, dispatch, Bind,
or persist data.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from veritas_os.policy.bind_adapter_contract_selection import (
    BindAdapterContractSelectionError,
    verify_bind_adapter_contract_descriptor,
)
from veritas_os.policy.bind_artifacts import (
    ExecutionIntent,
    canonical_execution_intent_json,
    hash_execution_intent,
)
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_request import (
    CanonicalPromotionLiveAdapterDryRunRequestError,
    CanonicalPromotionLiveAdapterDryRunRequestPacket,
    verify_canonical_promotion_live_adapter_dry_run_request_packet,
)

FORMAT_VERSION = "canonical-promotion-live-adapter-dry-run-dispatch-readiness/v1"
DISPATCH_READINESS_MECHANISM = (
    "evaluate_promotion_live_adapter_dry_run_dispatch_readiness_without_dispatch/v1"
)
CHECKS_DOMAIN = "veritas.promotion-live-adapter-dry-run-dispatch-readiness.checks/v1"
FUTURE_REQUIREMENTS_DOMAIN = (
    "veritas.promotion-live-adapter-dry-run-dispatch-readiness.future-requirements/v1"
)
PACKET_DOMAIN = "veritas.promotion-live-adapter-dry-run-dispatch-readiness.packet/v1"

CHECK_NAMES = (
    "source_request_independently_verified",
    "source_request_not_dispatched",
    "exact_request_descriptor_preserved",
    "exact_dispatch_preconditions_preserved",
    "exact_execution_intent_preserved",
    "exact_adapter_descriptor_preserved",
    "promotion_native_lineage_preserved",
    "approval_context_preserved",
    "policy_lineage_preserved",
    "no_endpoint_material_or_contact",
    "no_credential_material_or_access",
    "no_network",
    "no_webhook",
    "no_adapter_instance_or_invocation",
    "no_bind",
    "no_trustlog",
    "endpoint_allowlist_evaluation_still_required",
    "credential_evaluation_still_required",
    "operator_pre_dispatch_review_still_required",
    "final_fresh_source_gate_still_required",
)
EFFECT_FIELDS = (
    "endpoint_resolved",
    "endpoint_contacted",
    "dns_used",
    "credential_resolved",
    "credential_accessed",
    "credential_material_embedded",
    "authorization_header_constructed",
    "network_used",
    "webhook_invoked",
    "live_adapter_instantiated",
    "live_adapter_method_invoked",
    "request_dispatched",
    "bind_invoked",
    "bind_authorization_issued",
    "bind_receipt_created",
    "trustlog_written",
    "filesystem_used",
    "database_used",
    "subprocess_used",
    "provider_called",
    "external_effect_used",
    "operation_committed",
    "apply_performed",
    "postcondition_verified",
    "rollback_or_revert_performed",
)
FUTURE_REQUIREMENT_NAMES = (
    "promotion_native_endpoint_allowlist_evaluation",
    "credential_resolution_and_scope_evaluation",
    "operator_pre_dispatch_review",
    "final_fresh_source_gate",
    "network_dispatch_boundary",
    "bind_authorization_boundary",
    "postcondition_and_rollback_boundary",
)
LINEAGE_FIELDS = (
    "source_live_adapter_dry_run_readiness_id",
    "source_live_adapter_dry_run_readiness_hash",
    "source_reference_rehearsal_id",
    "source_reference_rehearsal_hash",
    "source_adapter_dry_run_fixture_result_id",
    "source_adapter_dry_run_fixture_result_hash",
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
SCOPE_LIMITATIONS = (
    "NOT_NETWORK_DISPATCH",
    "NOT_REAL_BIND",
    "NOT_EXECUTION_AUTHORIZATION",
    "NOT_HUMAN_APPROVAL_PROOF",
    "NOT_AUTHORITY_EVIDENCE",
    "NOT_ENDPOINT_ALLOWLIST_EVALUATION",
    "NOT_CREDENTIAL_EVALUATION",
    "NOT_EXTERNAL_EFFECT",
)


class CanonicalPromotionLiveAdapterDryRunDispatchReadinessError(ValueError):
    """Stable fail-closed refusal for invalid promotion-native evidence."""


class PromotionDispatchReadinessCheck(BaseModel):
    """One ordered deterministic assertion with explicit no-effect states."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    check_id: str = Field(pattern=r"^pladrdr-check:v1:[1-9][0-9]*:[a-z0-9-]+$")
    ordinal: int = Field(ge=1, le=len(CHECK_NAMES))
    name: Literal[*CHECK_NAMES]
    mode: Literal["deterministic_local_dispatch_readiness_evaluation_only"]
    passed: Literal[True]
    evidence_ref: str = Field(min_length=1)
    endpoint_resolved: Literal[False]
    endpoint_contacted: Literal[False]
    dns_used: Literal[False]
    credential_resolved: Literal[False]
    credential_accessed: Literal[False]
    credential_material_embedded: Literal[False]
    authorization_header_constructed: Literal[False]
    network_used: Literal[False]
    webhook_invoked: Literal[False]
    live_adapter_instantiated: Literal[False]
    live_adapter_method_invoked: Literal[False]
    request_dispatched: Literal[False]
    bind_invoked: Literal[False]
    bind_authorization_issued: Literal[False]
    bind_receipt_created: Literal[False]
    trustlog_written: Literal[False]
    filesystem_used: Literal[False]
    database_used: Literal[False]
    subprocess_used: Literal[False]
    provider_called: Literal[False]
    external_effect_used: Literal[False]
    operation_committed: Literal[False]
    apply_performed: Literal[False]
    postcondition_verified: Literal[False]
    rollback_or_revert_performed: Literal[False]


class PromotionFutureDispatchRequirement(BaseModel):
    """A requirement explicitly unsatisfied until a future boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    ordinal: int = Field(ge=1, le=len(FUTURE_REQUIREMENT_NAMES))
    name: Literal[*FUTURE_REQUIREMENT_NAMES]
    separate_future_artifact_required: Literal[True]
    satisfied_by_this_packet: Literal[False]


class CanonicalPromotionLiveAdapterDryRunDispatchReadinessPacket(BaseModel):
    """Immutable content-addressed promotion-native readiness evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    format_version: Literal[FORMAT_VERSION]
    promotion_live_adapter_dry_run_dispatch_readiness_id: str = Field(
        pattern=r"^pladrdr:v1:sha256:[0-9a-f]{64}$"
    )
    promotion_live_adapter_dry_run_dispatch_readiness_hash: str = Field(
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
    source_live_adapter_dry_run_readiness_id: str
    source_live_adapter_dry_run_readiness_hash: str
    source_reference_rehearsal_id: str
    source_reference_rehearsal_hash: str
    source_adapter_dry_run_fixture_result_id: str
    source_adapter_dry_run_fixture_result_hash: str
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
    dispatch_readiness_status: Literal[
        "PROMOTION_NATIVE_LIVE_ADAPTER_DRY_RUN_DISPATCH_READINESS_"
        "EVALUATED_NOT_DISPATCHED"
    ]
    request_dispatch_state: Literal["NOT_DISPATCHED"]
    ready_for_promotion_native_endpoint_allowlist_evaluation: Literal[True]
    ready_for_network_dispatch: Literal[False]
    ready_for_real_bind: Literal[False]
    execution_authorized: Literal[False]
    human_approval_proven: Literal[False]
    authority_evidence_proven: Literal[False]
    dispatch_readiness_checks: tuple[PromotionDispatchReadinessCheck, ...]
    dispatch_readiness_check_digest: str
    future_dispatch_requirements: tuple[PromotionFutureDispatchRequirement, ...]
    future_dispatch_requirement_digest: str
    scope_limitations: tuple[str, ...]


def _json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise CanonicalPromotionLiveAdapterDryRunDispatchReadinessError(
                "PLADRDR_PACKET_INVALID"
            )
        return value
    if isinstance(value, datetime):
        return _aware(value, "PLADRDR_EVALUATED_AT_INVALID").isoformat()
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _json_value(item) for key, item in value.items()}
    raise CanonicalPromotionLiveAdapterDryRunDispatchReadinessError(
        "PLADRDR_PACKET_INVALID"
    )


def _aware(value: Any, code: str) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunDispatchReadinessError(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CanonicalPromotionLiveAdapterDryRunDispatchReadinessError(code)
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
    omitted = {
        "promotion_live_adapter_dry_run_dispatch_readiness_id",
        "promotion_live_adapter_dry_run_dispatch_readiness_hash",
    }
    return _digest(
        PACKET_DOMAIN, {key: value for key, value in raw.items() if key not in omitted}
    )


def _source(value: Any) -> CanonicalPromotionLiveAdapterDryRunRequestPacket:
    try:
        return verify_canonical_promotion_live_adapter_dry_run_request_packet(value)
    except (
        CanonicalPromotionLiveAdapterDryRunRequestError,
        TypeError,
        ValueError,
    ) as exc:
        raise CanonicalPromotionLiveAdapterDryRunDispatchReadinessError(
            "PLADRDR_SOURCE_REQUEST_INVALID"
        ) from exc


def _intent(raw: dict[str, Any]) -> ExecutionIntent:
    try:
        intent = ExecutionIntent(**raw)
        canonical_execution_intent_json(intent)
    except (TypeError, ValueError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunDispatchReadinessError(
            "PLADRDR_EXECUTION_INTENT_INVALID"
        ) from exc
    if intent.to_dict() != raw:
        raise CanonicalPromotionLiveAdapterDryRunDispatchReadinessError(
            "PLADRDR_EXECUTION_INTENT_INVALID"
        )
    return intent


def _validate_identity(
    source: CanonicalPromotionLiveAdapterDryRunRequestPacket,
) -> None:
    intent = _intent(source.execution_intent)
    if intent.execution_intent_id != source.execution_intent_id:
        raise CanonicalPromotionLiveAdapterDryRunDispatchReadinessError(
            "PLADRDR_EXECUTION_INTENT_ID_MISMATCH"
        )
    if hash_execution_intent(intent) != source.execution_intent_hash:
        raise CanonicalPromotionLiveAdapterDryRunDispatchReadinessError(
            "PLADRDR_EXECUTION_INTENT_HASH_MISMATCH"
        )
    try:
        descriptor = verify_bind_adapter_contract_descriptor(
            source.adapter_contract_descriptor, intent
        )
    except BindAdapterContractSelectionError as exc:
        raise CanonicalPromotionLiveAdapterDryRunDispatchReadinessError(
            "PLADRDR_ADAPTER_DESCRIPTOR_MISMATCH"
        ) from exc
    if (
        descriptor.model_dump(mode="json") != source.adapter_contract_descriptor
        or descriptor.adapter_contract_id != source.adapter_contract_id
        or descriptor.adapter_contract_hash != source.adapter_contract_hash
        or descriptor.adapter_contract_version != source.adapter_contract_version
    ):
        raise CanonicalPromotionLiveAdapterDryRunDispatchReadinessError(
            "PLADRDR_ADAPTER_DESCRIPTOR_MISMATCH"
        )


def _checks(source_hash: str) -> list[dict[str, Any]]:
    return [
        {
            "check_id": f"pladrdr-check:v1:{ordinal}:{name.replace('_', '-')}",
            "ordinal": ordinal,
            "name": name,
            "mode": "deterministic_local_dispatch_readiness_evaluation_only",
            "passed": True,
            "evidence_ref": f"source_request_hash:{source_hash}:{name}",
            **{field: False for field in EFFECT_FIELDS},
        }
        for ordinal, name in enumerate(CHECK_NAMES, 1)
    ]


def _future_requirements() -> list[dict[str, Any]]:
    return [
        {
            "ordinal": ordinal,
            "name": name,
            "separate_future_artifact_required": True,
            "satisfied_by_this_packet": False,
        }
        for ordinal, name in enumerate(FUTURE_REQUIREMENT_NAMES, 1)
    ]


def build_canonical_promotion_live_adapter_dry_run_dispatch_readiness_packet(
    source_live_adapter_dry_run_request_packet: Any,
    dispatch_readiness_evaluated_at: datetime,
) -> CanonicalPromotionLiveAdapterDryRunDispatchReadinessPacket:
    """Build local readiness evidence from the sole authoritative request."""
    evaluated = _aware(dispatch_readiness_evaluated_at, "PLADRDR_EVALUATED_AT_INVALID")
    source = _source(_json_value(source_live_adapter_dry_run_request_packet))
    _validate_identity(source)
    if evaluated < _aware(source.requested_at, "PLADRDR_SOURCE_REQUEST_INVALID"):
        raise CanonicalPromotionLiveAdapterDryRunDispatchReadinessError(
            "PLADRDR_EVALUATED_BEFORE_REQUEST"
        )
    source_raw = source.model_dump(mode="json")
    checks = _checks(source.promotion_live_adapter_dry_run_request_hash)
    requirements = _future_requirements()
    raw = {
        "format_version": FORMAT_VERSION,
        "dispatch_readiness_mechanism": DISPATCH_READINESS_MECHANISM,
        "dispatch_readiness_evaluated_at": evaluated.isoformat(),
        "source_live_adapter_dry_run_request_id": (
            source.promotion_live_adapter_dry_run_request_id
        ),
        "source_live_adapter_dry_run_request_hash": (
            source.promotion_live_adapter_dry_run_request_hash
        ),
        "source_live_adapter_dry_run_request_packet": source_raw,
        "request_descriptor": source_raw["request_descriptor"],
        "dispatch_preconditions": source_raw["dispatch_preconditions"],
        "dispatch_precondition_digest": source.dispatch_precondition_digest,
        "execution_intent": source_raw["execution_intent"],
        "execution_intent_id": source.execution_intent_id,
        "execution_intent_hash": source.execution_intent_hash,
        "adapter_contract_descriptor": source_raw["adapter_contract_descriptor"],
        "adapter_contract_id": source.adapter_contract_id,
        "adapter_contract_hash": source.adapter_contract_hash,
        "adapter_contract_version": source.adapter_contract_version,
        **{field: source_raw[field] for field in LINEAGE_FIELDS},
        "dispatch_readiness_status": (
            "PROMOTION_NATIVE_LIVE_ADAPTER_DRY_RUN_DISPATCH_READINESS_"
            "EVALUATED_NOT_DISPATCHED"
        ),
        "request_dispatch_state": "NOT_DISPATCHED",
        "ready_for_promotion_native_endpoint_allowlist_evaluation": True,
        "ready_for_network_dispatch": False,
        "ready_for_real_bind": False,
        "execution_authorized": False,
        "human_approval_proven": False,
        "authority_evidence_proven": False,
        "dispatch_readiness_checks": checks,
        "dispatch_readiness_check_digest": _digest(CHECKS_DOMAIN, checks),
        "future_dispatch_requirements": requirements,
        "future_dispatch_requirement_digest": _digest(
            FUTURE_REQUIREMENTS_DOMAIN, requirements
        ),
        "scope_limitations": SCOPE_LIMITATIONS,
    }
    digest = _packet_hash(raw)
    raw["promotion_live_adapter_dry_run_dispatch_readiness_hash"] = digest
    raw["promotion_live_adapter_dry_run_dispatch_readiness_id"] = (
        f"pladrdr:v1:sha256:{digest}"
    )
    return verify_canonical_promotion_live_adapter_dry_run_dispatch_readiness_packet(
        raw
    )


def verify_canonical_promotion_live_adapter_dry_run_dispatch_readiness_packet(
    packet: Any,
) -> CanonicalPromotionLiveAdapterDryRunDispatchReadinessPacket:
    """Independently recompute source identity, claims, digests, hash, and ID."""
    try:
        value = (
            packet.model_dump(mode="json")
            if isinstance(packet, BaseModel)
            else _json_value(packet)
        )
        candidate = (
            CanonicalPromotionLiveAdapterDryRunDispatchReadinessPacket.model_validate(
                value
            )
        )
    except (
        ValidationError,
        TypeError,
        CanonicalPromotionLiveAdapterDryRunDispatchReadinessError,
    ) as exc:
        raise CanonicalPromotionLiveAdapterDryRunDispatchReadinessError(
            "PLADRDR_PACKET_INVALID"
        ) from exc
    raw = candidate.model_dump(mode="json")
    source = _source(candidate.source_live_adapter_dry_run_request_packet)
    _validate_identity(source)
    source_raw = source.model_dump(mode="json")
    if (
        candidate.source_live_adapter_dry_run_request_id
        != source.promotion_live_adapter_dry_run_request_id
        or candidate.source_live_adapter_dry_run_request_hash
        != source.promotion_live_adapter_dry_run_request_hash
    ):
        raise CanonicalPromotionLiveAdapterDryRunDispatchReadinessError(
            "PLADRDR_SOURCE_SUMMARY_MISMATCH"
        )
    if _aware(
        candidate.dispatch_readiness_evaluated_at, "PLADRDR_EVALUATED_AT_INVALID"
    ) < _aware(source.requested_at, "PLADRDR_SOURCE_REQUEST_INVALID"):
        raise CanonicalPromotionLiveAdapterDryRunDispatchReadinessError(
            "PLADRDR_EVALUATED_BEFORE_REQUEST"
        )
    copied = (
        "request_descriptor",
        "dispatch_preconditions",
        "dispatch_precondition_digest",
        "execution_intent",
        "execution_intent_id",
        "execution_intent_hash",
        "adapter_contract_descriptor",
        "adapter_contract_id",
        "adapter_contract_hash",
        "adapter_contract_version",
        *LINEAGE_FIELDS,
    )
    for field in copied:
        if _json_value(getattr(candidate, field)) != _json_value(source_raw[field]):
            raise CanonicalPromotionLiveAdapterDryRunDispatchReadinessError(
                "PLADRDR_SOURCE_FIELD_MISMATCH"
            )
    intent = _intent(candidate.execution_intent)
    if (
        intent.execution_intent_id != candidate.execution_intent_id
        or hash_execution_intent(intent) != candidate.execution_intent_hash
    ):
        raise CanonicalPromotionLiveAdapterDryRunDispatchReadinessError(
            "PLADRDR_EXECUTION_INTENT_MISMATCH"
        )
    checks = _checks(source.promotion_live_adapter_dry_run_request_hash)
    if _json_value(candidate.dispatch_readiness_checks) != checks:
        raise CanonicalPromotionLiveAdapterDryRunDispatchReadinessError(
            "PLADRDR_CHECKS_MISMATCH"
        )
    if candidate.dispatch_readiness_check_digest != _digest(CHECKS_DOMAIN, checks):
        raise CanonicalPromotionLiveAdapterDryRunDispatchReadinessError(
            "PLADRDR_CHECK_DIGEST_MISMATCH"
        )
    requirements = _future_requirements()
    if _json_value(candidate.future_dispatch_requirements) != requirements:
        raise CanonicalPromotionLiveAdapterDryRunDispatchReadinessError(
            "PLADRDR_REQUIREMENTS_MISMATCH"
        )
    if candidate.future_dispatch_requirement_digest != _digest(
        FUTURE_REQUIREMENTS_DOMAIN, requirements
    ):
        raise CanonicalPromotionLiveAdapterDryRunDispatchReadinessError(
            "PLADRDR_REQUIREMENT_DIGEST_MISMATCH"
        )
    if candidate.scope_limitations != SCOPE_LIMITATIONS:
        raise CanonicalPromotionLiveAdapterDryRunDispatchReadinessError(
            "PLADRDR_SCOPE_MISMATCH"
        )
    digest = _packet_hash(raw)
    if candidate.promotion_live_adapter_dry_run_dispatch_readiness_hash != digest:
        raise CanonicalPromotionLiveAdapterDryRunDispatchReadinessError(
            "PLADRDR_PACKET_HASH_MISMATCH"
        )
    if candidate.promotion_live_adapter_dry_run_dispatch_readiness_id != (
        f"pladrdr:v1:sha256:{digest}"
    ):
        raise CanonicalPromotionLiveAdapterDryRunDispatchReadinessError(
            "PLADRDR_PACKET_ID_MISMATCH"
        )
    return candidate
