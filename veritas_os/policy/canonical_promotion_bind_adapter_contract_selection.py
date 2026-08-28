"""Promotion-native, no-effect Bind adapter contract selection.

This boundary associates one canonical inert adapter descriptor with the exact
ExecutionIntent proven by promotion-native Bind preflight.  It creates neither
an adapter instance nor execution, approval, authority, receipt, or TrustLog
proof.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from veritas_os.policy.bind_adapter_contract_selection import (
    BindAdapterContractDescriptor,
    BindAdapterContractSelectionError,
    verify_bind_adapter_contract_descriptor,
)
from veritas_os.policy.bind_artifacts import ExecutionIntent, hash_execution_intent
from veritas_os.policy.canonical_promotion_bind_preflight_adjudication import (
    CanonicalPromotionBindPreflightAdjudicationError,
    CanonicalPromotionBindPreflightAdjudicationPacket,
    verify_canonical_promotion_bind_preflight_adjudication_packet,
)

FORMAT_VERSION = "canonical-promotion-bind-adapter-contract-selection/v1"
SELECTION_MECHANISM = "select_promotion_bind_adapter_contract_without_invocation/v1"
LOCAL_CHECKS_DOMAIN = "veritas.promotion-bind-adapter-selection.local-checks/v1"
FUTURE_REQUIREMENTS_DOMAIN = (
    "veritas.promotion-bind-adapter-selection.future-requirements/v1"
)
PACKET_DOMAIN = "veritas.promotion-bind-adapter-selection.packet/v1"
SELECTION_STATUS = "PROMOTION_NATIVE_ADAPTER_CONTRACT_SELECTED_FOR_DRY_RUN"

LOCAL_SELECTION_CHECKS = {
    key: True
    for key in (
        "promotion_bind_preflight_verified",
        "execution_intent_object_verified",
        "execution_intent_id_verified",
        "execution_intent_hash_verified",
        "adapter_descriptor_verified",
        "adapter_descriptor_hash_verified",
        "adapter_descriptor_id_verified",
        "adapter_descriptor_scope_matches_intent",
        "readiness_lineage_verified",
        "promotion_lineage_verified",
        "decision_lineage_verified",
        "candidate_lineage_verified",
        "selected_action_lineage_verified",
        "policy_snapshot_lineage_verified",
        "approval_context_preserved",
        "policy_lineage_preserved",
        "selected_after_bind_preflight",
        "no_adapter_instance",
        "no_adapter_invocation",
        "no_bind_invocation",
        "no_bind_receipt_created",
        "no_trustlog_write",
        "no_network",
        "no_filesystem",
        "no_external_effect",
        "no_human_approval_proof",
        "no_authority_evidence_proof",
    )
}
FUTURE_BIND_DRY_RUN_REQUIREMENTS = {
    key: True
    for key in (
        "adapter_instance_required",
        "snapshot_required",
        "state_fingerprint_required",
        "authority_revalidation_required",
        "constraint_validation_required",
        "runtime_risk_assessment_required",
        "commit_boundary_evaluation_required",
        "idempotency_key_required",
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
    "NOT_ADAPTER_INVOCATION",
    "NOT_ADAPTER_DRY_RUN_EXECUTION",
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


class CanonicalPromotionBindAdapterContractSelectionError(ValueError):
    """Stable fail-closed refusal for promotion-native selection."""


class CanonicalPromotionBindAdapterContractSelectionPacket(BaseModel):
    """Immutable promotion-native descriptor association without authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format_version: Literal["canonical-promotion-bind-adapter-contract-selection/v1"]
    adapter_contract_selection_id: str = Field(pattern=r"^pbac:v1:sha256:[0-9a-f]{64}$")
    adapter_contract_selection_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    selection_mechanism: Literal[
        "select_promotion_bind_adapter_contract_without_invocation/v1"
    ]
    selected_at: str
    source_bind_preflight_adjudication_id: str
    source_bind_preflight_adjudication_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_bind_preflight_adjudication_packet: dict[str, Any]
    source_pre_bind_validation_id: str
    source_pre_bind_validation_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
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
    adapter_contract_descriptor: dict[str, Any]
    adapter_contract_id: str
    adapter_contract_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    adapter_contract_version: Literal["bind-adapter-contract/v1"]
    approval_context: dict[str, Any]
    policy_lineage: dict[str, Any]
    local_selection_checks: dict[str, bool]
    local_selection_checks_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    future_bind_dry_run_requirements: dict[str, bool]
    future_bind_dry_run_requirements_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    selection_status: Literal["PROMOTION_NATIVE_ADAPTER_CONTRACT_SELECTED_FOR_DRY_RUN"]
    scope_limitations: tuple[str, ...]


