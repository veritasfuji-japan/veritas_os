"""Verify deterministic source readiness for future ExecutionIntent formation.

This local boundary only maps an already verified guarded-promotion eligibility
packet.  It deliberately creates no execution artifact, authority, receipt,
TrustLog entry, adapter invocation, or external effect.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from veritas_os.policy.guarded_promotion_eligibility import (
    CanonicalGuardedPromotionEligibilityPacket,
    GuardedPromotionEligibilityError,
    verify_guarded_promotion_eligibility_packet,
)

FORMAT_VERSION = "canonical-execution-intent-formation-readiness/v1"
VERIFICATION_MECHANISM = "verify_guarded_promotion_eligibility_packet/v1"
EXECUTION_INTENT_CONTRACT_VERSION = "execution-intent-contract/v1"
MAPPING_DOMAIN = "veritas.execution-intent-formation-readiness.mapping/v1"
REQUIRED_FIELDS_DOMAIN = (
    "veritas.execution-intent-formation-readiness.required-fields/v1"
)
PACKET_DOMAIN = "veritas.execution-intent-formation-readiness.packet/v1"
EXECUTION_INTENT_REQUIRED_FIELDS = (
    "execution_intent_id",
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
REQUIRED_FIELD_PRESENCE = {
    field: (
        "intentionally_deferred"
        if field in {"execution_intent_id", "ttl_seconds"}
        else "mapped"
    )
    for field in EXECUTION_INTENT_REQUIRED_FIELDS
}
SCOPE_LIMITATIONS = (
    "NOT_EXECUTION_INTENT",
    "NOT_EXECUTION_AUTHORITY",
    "NOT_BIND_AUTHORIZATION",
    "NOT_BIND_RECEIPT",
    "NOT_EXTERNAL_EFFECT",
    "NOT_ADAPTER_INVOCATION",
    "NOT_OPERATION_COMMIT",
    "NOT_TRUSTLOG_WRITE",
)


class ExecutionIntentFormationReadinessError(ValueError):
    """Stable fail-closed readiness construction or verification refusal."""


class CanonicalExecutionIntentFormationReadinessPacket(BaseModel):
    """Strict immutable audit packet proving formation-source readiness only."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format_version: Literal["canonical-execution-intent-formation-readiness/v1"]
    readiness_id: str = Field(pattern=r"^eifr:v1:sha256:[0-9a-f]{64}$")
    readiness_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    verification_mechanism: Literal["verify_guarded_promotion_eligibility_packet/v1"]
    checked_at: str
    source_eligibility: dict[str, Any]
    source_eligibility_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_eligibility_packet: dict[str, Any]
    source_handoff_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    trusted_validation_context_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    validation_result_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    formation_status: Literal["READY_FOR_EXECUTION_INTENT_FORMATION"]
    ready_for_execution_intent_formation: Literal[True]
    fail_closed: Literal[False]
    execution_intent_contract_version: Literal["execution-intent-contract/v1"]
    execution_intent_required_fields: tuple[str, ...]
    source_to_execution_intent_mapping: dict[str, Any]
    mapping_value_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
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
            raise ExecutionIntentFormationReadinessError("EIFR_PACKET_INVALID")
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ExecutionIntentFormationReadinessError("EIFR_CHECKED_AT_INVALID")
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ExecutionIntentFormationReadinessError("EIFR_PACKET_INVALID")
        return {key: _json_value(item) for key, item in value.items()}
    raise ExecutionIntentFormationReadinessError("EIFR_PACKET_INVALID")


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
            if key not in {"readiness_id", "readiness_hash"}
        },
    )


