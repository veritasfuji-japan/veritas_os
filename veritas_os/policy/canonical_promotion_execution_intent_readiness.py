"""Promotion-native readiness for one exact verified ``ExecutionIntent``.

This boundary preserves the promoted intent without translating historical
formation-readiness semantics.  It proves only pre-Bind source readiness and
does not establish approval, authority, authorization, or an external effect.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from veritas_os.policy.bind_artifacts import ExecutionIntent, hash_execution_intent
from veritas_os.policy.canonical_verified_decision_promotion import (
    CanonicalVerifiedDecisionPromotionError,
    CanonicalVerifiedDecisionPromotionPacket,
    verify_canonical_verified_decision_promotion_packet,
)

FORMAT_VERSION = "canonical-promotion-execution-intent-readiness/v1"
VERIFICATION_MECHANISM = (
    "verify_canonical_verified_decision_promotion_for_pre_bind/v1"
)
MAPPING_DOMAIN = "veritas.promotion-execution-intent-readiness.mapping/v1"
REQUIRED_FIELDS_DOMAIN = (
    "veritas.promotion-execution-intent-readiness.required-fields/v1"
)
PACKET_DOMAIN = "veritas.promotion-execution-intent-readiness.packet/v1"
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
SEMANTIC_FIELDS = EXECUTION_INTENT_REQUIRED_FIELDS[1:]
REQUIRED_FIELD_PRESENCE = {
    field: "verified_exact_value" for field in EXECUTION_INTENT_REQUIRED_FIELDS
}
SCOPE_LIMITATIONS = (
    "NOT_EXECUTION_AUTHORITY",
    "NOT_BIND_AUTHORIZATION",
    "NOT_BIND_RECEIPT",
    "NOT_HUMAN_APPROVAL_PROOF",
    "NOT_AUTHORITY_EVIDENCE_PROOF",
    "NOT_ADAPTER_SELECTION",
    "NOT_EXTERNAL_EFFECT",
    "NOT_TRUSTLOG_WRITE",
)


class CanonicalPromotionExecutionIntentReadinessError(ValueError):
    """Fail-closed promotion-native readiness error."""


class CanonicalPromotionExecutionIntentReadinessPacket(BaseModel):
    """Immutable readiness binding to an independently verified promotion."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format_version: Literal[
        "canonical-promotion-execution-intent-readiness/v1"
    ]
    readiness_id: str = Field(pattern=r"^peir:v1:sha256:[0-9a-f]{64}$")
    readiness_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    verification_mechanism: Literal[
        "verify_canonical_verified_decision_promotion_for_pre_bind/v1"
    ]
    checked_at: str
    source_promotion_id: str
    source_promotion_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_promotion_packet: dict[str, Any]
    execution_intent: dict[str, Any]
    execution_intent_id: str
    execution_intent_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_intent_required_fields: tuple[str, ...]
    required_field_presence: dict[str, str]
    required_field_presence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_to_execution_intent_mapping: dict[str, Any]
    mapping_value_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_decision_identity: dict[str, Any]
    candidate_identity: dict[str, Any]
    selected_action_lineage: dict[str, Any]
    policy_snapshot_lineage: dict[str, Any]
    readiness_status: Literal["READY_FOR_PROMOTION_NATIVE_PRE_BIND"]
    scope_limitations: tuple[str, ...]


def _canonical_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise CanonicalPromotionExecutionIntentReadinessError(
                "PEIR_NON_CANONICAL_VALUE"
            )
        return value
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise CanonicalPromotionExecutionIntentReadinessError(
                "PEIR_NON_CANONICAL_VALUE"
            )
        return {key: _canonical_value(item) for key, item in value.items()}
    raise CanonicalPromotionExecutionIntentReadinessError(
        "PEIR_NON_CANONICAL_VALUE"
    )


