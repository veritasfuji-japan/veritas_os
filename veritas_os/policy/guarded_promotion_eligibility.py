"""Content-addressed, pre-execution guarded-promotion eligibility packets.

This module is deliberately local and side-effect free.  A verified packet is
only evidence that the handoff validator returned READY for the captured input;
it is neither execution authority nor permission to invoke Bind.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from veritas_os.policy.canonical_decision_handoff import (
    AuthorityEvidenceRequirementBindingAssertion,
    CandidateHashBindingAssertion,
    CanonicalDecisionHandoffStatus,
    CanonicalDecisionHandoffValidationContext,
    TrustedValueAssertion,
    validate_canonical_decision_handoff,
)

FORMAT_VERSION = "canonical-guarded-promotion-eligibility-packet/v1"
VALIDATION_MECHANISM = "validate_canonical_decision_handoff/v1"
SOURCE_HANDOFF_DOMAIN = "veritas.guarded-promotion-eligibility.source-handoff/v1"
TRUSTED_CONTEXT_DOMAIN = "veritas.guarded-promotion-eligibility.trusted-context/v1"
VALIDATION_RESULT_DOMAIN = "veritas.guarded-promotion-eligibility.validation-result/v1"
PACKET_DOMAIN = "veritas.guarded-promotion-eligibility.packet/v1"
SCOPE_LIMITATIONS = (
    "NOT_EXECUTION_AUTHORITY",
    "NOT_EXECUTION_INTENT",
    "NOT_BIND_AUTHORIZATION",
    "NOT_BIND_RECEIPT",
    "NOT_EXTERNAL_EFFECT",
    "NOT_AUTHORITY_EVIDENCE",
    "NOT_HUMAN_APPROVAL",
    "NOT_TRUSTLOG_SUBSTITUTE",
)


class GuardedPromotionEligibilityError(ValueError):
    """Stable, fail-closed packet construction or verification refusal."""


class CanonicalGuardedPromotionEligibilityPacket(BaseModel):
    """Strict immutable snapshot of one READY handoff validation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format_version: Literal[
        "canonical-guarded-promotion-eligibility-packet/v1"
    ]
    eligibility_id: str = Field(pattern=r"^gpe:v1:sha256:[0-9a-f]{64}$")
    eligibility_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    validation_mechanism: Literal["validate_canonical_decision_handoff/v1"]
    handoff_validator_version: str
    issued_at: str
    evaluated_at: str
    validation_status: Literal["READY_FOR_GUARDED_PROMOTION"]
    ready_for_guarded_promotion: Literal[True]
    fail_closed: Literal[False]
    source_handoff: dict[str, Any]
    source_handoff_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    trusted_validation_context: dict[str, Any]
    trusted_validation_context_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    validation_result: dict[str, Any]
    validation_result_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    verified_provenance_paths: tuple[str, ...]
    source_decision_identity: dict[str, Any]
    candidate_identity: dict[str, Any]
    evidence_lineage: dict[str, Any]
    replay_summary: dict[str, Any]
    scope_limitations: tuple[str, ...]


def _json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    elif hasattr(value, "__dataclass_fields__"):
        value = asdict(value)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise GuardedPromotionEligibilityError("GPE_JSON_VALUE_INVALID")
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise GuardedPromotionEligibilityError("GPE_TIMESTAMP_INVALID")
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise GuardedPromotionEligibilityError("GPE_JSON_VALUE_INVALID")
        return {key: _json_value(item) for key, item in value.items()}
    raise GuardedPromotionEligibilityError("GPE_JSON_VALUE_INVALID")


