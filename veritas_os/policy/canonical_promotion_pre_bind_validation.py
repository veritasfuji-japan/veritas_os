"""Local pre-Bind validation for the exact promotion-native intent.

This boundary consumes only verified promotion-native readiness.  It performs
deterministic validation without approval, authority, adapter, Bind, storage,
network, or TrustLog effects.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from veritas_os.policy.bind_artifacts import (
    ExecutionIntent,
    canonical_execution_intent_json,
    hash_execution_intent,
)
from veritas_os.policy.canonical_promotion_execution_intent_readiness import (
    EXECUTION_INTENT_REQUIRED_FIELDS,
    CanonicalPromotionExecutionIntentReadinessError,
    CanonicalPromotionExecutionIntentReadinessPacket,
    verify_canonical_promotion_execution_intent_readiness_packet,
)

FORMAT_VERSION = "canonical-promotion-pre-bind-validation/v1"
VALIDATION_MECHANISM = "validate_promotion_execution_intent_before_bind/v1"
LOCAL_CHECKS_DOMAIN = "veritas.promotion-pre-bind-validation.local-checks/v1"
PACKET_DOMAIN = "veritas.promotion-pre-bind-validation.packet/v1"
PRE_BIND_STATUS = "READY_FOR_PROMOTION_NATIVE_BIND_PREFLIGHT"
LOCAL_VALIDATION_CHECKS = {
    "promotion_readiness_verified": True,
    "execution_intent_object_verified": True,
    "execution_intent_id_verified": True,
    "execution_intent_hash_verified": True,
    "semantic_mapping_verified": True,
    "required_fields_verified": True,
    "evidence_refs_verified": True,
    "decision_timestamp_verified": True,
    "approval_context_preserved": True,
    "policy_lineage_preserved": True,
    "checked_after_readiness": True,
    "no_bind_invocation": True,
    "no_external_effect": True,
    "no_human_approval_proof": True,
    "no_authority_evidence_proof": True,
}
SCOPE_LIMITATIONS = (
    "NOT_EXECUTION_AUTHORITY",
    "NOT_BIND_AUTHORIZATION",
    "NOT_BIND_RECEIPT",
    "NOT_BIND_INVOCATION",
    "NOT_HUMAN_APPROVAL_PROOF",
    "NOT_AUTHORITY_EVIDENCE_PROOF",
    "NOT_ADAPTER_SELECTION",
    "NOT_EXTERNAL_EFFECT",
    "NOT_OPERATION_COMMIT",
    "NOT_TRUSTLOG_WRITE",
)


class CanonicalPromotionPreBindValidationError(ValueError):
    """Stable fail-closed promotion-native validation refusal."""


class CanonicalPromotionPreBindValidationPacket(BaseModel):
    """Immutable proof of local checks over one exact promoted intent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format_version: Literal["canonical-promotion-pre-bind-validation/v1"]
    pre_bind_validation_id: str = Field(pattern=r"^ppbv:v1:sha256:[0-9a-f]{64}$")
    pre_bind_validation_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    validation_mechanism: Literal["validate_promotion_execution_intent_before_bind/v1"]
    checked_at: str
    source_readiness_id: str
    source_readiness_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_readiness_packet: dict[str, Any]
    source_promotion_id: str
    source_promotion_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_decision_identity: dict[str, Any]
    candidate_identity: dict[str, Any]
    selected_action_lineage: dict[str, Any]
    policy_snapshot_lineage: dict[str, Any]
    execution_intent: dict[str, Any]
    execution_intent_id: str = Field(pattern=r"^ei:v1:sha256:[0-9a-f]{64}$")
    execution_intent_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    approval_context: dict[str, Any]
    policy_lineage: dict[str, Any]
    local_validation_checks: dict[str, bool]
    local_validation_checks_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    pre_bind_status: Literal["READY_FOR_PROMOTION_NATIVE_BIND_PREFLIGHT"]
    scope_limitations: tuple[str, ...]


def _json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise CanonicalPromotionPreBindValidationError("PPBV_PACKET_INVALID")
        return value
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, Mapping) and all(isinstance(key, str) for key in value):
        return {key: _json_value(item) for key, item in value.items()}
    raise CanonicalPromotionPreBindValidationError("PPBV_PACKET_INVALID")


def _aware_iso(value: Any, code: str) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise CanonicalPromotionPreBindValidationError(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CanonicalPromotionPreBindValidationError(code)
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
            if key not in {"pre_bind_validation_id", "pre_bind_validation_hash"}
        },
    )


