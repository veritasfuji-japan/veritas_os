"""Validate a formed ExecutionIntent without crossing the Bind boundary.

This deterministic, local module binds an exact ExecutionIntent to an exact,
independently verified Canonical ExecutionIntent Formation Packet.  It performs
no authorization, I/O, adapter activity, TrustLog write, or Bind invocation.
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
    CanonicalExecutionIntentFormationError,
    CanonicalExecutionIntentFormationPacket,
    verify_canonical_execution_intent_formation_packet,
)

FORMAT_VERSION = "canonical-execution-intent-pre-bind-validation/v1"
VALIDATION_MECHANISM = "validate_execution_intent_before_bind/v1"
LOCAL_CHECKS_DOMAIN = (
    "veritas.execution-intent-pre-bind-validation.local-checks/v1"
)
PACKET_DOMAIN = "veritas.execution-intent-pre-bind-validation.packet/v1"
PRE_BIND_STATUS = "READY_FOR_BIND_PREFLIGHT"
LOCAL_VALIDATION_CHECKS = {
    "formation_verified": True,
    "execution_intent_hash_verified": True,
    "execution_intent_id_verified": True,
    "field_mapping_verified": True,
    "required_field_presence_verified": True,
    "evidence_refs_non_empty": True,
    "decision_timestamp_timezone_aware": True,
    "checked_after_formation": True,
    "no_bind_invocation": True,
    "no_trustlog_write": True,
}
SCOPE_LIMITATIONS = (
    "NOT_EXECUTION_AUTHORITY",
    "NOT_BIND_AUTHORIZATION",
    "NOT_BIND_RECEIPT",
    "NOT_BIND_INVOCATION",
    "NOT_ADAPTER_INVOCATION",
    "NOT_EXTERNAL_EFFECT",
    "NOT_OPERATION_COMMIT",
    "NOT_TRUSTLOG_WRITE",
    "NOT_LIVE_STATE_CHECK",
    "NOT_RUNTIME_RISK_ACCEPTANCE",
    "NOT_AUTHORITY_EVIDENCE",
    "NOT_HUMAN_APPROVAL",
)


class ExecutionIntentPreBindValidationError(ValueError):
    """Stable fail-closed pre-bind construction or verification refusal."""


class CanonicalExecutionIntentPreBindValidationPacket(BaseModel):
    """Strict immutable proof of deterministic local pre-bind checks only."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format_version: Literal[
        "canonical-execution-intent-pre-bind-validation/v1"
    ]
    pre_bind_validation_id: str = Field(
        pattern=r"^eipbv:v1:sha256:[0-9a-f]{64}$"
    )
    pre_bind_validation_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    validation_mechanism: Literal["validate_execution_intent_before_bind/v1"]
    checked_at: str
    source_formation: dict[str, Any]
    source_formation_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_formation_packet: dict[str, Any]
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
    pre_bind_status: Literal["READY_FOR_BIND_PREFLIGHT"]
    ready_for_bind_preflight: Literal[True]
    fail_closed: Literal[False]
    local_validation_checks: dict[str, bool]
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
            raise ExecutionIntentPreBindValidationError("EIPBV_PACKET_INVALID")
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ExecutionIntentPreBindValidationError(
                "EIPBV_CHECKED_AT_INVALID"
            )
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ExecutionIntentPreBindValidationError("EIPBV_PACKET_INVALID")
        return {key: _json_value(item) for key, item in value.items()}
    raise ExecutionIntentPreBindValidationError("EIPBV_PACKET_INVALID")


def _aware_iso(value: Any, code: str) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ExecutionIntentPreBindValidationError(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ExecutionIntentPreBindValidationError(code)
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
            if key not in {
                "pre_bind_validation_id",
                "pre_bind_validation_hash",
            }
        },
    )


def _verified_formation(
    value: Any,
) -> CanonicalExecutionIntentFormationPacket:
    try:
        formation = verify_canonical_execution_intent_formation_packet(value)
    except (CanonicalExecutionIntentFormationError, TypeError, ValueError) as exc:
        raise ExecutionIntentPreBindValidationError(
            "EIPBV_FORMATION_INVALID"
        ) from exc
    if formation.format_version != "canonical-execution-intent-formation/v1":
        raise ExecutionIntentPreBindValidationError("EIPBV_FORMATION_INVALID")
    return formation


