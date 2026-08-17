"""Adjudicate deterministic local readiness for a future Bind boundary.

This module verifies and preserves an exact pre-bind validation packet.  It
does not authorize execution, invoke Bind, contact an adapter, or write an
audit record.
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
from veritas_os.policy.canonical_execution_intent_formation import (
    EXECUTION_INTENT_FIELDS,
)
from veritas_os.policy.execution_intent_pre_bind_validation import (
    CanonicalExecutionIntentPreBindValidationPacket,
    ExecutionIntentPreBindValidationError,
    verify_execution_intent_pre_bind_validation_packet,
)

FORMAT_VERSION = "canonical-bind-preflight-adjudication/v1"
ADJUDICATION_MECHANISM = "adjudicate_bind_preflight_locally/v1"
LOCAL_CHECKS_DOMAIN = "veritas.bind-preflight-adjudication.local-checks/v1"
ENTRY_REQUIREMENTS_DOMAIN = (
    "veritas.bind-preflight-adjudication.entry-requirements/v1"
)
PACKET_DOMAIN = "veritas.bind-preflight-adjudication.packet/v1"
SOURCE_PRE_BIND_VALIDATION_SUMMARY_KEYS = (
    "pre_bind_validation_id",
    "pre_bind_validation_hash",
    "format_version",
    "validation_mechanism",
    "checked_at",
    "execution_intent_id",
    "execution_intent_hash",
    "pre_bind_status",
    "ready_for_bind_preflight",
)
LOCAL_ADJUDICATION_CHECKS = {
    "pre_bind_validation_verified": True,
    "execution_intent_hash_verified": True,
    "execution_intent_id_verified": True,
    "source_formation_verified": True,
    "field_mapping_verified": True,
    "required_field_presence_verified": True,
    "evidence_refs_non_empty": True,
    "decision_timestamp_timezone_aware": True,
    "adjudicated_after_pre_bind_validation": True,
    "ttl_locally_well_formed": True,
    "no_bind_invocation": True,
    "no_adapter_invocation": True,
    "no_bind_receipt_created": True,
    "no_trustlog_write": True,
    "no_live_state_check": True,
    "no_runtime_risk_check": True,
}
BIND_ENTRY_REQUIREMENTS = {
    key: True for key in (
        "adapter_required", "adapter_snapshot_required",
        "adapter_authority_revalidation_required",
        "adapter_constraint_validation_required",
        "runtime_risk_assessment_required",
        "commit_boundary_evaluation_required",
        "postcondition_verification_required",
        "rollback_or_revert_path_required", "bind_receipt_required",
        "trustlog_policy_required",
    )
}
SCOPE_LIMITATIONS = (
    "NOT_EXECUTION_AUTHORITY", "NOT_BIND_AUTHORIZATION", "NOT_BIND_RECEIPT",
    "NOT_BIND_INVOCATION", "NOT_ADAPTER_INVOCATION", "NOT_EXTERNAL_EFFECT",
    "NOT_OPERATION_COMMIT", "NOT_TRUSTLOG_WRITE", "NOT_LIVE_STATE_CHECK",
    "NOT_RUNTIME_RISK_ACCEPTANCE", "NOT_AUTHORITY_REVALIDATION",
    "NOT_CONSTRAINT_REVALIDATION", "NOT_POSTCONDITION_VERIFICATION",
    "NOT_ROLLBACK_PROOF", "NOT_AUTHORITY_EVIDENCE", "NOT_HUMAN_APPROVAL",
)


class BindPreflightAdjudicationError(ValueError):
    """Stable fail-closed local adjudication refusal."""


class CanonicalBindPreflightAdjudicationPacket(BaseModel):
    """Immutable proof of local structural readiness, not authorization."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format_version: Literal["canonical-bind-preflight-adjudication/v1"]
    bind_preflight_adjudication_id: str = Field(
        pattern=r"^bpa:v1:sha256:[0-9a-f]{64}$"
    )
    bind_preflight_adjudication_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    adjudication_mechanism: Literal["adjudicate_bind_preflight_locally/v1"]
    adjudicated_at: str
    source_pre_bind_validation: dict[str, Any]
    source_pre_bind_validation_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_pre_bind_validation_packet: dict[str, Any]
    source_formation_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_readiness_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_eligibility_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_handoff_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    trusted_validation_context_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    validation_result_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    mapping_value_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_intent_contract_version: str
    execution_intent: dict[str, Any]
    execution_intent_id: str = Field(pattern=r"^ei:v1:sha256:[0-9a-f]{64}$")
    execution_intent_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    bind_preflight_status: Literal["READY_FOR_BIND_ADJUDICATION"]
    ready_for_bind_adjudication: Literal[True]
    fail_closed: Literal[False]
    local_adjudication_checks: dict[str, bool]
    bind_entry_requirements: dict[str, bool]
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
            raise BindPreflightAdjudicationError("BPA_PACKET_INVALID")
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise BindPreflightAdjudicationError("BPA_ADJUDICATED_AT_INVALID")
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _json_value(item) for key, item in value.items()}
    raise BindPreflightAdjudicationError("BPA_PACKET_INVALID")


