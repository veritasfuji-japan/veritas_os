"""Promotion-native deterministic local Bind preflight adjudication.

This boundary preserves the exact intent and lineage proven by promotion-native
pre-Bind validation.  It creates no authorization, approval proof, adapter,
runtime observation, external effect, receipt, or TrustLog entry.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from veritas_os.policy.bind_artifacts import ExecutionIntent, hash_execution_intent
from veritas_os.policy.canonical_promotion_pre_bind_validation import (
    CanonicalPromotionPreBindValidationError,
    CanonicalPromotionPreBindValidationPacket,
    verify_canonical_promotion_pre_bind_validation_packet,
)

FORMAT_VERSION = "canonical-promotion-bind-preflight-adjudication/v1"
ADJUDICATION_MECHANISM = "adjudicate_promotion_bind_preflight_locally/v1"
LOCAL_CHECKS_DOMAIN = "veritas.promotion-bind-preflight.local-checks/v1"
ENTRY_REQUIREMENTS_DOMAIN = "veritas.promotion-bind-preflight.entry-requirements/v1"
PACKET_DOMAIN = "veritas.promotion-bind-preflight.packet/v1"
BIND_PREFLIGHT_STATUS = "READY_FOR_PROMOTION_NATIVE_ADAPTER_SELECTION"

LOCAL_ADJUDICATION_CHECKS = {
    "promotion_pre_bind_verified": True,
    "execution_intent_object_verified": True,
    "execution_intent_id_verified": True,
    "execution_intent_hash_verified": True,
    "readiness_lineage_verified": True,
    "promotion_lineage_verified": True,
    "decision_lineage_verified": True,
    "candidate_lineage_verified": True,
    "selected_action_lineage_verified": True,
    "policy_snapshot_lineage_verified": True,
    "approval_context_preserved": True,
    "policy_lineage_preserved": True,
    "evidence_refs_verified": True,
    "decision_timestamp_verified": True,
    "ttl_locally_well_formed": True,
    "adjudicated_after_pre_bind_validation": True,
    "no_bind_invocation": True,
    "no_adapter_instance": True,
    "no_adapter_invocation": True,
    "no_bind_receipt_created": True,
    "no_trustlog_write": True,
    "no_external_effect": True,
    "no_live_state_check": True,
    "no_runtime_risk_acceptance": True,
    "no_authority_revalidation": True,
    "no_human_approval_proof": True,
}
BIND_ENTRY_REQUIREMENTS = {
    key: True
    for key in (
        "adapter_required",
        "adapter_snapshot_required",
        "adapter_authority_revalidation_required",
        "adapter_constraint_validation_required",
        "runtime_risk_assessment_required",
        "commit_boundary_evaluation_required",
        "postcondition_verification_required",
        "rollback_or_revert_path_required",
        "bind_receipt_required",
        "trustlog_policy_required",
    )
}
SCOPE_LIMITATIONS = (
    "NOT_EXECUTION_AUTHORITY",
    "NOT_BIND_AUTHORIZATION",
    "NOT_BIND_RECEIPT",
    "NOT_BIND_INVOCATION",
    "NOT_ADAPTER_INSTANCE",
    "NOT_ADAPTER_SELECTION",
    "NOT_ADAPTER_INVOCATION",
    "NOT_HUMAN_APPROVAL_PROOF",
    "NOT_AUTHORITY_EVIDENCE_PROOF",
    "NOT_EXTERNAL_EFFECT",
    "NOT_OPERATION_COMMIT",
    "NOT_TRUSTLOG_WRITE",
    "NOT_LIVE_STATE_CHECK",
    "NOT_RUNTIME_RISK_ACCEPTANCE",
    "NOT_AUTHORITY_REVALIDATION",
    "NOT_CONSTRAINT_REVALIDATION",
    "NOT_POSTCONDITION_VERIFICATION",
    "NOT_ROLLBACK_PROOF",
)


class CanonicalPromotionBindPreflightAdjudicationError(ValueError):
    """Stable fail-closed promotion-native adjudication refusal."""


class CanonicalPromotionBindPreflightAdjudicationPacket(BaseModel):
    """Immutable local preflight proof that confers no Bind authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format_version: Literal["canonical-promotion-bind-preflight-adjudication/v1"]
    bind_preflight_adjudication_id: str = Field(
        pattern=r"^pbpa:v1:sha256:[0-9a-f]{64}$"
    )
    bind_preflight_adjudication_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    adjudication_mechanism: Literal["adjudicate_promotion_bind_preflight_locally/v1"]
    adjudicated_at: str
    source_pre_bind_validation_id: str
    source_pre_bind_validation_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_pre_bind_validation_packet: dict[str, Any]
    source_readiness_id: str
    source_readiness_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
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
    local_adjudication_checks: dict[str, bool]
    local_adjudication_checks_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    bind_entry_requirements: dict[str, bool]
    bind_entry_requirements_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    bind_preflight_status: Literal["READY_FOR_PROMOTION_NATIVE_ADAPTER_SELECTION"]
    scope_limitations: tuple[str, ...]


