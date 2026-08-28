"""Promotion-native readiness boundary before any live-adapter request.

This module only verifies and preserves a promotion-native in-memory rehearsal.
It has no adapter, request, credential, persistence, network, or I/O capability.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from veritas_os.policy.bind_adapter_contract_selection import (
    BindAdapterContractSelectionError,
    verify_bind_adapter_contract_descriptor,
)
from veritas_os.policy.bind_artifacts import ExecutionIntent, hash_execution_intent
from veritas_os.policy.canonical_promotion_adapter_dry_run_fixture_result import (
    RESULTS_DOMAIN as FIXTURE_RESULTS_DOMAIN,
    _digest as fixture_digest,
)
from veritas_os.policy.canonical_promotion_adapter_dry_run_plan import (
    STEPS_DOMAIN,
    _digest as plan_digest,
)
from veritas_os.policy.canonical_promotion_reference_adapter_rehearsal import (
    RESULTS_DOMAIN as REHEARSAL_RESULTS_DOMAIN,
    CanonicalPromotionReferenceAdapterInMemoryRehearsalPacket,
    CanonicalPromotionReferenceAdapterRehearsalError,
    _digest as rehearsal_digest,
    verify_canonical_promotion_reference_adapter_in_memory_rehearsal_packet,
)

FORMAT_VERSION = "canonical-promotion-live-adapter-dry-run-request-readiness/v1"
READINESS_MECHANISM = (
    "evaluate_promotion_live_adapter_dry_run_request_readiness_without_request/v1"
)
CHECKS_DOMAIN = "veritas.promotion-live-adapter-dry-run-readiness.checks/v1"
LOCAL_CHECKS_DOMAIN = "veritas.promotion-live-adapter-dry-run-readiness.local-checks/v1"
FUTURE_REQUIREMENTS_DOMAIN = (
    "veritas.promotion-live-adapter-dry-run-readiness.future-requirements/v1"
)
PACKET_DOMAIN = "veritas.promotion-live-adapter-dry-run-readiness.packet/v1"
STATUS = "PROMOTION_NATIVE_LIVE_ADAPTER_DRY_RUN_REQUEST_READY_BUT_NOT_REQUESTED"

CHECK_NAMES = (
    "source_reference_rehearsal_verified",
    "execution_intent_identity_verified",
    "adapter_contract_descriptor_preserved",
    "planned_steps_preserved",
    "fixture_results_preserved",
    "reference_rehearsal_results_preserved",
    "no_live_adapter_already_called",
    "no_webhook_already_called",
    "no_bind_already_invoked",
    "no_bind_receipt_created",
    "no_trustlog_written",
    "no_external_effect_observed",
    "live_dry_run_request_not_yet_created",
    "apply_still_forbidden",
    "postconditions_still_deferred",
    "rollback_still_deferred",
)
CHECK_LIMITATIONS = (
    "NOT_LIVE_ADAPTER_RESULT",
    "NOT_LIVE_STATE",
    "NOT_LIVE_AUTHORITY_REVALIDATION",
    "NOT_LIVE_CONSTRAINT_REVALIDATION",
    "NOT_RUNTIME_RISK_ACCEPTANCE",
    "NOT_BIND_AUTHORIZATION",
    "NOT_BIND_RECEIPT",
    "NOT_TRUSTLOG_WRITE",
    "NOT_OPERATION_COMMIT",
    "NOT_AUTHORITY_EVIDENCE_PROOF",
    "NOT_HUMAN_APPROVAL_PROOF",
)
LOCAL_READINESS_CHECKS = {
    key: True
    for key in (
        "source_reference_rehearsal_verified",
        "execution_intent_object_verified",
        "execution_intent_id_verified",
        "execution_intent_hash_verified",
        "adapter_descriptor_verified",
        "adapter_descriptor_target_verified",
        "planned_steps_preserved",
        "planned_step_digest_verified",
        "fixture_results_preserved",
        "fixture_result_digest_verified",
        "reference_rehearsal_results_preserved",
        "reference_rehearsal_result_digest_verified",
        "readiness_checks_ordered",
        "readiness_checks_digest_verified",
        "evaluated_after_reference_rehearsal",
        "no_live_adapter_instance",
        "no_live_adapter_invocation",
        "no_live_dry_run_request_created",
        "no_webhook_invocation",
        "no_network",
        "no_filesystem",
        "no_credential_access",
        "no_external_effect",
        "no_bind_invocation",
        "no_bind_receipt_created",
        "no_trustlog_write",
        "no_apply",
        "no_postcondition_verification",
        "no_revert",
        "no_authority_evidence_proof",
        "no_human_approval_proof",
    )
}
FUTURE_REQUIREMENTS = {
    key: True
    for key in (
        "explicit_promotion_native_live_dry_run_request_packet_required",
        "fresh_verified_source_gate_required",
        "live_adapter_descriptor_required",
        "live_adapter_endpoint_allowlist_required",
        "live_adapter_read_only_scope_required",
        "live_adapter_credentials_review_required",
        "live_adapter_timeout_required",
        "live_adapter_rate_limit_required",
        "live_adapter_idempotency_key_required",
        "live_adapter_no_apply_policy_required",
        "live_adapter_no_commit_policy_required",
        "authority_evidence_proof_still_deferred",
        "human_approval_proof_still_deferred",
        "bind_authorization_still_deferred",
        "bind_receipt_still_deferred",
        "apply_still_forbidden",
        "verify_postconditions_still_deferred",
        "rollback_or_revert_still_deferred",
    )
}
SCOPE_LIMITATIONS = (
    "NOT_EXECUTION_AUTHORITY",
    "NOT_BIND_AUTHORIZATION",
    "NOT_BIND_RECEIPT",
    "NOT_BIND_INVOCATION",
    "NOT_LIVE_ADAPTER_INSTANCE",
    "NOT_LIVE_ADAPTER_INVOCATION",
    "NOT_LIVE_ADAPTER_RESULT",
    "NOT_LIVE_DRY_RUN_REQUEST",
    "NOT_WEBHOOK_INVOCATION",
    "NOT_CREDENTIAL_AUTHORIZATION",
    "NOT_EXTERNAL_EFFECT",
    "NOT_OPERATION_COMMIT",
    "NOT_TRUSTLOG_WRITE",
    "NOT_LIVE_STATE_CHECK",
    "NOT_RUNTIME_RISK_ACCEPTANCE",
    "NOT_LIVE_AUTHORITY_REVALIDATION",
    "NOT_LIVE_CONSTRAINT_REVALIDATION",
    "NOT_POSTCONDITION_VERIFICATION",
    "NOT_ROLLBACK_PROOF",
    "NOT_AUTHORITY_EVIDENCE_PROOF",
    "NOT_HUMAN_APPROVAL_PROOF",
)
LINEAGE_FIELDS = (
    "source_adapter_dry_run_fixture_result_id",
    "source_adapter_dry_run_fixture_result_hash",
    "source_adapter_dry_run_plan_id",
    "source_adapter_dry_run_plan_hash",
    "source_adapter_contract_selection_id",
    "source_adapter_contract_selection_hash",
    "source_bind_preflight_adjudication_id",
    "source_bind_preflight_adjudication_hash",
    "source_pre_bind_validation_id",
    "source_pre_bind_validation_hash",
    "source_readiness_id",
    "source_readiness_hash",
    "source_promotion_id",
    "source_promotion_hash",
    "source_decision_identity",
    "candidate_identity",
    "selected_action_lineage",
    "policy_snapshot_lineage",
    "approval_context",
    "policy_lineage",
)


class CanonicalPromotionLiveAdapterDryRunReadinessError(ValueError):
    """Stable fail-closed refusal for promotion-native readiness packets."""


class PromotionLiveAdapterDryRunReadinessCheck(BaseModel):
    """Immutable evidence for one local, no-effect readiness assertion."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    readiness_check_id: str = Field(
        pattern=r"^promotion-live-adapter-dry-run-readiness-check:v1:[1-9][0-9]*:[a-z0-9-]+$"
    )
    ordinal: int = Field(ge=1, le=16)
    check_name: Literal[*CHECK_NAMES]
    check_mode: Literal["deterministic_local_readiness_only"]
    passed: Literal[True]
    evidence_ref: str = Field(min_length=1)
    live_observation_used: Literal[False]
    network_used: Literal[False]
    filesystem_used: Literal[False]
    credential_accessed: Literal[False]
    adapter_instance_created: Literal[False]
    adapter_method_called: Literal[False]
    request_created: Literal[False]
    request_dispatched: Literal[False]
    bind_invoked: Literal[False]
    bind_receipt_created: Literal[False]
    trustlog_written: Literal[False]
    external_effect_used: Literal[False]
    human_approval_proven: Literal[False]
    authority_evidence_proven: Literal[False]
    check_scope_limitations: tuple[str, ...]


