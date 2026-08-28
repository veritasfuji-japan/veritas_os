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

from veritas_os.policy.bind_adapter_contract_selection import (
    BindAdapterContractSelectionError,
    verify_bind_adapter_contract_descriptor,
)
from veritas_os.policy.bind_artifacts import (
    ExecutionIntent,
    canonical_execution_intent_json,
    hash_execution_intent,
)
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_readiness import (
    CHECKS_DOMAIN as READINESS_CHECKS_DOMAIN,
    CanonicalPromotionLiveAdapterDryRunRequestReadinessPacket,
    CanonicalPromotionLiveAdapterDryRunReadinessError,
    _digest as readiness_digest,
    verify_canonical_promotion_live_adapter_dry_run_request_readiness_packet,
)
from veritas_os.policy.canonical_promotion_adapter_dry_run_fixture_result import (
    RESULTS_DOMAIN as FIXTURE_DOMAIN,
    _digest as fixture_digest,
)
from veritas_os.policy.canonical_promotion_adapter_dry_run_plan import (
    STEPS_DOMAIN,
    _digest as plan_digest,
)
from veritas_os.policy.canonical_promotion_reference_adapter_rehearsal import (
    RESULTS_DOMAIN as REHEARSAL_DOMAIN,
    _digest as rehearsal_digest,
)

FORMAT_VERSION = "canonical-promotion-live-adapter-dry-run-request/v1"
REQUEST_MECHANISM = (
    "construct_promotion_live_adapter_dry_run_request_without_dispatch/v1"
)
DESCRIPTOR_DOMAIN = "veritas.promotion-live-adapter-dry-run-request.descriptor/v1"
DISPATCH_PRECONDITIONS_DOMAIN = (
    "veritas.promotion-live-adapter-dry-run-request.dispatch-preconditions/v1"
)
CONSTRUCTION_CHECKS_DOMAIN = (
    "veritas.promotion-live-adapter-dry-run-request.construction-checks/v1"
)
FUTURE_REQUIREMENTS_DOMAIN = (
    "veritas.promotion-live-adapter-dry-run-request.future-requirements/v1"
)
PACKET_DOMAIN = "veritas.promotion-live-adapter-dry-run-request.packet/v1"

