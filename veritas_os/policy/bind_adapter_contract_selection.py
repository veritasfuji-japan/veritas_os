"""Select an inert Bind adapter contract descriptor without invoking Bind.

The packet produced here is local, deterministic evidence of association only.
It never creates an adapter, calls an adapter, authorizes execution, or writes
TrustLog.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from veritas_os.policy.bind_artifacts import (
    ExecutionIntent,
    canonical_execution_intent_json,
    hash_execution_intent,
)
from veritas_os.policy.canonical_bind_preflight_adjudication import (
    BindPreflightAdjudicationError,
    CanonicalBindPreflightAdjudicationPacket,
    verify_canonical_bind_preflight_adjudication_packet,
)

FORMAT_VERSION = "canonical-bind-adapter-contract-selection/v1"
SELECTION_MECHANISM = "select_bind_adapter_contract_without_invocation/v1"
DESCRIPTOR_DOMAIN = "veritas.bind-adapter-contract-selection.descriptor/v1"
LOCAL_CHECKS_DOMAIN = "veritas.bind-adapter-contract-selection.local-checks/v1"
FUTURE_REQUIREMENTS_DOMAIN = (
    "veritas.bind-adapter-contract-selection.future-requirements/v1"
)
PACKET_DOMAIN = "veritas.bind-adapter-contract-selection.packet/v1"
SOURCE_SUMMARY_KEYS = (
    "bind_preflight_adjudication_id", "bind_preflight_adjudication_hash",
    "format_version", "adjudication_mechanism", "adjudicated_at",
    "execution_intent_id", "execution_intent_hash", "bind_preflight_status",
    "ready_for_bind_adjudication",
)
ADAPTER_METHODS = (
    "snapshot", "fingerprint_state", "validate_authority",
    "validate_constraints", "assess_runtime_risk", "apply",
    "verify_postconditions", "revert", "describe_target",
    "build_idempotency_key",
)
PROHIBITED_DURING_SELECTION = (
    "snapshot", "fingerprint_state", "validate_authority",
    "validate_constraints", "assess_runtime_risk", "apply",
    "verify_postconditions", "revert", "build_idempotency_key",
    "execute_bind_adjudication", "execute_bind_boundary", "BindReceipt",
    "TrustLogWrite",
)
EFFECT_PROFILE = {
    "selection_phase": "no_effect", "adapter_instantiated": False,
    "adapter_methods_called": False, "network_allowed": False,
    "filesystem_allowed": False, "external_effect_allowed": False,
    "trustlog_write_allowed": False, "bind_receipt_allowed": False,
}
DESCRIPTOR_SCOPE_LIMITATIONS = (
    "NOT_ADAPTER_INSTANCE", "NOT_ADAPTER_AUTHORIZATION",
    "NOT_ADAPTER_INVOCATION", "NOT_BIND_INVOCATION", "NOT_BIND_RECEIPT",
    "NOT_TRUSTLOG_WRITE", "NOT_EXTERNAL_EFFECT",
    "NOT_AUTHORITY_REVALIDATION", "NOT_CONSTRAINT_REVALIDATION",
    "NOT_RUNTIME_RISK_CHECK", "NOT_POSTCONDITION_VERIFICATION",
    "NOT_ROLLBACK_PROOF",
)
LOCAL_SELECTION_CHECKS = {key: True for key in (
    "bind_preflight_adjudication_verified", "execution_intent_hash_verified",
    "execution_intent_id_verified", "adapter_descriptor_hash_verified",
    "adapter_descriptor_scope_matches_intent", "required_methods_declared",
    "prohibited_methods_not_called", "selected_after_bind_preflight_adjudication",
    "no_adapter_instance", "no_adapter_invocation", "no_bind_invocation",
    "no_bind_receipt_created", "no_trustlog_write", "no_network",
    "no_filesystem", "no_external_effect",
)}
FUTURE_BIND_DRY_RUN_REQUIREMENTS = {key: True for key in (
    "adapter_instance_required", "snapshot_required",
    "state_fingerprint_required", "authority_revalidation_required",
    "constraint_validation_required", "runtime_risk_assessment_required",
    "commit_boundary_evaluation_required", "idempotency_key_required",
    "postcondition_verification_required", "rollback_or_revert_path_required",
    "bind_receipt_required", "trustlog_policy_required",
)}
SCOPE_LIMITATIONS = (
    "NOT_EXECUTION_AUTHORITY", "NOT_BIND_AUTHORIZATION", "NOT_BIND_RECEIPT",
    "NOT_BIND_INVOCATION", "NOT_ADAPTER_INSTANCE", "NOT_ADAPTER_INVOCATION",
    "NOT_EXTERNAL_EFFECT", "NOT_OPERATION_COMMIT", "NOT_TRUSTLOG_WRITE",
    "NOT_LIVE_STATE_CHECK", "NOT_RUNTIME_RISK_ACCEPTANCE",
    "NOT_AUTHORITY_REVALIDATION", "NOT_CONSTRAINT_REVALIDATION",
    "NOT_POSTCONDITION_VERIFICATION", "NOT_ROLLBACK_PROOF",
    "NOT_AUTHORITY_EVIDENCE", "NOT_HUMAN_APPROVAL",
)


class BindAdapterContractSelectionError(ValueError):
    """Stable fail-closed refusal for local contract selection."""


class BindAdapterContractDescriptor(BaseModel):
    """Immutable pure-data declaration; never an adapter instance."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    adapter_contract_id: str = Field(
        pattern=r"^adapter-contract:v1:sha256:[0-9a-f]{64}$"
    )
    adapter_contract_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    adapter_contract_version: Literal["bind-adapter-contract/v1"]
    adapter_kind: Literal["reference", "webhook", "external", "custom"]
    adapter_name: str = Field(min_length=1)
    target_system: str = Field(min_length=1)
    target_resource_scope: str = Field(min_length=1)
    supported_methods: tuple[str, ...]
    required_methods: tuple[str, ...]
    prohibited_during_selection: tuple[str, ...]
    effect_profile: dict[str, Any]
    declared_by: str = Field(min_length=1)
    declared_at: str
    descriptor_scope_limitations: tuple[str, ...]