def _digest(domain: str, value: Any) -> str:
    payload = json.dumps(
        {"domain": domain, "value": _canonical_value(value)},
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _aware_iso(value: Any) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise CanonicalPromotionExecutionIntentReadinessError(
            "PEIR_CHECKED_AT_INVALID"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CanonicalPromotionExecutionIntentReadinessError(
            "PEIR_CHECKED_AT_INVALID"
        )
    return parsed


def _verify_promotion(value: Any) -> CanonicalVerifiedDecisionPromotionPacket:
    try:
        return verify_canonical_verified_decision_promotion_packet(value)
    except (CanonicalVerifiedDecisionPromotionError, TypeError, ValueError) as exc:
        raise CanonicalPromotionExecutionIntentReadinessError(
            "PEIR_PROMOTION_INVALID"
        ) from exc


def _mapping(promotion: CanonicalVerifiedDecisionPromotionPacket) -> dict[str, Any]:
    intent = promotion.exact_execution_intent
    if set(intent) != set(EXECUTION_INTENT_REQUIRED_FIELDS):
        raise CanonicalPromotionExecutionIntentReadinessError(
            "PEIR_EXECUTION_INTENT_FIELDS_INVALID"
        )
    return {field: intent[field] for field in SEMANTIC_FIELDS}


def _packet_hash(raw: dict[str, Any]) -> str:
    value = {
        key: item
        for key, item in raw.items()
        if key not in {"readiness_id", "readiness_hash"}
    }
    return _digest(PACKET_DOMAIN, value)


def _source_lineage(
    promotion: CanonicalVerifiedDecisionPromotionPacket,
) -> dict[str, dict[str, Any]]:
    return {
        "source_decision_identity": promotion.source_decision_identity,
        "candidate_identity": {
            "candidate_id": promotion.candidate_id,
            "candidate_hash": promotion.candidate_hash,
        },
        "selected_action_lineage": {
            "selected_action_evidence": promotion.selected_action_evidence,
            "selected_action_evidence_hash": (
                promotion.selected_action_evidence_hash
            ),
        },
        "policy_snapshot_lineage": {
            "policy_snapshot_evidence": promotion.policy_snapshot_evidence,
            "policy_snapshot_evidence_hash": (
                promotion.policy_snapshot_evidence_hash
            ),
        },
    }


def build_canonical_promotion_execution_intent_readiness_packet(
    promotion_packet: CanonicalVerifiedDecisionPromotionPacket | Mapping[str, Any],
    *,
    checked_at: datetime,
) -> CanonicalPromotionExecutionIntentReadinessPacket:
    """Build readiness solely from one independently verified promotion packet."""
    checked = _aware_iso(checked_at)
    promotion = _verify_promotion(_canonical_value(promotion_packet))
    if checked < _aware_iso(promotion.promoted_at):
        raise CanonicalPromotionExecutionIntentReadinessError(
            "PEIR_CHECKED_BEFORE_PROMOTION"
        )
    mapping = _mapping(promotion)
    presence = dict(REQUIRED_FIELD_PRESENCE)
    raw = {
        "format_version": FORMAT_VERSION,
        "readiness_id": "peir:v1:sha256:" + "0" * 64,
        "readiness_hash": "0" * 64,
        "verification_mechanism": VERIFICATION_MECHANISM,
        "checked_at": checked.isoformat(),
        "source_promotion_id": promotion.promotion_id,
        "source_promotion_hash": promotion.promotion_hash,
        "source_promotion_packet": promotion.model_dump(mode="json"),
        "execution_intent": promotion.exact_execution_intent,
        "execution_intent_id": promotion.execution_intent_id,
        "execution_intent_hash": promotion.execution_intent_hash,
        "execution_intent_required_fields": EXECUTION_INTENT_REQUIRED_FIELDS,
        "required_field_presence": presence,
        "required_field_presence_digest": _digest(
            REQUIRED_FIELDS_DOMAIN, presence
        ),
        "source_to_execution_intent_mapping": mapping,
        "mapping_value_digest": _digest(MAPPING_DOMAIN, mapping),
        **_source_lineage(promotion),
        "readiness_status": "READY_FOR_PROMOTION_NATIVE_PRE_BIND",
        "scope_limitations": SCOPE_LIMITATIONS,
    }
    digest = _packet_hash(raw)
    raw.update(
        readiness_hash=digest,
        readiness_id=f"peir:v1:sha256:{digest}",
    )
    return verify_canonical_promotion_execution_intent_readiness_packet(raw)


def verify_canonical_promotion_execution_intent_readiness_packet(
    packet: CanonicalPromotionExecutionIntentReadinessPacket | Mapping[str, Any],
) -> CanonicalPromotionExecutionIntentReadinessPacket:
    """Strictly reconstruct every promotion, intent, lineage, and hash binding."""
    try:
        raw_input = _canonical_value(packet)
        parsed = CanonicalPromotionExecutionIntentReadinessPacket.model_validate(
            raw_input
        )
        raw = parsed.model_dump(mode="json")
        checked = _aware_iso(parsed.checked_at)
        promotion = _verify_promotion(parsed.source_promotion_packet)
        if checked < _aware_iso(promotion.promoted_at):
            raise CanonicalPromotionExecutionIntentReadinessError(
                "PEIR_CHECKED_BEFORE_PROMOTION"
            )
        intent = ExecutionIntent(**promotion.exact_execution_intent)
        mapping = _mapping(promotion)
        lineage = _source_lineage(promotion)
        if (
            parsed.source_promotion_id != promotion.promotion_id
            or parsed.source_promotion_hash != promotion.promotion_hash
            or parsed.execution_intent != promotion.exact_execution_intent
            or parsed.execution_intent_id != intent.execution_intent_id
            or parsed.execution_intent_id != promotion.execution_intent_id
            or parsed.execution_intent_hash != hash_execution_intent(intent)
            or parsed.execution_intent_hash != promotion.execution_intent_hash
            or parsed.source_to_execution_intent_mapping != mapping
            or parsed.mapping_value_digest != _digest(MAPPING_DOMAIN, mapping)
            or any(getattr(parsed, key) != value for key, value in lineage.items())
        ):
            raise CanonicalPromotionExecutionIntentReadinessError(
                "PEIR_BINDING_MISMATCH"
            )
        if (
            parsed.execution_intent_required_fields
            != EXECUTION_INTENT_REQUIRED_FIELDS
            or parsed.required_field_presence != REQUIRED_FIELD_PRESENCE
            or parsed.required_field_presence_digest
            != _digest(REQUIRED_FIELDS_DOMAIN, REQUIRED_FIELD_PRESENCE)
        ):
            raise CanonicalPromotionExecutionIntentReadinessError(
                "PEIR_REQUIRED_FIELDS_MISMATCH"
            )
        if parsed.scope_limitations != SCOPE_LIMITATIONS:
            raise CanonicalPromotionExecutionIntentReadinessError(
                "PEIR_SCOPE_LIMITATIONS_MISMATCH"
            )
        digest = _packet_hash(raw)
        if parsed.readiness_hash != digest:
            raise CanonicalPromotionExecutionIntentReadinessError(
                "PEIR_PACKET_HASH_MISMATCH"
            )
        if parsed.readiness_id != f"peir:v1:sha256:{digest}":
            raise CanonicalPromotionExecutionIntentReadinessError(
                "PEIR_PACKET_ID_MISMATCH"
            )
        return parsed
    except CanonicalPromotionExecutionIntentReadinessError:
        raise
    except (TypeError, ValueError, ValidationError) as exc:
        raise CanonicalPromotionExecutionIntentReadinessError(
            "PEIR_PACKET_INVALID"
        ) from exc