def _json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise CanonicalPromotionBindAdapterContractSelectionError(
                "PBAC_PACKET_INVALID"
            )
        return value
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, Mapping) and all(isinstance(key, str) for key in value):
        return {key: _json_value(item) for key, item in value.items()}
    raise CanonicalPromotionBindAdapterContractSelectionError("PBAC_PACKET_INVALID")


def _aware_iso(value: Any, code: str) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise CanonicalPromotionBindAdapterContractSelectionError(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CanonicalPromotionBindAdapterContractSelectionError(code)
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
                "adapter_contract_selection_id",
                "adapter_contract_selection_hash",
            }
        },
    )


def _verified_source(value: Any) -> CanonicalPromotionBindPreflightAdjudicationPacket:
    try:
        return verify_canonical_promotion_bind_preflight_adjudication_packet(value)
    except (
        CanonicalPromotionBindPreflightAdjudicationError,
        TypeError,
        ValueError,
    ) as exc:
        raise CanonicalPromotionBindAdapterContractSelectionError(
            "PBAC_BIND_PREFLIGHT_INVALID"
        ) from exc


def _verified_intent(
    source: CanonicalPromotionBindPreflightAdjudicationPacket,
) -> ExecutionIntent:
    try:
        intent = ExecutionIntent(**source.execution_intent)
    except (TypeError, ValueError) as exc:
        raise CanonicalPromotionBindAdapterContractSelectionError(
            "PBAC_EXECUTION_INTENT_INVALID"
        ) from exc
    if intent.to_dict() != source.execution_intent:
        raise CanonicalPromotionBindAdapterContractSelectionError(
            "PBAC_EXECUTION_INTENT_OBJECT_MISMATCH"
        )
    if intent.execution_intent_id != source.execution_intent_id:
        raise CanonicalPromotionBindAdapterContractSelectionError(
            "PBAC_EXECUTION_INTENT_ID_MISMATCH"
        )
    if hash_execution_intent(intent) != source.execution_intent_hash:
        raise CanonicalPromotionBindAdapterContractSelectionError(
            "PBAC_EXECUTION_INTENT_HASH_MISMATCH"
        )
    return intent


def _descriptor(value: Any, intent: ExecutionIntent) -> BindAdapterContractDescriptor:
    try:
        return verify_bind_adapter_contract_descriptor(value, intent)
    except (BindAdapterContractSelectionError, TypeError, ValueError) as exc:
        raise CanonicalPromotionBindAdapterContractSelectionError(
            "PBAC_DESCRIPTOR_INVALID"
        ) from exc


def _source_bindings(
    source: CanonicalPromotionBindPreflightAdjudicationPacket,
) -> dict[str, Any]:
    return {
        "source_pre_bind_validation_id": source.source_pre_bind_validation_id,
        "source_pre_bind_validation_hash": source.source_pre_bind_validation_hash,
        "source_readiness_id": source.source_readiness_id,
        "source_readiness_hash": source.source_readiness_hash,
        "source_promotion_id": source.source_promotion_id,
        "source_promotion_hash": source.source_promotion_hash,
        "source_decision_identity": source.source_decision_identity,
        "candidate_identity": source.candidate_identity,
        "selected_action_lineage": source.selected_action_lineage,
        "policy_snapshot_lineage": source.policy_snapshot_lineage,
    }