def _json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise CanonicalPromotionBindPreflightAdjudicationError(
                "PBPA_PACKET_INVALID"
            )
        return value
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, Mapping) and all(isinstance(key, str) for key in value):
        return {key: _json_value(item) for key, item in value.items()}
    raise CanonicalPromotionBindPreflightAdjudicationError("PBPA_PACKET_INVALID")


def _aware_iso(value: Any, code: str) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise CanonicalPromotionBindPreflightAdjudicationError(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CanonicalPromotionBindPreflightAdjudicationError(code)
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
            if key
            not in {
                "bind_preflight_adjudication_id",
                "bind_preflight_adjudication_hash",
            }
        },
    )


def _verified_source(value: Any) -> CanonicalPromotionPreBindValidationPacket:
    try:
        return verify_canonical_promotion_pre_bind_validation_packet(value)
    except (
        CanonicalPromotionPreBindValidationError,
        TypeError,
        ValueError,
    ) as exc:
        raise CanonicalPromotionBindPreflightAdjudicationError(
            "PBPA_PRE_BIND_VALIDATION_INVALID"
        ) from exc


def _verified_intent(
    source: CanonicalPromotionPreBindValidationPacket,
) -> ExecutionIntent:
    try:
        intent = ExecutionIntent(**source.execution_intent)
    except (TypeError, ValueError) as exc:
        raise CanonicalPromotionBindPreflightAdjudicationError(
            "PBPA_EXECUTION_INTENT_INVALID"
        ) from exc
    ttl = intent.ttl_seconds
    if intent.to_dict() != source.execution_intent:
        raise CanonicalPromotionBindPreflightAdjudicationError(
            "PBPA_EXECUTION_INTENT_OBJECT_MISMATCH"
        )
    if intent.execution_intent_id != source.execution_intent_id:
        raise CanonicalPromotionBindPreflightAdjudicationError(
            "PBPA_EXECUTION_INTENT_ID_MISMATCH"
        )
    if hash_execution_intent(intent) != source.execution_intent_hash:
        raise CanonicalPromotionBindPreflightAdjudicationError(
            "PBPA_EXECUTION_INTENT_HASH_MISMATCH"
        )
    if not intent.evidence_refs or any(not ref.strip() for ref in intent.evidence_refs):
        raise CanonicalPromotionBindPreflightAdjudicationError(
            "PBPA_EVIDENCE_REFS_INVALID"
        )
    _aware_iso(intent.decision_ts, "PBPA_DECISION_TIMESTAMP_INVALID")
    if ttl is not None and (isinstance(ttl, bool) or ttl < 0):
        raise CanonicalPromotionBindPreflightAdjudicationError("PBPA_TTL_INVALID")
    return intent


def _source_bindings(
    source: CanonicalPromotionPreBindValidationPacket,
) -> dict[str, Any]:
    return {
        "source_readiness_id": source.source_readiness_id,
        "source_readiness_hash": source.source_readiness_hash,
        "source_promotion_id": source.source_promotion_id,
        "source_promotion_hash": source.source_promotion_hash,
        "source_decision_identity": source.source_decision_identity,
        "candidate_identity": source.candidate_identity,
        "selected_action_lineage": source.selected_action_lineage,
        "policy_snapshot_lineage": source.policy_snapshot_lineage,
    }


def build_canonical_promotion_bind_preflight_adjudication_packet(
    pre_bind_validation_packet: CanonicalPromotionPreBindValidationPacket
    | Mapping[str, Any],
    adjudicated_at: datetime,
) -> CanonicalPromotionBindPreflightAdjudicationPacket:
    """Adjudicate exactly one independently verified promotion-native source."""
    adjudicated = _aware_iso(adjudicated_at, "PBPA_ADJUDICATED_AT_INVALID")
    source = _verified_source(_json_value(pre_bind_validation_packet))
    if adjudicated < _aware_iso(source.checked_at, "PBPA_SOURCE_CHECKED_AT_INVALID"):
        raise CanonicalPromotionBindPreflightAdjudicationError(
            "PBPA_ADJUDICATED_BEFORE_PRE_BIND_VALIDATION"
        )
    intent = _verified_intent(source)
    raw = {
        "format_version": FORMAT_VERSION,
        "bind_preflight_adjudication_id": "pbpa:v1:sha256:" + "0" * 64,
        "bind_preflight_adjudication_hash": "0" * 64,
        "adjudication_mechanism": ADJUDICATION_MECHANISM,
        "adjudicated_at": adjudicated.isoformat(),
        "source_pre_bind_validation_id": source.pre_bind_validation_id,
        "source_pre_bind_validation_hash": source.pre_bind_validation_hash,
        "source_pre_bind_validation_packet": source.model_dump(mode="json"),
        **_source_bindings(source),
        "execution_intent": source.execution_intent,
        "execution_intent_id": source.execution_intent_id,
        "execution_intent_hash": source.execution_intent_hash,
        "approval_context": intent.approval_context,
        "policy_lineage": intent.policy_lineage,
        "local_adjudication_checks": LOCAL_ADJUDICATION_CHECKS,
        "local_adjudication_checks_digest": _digest(
            LOCAL_CHECKS_DOMAIN, LOCAL_ADJUDICATION_CHECKS
        ),
        "bind_entry_requirements": BIND_ENTRY_REQUIREMENTS,
        "bind_entry_requirements_digest": _digest(
            ENTRY_REQUIREMENTS_DOMAIN, BIND_ENTRY_REQUIREMENTS
        ),
        "bind_preflight_status": BIND_PREFLIGHT_STATUS,
        "scope_limitations": SCOPE_LIMITATIONS,
    }
    digest = _packet_hash(raw)
    raw["bind_preflight_adjudication_hash"] = digest
    raw["bind_preflight_adjudication_id"] = f"pbpa:v1:sha256:{digest}"
    return verify_canonical_promotion_bind_preflight_adjudication_packet(raw)