def _aware_iso(value: Any, code: str) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise BindPreflightAdjudicationError(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise BindPreflightAdjudicationError(code)
    return parsed


def _digest(domain: str, value: Any) -> str:
    encoded = json.dumps(
        {"domain": domain, "value": _json_value(value)}, allow_nan=False,
        ensure_ascii=False, separators=(",", ":"), sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _packet_hash(raw: dict[str, Any]) -> str:
    return _digest(PACKET_DOMAIN, {key: value for key, value in raw.items() if key not in {
        "bind_preflight_adjudication_id", "bind_preflight_adjudication_hash"
    }})


def _verified_pre_bind(value: Any) -> CanonicalExecutionIntentPreBindValidationPacket:
    try:
        packet = verify_execution_intent_pre_bind_validation_packet(value)
    except (ExecutionIntentPreBindValidationError, TypeError, ValueError) as exc:
        raise BindPreflightAdjudicationError(
            "BPA_PRE_BIND_VALIDATION_INVALID"
        ) from exc
    return packet


def _intent(raw: dict[str, Any]) -> ExecutionIntent:
    if set(raw) != {"execution_intent_id", *EXECUTION_INTENT_FIELDS}:
        raise BindPreflightAdjudicationError("BPA_EXECUTION_INTENT_FIELD_MISMATCH")
    refs, ttl = raw.get("evidence_refs"), raw.get("ttl_seconds")
    if not isinstance(refs, list) or not refs or any(
        not isinstance(ref, str) or not ref.strip() for ref in refs
    ):
        raise BindPreflightAdjudicationError("BPA_EVIDENCE_REFS_INVALID")
    _aware_iso(raw.get("decision_ts"), "BPA_DECISION_TS_INVALID")
    if ttl is not None and (isinstance(ttl, bool) or not isinstance(ttl, int) or ttl < 0):
        raise BindPreflightAdjudicationError("BPA_TTL_INVALID")
    try:
        intent = ExecutionIntent(**raw)
    except (TypeError, ValueError) as exc:
        raise BindPreflightAdjudicationError(
            "BPA_EXECUTION_INTENT_FIELD_MISMATCH"
        ) from exc
    if intent.to_dict() != raw:
        raise BindPreflightAdjudicationError("BPA_EXECUTION_INTENT_FIELD_MISMATCH")
    canonical_execution_intent_json(intent)
    return intent


def build_canonical_bind_preflight_adjudication_packet(
    pre_bind_validation_packet: Any,
    adjudicated_at: datetime,
) -> CanonicalBindPreflightAdjudicationPacket:
    """Build a local packet after independently verifying its full source."""
    adjudicated = _aware_iso(adjudicated_at, "BPA_ADJUDICATED_AT_INVALID")
    source_packet = _verified_pre_bind(_json_value(pre_bind_validation_packet))
    source = source_packet.model_dump(mode="json")
    checked = _aware_iso(source_packet.checked_at, "BPA_PRE_BIND_VALIDATION_INVALID")
    if adjudicated < checked:
        raise BindPreflightAdjudicationError(
            "BPA_ADJUDICATED_BEFORE_PRE_BIND_CHECKED"
        )
    raw = {
        "format_version": FORMAT_VERSION,
        "adjudication_mechanism": ADJUDICATION_MECHANISM,
        "adjudicated_at": adjudicated.isoformat(),
        "source_pre_bind_validation": {
            key: source[key]
            for key in SOURCE_PRE_BIND_VALIDATION_SUMMARY_KEYS
        },
        "source_pre_bind_validation_hash": source_packet.pre_bind_validation_hash,
        "source_pre_bind_validation_packet": source,
        **{key: source[key] for key in (
            "source_formation_hash", "source_readiness_hash", "source_eligibility_hash",
            "source_handoff_hash", "trusted_validation_context_hash",
            "validation_result_hash", "mapping_value_digest",
            "execution_intent_contract_version", "execution_intent",
            "execution_intent_id", "execution_intent_hash",
            "source_to_execution_intent_mapping", "field_mapping_proof",
            "required_field_presence", "source_decision_identity", "candidate_identity",
            "evidence_lineage", "replay_summary",
        )},
        "bind_preflight_status": "READY_FOR_BIND_ADJUDICATION",
        "ready_for_bind_adjudication": True, "fail_closed": False,
        "local_adjudication_checks": LOCAL_ADJUDICATION_CHECKS,
        "bind_entry_requirements": BIND_ENTRY_REQUIREMENTS,
        "scope_limitations": SCOPE_LIMITATIONS,
    }
    digest = _packet_hash(raw)
    raw.update(bind_preflight_adjudication_hash=digest,
               bind_preflight_adjudication_id=f"bpa:v1:sha256:{digest}")
    return verify_canonical_bind_preflight_adjudication_packet(raw)


def verify_canonical_bind_preflight_adjudication_packet(
    packet: Any,
) -> CanonicalBindPreflightAdjudicationPacket:
    """Dump, revalidate, and independently recompute every source binding."""
    try:
        value = packet.model_dump(mode="json") if isinstance(packet, BaseModel) else _json_value(packet)
        candidate = CanonicalBindPreflightAdjudicationPacket.model_validate(value)
    except (ValidationError, BindPreflightAdjudicationError, TypeError) as exc:
        raise BindPreflightAdjudicationError("BPA_PACKET_INVALID") from exc
    raw = candidate.model_dump(mode="json")
    source_packet = _verified_pre_bind(candidate.source_pre_bind_validation_packet)
    source = source_packet.model_dump(mode="json")
    if set(candidate.source_pre_bind_validation) != set(
        SOURCE_PRE_BIND_VALIDATION_SUMMARY_KEYS
    ):
        raise BindPreflightAdjudicationError(
            "BPA_PRE_BIND_VALIDATION_INVALID"
        )
    expected_summary = {
        key: source[key]
        for key in SOURCE_PRE_BIND_VALIDATION_SUMMARY_KEYS
    }
    if candidate.source_pre_bind_validation != expected_summary:
        raise BindPreflightAdjudicationError("BPA_PRE_BIND_VALIDATION_INVALID")
    adjudicated = _aware_iso(candidate.adjudicated_at, "BPA_ADJUDICATED_AT_INVALID")
    checked = _aware_iso(source_packet.checked_at, "BPA_PRE_BIND_VALIDATION_INVALID")
    if adjudicated < checked:
        raise BindPreflightAdjudicationError("BPA_ADJUDICATED_BEFORE_PRE_BIND_CHECKED")
    copied = (
        "source_formation_hash", "source_readiness_hash", "source_eligibility_hash",
        "source_handoff_hash", "trusted_validation_context_hash", "validation_result_hash",
        "mapping_value_digest", "execution_intent_contract_version", "execution_intent",
        "execution_intent_id", "execution_intent_hash", "source_to_execution_intent_mapping",
        "field_mapping_proof", "required_field_presence", "source_decision_identity",
        "candidate_identity", "evidence_lineage", "replay_summary",
    )
    if candidate.source_pre_bind_validation_hash != source_packet.pre_bind_validation_hash or any(
        getattr(candidate, key) != getattr(source_packet, key) for key in copied
    ):
        raise BindPreflightAdjudicationError("BPA_MAPPING_MISMATCH")
    intent = _intent(candidate.execution_intent)
    mapping = {key: candidate.execution_intent[key] for key in EXECUTION_INTENT_FIELDS}
    if candidate.execution_intent_id != intent.execution_intent_id:
        raise BindPreflightAdjudicationError("BPA_EXECUTION_INTENT_ID_MISMATCH")
    if candidate.execution_intent_hash != hash_execution_intent(intent):
        raise BindPreflightAdjudicationError("BPA_EXECUTION_INTENT_HASH_MISMATCH")
    if candidate.source_to_execution_intent_mapping != mapping:
        raise BindPreflightAdjudicationError("BPA_MAPPING_MISMATCH")
    if candidate.field_mapping_proof != mapping:
        raise BindPreflightAdjudicationError("BPA_FIELD_MAPPING_PROOF_MISMATCH")
    if candidate.local_adjudication_checks != LOCAL_ADJUDICATION_CHECKS:
        raise BindPreflightAdjudicationError("BPA_LOCAL_CHECKS_MISMATCH")
    if candidate.bind_entry_requirements != BIND_ENTRY_REQUIREMENTS:
        raise BindPreflightAdjudicationError("BPA_ENTRY_REQUIREMENTS_MISMATCH")
    _digest(LOCAL_CHECKS_DOMAIN, candidate.local_adjudication_checks)
    _digest(ENTRY_REQUIREMENTS_DOMAIN, candidate.bind_entry_requirements)
    if candidate.scope_limitations != SCOPE_LIMITATIONS:
        raise BindPreflightAdjudicationError("BPA_SCOPE_LIMITATIONS_MISSING")
    digest = _packet_hash(raw)
    if candidate.bind_preflight_adjudication_hash != digest:
        raise BindPreflightAdjudicationError("BPA_PACKET_HASH_MISMATCH")
    if candidate.bind_preflight_adjudication_id != f"bpa:v1:sha256:{digest}":
        raise BindPreflightAdjudicationError("BPA_PACKET_ID_MISMATCH")
    return candidate