class CanonicalBindAdapterContractSelectionPacket(BaseModel):
    """Immutable association proof that conveys no execution authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    format_version: Literal["canonical-bind-adapter-contract-selection/v1"]
    adapter_contract_selection_id: str = Field(
        pattern=r"^bac:v1:sha256:[0-9a-f]{64}$"
    )
    adapter_contract_selection_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    selection_mechanism: Literal[
        "select_bind_adapter_contract_without_invocation/v1"
    ]
    selected_at: str
    source_bind_preflight_adjudication: dict[str, Any]
    source_bind_preflight_adjudication_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_bind_preflight_adjudication_packet: dict[str, Any]
    adapter_contract_descriptor: dict[str, Any]
    adapter_contract_id: str
    adapter_contract_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    adapter_contract_version: Literal["bind-adapter-contract/v1"]
    execution_intent: dict[str, Any]
    execution_intent_id: str = Field(pattern=r"^ei:v1:sha256:[0-9a-f]{64}$")
    execution_intent_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_formation_hash: str
    source_readiness_hash: str
    source_eligibility_hash: str
    source_handoff_hash: str
    trusted_validation_context_hash: str
    validation_result_hash: str
    mapping_value_digest: str
    execution_intent_contract_version: str
    selection_status: Literal["ADAPTER_CONTRACT_SELECTED_FOR_DRY_RUN"]
    ready_for_adapter_dry_run: Literal[True]
    fail_closed: Literal[False]
    local_selection_checks: dict[str, bool]
    future_bind_dry_run_requirements: dict[str, bool]
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
            raise BindAdapterContractSelectionError("BAC_PACKET_INVALID")
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise BindAdapterContractSelectionError("BAC_SELECTED_AT_INVALID")
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _json_value(item) for key, item in value.items()}
    raise BindAdapterContractSelectionError("BAC_PACKET_INVALID")


def _aware_iso(value: Any, code: str) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise BindAdapterContractSelectionError(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise BindAdapterContractSelectionError(code)
    return parsed


def _digest(domain: str, value: Any) -> str:
    encoded = json.dumps(
        {"domain": domain, "value": _json_value(value)}, allow_nan=False,
        ensure_ascii=False, separators=(",", ":"), sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _descriptor_hash(raw: dict[str, Any]) -> str:
    return _digest(DESCRIPTOR_DOMAIN, {key: value for key, value in raw.items()
                                      if key not in {"adapter_contract_id",
                                                     "adapter_contract_hash"}})


def _packet_hash(raw: dict[str, Any]) -> str:
    return _digest(PACKET_DOMAIN, {key: value for key, value in raw.items()
                                  if key not in {"adapter_contract_selection_id",
                                                 "adapter_contract_selection_hash"}})


def _verified_source(value: Any) -> CanonicalBindPreflightAdjudicationPacket:
    try:
        return verify_canonical_bind_preflight_adjudication_packet(value)
    except (BindPreflightAdjudicationError, TypeError, ValueError) as exc:
        raise BindAdapterContractSelectionError("BAC_BIND_PREFLIGHT_INVALID") from exc


def _intent(raw: dict[str, Any]) -> ExecutionIntent:
    try:
        intent = ExecutionIntent(**raw)
        canonical_execution_intent_json(intent)
    except (TypeError, ValueError) as exc:
        raise BindAdapterContractSelectionError("BAC_EXECUTION_INTENT_INVALID") from exc
    if intent.to_dict() != raw:
        raise BindAdapterContractSelectionError("BAC_EXECUTION_INTENT_INVALID")
    return intent


def _descriptor(value: Any, intent: ExecutionIntent) -> BindAdapterContractDescriptor:
    try:
        raw = _json_value(value)
        if not isinstance(raw, dict):
            raise BindAdapterContractSelectionError("BAC_DESCRIPTOR_INVALID")
        supplied_id = raw.pop("adapter_contract_id", None)
        supplied_hash = raw.pop("adapter_contract_hash", None)
        digest = _descriptor_hash(raw)
        if supplied_hash is not None and supplied_hash != digest:
            raise BindAdapterContractSelectionError("BAC_DESCRIPTOR_HASH_MISMATCH")
        expected_id = f"adapter-contract:v1:sha256:{digest}"
        if supplied_id is not None and supplied_id != expected_id:
            raise BindAdapterContractSelectionError("BAC_DESCRIPTOR_ID_MISMATCH")
        raw.update(adapter_contract_hash=digest, adapter_contract_id=expected_id)
        descriptor = BindAdapterContractDescriptor.model_validate(raw)
    except ValidationError as exc:
        raise BindAdapterContractSelectionError("BAC_DESCRIPTOR_INVALID") from exc
    _aware_iso(descriptor.declared_at, "BAC_DESCRIPTOR_INVALID")
    if (descriptor.target_system != intent.target_system or
            descriptor.target_resource_scope != intent.target_resource):
        raise BindAdapterContractSelectionError("BAC_DESCRIPTOR_TARGET_MISMATCH")
    if (descriptor.supported_methods != ADAPTER_METHODS or
            descriptor.required_methods != ADAPTER_METHODS or
            descriptor.prohibited_during_selection != PROHIBITED_DURING_SELECTION):
        raise BindAdapterContractSelectionError("BAC_METHODS_MISMATCH")
    if descriptor.effect_profile != EFFECT_PROFILE:
        raise BindAdapterContractSelectionError("BAC_EFFECT_PROFILE_INVALID")
    if descriptor.descriptor_scope_limitations != DESCRIPTOR_SCOPE_LIMITATIONS:
        raise BindAdapterContractSelectionError("BAC_SCOPE_LIMITATIONS_MISSING")
    return descriptor


def build_bind_adapter_contract_selection_packet(
    bind_preflight_adjudication_packet: Any,
    adapter_contract_descriptor: Any,
    selected_at: datetime,
) -> CanonicalBindAdapterContractSelectionPacket:
    """Build a no-effect association after verifying the complete source."""
    selected = _aware_iso(selected_at, "BAC_SELECTED_AT_INVALID")
    source_packet = _verified_source(_json_value(bind_preflight_adjudication_packet))
    source = source_packet.model_dump(mode="json")
    adjudicated = _aware_iso(source_packet.adjudicated_at, "BAC_BIND_PREFLIGHT_INVALID")
    if selected < adjudicated:
        raise BindAdapterContractSelectionError("BAC_SELECTED_BEFORE_BIND_PREFLIGHT")
    intent = _intent(source_packet.execution_intent)
    if intent.execution_intent_id != source_packet.execution_intent_id:
        raise BindAdapterContractSelectionError("BAC_EXECUTION_INTENT_ID_MISMATCH")
    if hash_execution_intent(intent) != source_packet.execution_intent_hash:
        raise BindAdapterContractSelectionError("BAC_EXECUTION_INTENT_HASH_MISMATCH")
    descriptor = _descriptor(adapter_contract_descriptor, intent)
    descriptor_raw = descriptor.model_dump(mode="json")
    copied = (
        "source_formation_hash", "source_readiness_hash", "source_eligibility_hash",
        "source_handoff_hash", "trusted_validation_context_hash",
        "validation_result_hash", "mapping_value_digest",
        "execution_intent_contract_version", "execution_intent",
        "execution_intent_id", "execution_intent_hash",
        "source_to_execution_intent_mapping", "field_mapping_proof",
        "required_field_presence", "source_decision_identity", "candidate_identity",
        "evidence_lineage", "replay_summary",
    )
    raw = {
        "format_version": FORMAT_VERSION, "selection_mechanism": SELECTION_MECHANISM,
        "selected_at": selected.isoformat(),
        "source_bind_preflight_adjudication": {
            key: source[key] for key in SOURCE_SUMMARY_KEYS
        },
        "source_bind_preflight_adjudication_hash": source_packet.bind_preflight_adjudication_hash,
        "source_bind_preflight_adjudication_packet": source,
        "adapter_contract_descriptor": descriptor_raw,
        "adapter_contract_id": descriptor.adapter_contract_id,
        "adapter_contract_hash": descriptor.adapter_contract_hash,
        "adapter_contract_version": descriptor.adapter_contract_version,
        **{key: source[key] for key in copied},
        "selection_status": "ADAPTER_CONTRACT_SELECTED_FOR_DRY_RUN",
        "ready_for_adapter_dry_run": True, "fail_closed": False,
        "local_selection_checks": LOCAL_SELECTION_CHECKS,
        "future_bind_dry_run_requirements": FUTURE_BIND_DRY_RUN_REQUIREMENTS,
        "scope_limitations": SCOPE_LIMITATIONS,
    }
    digest = _packet_hash(raw)
    raw.update(adapter_contract_selection_hash=digest,
               adapter_contract_selection_id=f"bac:v1:sha256:{digest}")
    return verify_bind_adapter_contract_selection_packet(raw)


def verify_bind_adapter_contract_selection_packet(
    packet: Any,
) -> CanonicalBindAdapterContractSelectionPacket:
    """Revalidate and independently recompute every selection packet binding."""
    try:
        value = packet.model_dump(mode="json") if isinstance(packet, BaseModel) else _json_value(packet)
        candidate = CanonicalBindAdapterContractSelectionPacket.model_validate(value)
    except (ValidationError, BindAdapterContractSelectionError, TypeError) as exc:
        raise BindAdapterContractSelectionError("BAC_PACKET_INVALID") from exc
    raw = candidate.model_dump(mode="json")
    source_packet = _verified_source(candidate.source_bind_preflight_adjudication_packet)
    source = source_packet.model_dump(mode="json")
    if set(candidate.source_bind_preflight_adjudication) != set(SOURCE_SUMMARY_KEYS):
        raise BindAdapterContractSelectionError("BAC_SOURCE_SUMMARY_MISMATCH")
    if candidate.source_bind_preflight_adjudication != {
            key: source[key] for key in SOURCE_SUMMARY_KEYS}:
        raise BindAdapterContractSelectionError("BAC_SOURCE_SUMMARY_MISMATCH")
    selected = _aware_iso(candidate.selected_at, "BAC_SELECTED_AT_INVALID")
    adjudicated = _aware_iso(source_packet.adjudicated_at, "BAC_BIND_PREFLIGHT_INVALID")
    if selected < adjudicated:
        raise BindAdapterContractSelectionError("BAC_SELECTED_BEFORE_BIND_PREFLIGHT")
    copied = (
        "source_formation_hash", "source_readiness_hash", "source_eligibility_hash",
        "source_handoff_hash", "trusted_validation_context_hash",
        "validation_result_hash", "mapping_value_digest",
        "execution_intent_contract_version", "execution_intent",
        "execution_intent_id", "execution_intent_hash",
        "source_to_execution_intent_mapping", "field_mapping_proof",
        "required_field_presence", "source_decision_identity", "candidate_identity",
        "evidence_lineage", "replay_summary",
    )
    if (candidate.source_bind_preflight_adjudication_hash !=
            source_packet.bind_preflight_adjudication_hash or
            any(getattr(candidate, key) != getattr(source_packet, key)
                for key in copied)):
        raise BindAdapterContractSelectionError("BAC_SOURCE_SUMMARY_MISMATCH")
    intent = _intent(candidate.execution_intent)
    if intent.execution_intent_id != candidate.execution_intent_id:
        raise BindAdapterContractSelectionError("BAC_EXECUTION_INTENT_ID_MISMATCH")
    if hash_execution_intent(intent) != candidate.execution_intent_hash:
        raise BindAdapterContractSelectionError("BAC_EXECUTION_INTENT_HASH_MISMATCH")
    descriptor = _descriptor(candidate.adapter_contract_descriptor, intent)
    if (candidate.adapter_contract_descriptor != descriptor.model_dump(mode="json") or
            candidate.adapter_contract_id != descriptor.adapter_contract_id or
            candidate.adapter_contract_hash != descriptor.adapter_contract_hash or
            candidate.adapter_contract_version != descriptor.adapter_contract_version):
        raise BindAdapterContractSelectionError("BAC_DESCRIPTOR_HASH_MISMATCH")
    if candidate.local_selection_checks != LOCAL_SELECTION_CHECKS:
        raise BindAdapterContractSelectionError("BAC_LOCAL_CHECKS_MISMATCH")
    if candidate.future_bind_dry_run_requirements != FUTURE_BIND_DRY_RUN_REQUIREMENTS:
        raise BindAdapterContractSelectionError("BAC_FUTURE_REQUIREMENTS_MISMATCH")
    _digest(LOCAL_CHECKS_DOMAIN, candidate.local_selection_checks)
    _digest(FUTURE_REQUIREMENTS_DOMAIN, candidate.future_bind_dry_run_requirements)
    if candidate.scope_limitations != SCOPE_LIMITATIONS:
        raise BindAdapterContractSelectionError("BAC_SCOPE_LIMITATIONS_MISSING")
    digest = _packet_hash(raw)
    if candidate.adapter_contract_selection_hash != digest:
        raise BindAdapterContractSelectionError("BAC_PACKET_HASH_MISMATCH")
    if candidate.adapter_contract_selection_id != f"bac:v1:sha256:{digest}":
        raise BindAdapterContractSelectionError("BAC_PACKET_ID_MISMATCH")
    return candidate