def _aware_iso(value: Any, code: str) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ExecutionIntentFormationReadinessError(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ExecutionIntentFormationReadinessError(code)
    return parsed


def _require_source_fields(
    eligibility: CanonicalGuardedPromotionEligibilityPacket,
) -> None:
    paths = {
        "source_decision_identity": (
            "request_id",
            "canonical_decision_id",
            "canonical_decision_hash",
            "canonical_decision_ts",
        ),
        "candidate_identity": (
            "actor_identity",
            "target_system",
            "target_resource",
            "action_contract_id",
            "action_contract_version",
        ),
        "evidence_lineage": (
            "trustlog_artifact_ref",
            "trustlog_chain_hash",
            "replay_artifact_ref",
            "replay_artifact_hash",
            "authority_evidence_ref",
            "authority_evidence_hash",
            "human_approval_receipt_ref",
            "human_approval_receipt_hash",
            "policy_snapshot_id",
            "policy_version",
            "policy_semantic_digest",
            "expected_state_fingerprint",
            "expected_state_source_ref",
        ),
    }
    for section, fields in paths.items():
        values = getattr(eligibility, section)
        if any(
            not isinstance(values.get(field), str) or not values[field].strip()
            for field in fields
        ):
            raise ExecutionIntentFormationReadinessError("EIFR_SOURCE_FIELD_MISSING")
    _aware_iso(
        eligibility.source_decision_identity["canonical_decision_ts"],
        "EIFR_SOURCE_FIELD_MISSING",
    )
    replay = eligibility.replay_summary
    if replay.get("original_request_id") is not None and (
        replay.get("original_request_id") == replay.get("replay_request_id")
        or replay.get("original_decision_id") == replay.get("replay_decision_id")
    ):
        raise ExecutionIntentFormationReadinessError("EIFR_REPLAY_IDENTITY_COLLAPSED")


def _mapping(
    eligibility: CanonicalGuardedPromotionEligibilityPacket,
) -> dict[str, Any]:
    source = eligibility.source_decision_identity
    candidate = eligibility.candidate_identity
    evidence = eligibility.evidence_lineage
    return {
        "decision_id": source["canonical_decision_id"],
        "request_id": source["request_id"],
        "policy_snapshot_id": evidence["policy_snapshot_id"],
        "actor_identity": candidate["actor_identity"],
        "target_system": candidate["target_system"],
        "target_resource": candidate["target_resource"],
        "intended_action": candidate["action_contract_id"],
        "evidence_refs": [
            evidence["trustlog_artifact_ref"],
            evidence["replay_artifact_ref"],
            evidence["authority_evidence_ref"],
            evidence["human_approval_receipt_ref"],
            evidence["expected_state_source_ref"],
        ],
        "decision_hash": source["canonical_decision_hash"],
        "decision_ts": source["canonical_decision_ts"],
        "ttl_seconds": None,
        "expected_state_fingerprint": evidence["expected_state_fingerprint"],
        "approval_context": {
            "human_approval_receipt_ref": evidence["human_approval_receipt_ref"],
            "human_approval_receipt_hash": evidence["human_approval_receipt_hash"],
        },
        "policy_lineage": {
            "policy_snapshot_id": evidence["policy_snapshot_id"],
            "policy_version": evidence["policy_version"],
            "policy_semantic_digest": evidence["policy_semantic_digest"],
        },
    }


def _verify_eligibility(value: Any) -> CanonicalGuardedPromotionEligibilityPacket:
    try:
        eligibility = verify_guarded_promotion_eligibility_packet(value)
    except (GuardedPromotionEligibilityError, TypeError, ValueError) as exc:
        raise ExecutionIntentFormationReadinessError(
            "EIFR_ELIGIBILITY_INVALID"
        ) from exc
    if not (
        eligibility.validation_status == "READY_FOR_GUARDED_PROMOTION"
        and eligibility.ready_for_guarded_promotion is True
        and eligibility.fail_closed is False
    ):
        raise ExecutionIntentFormationReadinessError("EIFR_ELIGIBILITY_INVALID")
    _require_source_fields(eligibility)
    return eligibility


def build_execution_intent_formation_readiness_packet(
    eligibility_packet: Any,
    checked_at: datetime,
) -> CanonicalExecutionIntentFormationReadinessPacket:
    """Build readiness after verifying all mapped source values.

    Args:
        eligibility_packet: Full guarded-promotion eligibility artifact.
        checked_at: Caller-supplied timezone-aware check time.

    Returns:
        A verified immutable readiness packet, never an execution artifact.
    """
    checked = _aware_iso(checked_at, "EIFR_CHECKED_AT_INVALID")
    eligibility = _verify_eligibility(_json_value(eligibility_packet))
    issued = _aware_iso(eligibility.issued_at, "EIFR_ELIGIBILITY_INVALID")
    if checked < issued:
        raise ExecutionIntentFormationReadinessError(
            "EIFR_CHECKED_BEFORE_ELIGIBILITY_ISSUED"
        )
    source_packet = eligibility.model_dump(mode="json")
    mapping = _mapping(eligibility)
    summary = {
        key: source_packet[key]
        for key in (
            "eligibility_id",
            "eligibility_hash",
            "format_version",
            "validation_mechanism",
            "handoff_validator_version",
            "issued_at",
            "evaluated_at",
        )
    }
    raw = {
        "format_version": FORMAT_VERSION,
        "verification_mechanism": VERIFICATION_MECHANISM,
        "checked_at": checked.isoformat(),
        "source_eligibility": summary,
        "source_eligibility_hash": eligibility.eligibility_hash,
        "source_eligibility_packet": source_packet,
        "source_handoff_hash": eligibility.source_handoff_hash,
        "trusted_validation_context_hash": eligibility.trusted_validation_context_hash,
        "validation_result_hash": eligibility.validation_result_hash,
        "formation_status": "READY_FOR_EXECUTION_INTENT_FORMATION",
        "ready_for_execution_intent_formation": True,
        "fail_closed": False,
        "execution_intent_contract_version": EXECUTION_INTENT_CONTRACT_VERSION,
        "execution_intent_required_fields": EXECUTION_INTENT_REQUIRED_FIELDS,
        "source_to_execution_intent_mapping": mapping,
        "mapping_value_digest": _digest(MAPPING_DOMAIN, mapping),
        "required_field_presence": REQUIRED_FIELD_PRESENCE,
        "source_decision_identity": eligibility.source_decision_identity,
        "candidate_identity": eligibility.candidate_identity,
        "evidence_lineage": eligibility.evidence_lineage,
        "replay_summary": eligibility.replay_summary,
        "scope_limitations": SCOPE_LIMITATIONS,
    }
    digest = _packet_hash(raw)
    raw.update(
        readiness_hash=digest,
        readiness_id=f"eifr:v1:sha256:{digest}",
    )
    return verify_execution_intent_formation_readiness_packet(raw)


def verify_execution_intent_formation_readiness_packet(
    packet: Any,
) -> CanonicalExecutionIntentFormationReadinessPacket:
    """Revalidate and independently recompute every readiness binding."""
    try:
        raw = (
            packet.model_dump(mode="json")
            if isinstance(packet, BaseModel)
            else _json_value(packet)
        )
        candidate = CanonicalExecutionIntentFormationReadinessPacket.model_validate(raw)
    except (ValidationError, ExecutionIntentFormationReadinessError, TypeError) as exc:
        raise ExecutionIntentFormationReadinessError("EIFR_PACKET_INVALID") from exc
    raw = candidate.model_dump(mode="json")
    eligibility = _verify_eligibility(candidate.source_eligibility_packet)
    checked = _aware_iso(candidate.checked_at, "EIFR_CHECKED_AT_INVALID")
    issued = _aware_iso(eligibility.issued_at, "EIFR_ELIGIBILITY_INVALID")
    if checked < issued:
        raise ExecutionIntentFormationReadinessError(
            "EIFR_CHECKED_BEFORE_ELIGIBILITY_ISSUED"
        )
    source_packet = eligibility.model_dump(mode="json")
    summary = {
        key: source_packet[key]
        for key in candidate.source_eligibility
        if key in source_packet
    }
    expected_summary_keys = {
        "eligibility_id",
        "eligibility_hash",
        "format_version",
        "validation_mechanism",
        "handoff_validator_version",
        "issued_at",
        "evaluated_at",
    }
    if set(candidate.source_eligibility) != expected_summary_keys or (
        candidate.source_eligibility != summary
    ):
        raise ExecutionIntentFormationReadinessError("EIFR_ELIGIBILITY_INVALID")
    bindings = (
        (candidate.source_eligibility_hash, eligibility.eligibility_hash),
        (candidate.source_handoff_hash, eligibility.source_handoff_hash),
        (
            candidate.trusted_validation_context_hash,
            eligibility.trusted_validation_context_hash,
        ),
        (candidate.validation_result_hash, eligibility.validation_result_hash),
    )
    if any(actual != expected for actual, expected in bindings):
        raise ExecutionIntentFormationReadinessError("EIFR_ELIGIBILITY_INVALID")
    expected_mapping = _mapping(eligibility)
    if candidate.source_to_execution_intent_mapping != expected_mapping:
        raise ExecutionIntentFormationReadinessError("EIFR_MAPPING_MISMATCH")
    if candidate.mapping_value_digest != _digest(MAPPING_DOMAIN, expected_mapping):
        raise ExecutionIntentFormationReadinessError("EIFR_MAPPING_DIGEST_MISMATCH")
    if (
        candidate.execution_intent_required_fields != EXECUTION_INTENT_REQUIRED_FIELDS
        or candidate.required_field_presence != REQUIRED_FIELD_PRESENCE
        or _digest(REQUIRED_FIELDS_DOMAIN, candidate.required_field_presence)
        != _digest(REQUIRED_FIELDS_DOMAIN, REQUIRED_FIELD_PRESENCE)
    ):
        raise ExecutionIntentFormationReadinessError("EIFR_REQUIRED_FIELD_MISMATCH")
    summaries = (
        (candidate.source_decision_identity, eligibility.source_decision_identity),
        (candidate.candidate_identity, eligibility.candidate_identity),
        (candidate.evidence_lineage, eligibility.evidence_lineage),
        (candidate.replay_summary, eligibility.replay_summary),
    )
    if any(actual != expected for actual, expected in summaries):
        raise ExecutionIntentFormationReadinessError("EIFR_MAPPING_MISMATCH")
    if candidate.scope_limitations != SCOPE_LIMITATIONS:
        raise ExecutionIntentFormationReadinessError("EIFR_SCOPE_LIMITATIONS_MISSING")
    digest = _packet_hash(raw)
    if candidate.readiness_hash != digest:
        raise ExecutionIntentFormationReadinessError("EIFR_PACKET_HASH_MISMATCH")
    if candidate.readiness_id != f"eifr:v1:sha256:{digest}":
        raise ExecutionIntentFormationReadinessError("EIFR_PACKET_ID_MISMATCH")
    return candidate