def _digest(domain: str, value: Any) -> str:
    raw = json.dumps(
        {"domain": domain, "value": _json_value(value)},
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def _aware_iso(value: datetime, code: str) -> str:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise GuardedPromotionEligibilityError(code)
    return value.isoformat()


def _context_from_json(
    raw: dict[str, Any],
) -> CanonicalDecisionHandoffValidationContext:
    try:
        assertions = tuple(
            TrustedValueAssertion(
                **{
                    **item,
                    "verified_at": datetime.fromisoformat(item["verified_at"]),
                    "claims": tuple(item.get("claims", ())),
                },
            )
            for item in raw["value_assertions"]
        )
        candidate = raw.get("candidate_hash_binding")
        authority = raw.get("authority_requirement_binding")
        if candidate:
            candidate = CandidateHashBindingAssertion(
                **{
                    **candidate,
                    "verified_at": datetime.fromisoformat(
                        candidate["verified_at"]
                    ),
                }
            )
        if authority:
            authority = AuthorityEvidenceRequirementBindingAssertion(
                **{
                    **authority,
                    "verified_at": datetime.fromisoformat(
                        authority["verified_at"]
                    ),
                }
            )
        context = CanonicalDecisionHandoffValidationContext(
            assertions, candidate, authority
        )
        _json_value(context)
        return context
    except (KeyError, TypeError, ValueError) as exc:
        raise GuardedPromotionEligibilityError(
            "GPE_CONTEXT_RECONSTRUCTION_FAILED"
        ) from exc


def _identities(handoff: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    source = handoff["source_decision"]
    candidate = handoff["candidate"]
    action = candidate["canonical_action"]
    trust = handoff["trustlog_lineage"]
    replay = handoff["replay_lineage"]
    authority = handoff["authority_evidence"]
    approval = handoff["human_approval_evidence"]
    policy = handoff["policy_lineage"]
    state = handoff["expected_state"]
    source_identity = {key: source[key] for key in (
        "request_id", "canonical_decision_id", "canonical_decision_hash",
        "canonical_decision_ts")}
    candidate_identity = {
        "candidate_id": candidate["candidate_id"],
        "candidate_hash": handoff["candidate_hash"],
        "actor_identity": candidate["actor_identity"],
        "target_system": candidate["target_system"],
        "target_resource": candidate["target_resource"],
        "action_contract_id": action["contract_id"],
        "action_contract_version": action["version"],
    }
    evidence = {
        "trustlog_artifact_ref": trust["artifact_ref"],
        "trustlog_chain_hash": trust["chain_hash"],
        "replay_artifact_ref": replay["artifact_ref"],
        "replay_artifact_hash": replay["artifact_hash"],
        "authority_evidence_ref": authority["evidence_ref"],
        "authority_evidence_hash": authority["evidence_hash"],
        "human_approval_receipt_ref": approval["receipt_ref"],
        "human_approval_receipt_hash": approval["receipt_hash"],
        "policy_snapshot_id": policy["snapshot_id"],
        "policy_version": policy["version"],
        "policy_semantic_digest": policy["semantic_digest"],
        "expected_state_fingerprint": state["fingerprint"],
        "expected_state_source_ref": state["source_ref"],
    }
    replay_summary = {key: replay.get(key) for key in (
        "original_decision_id", "replay_decision_id", "original_request_id",
        "replay_request_id", "semantic_profile", "semantic_match",
        "fields_changed", "severity", "divergence_level")}
    return source_identity, candidate_identity, evidence, replay_summary


def _packet_hash(raw: dict[str, Any]) -> str:
    return _digest(PACKET_DOMAIN, {
        key: value for key, value in raw.items()
        if key not in {"eligibility_id", "eligibility_hash"}
    })


def build_guarded_promotion_eligibility_packet(
    handoff: Any,
    trusted_context: CanonicalDecisionHandoffValidationContext,
    evaluated_at: datetime,
    issued_at: datetime,
) -> CanonicalGuardedPromotionEligibilityPacket:
    """Build a packet only after independently rerunning the handoff validator."""
    evaluated = _aware_iso(evaluated_at, "GPE_EVALUATED_AT_INVALID")
    issued = _aware_iso(issued_at, "GPE_ISSUED_AT_INVALID")
    source = _json_value(handoff)
    context = _json_value(trusted_context)
    result = validate_canonical_decision_handoff(source, trusted_context, evaluated_at)
    if not (
        result.status is CanonicalDecisionHandoffStatus.READY_FOR_GUARDED_PROMOTION
        and result.ready_for_guarded_promotion
        and not result.fail_closed
        and result.reason_codes == ()
    ):
        raise GuardedPromotionEligibilityError("GPE_HANDOFF_NOT_READY")
    result_json = _json_value(result.to_dict())
    source_id, candidate_id, evidence, replay = _identities(source)
    raw = {
        "format_version": FORMAT_VERSION,
        "validation_mechanism": VALIDATION_MECHANISM,
        "handoff_validator_version": result.validation_version,
        "issued_at": issued, "evaluated_at": evaluated,
        "validation_status": result.status.value,
        "ready_for_guarded_promotion": True, "fail_closed": False,
        "source_handoff": source,
        "source_handoff_hash": _digest(SOURCE_HANDOFF_DOMAIN, source),
        "trusted_validation_context": context,
        "trusted_validation_context_hash": _digest(TRUSTED_CONTEXT_DOMAIN, context),
        "validation_result": result_json,
        "validation_result_hash": _digest(VALIDATION_RESULT_DOMAIN, result_json),
        "verified_provenance_paths": result.verified_provenance_paths,
        "source_decision_identity": source_id, "candidate_identity": candidate_id,
        "evidence_lineage": evidence, "replay_summary": replay,
        "scope_limitations": SCOPE_LIMITATIONS,
    }
    digest = _packet_hash(raw)
    raw.update(eligibility_hash=digest, eligibility_id=f"gpe:v1:sha256:{digest}")
    return verify_guarded_promotion_eligibility_packet(raw)


def verify_guarded_promotion_eligibility_packet(
    packet: Any,
) -> CanonicalGuardedPromotionEligibilityPacket:
    """Dump, revalidate, and independently recompute every packet binding."""
    try:
        raw = (
            packet.model_dump(mode="json")
            if isinstance(packet, BaseModel)
            else _json_value(packet)
        )
        candidate = CanonicalGuardedPromotionEligibilityPacket.model_validate(raw)
    except (ValidationError, GuardedPromotionEligibilityError, TypeError) as exc:
        raise GuardedPromotionEligibilityError("GPE_PACKET_INVALID") from exc
    raw = candidate.model_dump(mode="json")
    checks = (
        (
            candidate.source_handoff_hash,
            _digest(SOURCE_HANDOFF_DOMAIN, candidate.source_handoff),
            "GPE_SOURCE_HANDOFF_HASH_MISMATCH",
        ),
        (
            candidate.trusted_validation_context_hash,
            _digest(
                TRUSTED_CONTEXT_DOMAIN,
                candidate.trusted_validation_context,
            ),
            "GPE_TRUSTED_CONTEXT_HASH_MISMATCH",
        ),
        (
            candidate.validation_result_hash,
            _digest(VALIDATION_RESULT_DOMAIN, candidate.validation_result),
            "GPE_VALIDATION_RESULT_MISMATCH",
        ),
    )
    for actual, expected, code in checks:
        if actual != expected:
            raise GuardedPromotionEligibilityError(code)
    context = _context_from_json(candidate.trusted_validation_context)
    try:
        evaluated = datetime.fromisoformat(candidate.evaluated_at)
        issued = datetime.fromisoformat(candidate.issued_at)
        _aware_iso(evaluated, "GPE_EVALUATED_AT_INVALID")
        _aware_iso(issued, "GPE_ISSUED_AT_INVALID")
    except ValueError as exc:
        raise GuardedPromotionEligibilityError("GPE_TIMESTAMP_INVALID") from exc
    result = validate_canonical_decision_handoff(
        candidate.source_handoff, context, evaluated
    )
    if result.status is not CanonicalDecisionHandoffStatus.READY_FOR_GUARDED_PROMOTION:
        raise GuardedPromotionEligibilityError("GPE_HANDOFF_NOT_READY")
    if _json_value(result.to_dict()) != candidate.validation_result:
        raise GuardedPromotionEligibilityError("GPE_VALIDATION_RESULT_MISMATCH")
    identities = _identities(candidate.source_handoff)
    if identities != (candidate.source_decision_identity, candidate.candidate_identity,
                      candidate.evidence_lineage, candidate.replay_summary):
        raise GuardedPromotionEligibilityError("GPE_PACKET_SUMMARY_MISMATCH")
    replay = candidate.replay_summary
    if replay.get("original_request_id") is not None and (
        replay["original_request_id"] == replay.get("replay_request_id")
        or replay.get("original_decision_id") == replay.get("replay_decision_id")
    ):
        raise GuardedPromotionEligibilityError("GPE_REPLAY_IDENTITY_COLLAPSED")
    if candidate.scope_limitations != SCOPE_LIMITATIONS:
        raise GuardedPromotionEligibilityError("GPE_SCOPE_LIMITATIONS_MISSING")
    digest = _packet_hash(raw)
    if candidate.eligibility_hash != digest:
        raise GuardedPromotionEligibilityError("GPE_PACKET_HASH_MISMATCH")
    if candidate.eligibility_id != f"gpe:v1:sha256:{digest}":
        raise GuardedPromotionEligibilityError("GPE_PACKET_ID_MISMATCH")
    return candidate