def _reconstruct_intent(raw: dict[str, Any]) -> ExecutionIntent:
    expected = {"execution_intent_id", *EXECUTION_INTENT_FIELDS}
    if set(raw) != expected:
        raise ExecutionIntentPreBindValidationError(
            "EIPBV_EXECUTION_INTENT_FIELD_MISMATCH"
        )
    required_strings = set(EXECUTION_INTENT_FIELDS) - {
        "evidence_refs",
        "ttl_seconds",
        "approval_context",
        "policy_lineage",
    }
    if any(
        not isinstance(raw[field], str) or not raw[field].strip()
        for field in required_strings
    ):
        raise ExecutionIntentPreBindValidationError(
            "EIPBV_EXECUTION_INTENT_FIELD_MISMATCH"
        )
    refs = raw["evidence_refs"]
    if not isinstance(refs, list) or not refs or any(
        not isinstance(ref, str) or not ref.strip() for ref in refs
    ):
        raise ExecutionIntentPreBindValidationError(
            "EIPBV_EVIDENCE_REFS_INVALID"
        )
    _aware_iso(raw["decision_ts"], "EIPBV_DECISION_TS_INVALID")
    ttl = raw["ttl_seconds"]
    if ttl is not None and (
        isinstance(ttl, bool) or not isinstance(ttl, int) or ttl < 0
    ):
        raise ExecutionIntentPreBindValidationError("EIPBV_TTL_INVALID")
    try:
        intent = ExecutionIntent(**raw)
    except (TypeError, ValueError) as exc:
        raise ExecutionIntentPreBindValidationError(
            "EIPBV_EXECUTION_INTENT_FIELD_MISMATCH"
        ) from exc
    if intent.to_dict() != raw:
        raise ExecutionIntentPreBindValidationError(
            "EIPBV_EXECUTION_INTENT_FIELD_MISMATCH"
        )
    canonical_execution_intent_json(intent)
    return intent


def build_execution_intent_pre_bind_validation_packet(
    formation_packet: Any,
    checked_at: datetime,
) -> CanonicalExecutionIntentPreBindValidationPacket:
    """Build a local validation packet from an independently verified formation.

    Args:
        formation_packet: Full Canonical ExecutionIntent Formation Packet.
        checked_at: Caller-supplied timezone-aware validation time.

    Returns:
        A content-addressed packet that makes no authorization claim.
    """
    checked = _aware_iso(checked_at, "EIPBV_CHECKED_AT_INVALID")
    formation = _verified_formation(_json_value(formation_packet))
    formed = _aware_iso(formation.formed_at, "EIPBV_FORMATION_INVALID")
    if checked < formed:
        raise ExecutionIntentPreBindValidationError(
            "EIPBV_CHECKED_BEFORE_FORMED"
        )
    source = formation.model_dump(mode="json")
    raw = {
        "format_version": FORMAT_VERSION,
        "validation_mechanism": VALIDATION_MECHANISM,
        "checked_at": checked.isoformat(),
        "source_formation": {
            key: source[key]
            for key in (
                "formation_id",
                "formation_hash",
                "format_version",
                "formation_mechanism",
                "formed_at",
                "execution_intent_id",
                "execution_intent_hash",
            )
        },
        "source_formation_hash": formation.formation_hash,
        "source_formation_packet": source,
        "source_readiness_hash": formation.source_readiness_hash,
        "source_eligibility_hash": formation.source_eligibility_hash,
        "source_handoff_hash": formation.source_handoff_hash,
        "trusted_validation_context_hash": (
            formation.trusted_validation_context_hash
        ),
        "validation_result_hash": formation.validation_result_hash,
        "mapping_value_digest": formation.mapping_value_digest,
        "execution_intent_contract_version": (
            formation.execution_intent_contract_version
        ),
        "execution_intent": formation.execution_intent,
        "execution_intent_id": formation.execution_intent_id,
        "execution_intent_hash": formation.execution_intent_hash,
        "pre_bind_status": PRE_BIND_STATUS,
        "ready_for_bind_preflight": True,
        "fail_closed": False,
        "local_validation_checks": LOCAL_VALIDATION_CHECKS,
        "source_to_execution_intent_mapping": (
            formation.source_to_execution_intent_mapping
        ),
        "field_mapping_proof": formation.field_mapping_proof,
        "required_field_presence": formation.required_field_presence,
        "source_decision_identity": formation.source_decision_identity,
        "candidate_identity": formation.candidate_identity,
        "evidence_lineage": formation.evidence_lineage,
        "replay_summary": formation.replay_summary,
        "scope_limitations": SCOPE_LIMITATIONS,
    }
    digest = _packet_hash(raw)
    raw.update(
        pre_bind_validation_hash=digest,
        pre_bind_validation_id=f"eipbv:v1:sha256:{digest}",
    )
    return verify_execution_intent_pre_bind_validation_packet(raw)