class CanonicalPromotionLiveAdapterDryRunRequestReadinessPacket(BaseModel):
    """Strict content-addressed promotion-native readiness-only packet."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    format_version: Literal[FORMAT_VERSION]
    promotion_live_adapter_dry_run_readiness_id: str = Field(
        pattern=r"^pladr:v1:sha256:[0-9a-f]{64}$"
    )
    promotion_live_adapter_dry_run_readiness_hash: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )
    readiness_mechanism: Literal[READINESS_MECHANISM]
    readiness_evaluated_at: str
    source_reference_rehearsal_id: str
    source_reference_rehearsal_hash: str
    source_reference_rehearsal_packet: dict[str, Any]
    source_adapter_dry_run_fixture_result_id: str
    source_adapter_dry_run_fixture_result_hash: str
    source_adapter_dry_run_plan_id: str
    source_adapter_dry_run_plan_hash: str
    source_adapter_contract_selection_id: str
    source_adapter_contract_selection_hash: str
    source_bind_preflight_adjudication_id: str
    source_bind_preflight_adjudication_hash: str
    source_pre_bind_validation_id: str
    source_pre_bind_validation_hash: str
    source_readiness_id: str
    source_readiness_hash: str
    source_promotion_id: str
    source_promotion_hash: str
    source_decision_identity: dict[str, Any]
    candidate_identity: dict[str, Any]
    selected_action_lineage: dict[str, Any]
    policy_snapshot_lineage: dict[str, Any]
    approval_context: dict[str, Any]
    policy_lineage: dict[str, Any]
    execution_intent: dict[str, Any]
    execution_intent_id: str
    execution_intent_hash: str
    adapter_contract_descriptor: dict[str, Any]
    adapter_contract_id: str
    adapter_contract_hash: str
    adapter_contract_version: Literal["bind-adapter-contract/v1"]
    planned_steps: tuple[dict[str, Any], ...]
    planned_step_digest: str
    fixture_step_results: tuple[dict[str, Any], ...]
    fixture_result_digest: str
    reference_rehearsal_results: tuple[dict[str, Any], ...]
    reference_rehearsal_result_digest: str
    readiness_checks: tuple[PromotionLiveAdapterDryRunReadinessCheck, ...]
    readiness_check_digest: str
    local_readiness_checks: dict[str, bool]
    local_readiness_checks_digest: str
    future_requirements: dict[str, bool]
    future_requirements_digest: str
    live_adapter_dry_run_request_readiness_status: Literal[STATUS]
    ready_for_promotion_native_live_adapter_dry_run_request_packet: Literal[True]
    human_approval_proven: Literal[False]
    authority_evidence_proven: Literal[False]
    request_created: Literal[False]
    request_dispatched: Literal[False]
    network_used: Literal[False]
    filesystem_used: Literal[False]
    external_effect_used: Literal[False]
    scope_limitations: tuple[str, ...]


def _json(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if (
        isinstance(value, float)
        and value == value
        and value not in (float("inf"), float("-inf"))
    ):
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise CanonicalPromotionLiveAdapterDryRunReadinessError(
                "PLADR_EVALUATED_AT_INVALID"
            )
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    if isinstance(value, Mapping) and all(isinstance(key, str) for key in value):
        return {key: _json(item) for key, item in value.items()}
    raise CanonicalPromotionLiveAdapterDryRunReadinessError("PLADR_PACKET_INVALID")


def _digest(domain: str, value: Any) -> str:
    encoded = json.dumps(
        {"domain": domain, "value": _json(value)},
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _aware(value: Any, code: str) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunReadinessError(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CanonicalPromotionLiveAdapterDryRunReadinessError(code)
    return parsed


def _packet_hash(raw: dict[str, Any]) -> str:
    excluded = {
        "promotion_live_adapter_dry_run_readiness_id",
        "promotion_live_adapter_dry_run_readiness_hash",
    }
    return _digest(
        PACKET_DOMAIN, {key: value for key, value in raw.items() if key not in excluded}
    )


def _source(
    value: Any,
) -> CanonicalPromotionReferenceAdapterInMemoryRehearsalPacket:
    try:
        return verify_canonical_promotion_reference_adapter_in_memory_rehearsal_packet(
            value
        )
    except (
        CanonicalPromotionReferenceAdapterRehearsalError,
        TypeError,
        ValueError,
    ) as exc:
        raise CanonicalPromotionLiveAdapterDryRunReadinessError(
            "PLADR_SOURCE_REHEARSAL_INVALID"
        ) from exc


def _validate_source(
    source: CanonicalPromotionReferenceAdapterInMemoryRehearsalPacket,
) -> ExecutionIntent:
    try:
        intent = ExecutionIntent(**source.execution_intent)
    except (TypeError, ValueError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunReadinessError(
            "PLADR_EXECUTION_INTENT_INVALID"
        ) from exc
    if (
        intent.to_dict() != source.execution_intent
        or intent.execution_intent_id != source.execution_intent_id
        or hash_execution_intent(intent) != source.execution_intent_hash
    ):
        raise CanonicalPromotionLiveAdapterDryRunReadinessError(
            "PLADR_EXECUTION_INTENT_MISMATCH"
        )
    try:
        descriptor = verify_bind_adapter_contract_descriptor(
            source.adapter_contract_descriptor, intent
        )
    except (BindAdapterContractSelectionError, TypeError, ValueError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunReadinessError(
            "PLADR_DESCRIPTOR_INVALID"
        ) from exc
    if (
        descriptor.model_dump(mode="json") != source.adapter_contract_descriptor
        or descriptor.adapter_contract_id != source.adapter_contract_id
        or descriptor.adapter_contract_hash != source.adapter_contract_hash
        or descriptor.adapter_contract_version != source.adapter_contract_version
        or descriptor.target_system != intent.target_system
        or descriptor.target_resource_scope != intent.target_resource
    ):
        raise CanonicalPromotionLiveAdapterDryRunReadinessError(
            "PLADR_DESCRIPTOR_MISMATCH"
        )
    return intent


def _checks(source_hash: str) -> list[dict[str, Any]]:
    return [
        {
            "readiness_check_id": (
                "promotion-live-adapter-dry-run-readiness-check:v1:"
                f"{ordinal}:{name.replace('_', '-')}"
            ),
            "ordinal": ordinal,
            "check_name": name,
            "check_mode": "deterministic_local_readiness_only",
            "passed": True,
            "evidence_ref": f"promotion_reference_rehearsal_hash:{source_hash}:{name}",
            "live_observation_used": False,
            "network_used": False,
            "filesystem_used": False,
            "credential_accessed": False,
            "adapter_instance_created": False,
            "adapter_method_called": False,
            "request_created": False,
            "request_dispatched": False,
            "bind_invoked": False,
            "bind_receipt_created": False,
            "trustlog_written": False,
            "external_effect_used": False,
            "human_approval_proven": False,
            "authority_evidence_proven": False,
            "check_scope_limitations": CHECK_LIMITATIONS,
        }
        for ordinal, name in enumerate(CHECK_NAMES, 1)
    ]


def build_canonical_promotion_live_adapter_dry_run_request_readiness_packet(
    reference_rehearsal_packet: CanonicalPromotionReferenceAdapterInMemoryRehearsalPacket
    | Mapping[str, Any],
    readiness_evaluated_at: datetime,
) -> CanonicalPromotionLiveAdapterDryRunRequestReadinessPacket:
    """Build verified promotion-native readiness without creating a request."""
    source = _source(_json(reference_rehearsal_packet))
    _validate_source(source)
    evaluated = _aware(readiness_evaluated_at, "PLADR_EVALUATED_AT_INVALID")
    if evaluated < _aware(source.rehearsed_at, "PLADR_SOURCE_REHEARSAL_INVALID"):
        raise CanonicalPromotionLiveAdapterDryRunReadinessError(
            "PLADR_EVALUATED_BEFORE_REHEARSAL"
        )
    source_raw = source.model_dump(mode="json")
    checks = _checks(source.promotion_reference_rehearsal_hash)
    raw = {
        "format_version": FORMAT_VERSION,
        "readiness_mechanism": READINESS_MECHANISM,
        "readiness_evaluated_at": evaluated.isoformat(),
        "source_reference_rehearsal_id": source.promotion_reference_rehearsal_id,
        "source_reference_rehearsal_hash": source.promotion_reference_rehearsal_hash,
        "source_reference_rehearsal_packet": source_raw,
        **{field: source_raw[field] for field in LINEAGE_FIELDS},
        **{
            field: source_raw[field]
            for field in (
                "execution_intent",
                "execution_intent_id",
                "execution_intent_hash",
                "adapter_contract_descriptor",
                "adapter_contract_id",
                "adapter_contract_hash",
                "adapter_contract_version",
                "planned_steps",
                "planned_step_digest",
                "fixture_step_results",
                "fixture_result_digest",
                "reference_rehearsal_results",
                "reference_rehearsal_result_digest",
            )
        },
        "readiness_checks": checks,
        "readiness_check_digest": _digest(CHECKS_DOMAIN, checks),
        "local_readiness_checks": LOCAL_READINESS_CHECKS,
        "local_readiness_checks_digest": _digest(
            LOCAL_CHECKS_DOMAIN, LOCAL_READINESS_CHECKS
        ),
        "future_requirements": FUTURE_REQUIREMENTS,
        "future_requirements_digest": _digest(
            FUTURE_REQUIREMENTS_DOMAIN, FUTURE_REQUIREMENTS
        ),
        "live_adapter_dry_run_request_readiness_status": STATUS,
        "ready_for_promotion_native_live_adapter_dry_run_request_packet": True,
        "human_approval_proven": False,
        "authority_evidence_proven": False,
        "request_created": False,
        "request_dispatched": False,
        "network_used": False,
        "filesystem_used": False,
        "external_effect_used": False,
        "scope_limitations": SCOPE_LIMITATIONS,
    }
    digest = _packet_hash(raw)
    raw["promotion_live_adapter_dry_run_readiness_hash"] = digest
    raw["promotion_live_adapter_dry_run_readiness_id"] = f"pladr:v1:sha256:{digest}"
    return verify_canonical_promotion_live_adapter_dry_run_request_readiness_packet(raw)


def verify_canonical_promotion_live_adapter_dry_run_request_readiness_packet(
    packet: Any,
) -> CanonicalPromotionLiveAdapterDryRunRequestReadinessPacket:
    """Independently fail closed on every source, evidence, and no-effect claim."""
    try:
        candidate = (
            CanonicalPromotionLiveAdapterDryRunRequestReadinessPacket.model_validate(
                _json(packet)
            )
        )
        raw = candidate.model_dump(mode="json")
        source = _source(candidate.source_reference_rehearsal_packet)
        intent = _validate_source(source)
        if (
            candidate.source_reference_rehearsal_id
            != source.promotion_reference_rehearsal_id
            or candidate.source_reference_rehearsal_hash
            != source.promotion_reference_rehearsal_hash
            or any(
                getattr(candidate, field) != getattr(source, field)
                for field in LINEAGE_FIELDS
            )
            or candidate.execution_intent != intent.to_dict()
            or candidate.execution_intent_id != intent.execution_intent_id
            or candidate.execution_intent_hash != hash_execution_intent(intent)
            or candidate.adapter_contract_descriptor
            != source.adapter_contract_descriptor
            or candidate.adapter_contract_id != source.adapter_contract_id
            or candidate.adapter_contract_hash != source.adapter_contract_hash
            or candidate.adapter_contract_version != source.adapter_contract_version
        ):
            raise CanonicalPromotionLiveAdapterDryRunReadinessError(
                "PLADR_SOURCE_BINDING_MISMATCH"
            )
        if _aware(
            candidate.readiness_evaluated_at, "PLADR_EVALUATED_AT_INVALID"
        ) < _aware(source.rehearsed_at, "PLADR_SOURCE_REHEARSAL_INVALID"):
            raise CanonicalPromotionLiveAdapterDryRunReadinessError(
                "PLADR_EVALUATED_BEFORE_REHEARSAL"
            )
        steps = [_json(item) for item in source.planned_steps]
        fixtures = [_json(item) for item in source.fixture_step_results]
        results = [_json(item) for item in source.reference_rehearsal_results]
        if (
            list(candidate.planned_steps) != steps
            or candidate.planned_step_digest != source.planned_step_digest
            or candidate.planned_step_digest != plan_digest(STEPS_DOMAIN, steps)
        ):
            raise CanonicalPromotionLiveAdapterDryRunReadinessError(
                "PLADR_PLANNED_STEPS_MISMATCH"
            )
        if (
            list(candidate.fixture_step_results) != fixtures
            or candidate.fixture_result_digest != source.fixture_result_digest
            or candidate.fixture_result_digest
            != fixture_digest(FIXTURE_RESULTS_DOMAIN, fixtures)
        ):
            raise CanonicalPromotionLiveAdapterDryRunReadinessError(
                "PLADR_FIXTURE_RESULTS_MISMATCH"
            )
        if (
            list(candidate.reference_rehearsal_results) != results
            or candidate.reference_rehearsal_result_digest
            != source.reference_rehearsal_result_digest
            or candidate.reference_rehearsal_result_digest
            != rehearsal_digest(REHEARSAL_RESULTS_DOMAIN, results)
        ):
            raise CanonicalPromotionLiveAdapterDryRunReadinessError(
                "PLADR_REHEARSAL_RESULTS_MISMATCH"
            )
        checks = _checks(source.promotion_reference_rehearsal_hash)
        if [_json(item) for item in candidate.readiness_checks] != _json(checks):
            raise CanonicalPromotionLiveAdapterDryRunReadinessError(
                "PLADR_READINESS_CHECKS_INVALID"
            )
        if candidate.readiness_check_digest != _digest(CHECKS_DOMAIN, checks):
            raise CanonicalPromotionLiveAdapterDryRunReadinessError(
                "PLADR_READINESS_CHECK_DIGEST_MISMATCH"
            )
        if (
            candidate.local_readiness_checks != LOCAL_READINESS_CHECKS
            or candidate.local_readiness_checks_digest
            != _digest(LOCAL_CHECKS_DOMAIN, LOCAL_READINESS_CHECKS)
            or candidate.future_requirements != FUTURE_REQUIREMENTS
            or candidate.future_requirements_digest
            != _digest(FUTURE_REQUIREMENTS_DOMAIN, FUTURE_REQUIREMENTS)
            or candidate.scope_limitations != SCOPE_LIMITATIONS
        ):
            raise CanonicalPromotionLiveAdapterDryRunReadinessError(
                "PLADR_CANONICAL_CHECKS_MISMATCH"
            )
        digest = _packet_hash(raw)
        if (
            candidate.promotion_live_adapter_dry_run_readiness_hash != digest
            or candidate.promotion_live_adapter_dry_run_readiness_id
            != f"pladr:v1:sha256:{digest}"
        ):
            raise CanonicalPromotionLiveAdapterDryRunReadinessError(
                "PLADR_PACKET_IDENTITY_MISMATCH"
            )
        return candidate
    except CanonicalPromotionLiveAdapterDryRunReadinessError:
        raise
    except (TypeError, ValueError, ValidationError, KeyError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunReadinessError(
            "PLADR_PACKET_INVALID"
        ) from exc