def _verified_readiness(value: Any) -> CanonicalPromotionExecutionIntentReadinessPacket:
    try:
        return verify_canonical_promotion_execution_intent_readiness_packet(value)
    except (
        CanonicalPromotionExecutionIntentReadinessError,
        TypeError,
        ValueError,
    ) as exc:
        raise CanonicalPromotionPreBindValidationError(
            "PPBV_READINESS_INVALID"
        ) from exc


def _reconstruct_intent(raw: dict[str, Any]) -> ExecutionIntent:
    if set(raw) != set(EXECUTION_INTENT_REQUIRED_FIELDS):
        raise CanonicalPromotionPreBindValidationError("PPBV_INTENT_FIELDS_INVALID")
    required_strings = {
        "execution_intent_id",
        "decision_id",
        "request_id",
        "policy_snapshot_id",
        "actor_identity",
        "target_system",
        "target_resource",
        "intended_action",
        "decision_hash",
    }
    if any(
        not isinstance(raw[field], str) or not raw[field].strip()
        for field in required_strings
    ):
        raise CanonicalPromotionPreBindValidationError("PPBV_REQUIRED_FIELD_INVALID")
    refs = raw["evidence_refs"]
    if (
        not isinstance(refs, list)
        or not refs
        or any(not isinstance(ref, str) or not ref.strip() for ref in refs)
    ):
        raise CanonicalPromotionPreBindValidationError("PPBV_EVIDENCE_REFS_INVALID")
    _aware_iso(raw["decision_ts"], "PPBV_DECISION_TS_INVALID")
    ttl = raw["ttl_seconds"]
    if ttl is not None and (
        isinstance(ttl, bool) or not isinstance(ttl, int) or ttl < 0
    ):
        raise CanonicalPromotionPreBindValidationError("PPBV_TTL_INVALID")
    fingerprint = raw["expected_state_fingerprint"]
    if fingerprint is not None and (
        not isinstance(fingerprint, str) or not fingerprint.strip()
    ):
        raise CanonicalPromotionPreBindValidationError(
            "PPBV_EXPECTED_STATE_FINGERPRINT_INVALID"
        )
    approval = raw["approval_context"]
    if not isinstance(approval, dict) or set(approval) != {
        "required_human_approval",
        "policy_context_refs",
    }:
        raise CanonicalPromotionPreBindValidationError("PPBV_APPROVAL_CONTEXT_INVALID")
    if not isinstance(approval["required_human_approval"], bool):
        raise CanonicalPromotionPreBindValidationError("PPBV_APPROVAL_CONTEXT_INVALID")
    refs = approval["policy_context_refs"]
    if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
        raise CanonicalPromotionPreBindValidationError("PPBV_APPROVAL_CONTEXT_INVALID")
    lineage = raw["policy_lineage"]
    if not isinstance(lineage, dict) or set(lineage) != {
        "version",
        "semantic_digest",
        "signer_id",
        "verified_at",
    }:
        raise CanonicalPromotionPreBindValidationError("PPBV_POLICY_LINEAGE_INVALID")
    if any(
        not isinstance(lineage[key], str) or not lineage[key].strip() for key in lineage
    ):
        raise CanonicalPromotionPreBindValidationError("PPBV_POLICY_LINEAGE_INVALID")
    _aware_iso(lineage["verified_at"], "PPBV_POLICY_LINEAGE_INVALID")
    intent = ExecutionIntent(**raw)
    if intent.to_dict() != raw:
        raise CanonicalPromotionPreBindValidationError("PPBV_INTENT_FIELDS_INVALID")
    canonical_execution_intent_json(intent)
    return intent


def _lineage(
    readiness: CanonicalPromotionExecutionIntentReadinessPacket,
) -> dict[str, Any]:
    return {
        "source_promotion_id": readiness.source_promotion_id,
        "source_promotion_hash": readiness.source_promotion_hash,
        "source_decision_identity": readiness.source_decision_identity,
        "candidate_identity": readiness.candidate_identity,
        "selected_action_lineage": readiness.selected_action_lineage,
        "policy_snapshot_lineage": readiness.policy_snapshot_lineage,
    }