def verify_execution_intent_pre_bind_validation_packet(
    packet: Any,
) -> CanonicalExecutionIntentPreBindValidationPacket:
    """Independently revalidate all formation, intent, and packet bindings."""
    try:
        raw_input = (
            packet.model_dump(mode="json")
            if isinstance(packet, BaseModel)
            else _json_value(packet)
        )
        candidate = CanonicalExecutionIntentPreBindValidationPacket.model_validate(
            raw_input
        )
    except (ValidationError, ExecutionIntentPreBindValidationError, TypeError) as exc:
        raise ExecutionIntentPreBindValidationError("EIPBV_PACKET_INVALID") from exc
    raw = candidate.model_dump(mode="json")
    formation = _verified_formation(candidate.source_formation_packet)
    checked = _aware_iso(candidate.checked_at, "EIPBV_CHECKED_AT_INVALID")
    formed = _aware_iso(formation.formed_at, "EIPBV_FORMATION_INVALID")
    if checked < formed:
        raise ExecutionIntentPreBindValidationError(
            "EIPBV_CHECKED_BEFORE_FORMED"
        )
    source = formation.model_dump(mode="json")
    summary_keys = (
        "formation_id",
        "formation_hash",
        "format_version",
        "formation_mechanism",
        "formed_at",
        "execution_intent_id",
        "execution_intent_hash",
    )
    if candidate.source_formation != {
        key: source[key] for key in summary_keys
    }:
        raise ExecutionIntentPreBindValidationError("EIPBV_FORMATION_INVALID")
    bindings = (
        (candidate.source_formation_hash, formation.formation_hash),
        (candidate.source_readiness_hash, formation.source_readiness_hash),
        (candidate.source_eligibility_hash, formation.source_eligibility_hash),
        (candidate.source_handoff_hash, formation.source_handoff_hash),
        (
            candidate.trusted_validation_context_hash,
            formation.trusted_validation_context_hash,
        ),
        (candidate.validation_result_hash, formation.validation_result_hash),
        (candidate.mapping_value_digest, formation.mapping_value_digest),
        (
            candidate.execution_intent_contract_version,
            formation.execution_intent_contract_version,
        ),
    )
    if any(actual != expected for actual, expected in bindings):
        raise ExecutionIntentPreBindValidationError("EIPBV_MAPPING_MISMATCH")
    intent = _reconstruct_intent(candidate.execution_intent)
    if candidate.execution_intent != formation.execution_intent:
        raise ExecutionIntentPreBindValidationError(
            "EIPBV_EXECUTION_INTENT_FIELD_MISMATCH"
        )
    if candidate.execution_intent_id != intent.execution_intent_id or (
        candidate.execution_intent_id != formation.execution_intent_id
    ):
        raise ExecutionIntentPreBindValidationError(
            "EIPBV_EXECUTION_INTENT_ID_MISMATCH"
        )
    computed_intent_hash = hash_execution_intent(intent)
    if candidate.execution_intent_hash != computed_intent_hash or (
        candidate.execution_intent_hash != formation.execution_intent_hash
    ):
        raise ExecutionIntentPreBindValidationError(
            "EIPBV_EXECUTION_INTENT_HASH_MISMATCH"
        )
    mapping = {
        key: candidate.execution_intent[key] for key in EXECUTION_INTENT_FIELDS
    }
    if candidate.source_to_execution_intent_mapping != mapping or (
        candidate.source_to_execution_intent_mapping
        != formation.source_to_execution_intent_mapping
    ):
        raise ExecutionIntentPreBindValidationError("EIPBV_MAPPING_MISMATCH")
    if candidate.field_mapping_proof != mapping or (
        candidate.field_mapping_proof != formation.field_mapping_proof
    ):
        raise ExecutionIntentPreBindValidationError(
            "EIPBV_FIELD_MAPPING_PROOF_MISMATCH"
        )
    preserved = (
        (candidate.required_field_presence, formation.required_field_presence),
        (candidate.source_decision_identity, formation.source_decision_identity),
        (candidate.candidate_identity, formation.candidate_identity),
        (candidate.evidence_lineage, formation.evidence_lineage),
        (candidate.replay_summary, formation.replay_summary),
    )
    if any(actual != expected for actual, expected in preserved):
        raise ExecutionIntentPreBindValidationError("EIPBV_MAPPING_MISMATCH")
    if candidate.local_validation_checks != LOCAL_VALIDATION_CHECKS:
        raise ExecutionIntentPreBindValidationError(
            "EIPBV_LOCAL_CHECKS_MISMATCH"
        )
    # Bind the checks to their own domain without changing packet hash semantics.
    _digest(LOCAL_CHECKS_DOMAIN, candidate.local_validation_checks)
    if candidate.scope_limitations != SCOPE_LIMITATIONS:
        raise ExecutionIntentPreBindValidationError(
            "EIPBV_SCOPE_LIMITATIONS_MISSING"
        )
    digest = _packet_hash(raw)
    if candidate.pre_bind_validation_hash != digest:
        raise ExecutionIntentPreBindValidationError(
            "EIPBV_PACKET_HASH_MISMATCH"
        )
    if candidate.pre_bind_validation_id != f"eipbv:v1:sha256:{digest}":
        raise ExecutionIntentPreBindValidationError("EIPBV_PACKET_ID_MISMATCH")
    return candidate
