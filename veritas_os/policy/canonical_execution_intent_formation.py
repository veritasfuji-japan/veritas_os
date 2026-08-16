"""Deterministically form an ExecutionIntent without crossing the Bind boundary.

The artifact produced here proves only that an exact, verified readiness packet
was mapped into an exact ``ExecutionIntent``.  This module deliberately has no
I/O, TrustLog, adapter, authorization, or Bind capability.
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
from veritas_os.policy.execution_intent_formation_readiness import (
    CanonicalExecutionIntentFormationReadinessPacket,
    ExecutionIntentFormationReadinessError,
    verify_execution_intent_formation_readiness_packet,
)

FORMAT_VERSION = "canonical-execution-intent-formation/v1"
FORMATION_MECHANISM = "build_execution_intent_from_readiness/v1"
EXECUTION_INTENT_ID_DOMAIN = (
    "veritas.execution-intent-formation.execution-intent-id/v1"
)
FIELD_MAPPING_DOMAIN = "veritas.execution-intent-formation.field-mapping/v1"
PACKET_DOMAIN = "veritas.execution-intent-formation.packet/v1"
EXECUTION_INTENT_FIELDS = (
    "decision_id",
    "request_id",
    "policy_snapshot_id",
    "actor_identity",
    "target_system",
    "target_resource",
    "intended_action",
    "evidence_refs",
    "decision_hash",
    "decision_ts",
    "ttl_seconds",
    "expected_state_fingerprint",
    "approval_context",
    "policy_lineage",
)
SCOPE_LIMITATIONS = (
    "NOT_EXECUTION_AUTHORITY",
    "NOT_BIND_AUTHORIZATION",
    "NOT_BIND_RECEIPT",
    "NOT_BIND_INVOCATION",
    "NOT_EXTERNAL_EFFECT",
    "NOT_ADAPTER_INVOCATION",
    "NOT_OPERATION_COMMIT",
    "NOT_TRUSTLOG_WRITE",
    "NOT_AUTHORITY_EVIDENCE",
    "NOT_HUMAN_APPROVAL",
)


class CanonicalExecutionIntentFormationError(ValueError):
    """Stable fail-closed formation construction or verification refusal."""


class CanonicalExecutionIntentFormationPacket(BaseModel):
    """Strict immutable binding between readiness and a formed intent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format_version: Literal["canonical-execution-intent-formation/v1"]
    formation_id: str = Field(pattern=r"^eif:v1:sha256:[0-9a-f]{64}$")
    formation_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    formation_mechanism: Literal["build_execution_intent_from_readiness/v1"]
    formed_at: str
    source_readiness: dict[str, Any]
    source_readiness_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_readiness_packet: dict[str, Any]
    source_eligibility_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_handoff_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    trusted_validation_context_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    validation_result_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    mapping_value_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_intent_contract_version: str
    execution_intent: dict[str, Any]
    execution_intent_id: str = Field(pattern=r"^ei:v1:sha256:[0-9a-f]{64}$")
    execution_intent_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
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
            raise CanonicalExecutionIntentFormationError("EIF_PACKET_INVALID")
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise CanonicalExecutionIntentFormationError("EIF_FORMED_AT_INVALID")
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise CanonicalExecutionIntentFormationError("EIF_PACKET_INVALID")
        return {key: _json_value(item) for key, item in value.items()}
    raise CanonicalExecutionIntentFormationError("EIF_PACKET_INVALID")