def build_canonical_promotion_pre_bind_validation_packet(
    readiness_packet: CanonicalPromotionExecutionIntentReadinessPacket
    | Mapping[str, Any],
    *,
    checked_at: datetime,
) -> CanonicalPromotionPreBindValidationPacket:
    """Build local validation from exactly one verified readiness source."""
    checked = _aware_iso(checked_at, "PPBV_CHECKED_AT_INVALID")
    readiness = _verified_readiness(_json_value(readiness_packet))
    if checked < _aware_iso(readiness.checked_at, "PPBV_READINESS_INVALID"):
        raise CanonicalPromotionPreBindValidationError("PPBV_CHECKED_BEFORE_READINESS")
    intent = _reconstruct_intent(readiness.execution_intent)
    if intent.execution_intent_id != readiness.execution_intent_id or (
        hash_execution_intent(intent) != readiness.execution_intent_hash
    ):
        raise CanonicalPromotionPreBindValidationError("PPBV_INTENT_BINDING_MISMATCH")
    raw = {
        "format_version": FORMAT_VERSION,
        "pre_bind_validation_id": "ppbv:v1:sha256:" + "0" * 64,
        "pre_bind_validation_hash": "0" * 64,
        "validation_mechanism": VALIDATION_MECHANISM,
        "checked_at": checked.isoformat(),
        "source_readiness_id": readiness.readiness_id,
        "source_readiness_hash": readiness.readiness_hash,
        "source_readiness_packet": readiness.model_dump(mode="json"),
        **_lineage(readiness),
        "execution_intent": readiness.execution_intent,
        "execution_intent_id": readiness.execution_intent_id,
        "execution_intent_hash": readiness.execution_intent_hash,
        "approval_context": readiness.execution_intent["approval_context"],
        "policy_lineage": readiness.execution_intent["policy_lineage"],
        "local_validation_checks": LOCAL_VALIDATION_CHECKS,
        "local_validation_checks_digest": _digest(
            LOCAL_CHECKS_DOMAIN, LOCAL_VALIDATION_CHECKS
        ),
        "pre_bind_status": PRE_BIND_STATUS,
        "scope_limitations": SCOPE_LIMITATIONS,
    }
    digest = _packet_hash(raw)
    raw.update(
        pre_bind_validation_hash=digest,
        pre_bind_validation_id=f"ppbv:v1:sha256:{digest}",
    )
    return verify_canonical_promotion_pre_bind_validation_packet(raw)


def verify_canonical_promotion_pre_bind_validation_packet(
    packet: CanonicalPromotionPreBindValidationPacket | Mapping[str, Any],
) -> CanonicalPromotionPreBindValidationPacket:
    """Independently re-run readiness, intent, lineage, checks, and hashes."""
    try:
        parsed = CanonicalPromotionPreBindValidationPacket.model_validate(
            _json_value(packet)
        )
        raw = parsed.model_dump(mode="json")
        readiness = _verified_readiness(parsed.source_readiness_packet)
        checked = _aware_iso(parsed.checked_at, "PPBV_CHECKED_AT_INVALID")
        if checked < _aware_iso(readiness.checked_at, "PPBV_READINESS_INVALID"):
            raise CanonicalPromotionPreBindValidationError(
                "PPBV_CHECKED_BEFORE_READINESS"
            )
        intent = _reconstruct_intent(parsed.execution_intent)
        if (
            parsed.source_readiness_id != readiness.readiness_id
            or parsed.source_readiness_hash != readiness.readiness_hash
            or parsed.execution_intent != readiness.execution_intent
            or parsed.execution_intent_id != intent.execution_intent_id
            or parsed.execution_intent_id != readiness.execution_intent_id
            or parsed.execution_intent_hash != hash_execution_intent(intent)
            or parsed.execution_intent_hash != readiness.execution_intent_hash
            or parsed.approval_context != intent.approval_context
            or parsed.approval_context != readiness.execution_intent["approval_context"]
            or parsed.policy_lineage != intent.policy_lineage
            or parsed.policy_lineage != readiness.execution_intent["policy_lineage"]
            or any(
                getattr(parsed, key) != value
                for key, value in _lineage(readiness).items()
            )
        ):
            raise CanonicalPromotionPreBindValidationError("PPBV_BINDING_MISMATCH")
        if parsed.local_validation_checks != LOCAL_VALIDATION_CHECKS or (
            parsed.local_validation_checks_digest
            != _digest(LOCAL_CHECKS_DOMAIN, LOCAL_VALIDATION_CHECKS)
        ):
            raise CanonicalPromotionPreBindValidationError("PPBV_LOCAL_CHECKS_MISMATCH")
        if parsed.scope_limitations != SCOPE_LIMITATIONS:
            raise CanonicalPromotionPreBindValidationError(
                "PPBV_SCOPE_LIMITATIONS_MISMATCH"
            )
        digest = _packet_hash(raw)
        if parsed.pre_bind_validation_hash != digest:
            raise CanonicalPromotionPreBindValidationError("PPBV_PACKET_HASH_MISMATCH")
        if parsed.pre_bind_validation_id != f"ppbv:v1:sha256:{digest}":
            raise CanonicalPromotionPreBindValidationError("PPBV_PACKET_ID_MISMATCH")
        return parsed
    except CanonicalPromotionPreBindValidationError:
        raise
    except (TypeError, ValueError, ValidationError) as exc:
        raise CanonicalPromotionPreBindValidationError("PPBV_PACKET_INVALID") from exc