def build_canonical_promotion_bind_adapter_contract_selection_packet(
    bind_preflight_adjudication_packet: (
        CanonicalPromotionBindPreflightAdjudicationPacket | Mapping[str, Any]
    ),
    adapter_contract_descriptor: BindAdapterContractDescriptor | Mapping[str, Any],
    selected_at: datetime,
) -> CanonicalPromotionBindAdapterContractSelectionPacket:
    """Associate one descriptor with an independently verified source intent."""
    selected = _aware_iso(selected_at, "PBAC_SELECTED_AT_INVALID")
    source = _verified_source(_json_value(bind_preflight_adjudication_packet))
    if selected < _aware_iso(source.adjudicated_at, "PBAC_SOURCE_TIME_INVALID"):
        raise CanonicalPromotionBindAdapterContractSelectionError(
            "PBAC_SELECTED_BEFORE_BIND_PREFLIGHT"
        )
    intent = _verified_intent(source)
    descriptor = _descriptor(adapter_contract_descriptor, intent)
    raw = {
        "format_version": FORMAT_VERSION,
        "adapter_contract_selection_id": "pbac:v1:sha256:" + "0" * 64,
        "adapter_contract_selection_hash": "0" * 64,
        "selection_mechanism": SELECTION_MECHANISM,
        "selected_at": selected.isoformat(),
        "source_bind_preflight_adjudication_id": (
            source.bind_preflight_adjudication_id
        ),
        "source_bind_preflight_adjudication_hash": (
            source.bind_preflight_adjudication_hash
        ),
        "source_bind_preflight_adjudication_packet": source.model_dump(mode="json"),
        **_source_bindings(source),
        "execution_intent": source.execution_intent,
        "execution_intent_id": source.execution_intent_id,
        "execution_intent_hash": source.execution_intent_hash,
        "adapter_contract_descriptor": descriptor.model_dump(mode="json"),
        "adapter_contract_id": descriptor.adapter_contract_id,
        "adapter_contract_hash": descriptor.adapter_contract_hash,
        "adapter_contract_version": descriptor.adapter_contract_version,
        "approval_context": source.approval_context,
        "policy_lineage": source.policy_lineage,
        "local_selection_checks": LOCAL_SELECTION_CHECKS,
        "local_selection_checks_digest": _digest(
            LOCAL_CHECKS_DOMAIN, LOCAL_SELECTION_CHECKS
        ),
        "future_bind_dry_run_requirements": FUTURE_BIND_DRY_RUN_REQUIREMENTS,
        "future_bind_dry_run_requirements_digest": _digest(
            FUTURE_REQUIREMENTS_DOMAIN, FUTURE_BIND_DRY_RUN_REQUIREMENTS
        ),
        "selection_status": SELECTION_STATUS,
        "scope_limitations": SCOPE_LIMITATIONS,
    }
    digest = _packet_hash(raw)
    raw["adapter_contract_selection_hash"] = digest
    raw["adapter_contract_selection_id"] = f"pbac:v1:sha256:{digest}"
    return verify_canonical_promotion_bind_adapter_contract_selection_packet(raw)