PRECONDITION_NAMES = (
    "readiness_packet_verified",
    "execution_intent_identity_verified",
    "adapter_descriptor_preserved",
    "request_descriptor_constructed",
    "dry_run_only_policy_declared",
    "read_only_scope_declared",
    "no_apply_policy_declared",
    "no_commit_policy_declared",
    "no_credential_material_embedded",
    "no_endpoint_material_embedded",
    "dispatch_not_performed",
    "webhook_not_called",
    "live_adapter_not_instantiated",
    "bind_not_invoked",
    "bind_receipt_not_created",
    "trustlog_not_written",
    "external_effect_not_used",
    "future_dispatch_gate_required",
)
PRECONDITION_LIMITATIONS = (
    "NOT_DISPATCHED",
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
DESCRIPTOR_LIMITATIONS = (
    "NOT_DISPATCHED",
    "NOT_LIVE_ADAPTER_INVOCATION",
    "NOT_WEBHOOK_INVOCATION",
    "NOT_NETWORK_CALL",
    "NOT_CREDENTIAL_ACCESS",
    "NOT_LIVE_STATE",
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
    "NOT_LIVE_ADAPTER_INSTANCE",
    "NOT_LIVE_ADAPTER_INVOCATION",
    "NOT_LIVE_ADAPTER_RESULT",
    "NOT_LIVE_DRY_RUN_DISPATCH",
    "NOT_WEBHOOK_INVOCATION",
    "NOT_NETWORK_CALL",
    "NOT_CREDENTIAL_ACCESS",
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
SOURCE_SUMMARY_KEYS = (
    "promotion_live_adapter_dry_run_readiness_id",
    "promotion_live_adapter_dry_run_readiness_hash",
    "format_version",
    "readiness_mechanism",
    "readiness_evaluated_at",
    "execution_intent_id",
    "execution_intent_hash",
    "live_adapter_dry_run_request_readiness_status",
    "ready_for_promotion_native_live_adapter_dry_run_request_packet",
)
COPIED_FIELDS = (
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
CONSTRUCTION_CHECKS = {
    key: True
    for key in (
        "readiness_packet_verified",
        "execution_intent_hash_verified",
        "execution_intent_id_verified",
        "adapter_descriptor_preserved",
        "planned_steps_preserved",
        "fixture_results_preserved",
        "reference_rehearsal_results_preserved",
        "readiness_checks_preserved",
        "planned_step_digest_verified",
        "fixture_result_digest_verified",
        "reference_rehearsal_result_digest_verified",
        "readiness_check_digest_verified",
        "request_descriptor_constructed",
        "dispatch_preconditions_ordered",
        "dispatch_precondition_digest_verified",
        "requested_after_readiness_evaluation",
        "no_live_adapter_instance",
        "no_live_adapter_invocation",
        "no_webhook_invocation",
        "no_live_dry_run_dispatch",
        "no_bind_invocation",
        "no_bind_receipt_created",
        "no_trustlog_write",
        "no_network",
        "no_filesystem",
        "no_credential_access",
        "no_endpoint_contact",
        "no_external_effect",
        "no_apply",
        "no_postcondition_verification",
        "no_revert",
        "semantic_match_not_authority",
    )
}
FUTURE_REQUIREMENTS = {
    key: True
    for key in (
        "dispatch_readiness_packet_required",
        "endpoint_allowlist_resolution_required",
        "credential_resolution_required",
        "credential_scope_review_required",
        "live_adapter_instance_policy_required",
        "live_adapter_timeout_required",
        "live_adapter_rate_limit_required",
        "live_adapter_idempotency_key_required",
        "dry_run_only_enforcement_required",
        "no_apply_runtime_guard_required",
        "no_commit_runtime_guard_required",
        "network_egress_policy_required",
        "webhook_dispatch_policy_required",
        "live_result_packet_required",
        "bind_receipt_still_deferred",
        "human_approval_still_required_when_policy_requires",
        "authority_evidence_still_required",
        "apply_still_forbidden",
        "verify_postconditions_still_deferred",
        "rollback_or_revert_still_deferred",
    )
}


class CanonicalPromotionLiveAdapterDryRunRequestError(ValueError):
    """Stable fail-closed refusal for request packet processing."""


class PromotionLiveAdapterDryRunRequestDescriptor(BaseModel):
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


class PromotionLiveAdapterDryRunDispatchPrecondition(BaseModel):
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


class CanonicalPromotionLiveAdapterDryRunRequestPacket(BaseModel):
    """Strict immutable content-addressed, non-dispatched request packet."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    format_version: Literal[FORMAT_VERSION]
    promotion_live_adapter_dry_run_request_id: str = Field(
        pattern=r"^pladrq:v1:sha256:[0-9a-f]{64}$"
    )
    promotion_live_adapter_dry_run_request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_mechanism: Literal[REQUEST_MECHANISM]
    requested_at: str
    source_live_adapter_dry_run_readiness_id: str
    source_live_adapter_dry_run_readiness_hash: str
    source_live_adapter_dry_run_readiness_packet: dict[str, Any]
    request_descriptor: PromotionLiveAdapterDryRunRequestDescriptor
    adapter_contract_descriptor: dict[str, Any]
    adapter_contract_id: str
    adapter_contract_hash: str
    adapter_contract_version: str
    execution_intent: dict[str, Any]
    execution_intent_id: str
    execution_intent_hash: str
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
    promotion_live_adapter_dry_run_request_status: Literal[
        "PROMOTION_NATIVE_LIVE_ADAPTER_DRY_RUN_REQUEST_CREATED_NOT_DISPATCHED"
    ]
    request_dispatch_state: Literal["NOT_DISPATCHED"]
    request_created: Literal[True]
    request_dispatched: Literal[False]
    ready_for_promotion_native_live_adapter_dry_run_dispatch_readiness: Literal[True]
    fail_closed: Literal[False]
    planned_steps: tuple[dict[str, Any], ...]
    planned_step_digest: str
    fixture_step_results: tuple[dict[str, Any], ...]
    fixture_result_digest: str
    reference_rehearsal_results: tuple[dict[str, Any], ...]
    reference_rehearsal_result_digest: str
    readiness_checks: tuple[dict[str, Any], ...]
    readiness_check_digest: str
    dispatch_preconditions: tuple[PromotionLiveAdapterDryRunDispatchPrecondition, ...]
    dispatch_precondition_digest: str
    request_construction_checks: dict[str, bool]
    future_live_adapter_dry_run_dispatch_requirements: dict[str, bool]
    source_decision_identity: dict[str, Any]
    candidate_identity: dict[str, Any]
    selected_action_lineage: dict[str, Any]
    policy_snapshot_lineage: dict[str, Any]
    approval_context: dict[str, Any]
    policy_lineage: dict[str, Any]
    credential_accessed: Literal[False]
    endpoint_contacted: Literal[False]
    webhook_contacted: Literal[False]
    network_used: Literal[False]
    filesystem_used: Literal[False]
    external_effect_used: Literal[False]
    human_approval_proven: Literal[False]
    authority_evidence_proven: Literal[False]
    scope_limitations: tuple[str, ...]


def _json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise CanonicalPromotionLiveAdapterDryRunRequestError(
                "PLADRQ_PACKET_INVALID"
            )
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise CanonicalPromotionLiveAdapterDryRunRequestError(
                "PLADRQ_REQUESTED_AT_INVALID"
            )
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _json_value(item) for key, item in value.items()}
    raise CanonicalPromotionLiveAdapterDryRunRequestError("PLADRQ_PACKET_INVALID")


def _aware(value: Any, code: str) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunRequestError(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CanonicalPromotionLiveAdapterDryRunRequestError(code)
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
            not in {
                "promotion_live_adapter_dry_run_request_id",
                "promotion_live_adapter_dry_run_request_hash",
            }
        },
    )


def _source(value: Any) -> CanonicalPromotionLiveAdapterDryRunRequestReadinessPacket:
    try:
        return verify_canonical_promotion_live_adapter_dry_run_request_readiness_packet(
            value
        )
    except (
        CanonicalPromotionLiveAdapterDryRunReadinessError,
        TypeError,
        ValueError,
    ) as exc:
        raise CanonicalPromotionLiveAdapterDryRunRequestError(
            "PLADRQ_READINESS_PACKET_INVALID"
        ) from exc


def _intent(raw: dict[str, Any]) -> ExecutionIntent:
    try:
        intent = ExecutionIntent(**raw)
        canonical_execution_intent_json(intent)
    except (TypeError, ValueError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunRequestError(
            "PLADRQ_PACKET_INVALID"
        ) from exc
    if intent.to_dict() != raw:
        raise CanonicalPromotionLiveAdapterDryRunRequestError("PLADRQ_PACKET_INVALID")
    return intent


def _build_expected_request_descriptor(
    source_readiness_packet: CanonicalPromotionLiveAdapterDryRunRequestReadinessPacket,
) -> dict[str, Any]:
    """Build the canonical request descriptor from the verified source only."""
    source = source_readiness_packet
    intent = _intent(source.execution_intent)
    slug = re.sub(r"[^a-z0-9]+", "-", source.adapter_contract_id.lower()).strip("-")
    raw = {
        "request_descriptor_id": f"live-adapter-dry-run-request-descriptor:v1:{slug}",
        "request_kind": "live_adapter_dry_run",
        "dispatch_mode": "not_dispatched",
        "adapter_contract_id": source.adapter_contract_id,
        "adapter_contract_hash": source.adapter_contract_hash,
        "adapter_contract_version": source.adapter_contract_version,
        "target_system": intent.target_system,
        "target_resource_scope": intent.target_resource,
        "action_name": intent.intended_action,
        "dry_run_only": True,
        "read_only_scope_required": True,
        "no_apply": True,
        "no_commit": True,
        "no_state_mutation": True,
        "no_trustlog_write_before_policy": True,
        "no_bind_receipt_before_bind": True,
        "credential_material_included": False,
        "credential_accessed": False,
        "endpoint_material_included": False,
        "endpoint_contacted": False,
        "webhook_contacted": False,
        "network_used": False,
        "external_effect_used": False,
        "descriptor_scope_limitations": DESCRIPTOR_LIMITATIONS,
    }
    descriptor = _json_value(raw)
    _digest(DESCRIPTOR_DOMAIN, descriptor)
    return descriptor


def _build_expected_dispatch_preconditions(
    source_readiness_packet: CanonicalPromotionLiveAdapterDryRunRequestReadinessPacket,
    request_descriptor: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build the canonical ordered preconditions used by both public helpers."""
    descriptor = _json_value(request_descriptor)
    descriptor_digest = _digest(DESCRIPTOR_DOMAIN, descriptor)
    source_hash = source_readiness_packet.promotion_live_adapter_dry_run_readiness_hash
    preconditions = [
        {
            "precondition_id": (
                "live-adapter-dry-run-dispatch-precondition:"
                f"v1:{ordinal}:{name.replace('_', '-')}"
            ),
            "ordinal": ordinal,
            "precondition_name": name,
            "precondition_mode": "deterministic_local_request_construction_only",
            "passed": True,
            "evidence_ref": (
                f"readiness_hash:{source_hash}:"
                f"request_descriptor_hash:{descriptor_digest}:{name}"
            ),
            "live_observation_used": False,
            "network_used": False,
            "filesystem_used": False,
            "credential_accessed": False,
            "adapter_instance_created": False,
            "adapter_method_called": False,
            "request_dispatched": False,
            "webhook_called": False,
            "bind_invoked": False,
            "bind_receipt_created": False,
            "trustlog_written": False,
            "external_effect_used": False,
            "precondition_scope_limitations": PRECONDITION_LIMITATIONS,
        }
        for ordinal, name in enumerate(PRECONDITION_NAMES, 1)
    ]
    return _json_value(preconditions)


def _validate_source(
    source: CanonicalPromotionLiveAdapterDryRunRequestReadinessPacket,
) -> None:
    intent = _intent(source.execution_intent)
    if intent.execution_intent_id != source.execution_intent_id:
        raise CanonicalPromotionLiveAdapterDryRunRequestError(
            "PLADRQ_EXECUTION_INTENT_ID_MISMATCH"
        )
    if hash_execution_intent(intent) != source.execution_intent_hash:
        raise CanonicalPromotionLiveAdapterDryRunRequestError(
            "PLADRQ_EXECUTION_INTENT_HASH_MISMATCH"
        )
    try:
        descriptor = verify_bind_adapter_contract_descriptor(
            source.adapter_contract_descriptor, intent
        )
    except BindAdapterContractSelectionError as exc:
        raise CanonicalPromotionLiveAdapterDryRunRequestError(
            "PLADRQ_DESCRIPTOR_MISMATCH"
        ) from exc
    if (
        descriptor.model_dump(mode="json") != source.adapter_contract_descriptor
        or descriptor.adapter_contract_id != source.adapter_contract_id
        or descriptor.adapter_contract_hash != source.adapter_contract_hash
        or descriptor.adapter_contract_version != source.adapter_contract_version
    ):
        raise CanonicalPromotionLiveAdapterDryRunRequestError(
            "PLADRQ_DESCRIPTOR_MISMATCH"
        )


def build_canonical_promotion_live_adapter_dry_run_request_packet(
    canonical_promotion_live_adapter_dry_run_readiness_packet: Any,
    requested_at: datetime,
) -> CanonicalPromotionLiveAdapterDryRunRequestPacket:
    """Verify readiness and construct a request packet without dispatching it."""
    requested = _aware(requested_at, "PLADRQ_REQUESTED_AT_INVALID")
    source = _source(
        _json_value(canonical_promotion_live_adapter_dry_run_readiness_packet)
    )
    _validate_source(source)
    if requested < _aware(
        source.readiness_evaluated_at, "PLADRQ_READINESS_PACKET_INVALID"
    ):
        raise CanonicalPromotionLiveAdapterDryRunRequestError(
            "PLADRQ_REQUESTED_BEFORE_READINESS"
        )
    source_raw = source.model_dump(mode="json")
    request_descriptor = _build_expected_request_descriptor(source)
    preconditions = _build_expected_dispatch_preconditions(source, request_descriptor)
    raw = {
        "format_version": FORMAT_VERSION,
        "request_mechanism": REQUEST_MECHANISM,
        "requested_at": requested.isoformat(),
        "source_live_adapter_dry_run_readiness_id": (
            source.promotion_live_adapter_dry_run_readiness_id
        ),
        "source_live_adapter_dry_run_readiness_hash": (
            source.promotion_live_adapter_dry_run_readiness_hash
        ),
        "source_live_adapter_dry_run_readiness_packet": source_raw,
        "request_descriptor": request_descriptor,
        "adapter_contract_descriptor": source_raw["adapter_contract_descriptor"],
        "adapter_contract_id": source.adapter_contract_id,
        "adapter_contract_hash": source.adapter_contract_hash,
        "adapter_contract_version": source.adapter_contract_version,
        "execution_intent": source_raw["execution_intent"],
        "execution_intent_id": source.execution_intent_id,
        "execution_intent_hash": source.execution_intent_hash,
        **{key: source_raw[key] for key in COPIED_FIELDS},
        "promotion_live_adapter_dry_run_request_status": (
            "PROMOTION_NATIVE_LIVE_ADAPTER_DRY_RUN_REQUEST_CREATED_NOT_DISPATCHED"
        ),
        "request_dispatch_state": "NOT_DISPATCHED",
        "request_created": True,
        "request_dispatched": False,
        "ready_for_promotion_native_live_adapter_dry_run_dispatch_readiness": True,
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
        "dispatch_precondition_digest": _digest(
            DISPATCH_PRECONDITIONS_DOMAIN, preconditions
        ),
        "request_construction_checks": CONSTRUCTION_CHECKS,
        "future_live_adapter_dry_run_dispatch_requirements": FUTURE_REQUIREMENTS,
        "credential_accessed": False,
        "endpoint_contacted": False,
        "webhook_contacted": False,
        "network_used": False,
        "filesystem_used": False,
        "external_effect_used": False,
        "human_approval_proven": False,
        "authority_evidence_proven": False,
        "scope_limitations": SCOPE_LIMITATIONS,
    }
    digest = _packet_hash(raw)
    raw.update(
        promotion_live_adapter_dry_run_request_hash=digest,
        promotion_live_adapter_dry_run_request_id=f"pladrq:v1:sha256:{digest}",
    )
    return verify_canonical_promotion_live_adapter_dry_run_request_packet(raw)


def verify_canonical_promotion_live_adapter_dry_run_request_packet(
    packet: Any,
) -> CanonicalPromotionLiveAdapterDryRunRequestPacket:
    """Independently reverify source, preserved data, claims, and identity."""
    try:
        value = (
            packet.model_dump(mode="json")
            if isinstance(packet, BaseModel)
            else _json_value(packet)
        )
        candidate = CanonicalPromotionLiveAdapterDryRunRequestPacket.model_validate(
            value
        )
    except (
        ValidationError,
        CanonicalPromotionLiveAdapterDryRunRequestError,
        TypeError,
    ) as exc:
        raise CanonicalPromotionLiveAdapterDryRunRequestError(
            "PLADRQ_PACKET_INVALID"
        ) from exc
    raw = candidate.model_dump(mode="json")
    source = _source(candidate.source_live_adapter_dry_run_readiness_packet)
    _validate_source(source)
    if (
        candidate.source_live_adapter_dry_run_readiness_id
        != source.promotion_live_adapter_dry_run_readiness_id
        or candidate.source_live_adapter_dry_run_readiness_hash
        != source.promotion_live_adapter_dry_run_readiness_hash
    ):
        raise CanonicalPromotionLiveAdapterDryRunRequestError(
            "PLADRQ_SOURCE_SUMMARY_MISMATCH"
        )
    if _aware(candidate.requested_at, "PLADRQ_REQUESTED_AT_INVALID") < _aware(
        source.readiness_evaluated_at, "PLADRQ_READINESS_PACKET_INVALID"
    ):
        raise CanonicalPromotionLiveAdapterDryRunRequestError(
            "PLADRQ_REQUESTED_BEFORE_READINESS"
        )
    intent = _intent(candidate.execution_intent)
    if candidate.execution_intent != source.execution_intent:
        raise CanonicalPromotionLiveAdapterDryRunRequestError(
            "PLADRQ_EXECUTION_INTENT_HASH_MISMATCH"
        )
    if (
        intent.execution_intent_id != candidate.execution_intent_id
        or candidate.execution_intent_id != source.execution_intent_id
    ):
        raise CanonicalPromotionLiveAdapterDryRunRequestError(
            "PLADRQ_EXECUTION_INTENT_ID_MISMATCH"
        )
    if (
        hash_execution_intent(intent) != candidate.execution_intent_hash
        or candidate.execution_intent_hash != source.execution_intent_hash
    ):
        raise CanonicalPromotionLiveAdapterDryRunRequestError(
            "PLADRQ_EXECUTION_INTENT_HASH_MISMATCH"
        )
    expected_descriptor = _build_expected_request_descriptor(source)
    if _json_value(candidate.request_descriptor) != _json_value(expected_descriptor):
        raise CanonicalPromotionLiveAdapterDryRunRequestError(
            "PLADRQ_REQUEST_DESCRIPTOR_INVALID"
        )
    for key in (
        "adapter_contract_descriptor",
        "adapter_contract_id",
        "adapter_contract_hash",
        "adapter_contract_version",
        *COPIED_FIELDS,
    ):
        if _json_value(getattr(candidate, key)) != _json_value(getattr(source, key)):
            raise CanonicalPromotionLiveAdapterDryRunRequestError(
                "PLADRQ_DESCRIPTOR_MISMATCH"
            )
    collections = (
        (
            "planned_steps",
            "planned_step_digest",
            STEPS_DOMAIN,
            plan_digest,
            "PLADRQ_PLANNED_STEPS_MISMATCH",
        ),
        (
            "fixture_step_results",
            "fixture_result_digest",
            FIXTURE_DOMAIN,
            fixture_digest,
            "PLADRQ_FIXTURE_RESULTS_MISMATCH",
        ),
        (
            "reference_rehearsal_results",
            "reference_rehearsal_result_digest",
            REHEARSAL_DOMAIN,
            rehearsal_digest,
            "PLADRQ_REFERENCE_REHEARSAL_RESULTS_MISMATCH",
        ),
        (
            "readiness_checks",
            "readiness_check_digest",
            READINESS_CHECKS_DOMAIN,
            readiness_digest,
            "PLADRQ_READINESS_CHECKS_MISMATCH",
        ),
    )
    for field, digest_field, domain, digest_fn, code in collections:
        value = _json_value(getattr(candidate, field))
        if (
            value != _json_value(getattr(source, field))
            or getattr(candidate, digest_field) != getattr(source, digest_field)
            or getattr(candidate, digest_field) != digest_fn(domain, value)
        ):
            raise CanonicalPromotionLiveAdapterDryRunRequestError(code)
    preconditions = _build_expected_dispatch_preconditions(source, expected_descriptor)
    if _json_value(candidate.dispatch_preconditions) != _json_value(preconditions):
        raise CanonicalPromotionLiveAdapterDryRunRequestError(
            "PLADRQ_DISPATCH_PRECONDITIONS_INVALID"
        )
    if candidate.dispatch_precondition_digest != _digest(
        DISPATCH_PRECONDITIONS_DOMAIN, preconditions
    ):
        raise CanonicalPromotionLiveAdapterDryRunRequestError(
            "PLADRQ_DISPATCH_PRECONDITION_DIGEST_MISMATCH"
        )
    if candidate.request_construction_checks != CONSTRUCTION_CHECKS:
        raise CanonicalPromotionLiveAdapterDryRunRequestError(
            "PLADRQ_CONSTRUCTION_CHECKS_MISMATCH"
        )
    if (
        candidate.future_live_adapter_dry_run_dispatch_requirements
        != FUTURE_REQUIREMENTS
    ):
        raise CanonicalPromotionLiveAdapterDryRunRequestError(
            "PLADRQ_FUTURE_REQUIREMENTS_MISMATCH"
        )
    _digest(CONSTRUCTION_CHECKS_DOMAIN, candidate.request_construction_checks)
    _digest(
        FUTURE_REQUIREMENTS_DOMAIN,
        candidate.future_live_adapter_dry_run_dispatch_requirements,
    )
    if candidate.scope_limitations != SCOPE_LIMITATIONS:
        raise CanonicalPromotionLiveAdapterDryRunRequestError(
            "PLADRQ_SCOPE_LIMITATIONS_MISSING"
        )
    digest = _packet_hash(raw)
    if candidate.promotion_live_adapter_dry_run_request_hash != digest:
        raise CanonicalPromotionLiveAdapterDryRunRequestError(
            "PLADRQ_PACKET_HASH_MISMATCH"
        )
    if (
        candidate.promotion_live_adapter_dry_run_request_id
        != f"pladrq:v1:sha256:{digest}"
    ):
        raise CanonicalPromotionLiveAdapterDryRunRequestError(
            "PLADRQ_PACKET_ID_MISMATCH"
        )
    return candidate