def verify_canonical_promotion_bind_preflight_adjudication_packet(
    packet: CanonicalPromotionBindPreflightAdjudicationPacket | Mapping[str, Any],
) -> CanonicalPromotionBindPreflightAdjudicationPacket:
    """Strictly re-run source, intent, lineage, timeline, checks, and hashes."""
    try:
        parsed = CanonicalPromotionBindPreflightAdjudicationPacket.model_validate(
            _json_value(packet)
        )
        raw = parsed.model_dump(mode="json")
        source = _verified_source(parsed.source_pre_bind_validation_packet)
        intent = _verified_intent(source)
        if _aware_iso(parsed.adjudicated_at, "PBPA_ADJUDICATED_AT_INVALID") < (
            _aware_iso(source.checked_at, "PBPA_SOURCE_CHECKED_AT_INVALID")
        ):
            raise CanonicalPromotionBindPreflightAdjudicationError(
                "PBPA_ADJUDICATED_BEFORE_PRE_BIND_VALIDATION"
            )
        if (
            parsed.source_pre_bind_validation_id != source.pre_bind_validation_id
            or parsed.source_pre_bind_validation_hash != source.pre_bind_validation_hash
            or any(
                getattr(parsed, key) != value
                for key, value in _source_bindings(source).items()
            )
            or parsed.execution_intent != source.execution_intent
            or parsed.execution_intent_id != source.execution_intent_id
            or parsed.execution_intent_id != intent.execution_intent_id
            or parsed.execution_intent_hash != source.execution_intent_hash
            or parsed.execution_intent_hash != hash_execution_intent(intent)
            or parsed.approval_context != source.approval_context
            or parsed.approval_context != intent.approval_context
            or parsed.policy_lineage != source.policy_lineage
            or parsed.policy_lineage != intent.policy_lineage
        ):
            raise CanonicalPromotionBindPreflightAdjudicationError(
                "PBPA_SOURCE_BINDING_MISMATCH"
            )
        if parsed.local_adjudication_checks != LOCAL_ADJUDICATION_CHECKS or (
            parsed.local_adjudication_checks_digest
            != _digest(LOCAL_CHECKS_DOMAIN, LOCAL_ADJUDICATION_CHECKS)
        ):
            raise CanonicalPromotionBindPreflightAdjudicationError(
                "PBPA_LOCAL_CHECKS_MISMATCH"
            )
        if parsed.bind_entry_requirements != BIND_ENTRY_REQUIREMENTS or (
            parsed.bind_entry_requirements_digest
            != _digest(ENTRY_REQUIREMENTS_DOMAIN, BIND_ENTRY_REQUIREMENTS)
        ):
            raise CanonicalPromotionBindPreflightAdjudicationError(
                "PBPA_ENTRY_REQUIREMENTS_MISMATCH"
            )
        if parsed.scope_limitations != SCOPE_LIMITATIONS:
            raise CanonicalPromotionBindPreflightAdjudicationError(
                "PBPA_SCOPE_LIMITATIONS_MISMATCH"
            )
        digest = _packet_hash(raw)
        if parsed.bind_preflight_adjudication_hash != digest:
            raise CanonicalPromotionBindPreflightAdjudicationError(
                "PBPA_PACKET_HASH_MISMATCH"
            )
        if parsed.bind_preflight_adjudication_id != f"pbpa:v1:sha256:{digest}":
            raise CanonicalPromotionBindPreflightAdjudicationError(
                "PBPA_PACKET_ID_MISMATCH"
            )
        return parsed
    except CanonicalPromotionBindPreflightAdjudicationError:
        raise
    except (TypeError, ValueError, ValidationError) as exc:
        raise CanonicalPromotionBindPreflightAdjudicationError(
            "PBPA_PACKET_INVALID"
        ) from exc