def verify_canonical_promotion_bind_adapter_contract_selection_packet(
    packet: CanonicalPromotionBindAdapterContractSelectionPacket | Mapping[str, Any],
) -> CanonicalPromotionBindAdapterContractSelectionPacket:
    """Independently reverify source, intent, descriptor, lineage, and hashes."""
    try:
        parsed = CanonicalPromotionBindAdapterContractSelectionPacket.model_validate(
            _json_value(packet)
        )
        raw = parsed.model_dump(mode="json")
        source = _verified_source(parsed.source_bind_preflight_adjudication_packet)
        intent = _verified_intent(source)
        descriptor = _descriptor(parsed.adapter_contract_descriptor, intent)
        if _aware_iso(parsed.selected_at, "PBAC_SELECTED_AT_INVALID") < _aware_iso(
            source.adjudicated_at, "PBAC_SOURCE_TIME_INVALID"
        ):
            raise CanonicalPromotionBindAdapterContractSelectionError(
                "PBAC_SELECTED_BEFORE_BIND_PREFLIGHT"
            )
        if (
            parsed.source_bind_preflight_adjudication_id
            != source.bind_preflight_adjudication_id
            or parsed.source_bind_preflight_adjudication_hash
            != source.bind_preflight_adjudication_hash
            or any(
                getattr(parsed, key) != value
                for key, value in _source_bindings(source).items()
            )
            or parsed.execution_intent != source.execution_intent
            or parsed.execution_intent != intent.to_dict()
            or parsed.execution_intent_id != source.execution_intent_id
            or parsed.execution_intent_id != intent.execution_intent_id
            or parsed.execution_intent_hash != source.execution_intent_hash
            or parsed.execution_intent_hash != hash_execution_intent(intent)
            or parsed.approval_context != source.approval_context
            or parsed.approval_context != intent.approval_context
            or parsed.policy_lineage != source.policy_lineage
            or parsed.policy_lineage != intent.policy_lineage
        ):
            raise CanonicalPromotionBindAdapterContractSelectionError(
                "PBAC_SOURCE_BINDING_MISMATCH"
            )
        descriptor_raw = descriptor.model_dump(mode="json")
        if (
            parsed.adapter_contract_descriptor != descriptor_raw
            or parsed.adapter_contract_id != descriptor.adapter_contract_id
            or parsed.adapter_contract_hash != descriptor.adapter_contract_hash
            or parsed.adapter_contract_version != descriptor.adapter_contract_version
        ):
            raise CanonicalPromotionBindAdapterContractSelectionError(
                "PBAC_DESCRIPTOR_BINDING_MISMATCH"
            )
        if parsed.local_selection_checks != LOCAL_SELECTION_CHECKS or (
            parsed.local_selection_checks_digest
            != _digest(LOCAL_CHECKS_DOMAIN, LOCAL_SELECTION_CHECKS)
        ):
            raise CanonicalPromotionBindAdapterContractSelectionError(
                "PBAC_LOCAL_CHECKS_MISMATCH"
            )
        if (
            parsed.future_bind_dry_run_requirements != FUTURE_BIND_DRY_RUN_REQUIREMENTS
            or parsed.future_bind_dry_run_requirements_digest
            != _digest(FUTURE_REQUIREMENTS_DOMAIN, FUTURE_BIND_DRY_RUN_REQUIREMENTS)
        ):
            raise CanonicalPromotionBindAdapterContractSelectionError(
                "PBAC_FUTURE_REQUIREMENTS_MISMATCH"
            )
        if parsed.scope_limitations != SCOPE_LIMITATIONS:
            raise CanonicalPromotionBindAdapterContractSelectionError(
                "PBAC_SCOPE_LIMITATIONS_MISMATCH"
            )
        digest = _packet_hash(raw)
        if parsed.adapter_contract_selection_hash != digest:
            raise CanonicalPromotionBindAdapterContractSelectionError(
                "PBAC_PACKET_HASH_MISMATCH"
            )
        if parsed.adapter_contract_selection_id != f"pbac:v1:sha256:{digest}":
            raise CanonicalPromotionBindAdapterContractSelectionError(
                "PBAC_PACKET_ID_MISMATCH"
            )
        return parsed
    except CanonicalPromotionBindAdapterContractSelectionError:
        raise
    except (TypeError, ValueError, ValidationError) as exc:
        raise CanonicalPromotionBindAdapterContractSelectionError(
            "PBAC_PACKET_INVALID"
        ) from exc