def _digest(domain: str, value: Any) -> str:
    payload = json.dumps(
        {"domain": domain, "value": _json_value(value)},
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _packet_hash(raw: dict[str, Any]) -> str:
    preimage = {
        key: value
        for key, value in raw.items()
        if key not in {"formation_id", "formation_hash"}
    }
    return _digest(PACKET_DOMAIN, preimage)


def _aware_iso(value: Any) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise CanonicalExecutionIntentFormationError(
            "EIF_FORMED_AT_INVALID"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CanonicalExecutionIntentFormationError("EIF_FORMED_AT_INVALID")
    return parsed


def _verified_readiness(
    value: Any,
) -> CanonicalExecutionIntentFormationReadinessPacket:
    try:
        readiness = verify_execution_intent_formation_readiness_packet(value)
    except (ExecutionIntentFormationReadinessError, TypeError, ValueError) as exc:
        raise CanonicalExecutionIntentFormationError("EIF_READINESS_INVALID") from exc
    if not (
        readiness.formation_status == "READY_FOR_EXECUTION_INTENT_FORMATION"
        and readiness.ready_for_execution_intent_formation is True
        and readiness.fail_closed is False
    ):
        raise CanonicalExecutionIntentFormationError("EIF_READINESS_INVALID")
    return readiness


def _execution_intent_id(readiness: Any) -> str:
    value = {
        "source_readiness_id": readiness.readiness_id,
        "source_readiness_hash": readiness.readiness_hash,
        "mapping_value_digest": readiness.mapping_value_digest,
        "source_to_execution_intent_mapping": (
            readiness.source_to_execution_intent_mapping
        ),
        "execution_intent_contract_version": (
            readiness.execution_intent_contract_version
        ),
    }
    return f"ei:v1:sha256:{_digest(EXECUTION_INTENT_ID_DOMAIN, value)}"


def _intent(intent_id: str, mapping: dict[str, Any]) -> ExecutionIntent:
    if set(mapping) != set(EXECUTION_INTENT_FIELDS):
        raise CanonicalExecutionIntentFormationError("EIF_MAPPING_MISMATCH")
    try:
        return ExecutionIntent(execution_intent_id=intent_id, **mapping)
    except (TypeError, ValueError) as exc:
        raise CanonicalExecutionIntentFormationError(
            "EIF_EXECUTION_INTENT_FIELD_MISMATCH"
        ) from exc


def build_canonical_execution_intent_formation_packet(
    readiness_packet: Any,
    formed_at: datetime,
) -> CanonicalExecutionIntentFormationPacket:
    """Form an intent solely from a verified readiness packet.

    Args:
        readiness_packet: Full canonical formation-readiness artifact.
        formed_at: Caller-supplied timezone-aware formation time.

    Returns:
        A content-addressed packet containing the deterministic intent.
    """
    formed = _aware_iso(formed_at)
    readiness = _verified_readiness(_json_value(readiness_packet))
    checked = _aware_iso(readiness.checked_at)
    if formed < checked:
        raise CanonicalExecutionIntentFormationError(
            "EIF_FORMED_BEFORE_READINESS_CHECKED"
        )
    source_packet = readiness.model_dump(mode="json")
    intent_id = _execution_intent_id(readiness)
    intent = _intent(intent_id, readiness.source_to_execution_intent_mapping)
    intent_json = intent.to_dict()
    raw = {
        "format_version": FORMAT_VERSION,
        "formation_mechanism": FORMATION_MECHANISM,
        "formed_at": formed.isoformat(),
        "source_readiness": {
            key: source_packet[key]
            for key in (
                "readiness_id",
                "readiness_hash",
                "format_version",
                "checked_at",
                "formation_status",
                "ready_for_execution_intent_formation",
            )
        },
        "source_readiness_hash": readiness.readiness_hash,
        "source_readiness_packet": source_packet,
        "source_eligibility_hash": readiness.source_eligibility_hash,
        "source_handoff_hash": readiness.source_handoff_hash,
        "trusted_validation_context_hash": readiness.trusted_validation_context_hash,
        "validation_result_hash": readiness.validation_result_hash,
        "mapping_value_digest": readiness.mapping_value_digest,
        "execution_intent_contract_version": (
            readiness.execution_intent_contract_version
        ),
        "execution_intent": intent_json,
        "execution_intent_id": intent_id,
        "execution_intent_hash": hash_execution_intent(intent),
        "source_to_execution_intent_mapping": (
            readiness.source_to_execution_intent_mapping
        ),
        "field_mapping_proof": {
            key: intent_json[key] for key in EXECUTION_INTENT_FIELDS
        },
        "required_field_presence": readiness.required_field_presence,
        "source_decision_identity": readiness.source_decision_identity,
        "candidate_identity": readiness.candidate_identity,
        "evidence_lineage": readiness.evidence_lineage,
        "replay_summary": readiness.replay_summary,
        "scope_limitations": SCOPE_LIMITATIONS,
    }
    digest = _packet_hash(raw)
    raw.update(formation_hash=digest, formation_id=f"eif:v1:sha256:{digest}")
    return verify_canonical_execution_intent_formation_packet(raw)


def verify_canonical_execution_intent_formation_packet(
    packet: Any,
) -> CanonicalExecutionIntentFormationPacket:
    """Independently revalidate every source, mapping, and hash binding."""
    try:
        raw_input = (
            packet.model_dump(mode="json")
            if isinstance(packet, BaseModel)
            else _json_value(packet)
        )
        candidate = CanonicalExecutionIntentFormationPacket.model_validate(raw_input)
    except (ValidationError, CanonicalExecutionIntentFormationError, TypeError) as exc:
        raise CanonicalExecutionIntentFormationError("EIF_PACKET_INVALID") from exc
    raw = candidate.model_dump(mode="json")
    readiness = _verified_readiness(candidate.source_readiness_packet)
    formed = _aware_iso(candidate.formed_at)
    if formed < _aware_iso(readiness.checked_at):
        raise CanonicalExecutionIntentFormationError(
            "EIF_FORMED_BEFORE_READINESS_CHECKED"
        )
    source_packet = readiness.model_dump(mode="json")
    summary_keys = {
        "readiness_id",
        "readiness_hash",
        "format_version",
        "checked_at",
        "formation_status",
        "ready_for_execution_intent_formation",
    }
    expected_summary = {key: source_packet[key] for key in summary_keys}
    if candidate.source_readiness != expected_summary:
        raise CanonicalExecutionIntentFormationError("EIF_READINESS_INVALID")
    bindings = (
        (candidate.source_readiness_hash, readiness.readiness_hash),
        (candidate.source_eligibility_hash, readiness.source_eligibility_hash),
        (candidate.source_handoff_hash, readiness.source_handoff_hash),
        (
            candidate.trusted_validation_context_hash,
            readiness.trusted_validation_context_hash,
        ),
        (candidate.validation_result_hash, readiness.validation_result_hash),
        (candidate.mapping_value_digest, readiness.mapping_value_digest),
        (
            candidate.execution_intent_contract_version,
            readiness.execution_intent_contract_version,
        ),
    )
    if any(actual != expected for actual, expected in bindings):
        raise CanonicalExecutionIntentFormationError("EIF_MAPPING_MISMATCH")
    mapping = readiness.source_to_execution_intent_mapping
    if candidate.source_to_execution_intent_mapping != mapping:
        raise CanonicalExecutionIntentFormationError("EIF_MAPPING_MISMATCH")
    intent_id = _execution_intent_id(readiness)
    if candidate.execution_intent_id != intent_id:
        raise CanonicalExecutionIntentFormationError(
            "EIF_EXECUTION_INTENT_ID_MISMATCH"
        )
    expected_intent = _intent(intent_id, mapping)
    expected_json = expected_intent.to_dict()
    if candidate.execution_intent != expected_json:
        raise CanonicalExecutionIntentFormationError(
            "EIF_EXECUTION_INTENT_FIELD_MISMATCH"
        )
    reconstructed = _intent(intent_id, {
        key: candidate.execution_intent[key] for key in EXECUTION_INTENT_FIELDS
    })
    if reconstructed.to_dict() != candidate.execution_intent:
        raise CanonicalExecutionIntentFormationError(
            "EIF_EXECUTION_INTENT_FIELD_MISMATCH"
        )
    if candidate.execution_intent_hash != hash_execution_intent(reconstructed):
        raise CanonicalExecutionIntentFormationError(
            "EIF_EXECUTION_INTENT_HASH_MISMATCH"
        )
    # Exercise and bind the existing canonical serialization contract as well.
    canonical_execution_intent_json(reconstructed)
    proof = {key: expected_json[key] for key in EXECUTION_INTENT_FIELDS}
    if candidate.field_mapping_proof != proof:
        raise CanonicalExecutionIntentFormationError(
            "EIF_FIELD_MAPPING_PROOF_MISMATCH"
        )
    preserved = (
        (candidate.required_field_presence, readiness.required_field_presence),
        (candidate.source_decision_identity, readiness.source_decision_identity),
        (candidate.candidate_identity, readiness.candidate_identity),
        (candidate.evidence_lineage, readiness.evidence_lineage),
        (candidate.replay_summary, readiness.replay_summary),
    )
    if any(actual != expected for actual, expected in preserved):
        raise CanonicalExecutionIntentFormationError("EIF_MAPPING_MISMATCH")
    if candidate.scope_limitations != SCOPE_LIMITATIONS:
        raise CanonicalExecutionIntentFormationError("EIF_SCOPE_LIMITATIONS_MISSING")
    digest = _packet_hash(raw)
    if candidate.formation_hash != digest:
        raise CanonicalExecutionIntentFormationError("EIF_FORMATION_HASH_MISMATCH")
    if candidate.formation_id != f"eif:v1:sha256:{digest}":
        raise CanonicalExecutionIntentFormationError("EIF_FORMATION_ID_MISMATCH")
    return candidate
