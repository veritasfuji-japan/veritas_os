"""Authorize promotion-native credential metadata without credential access.

This pure-data boundary consumes a verified promotion-native endpoint
allowlist evaluation.  It performs exact local policy comparison only and has
no capability to resolve credentials, construct authorization headers,
dispatch requests, invoke Bind, or create external effects.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from veritas_os.policy.bind_adapter_contract_selection import (
    BindAdapterContractSelectionError,
    verify_bind_adapter_contract_descriptor,
)
from veritas_os.policy.bind_artifacts import ExecutionIntent, hash_execution_intent
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_endpoint_allowlist import (
    CanonicalPromotionLiveAdapterDryRunEndpointAllowlistError,
    CanonicalPromotionLiveAdapterDryRunEndpointAllowlistEvaluationPacket,
    verify_canonical_promotion_live_adapter_dry_run_endpoint_allowlist_evaluation_packet,
)

FORMAT_VERSION = (
    "canonical-promotion-live-adapter-dry-run-credential-authorization-"
    "evaluation/v1"
)
EVALUATION_MECHANISM = (
    "evaluate_promotion_live_adapter_dry_run_credential_authorization_"
    "without_access/v1"
)
STATUS = "PROMOTION_NATIVE_CREDENTIAL_AUTHORIZATION_EVALUATED_NOT_DISPATCHED"
CHECK_MODE = "deterministic_local_credential_authorization_evaluation_only"
PREFIX = "veritas.promotion-live-adapter-dry-run-credential-authorization"
REFERENCE_DOMAIN = PREFIX + ".reference/v1"
POLICY_SNAPSHOT_DOMAIN = PREFIX + ".policy-snapshot/v1"
RESULT_DOMAIN = PREFIX + ".result/v1"
SCOPE_BINDING_DOMAIN = PREFIX + ".scope-binding/v1"
CHECKS_DOMAIN = PREFIX + ".checks/v1"
FUTURE_REQUIREMENTS_DOMAIN = PREFIX + ".future-requirements/v1"
PACKET_DOMAIN = PREFIX + ".packet/v1"

EXACT_FIELDS = (
    "credential_kind",
    "credential_provider_type",
    "credential_scope",
    "credential_environment",
    "adapter_contract_id",
    "endpoint_candidate_id",
    "target_system",
    "target_resource_scope",
    "credential_purpose",
)
PROHIBITED_KEYS = frozenset(
    {
        "secret",
        "secret_value",
        "api_key",
        "bearer_token",
        "token",
        "authorization",
        "authorization_header",
        "cookie",
        "password",
        "private_key",
        "credential",
        "credentials",
        "credential_payload",
        "credential_material",
        "resolved_credential_material",
        "request_body",
        "body",
    }
)
LINEAGE_FIELDS = (
    "source_live_adapter_dry_run_readiness_id",
    "source_live_adapter_dry_run_readiness_hash",
    "source_reference_rehearsal_id",
    "source_reference_rehearsal_hash",
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
CHECK_NAMES = (
    "source_promotion_native_endpoint_evaluation_verified",
    "source_endpoint_matched",
    "source_remains_not_dispatched",
    "exact_execution_intent_verified",
    "exact_adapter_verified",
    "exact_endpoint_identity_preserved",
    "credential_reference_closed_schema_valid",
    "credential_reference_contains_no_secret_material",
    "credential_reference_binds_exact_adapter",
    "credential_reference_binds_exact_endpoint",
    "credential_reference_binds_exact_target_system_resource",
    "credential_policy_snapshot_valid",
    "credential_policy_snapshot_hash_verified",
    "active_policy_entry_required",
    "all_exact_credential_dimensions_compared",
    "credential_scope_binding_constructed",
    "credential_not_resolved",
    "credential_material_not_accessed",
    "credential_store_not_accessed",
    "authorization_header_not_constructed",
    "network_not_used",
    "adapter_not_instantiated",
    "bind_not_invoked",
    "trustlog_not_written",
    "future_operator_review_still_required",
    "fresh_source_gate_still_required",
)
FUTURE_REQUIREMENT_NAMES = (
    "promotion_native_operator_dispatch_review",
    "bind_pre_dispatch_review",
    "endpoint_identity_recheck",
    "credential_reference_recheck",
    "credential_material_resolution_boundary",
    "credential_material_non_embedding",
    "authorization_header_construction_boundary",
    "authority_evidence_verification",
    "fresh_source_gate",
    "gate_bound_human_approval",
    "real_bind_authorization",
    "network_dispatch",
    "request_dispatch_receipt",
    "external_effect",
    "postcondition_rollback_reconciliation",
)
EFFECT_FIELDS = (
    "credential_resolved",
    "credential_material_accessed",
    "credential_material_embedded",
    "credential_store_accessed",
    "authorization_header_constructed",
    "token_embedded",
    "secret_embedded",
    "cookie_embedded",
    "password_embedded",
    "private_key_embedded",
    "endpoint_resolved",
    "endpoint_contacted",
    "dns_used",
    "network_used",
    "webhook_invoked",
    "live_adapter_instantiated",
    "live_adapter_method_invoked",
    "request_dispatched",
    "bind_invoked",
    "bind_authorization_issued",
    "bind_receipt_created",
    "trustlog_written",
    "filesystem_used",
    "database_used",
    "provider_called",
    "subprocess_used",
    "external_effect_used",
    "operation_committed",
    "apply_performed",
    "postcondition_verified",
    "rollback_or_revert_performed",
)


class CanonicalPromotionLiveAdapterDryRunCredentialAuthorizationError(ValueError):
    """Stable fail-closed error for invalid credential authorization evidence."""


class CredentialReference(BaseModel):
    """Closed metadata-only reference that cannot carry credential material."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    credential_reference_id: str = Field(min_length=1)
    credential_kind: str = Field(min_length=1)
    credential_provider_type: str = Field(min_length=1)
    credential_scope: str = Field(min_length=1)
    credential_environment: str = Field(min_length=1)
    credential_purpose: str = Field(min_length=1)
    adapter_contract_id: str = Field(min_length=1)
    endpoint_candidate_id: str = Field(min_length=1)
    target_system: str = Field(min_length=1)
    target_resource_scope: str = Field(min_length=1)
    declared_by: str = Field(min_length=1)
    declared_at: str


class CredentialPolicyEntry(BaseModel):
    """One exact local credential-metadata policy entry."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    entry_id: str = Field(min_length=1)
    credential_kind: str
    credential_provider_type: str
    credential_scope: str
    credential_environment: str
    allowed_adapter_contract_ids: tuple[str, ...]
    allowed_endpoint_candidate_ids: tuple[str, ...]
    allowed_target_systems: tuple[str, ...]
    allowed_target_resource_scopes: tuple[str, ...]
    allowed_purposes: tuple[str, ...]
    requires_operator_review: bool
    requires_bind_pre_dispatch_review: bool
    entry_status: Literal["ACTIVE", "INACTIVE"]


class CredentialPolicySnapshot(BaseModel):
    """Closed content-addressed credential metadata policy snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    credential_policy_snapshot_id: str = Field(min_length=1)
    credential_policy_snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    credential_policy_version: str = Field(min_length=1)
    credential_policy_source: str = Field(min_length=1)
    credential_policy_generated_at: str
    credential_policy_entries: tuple[CredentialPolicyEntry, ...]
    credential_policy_scope_limitations: tuple[str, ...]


class CredentialAuthorizationResult(BaseModel):
    """Deterministic exact-match credential metadata authorization result."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    authorized: bool
    matched_policy_entry_id: str | None
    authorization_reason: str
    rejection_reasons: tuple[str, ...]
    comparison_mode: Literal["exact_local_credential_policy_comparison_only"]
    exact_fields_compared: tuple[Literal[*EXACT_FIELDS], ...]
    semantic_match_used: Literal[False]
    credential_material_accessed: Literal[False]


class CredentialAuthorizationCheck(BaseModel):
    """One independently reconstructed ordered authorization check."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    check_id: str
    ordinal: int = Field(ge=1, le=len(CHECK_NAMES))
    name: Literal[*CHECK_NAMES]
    mode: Literal[CHECK_MODE]
    passed: bool
    evidence_ref: str
    credential_material_accessed: Literal[False]
    network_used: Literal[False]
    request_dispatched: Literal[False]
    bind_invoked: Literal[False]
    trustlog_written: Literal[False]


class FutureRequirement(BaseModel):
    """A later security boundary explicitly unsatisfied by this packet."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    ordinal: int = Field(ge=1, le=len(FUTURE_REQUIREMENT_NAMES))
    name: Literal[*FUTURE_REQUIREMENT_NAMES]
    separate_future_artifact_required: Literal[True]
    satisfied_by_this_packet: Literal[False]


class CanonicalPromotionLiveAdapterDryRunCredentialAuthorizationEvaluationPacket(
    BaseModel
):
    """Content-addressed promotion-native credential authorization evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    format_version: Literal[FORMAT_VERSION]
    promotion_live_adapter_dry_run_credential_authorization_evaluation_id: str = (
        Field(pattern=r"^pladrca:v1:sha256:[0-9a-f]{64}$")
    )
    promotion_live_adapter_dry_run_credential_authorization_evaluation_hash: str = (
        Field(pattern=r"^[0-9a-f]{64}$")
    )
    credential_authorization_evaluation_mechanism: Literal[EVALUATION_MECHANISM]
    credential_authorization_evaluated_at: str
    source_endpoint_allowlist_evaluation_id: str
    source_endpoint_allowlist_evaluation_hash: str
    source_endpoint_allowlist_evaluation_packet: dict[str, Any]
    source_dispatch_readiness_id: str
    source_dispatch_readiness_hash: str
    source_live_adapter_dry_run_request_id: str
    source_live_adapter_dry_run_request_hash: str
    request_descriptor: dict[str, Any]
    execution_intent: dict[str, Any]
    execution_intent_id: str
    execution_intent_hash: str
    adapter_contract_descriptor: dict[str, Any]
    adapter_contract_id: str
    adapter_contract_hash: str
    adapter_contract_version: str
    source_live_adapter_dry_run_readiness_id: str
    source_live_adapter_dry_run_readiness_hash: str
    source_reference_rehearsal_id: str
    source_reference_rehearsal_hash: str
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
    endpoint_candidate: dict[str, Any]
    endpoint_candidate_digest: str
    allowlist_snapshot: dict[str, Any]
    allowlist_snapshot_hash: str
    allowlist_evaluation_result: dict[str, Any]
    allowlist_evaluation_digest: str
    endpoint_identity_binding: dict[str, Any]
    endpoint_identity_binding_digest: str
    credential_reference: CredentialReference
    credential_reference_digest: str
    credential_policy_snapshot: CredentialPolicySnapshot
    credential_policy_snapshot_hash: str
    credential_authorization_result: CredentialAuthorizationResult
    credential_authorization_result_digest: str
    credential_scope_binding: dict[str, Any]
    credential_scope_binding_digest: str
    credential_authorization_checks: tuple[CredentialAuthorizationCheck, ...]
    credential_authorization_check_digest: str
    future_requirements: tuple[FutureRequirement, ...]
    future_requirement_digest: str
    credential_authorization_status: Literal[STATUS]
    request_dispatch_state: Literal["NOT_DISPATCHED"]
    ready_for_promotion_native_operator_dispatch_review: bool
    fail_closed: bool
    execution_authorized: Literal[False]
    human_approval_proven: Literal[False]
    authority_evidence_proven: Literal[False]
    ready_for_real_bind: Literal[False]
    ready_for_network_dispatch: Literal[False]
    credential_resolved: Literal[False]
    credential_material_accessed: Literal[False]
    credential_material_embedded: Literal[False]
    credential_store_accessed: Literal[False]
    authorization_header_constructed: Literal[False]
    token_embedded: Literal[False]
    secret_embedded: Literal[False]
    cookie_embedded: Literal[False]
    password_embedded: Literal[False]
    private_key_embedded: Literal[False]
    endpoint_resolved: Literal[False]
    endpoint_contacted: Literal[False]
    dns_used: Literal[False]
    network_used: Literal[False]
    webhook_invoked: Literal[False]
    live_adapter_instantiated: Literal[False]
    live_adapter_method_invoked: Literal[False]
    request_dispatched: Literal[False]
    bind_invoked: Literal[False]
    bind_authorization_issued: Literal[False]
    bind_receipt_created: Literal[False]
    trustlog_written: Literal[False]
    filesystem_used: Literal[False]
    database_used: Literal[False]
    provider_called: Literal[False]
    subprocess_used: Literal[False]
    external_effect_used: Literal[False]
    operation_committed: Literal[False]
    apply_performed: Literal[False]
    postcondition_verified: Literal[False]
    rollback_or_revert_performed: Literal[False]


def _fail(code: str) -> None:
    raise CanonicalPromotionLiveAdapterDryRunCredentialAuthorizationError(code)


def _aware(value: Any, code: str) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunCredentialAuthorizationError(
            code
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail(code)
    return parsed


def _json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            _fail("PLADRCA_PACKET_INVALID")
        return value
    if isinstance(value, datetime):
        return _aware(value, "PLADRCA_TIMESTAMP_INVALID").isoformat()
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _json_value(item) for key, item in value.items()}
    _fail("PLADRCA_PACKET_INVALID")


def _digest(domain: str, value: Any) -> str:
    encoded = json.dumps(
        {"domain": domain, "value": _json_value(value)},
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _policy_snapshot_hash(raw: dict[str, Any]) -> str:
    """Recompute the policy hash without trusting its self-hash field."""
    return _digest(
        POLICY_SNAPSHOT_DOMAIN,
        {
            key: value
            for key, value in raw.items()
            if key != "credential_policy_snapshot_hash"
        },
    )


def _packet_hash(raw: dict[str, Any]) -> str:
    """Recompute the packet hash without its content address fields."""
    omitted = {
        "promotion_live_adapter_dry_run_credential_authorization_evaluation_id",
        "promotion_live_adapter_dry_run_credential_authorization_evaluation_hash",
    }
    return _digest(
        PACKET_DOMAIN,
        {key: value for key, value in raw.items() if key not in omitted},
    )


def _source(
    value: Any,
) -> CanonicalPromotionLiveAdapterDryRunEndpointAllowlistEvaluationPacket:
    try:
        source = (
            verify_canonical_promotion_live_adapter_dry_run_endpoint_allowlist_evaluation_packet(
                value
            )
        )
    except (
        CanonicalPromotionLiveAdapterDryRunEndpointAllowlistError,
        TypeError,
        ValueError,
    ) as exc:
        raise CanonicalPromotionLiveAdapterDryRunCredentialAuthorizationError(
            "PLADRCA_SOURCE_INVALID"
        ) from exc
    if (
        not source.allowlist_evaluation_result.matched
        or not source.ready_for_promotion_native_credential_authorization_evaluation
        or source.fail_closed
        or source.request_dispatch_state != "NOT_DISPATCHED"
    ):
        _fail("PLADRCA_SOURCE_NOT_READY")
    return source


def _validate_intent_adapter(
    source: CanonicalPromotionLiveAdapterDryRunEndpointAllowlistEvaluationPacket,
) -> ExecutionIntent:
    try:
        intent = ExecutionIntent(**source.execution_intent)
    except (TypeError, ValueError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunCredentialAuthorizationError(
            "PLADRCA_INTENT_INVALID"
        ) from exc
    if (
        intent.to_dict() != source.execution_intent
        or intent.execution_intent_id != source.execution_intent_id
        or hash_execution_intent(intent) != source.execution_intent_hash
    ):
        _fail("PLADRCA_INTENT_MISMATCH")
    try:
        descriptor = verify_bind_adapter_contract_descriptor(
            source.adapter_contract_descriptor, intent
        )
    except BindAdapterContractSelectionError as exc:
        raise CanonicalPromotionLiveAdapterDryRunCredentialAuthorizationError(
            "PLADRCA_ADAPTER_INVALID"
        ) from exc
    if (
        descriptor.model_dump(mode="json") != source.adapter_contract_descriptor
        or descriptor.adapter_contract_id != source.adapter_contract_id
        or descriptor.adapter_contract_hash != source.adapter_contract_hash
        or descriptor.adapter_contract_version != source.adapter_contract_version
    ):
        _fail("PLADRCA_ADAPTER_MISMATCH")
    return intent


def _reference(value: Any) -> CredentialReference:
    raw = _json_value(value)
    if isinstance(raw, dict) and any(
        key.lower().replace("-", "_") in PROHIBITED_KEYS for key in raw
    ):
        _fail("PLADRCA_SENSITIVE_INPUT")
    try:
        return CredentialReference.model_validate(raw)
    except ValidationError as exc:
        raise CanonicalPromotionLiveAdapterDryRunCredentialAuthorizationError(
            "PLADRCA_REFERENCE_INVALID"
        ) from exc


def _snapshot(value: Any) -> CredentialPolicySnapshot:
    try:
        snapshot = CredentialPolicySnapshot.model_validate(_json_value(value))
    except ValidationError as exc:
        raise CanonicalPromotionLiveAdapterDryRunCredentialAuthorizationError(
            "PLADRCA_POLICY_INVALID"
        ) from exc
    if snapshot.credential_policy_snapshot_hash != _policy_snapshot_hash(
        snapshot.model_dump(mode="json")
    ):
        _fail("PLADRCA_POLICY_HASH_INVALID")
    return snapshot


def _bind_reference(
    reference: CredentialReference,
    source: CanonicalPromotionLiveAdapterDryRunEndpointAllowlistEvaluationPacket,
    intent: ExecutionIntent,
) -> None:
    candidate = source.endpoint_candidate
    if reference.adapter_contract_id != source.adapter_contract_id:
        _fail("PLADRCA_REFERENCE_ADAPTER_MISMATCH")
    if reference.endpoint_candidate_id != candidate.endpoint_candidate_id:
        _fail("PLADRCA_REFERENCE_ENDPOINT_MISMATCH")
    if (
        reference.target_system != intent.target_system
        or reference.target_system != candidate.target_system
    ):
        _fail("PLADRCA_REFERENCE_TARGET_SYSTEM_MISMATCH")
    if (
        reference.target_resource_scope != intent.target_resource
        or reference.target_resource_scope != candidate.target_resource_scope
    ):
        _fail("PLADRCA_REFERENCE_TARGET_RESOURCE_MISMATCH")


def _evaluation(
    reference: CredentialReference, snapshot: CredentialPolicySnapshot
) -> dict[str, Any]:
    failures: set[str] = set()
    active_seen = False
    for entry in snapshot.credential_policy_entries:
        if entry.entry_status != "ACTIVE":
            continue
        active_seen = True
        comparisons = {
            "credential_kind": reference.credential_kind == entry.credential_kind,
            "credential_provider_type": (
                reference.credential_provider_type
                == entry.credential_provider_type
            ),
            "credential_scope": reference.credential_scope == entry.credential_scope,
            "credential_environment": (
                reference.credential_environment == entry.credential_environment
            ),
            "adapter_contract_id": (
                reference.adapter_contract_id
                in entry.allowed_adapter_contract_ids
            ),
            "endpoint_candidate_id": (
                reference.endpoint_candidate_id
                in entry.allowed_endpoint_candidate_ids
            ),
            "target_system": reference.target_system in entry.allowed_target_systems,
            "target_resource_scope": (
                reference.target_resource_scope
                in entry.allowed_target_resource_scopes
            ),
            "credential_purpose": (
                reference.credential_purpose in entry.allowed_purposes
            ),
        }
        if all(comparisons.values()):
            return {
                "authorized": True,
                "matched_policy_entry_id": entry.entry_id,
                "authorization_reason": "active_entry_exact_match",
                "rejection_reasons": [],
                "comparison_mode": (
                    "exact_local_credential_policy_comparison_only"
                ),
                "exact_fields_compared": list(EXACT_FIELDS),
                "semantic_match_used": False,
                "credential_material_accessed": False,
            }
        failures.update(name for name, passed in comparisons.items() if not passed)
    reasons = (
        ["no_active_credential_policy_entry"]
        if not active_seen
        else [f"{name}_mismatch" for name in EXACT_FIELDS if name in failures]
    )
    return {
        "authorized": False,
        "matched_policy_entry_id": None,
        "authorization_reason": "no_active_exact_match",
        "rejection_reasons": reasons,
        "comparison_mode": "exact_local_credential_policy_comparison_only",
        "exact_fields_compared": list(EXACT_FIELDS),
        "semantic_match_used": False,
        "credential_material_accessed": False,
    }


def _scope_binding(
    source: CanonicalPromotionLiveAdapterDryRunEndpointAllowlistEvaluationPacket,
    reference: CredentialReference,
    reference_digest: str,
    snapshot: CredentialPolicySnapshot,
    result: dict[str, Any],
    result_digest: str,
) -> dict[str, Any]:
    return {
        "source_endpoint_allowlist_evaluation_id": (
            source.promotion_live_adapter_dry_run_endpoint_allowlist_evaluation_id
        ),
        "source_endpoint_allowlist_evaluation_hash": (
            source.promotion_live_adapter_dry_run_endpoint_allowlist_evaluation_hash
        ),
        "source_dispatch_readiness_id": source.source_dispatch_readiness_id,
        "source_dispatch_readiness_hash": source.source_dispatch_readiness_hash,
        "source_live_adapter_dry_run_request_id": (
            source.source_live_adapter_dry_run_request_id
        ),
        "source_live_adapter_dry_run_request_hash": (
            source.source_live_adapter_dry_run_request_hash
        ),
        "execution_intent_id": source.execution_intent_id,
        "execution_intent_hash": source.execution_intent_hash,
        "adapter_contract_id": source.adapter_contract_id,
        "adapter_contract_hash": source.adapter_contract_hash,
        "endpoint_candidate_id": source.endpoint_candidate.endpoint_candidate_id,
        "endpoint_candidate_digest": source.endpoint_candidate_digest,
        "endpoint_identity_binding_digest": source.endpoint_identity_binding_digest,
        "credential_reference_id": reference.credential_reference_id,
        "credential_reference_digest": reference_digest,
        "credential_kind": reference.credential_kind,
        "credential_provider_type": reference.credential_provider_type,
        "credential_scope": reference.credential_scope,
        "credential_environment": reference.credential_environment,
        "credential_purpose": reference.credential_purpose,
        "target_system": reference.target_system,
        "target_resource_scope": reference.target_resource_scope,
        "credential_policy_snapshot_id": snapshot.credential_policy_snapshot_id,
        "credential_policy_snapshot_hash": snapshot.credential_policy_snapshot_hash,
        "matched_credential_policy_entry_id": result["matched_policy_entry_id"],
        "credential_authorization_result_digest": result_digest,
    }


def _checks(source_hash: str, authorized: bool) -> list[dict[str, Any]]:
    conditional = {
        "active_policy_entry_required",
        "all_exact_credential_dimensions_compared",
    }
    return [
        {
            "check_id": f"pladrca-check:v1:{ordinal}:{name.replace('_', '-')}",
            "ordinal": ordinal,
            "name": name,
            "mode": CHECK_MODE,
            "passed": authorized if name in conditional else True,
            "evidence_ref": f"source_endpoint_allowlist_hash:{source_hash}:{name}",
            "credential_material_accessed": False,
            "network_used": False,
            "request_dispatched": False,
            "bind_invoked": False,
            "trustlog_written": False,
        }
        for ordinal, name in enumerate(CHECK_NAMES, 1)
    ]


def _requirements() -> list[dict[str, Any]]:
    return [
        {
            "ordinal": ordinal,
            "name": name,
            "separate_future_artifact_required": True,
            "satisfied_by_this_packet": False,
        }
        for ordinal, name in enumerate(FUTURE_REQUIREMENT_NAMES, 1)
    ]


def build_canonical_promotion_live_adapter_dry_run_credential_authorization_evaluation_packet(
    source_endpoint_allowlist_evaluation_packet: Any,
    credential_reference: Any,
    credential_policy_snapshot: Any,
    credential_authorization_evaluated_at: datetime,
) -> CanonicalPromotionLiveAdapterDryRunCredentialAuthorizationEvaluationPacket:
    """Build metadata-only credential authorization from authoritative endpoint evidence."""
    evaluated = _aware(
        credential_authorization_evaluated_at, "PLADRCA_EVALUATED_AT_INVALID"
    )
    source = _source(_json_value(source_endpoint_allowlist_evaluation_packet))
    intent = _validate_intent_adapter(source)
    reference = _reference(credential_reference)
    snapshot = _snapshot(credential_policy_snapshot)
    _bind_reference(reference, source, intent)
    if (
        _aware(reference.declared_at, "PLADRCA_DECLARED_AT_INVALID") > evaluated
        or _aware(
            snapshot.credential_policy_generated_at,
            "PLADRCA_POLICY_GENERATED_AT_INVALID",
        )
        > evaluated
        or evaluated
        < _aware(
            source.endpoint_allowlist_evaluated_at,
            "PLADRCA_SOURCE_TIME_INVALID",
        )
    ):
        _fail("PLADRCA_TIMESTAMP_ORDER_INVALID")
    source_raw = source.model_dump(mode="json")
    reference_raw = reference.model_dump(mode="json")
    reference_digest = _digest(REFERENCE_DOMAIN, reference_raw)
    result = _evaluation(reference, snapshot)
    result_digest = _digest(RESULT_DOMAIN, result)
    binding = _scope_binding(
        source, reference, reference_digest, snapshot, result, result_digest
    )
    checks = _checks(
        source.promotion_live_adapter_dry_run_endpoint_allowlist_evaluation_hash,
        result["authorized"],
    )
    requirements = _requirements()
    copied = {
        field: source_raw[field]
        for field in (
            "source_dispatch_readiness_id",
            "source_dispatch_readiness_hash",
            "source_live_adapter_dry_run_request_id",
            "source_live_adapter_dry_run_request_hash",
            "request_descriptor",
            "execution_intent",
            "execution_intent_id",
            "execution_intent_hash",
            "adapter_contract_descriptor",
            "adapter_contract_id",
            "adapter_contract_hash",
            "adapter_contract_version",
            *LINEAGE_FIELDS,
            "endpoint_candidate",
            "endpoint_candidate_digest",
            "allowlist_snapshot",
            "allowlist_snapshot_hash",
            "allowlist_evaluation_result",
            "allowlist_evaluation_digest",
            "endpoint_identity_binding",
            "endpoint_identity_binding_digest",
        )
    }
    raw = {
        "format_version": FORMAT_VERSION,
        "credential_authorization_evaluation_mechanism": EVALUATION_MECHANISM,
        "credential_authorization_evaluated_at": evaluated.isoformat(),
        "source_endpoint_allowlist_evaluation_id": (
            source.promotion_live_adapter_dry_run_endpoint_allowlist_evaluation_id
        ),
        "source_endpoint_allowlist_evaluation_hash": (
            source.promotion_live_adapter_dry_run_endpoint_allowlist_evaluation_hash
        ),
        "source_endpoint_allowlist_evaluation_packet": source_raw,
        **copied,
        "credential_reference": reference_raw,
        "credential_reference_digest": reference_digest,
        "credential_policy_snapshot": snapshot.model_dump(mode="json"),
        "credential_policy_snapshot_hash": snapshot.credential_policy_snapshot_hash,
        "credential_authorization_result": result,
        "credential_authorization_result_digest": result_digest,
        "credential_scope_binding": binding,
        "credential_scope_binding_digest": _digest(SCOPE_BINDING_DOMAIN, binding),
        "credential_authorization_checks": checks,
        "credential_authorization_check_digest": _digest(CHECKS_DOMAIN, checks),
        "future_requirements": requirements,
        "future_requirement_digest": _digest(
            FUTURE_REQUIREMENTS_DOMAIN, requirements
        ),
        "credential_authorization_status": STATUS,
        "request_dispatch_state": "NOT_DISPATCHED",
        "ready_for_promotion_native_operator_dispatch_review": result["authorized"],
        "fail_closed": not result["authorized"],
        "execution_authorized": False,
        "human_approval_proven": False,
        "authority_evidence_proven": False,
        "ready_for_real_bind": False,
        "ready_for_network_dispatch": False,
        **{field: False for field in EFFECT_FIELDS},
    }
    digest = _packet_hash(raw)
    raw[
        "promotion_live_adapter_dry_run_credential_authorization_evaluation_hash"
    ] = digest
    raw[
        "promotion_live_adapter_dry_run_credential_authorization_evaluation_id"
    ] = f"pladrca:v1:sha256:{digest}"
    return verify_canonical_promotion_live_adapter_dry_run_credential_authorization_evaluation_packet(
        raw
    )


def verify_canonical_promotion_live_adapter_dry_run_credential_authorization_evaluation_packet(
    packet: Any,
) -> CanonicalPromotionLiveAdapterDryRunCredentialAuthorizationEvaluationPacket:
    """Independently reconstruct every source binding, comparison, and digest."""
    try:
        value = (
            packet.model_dump(mode="json")
            if isinstance(packet, BaseModel)
            else _json_value(packet)
        )
        candidate = (
            CanonicalPromotionLiveAdapterDryRunCredentialAuthorizationEvaluationPacket.model_validate(
                value
            )
        )
    except (
        ValidationError,
        TypeError,
        CanonicalPromotionLiveAdapterDryRunCredentialAuthorizationError,
    ) as exc:
        raise CanonicalPromotionLiveAdapterDryRunCredentialAuthorizationError(
            "PLADRCA_PACKET_INVALID"
        ) from exc
    raw = candidate.model_dump(mode="json")
    source = _source(candidate.source_endpoint_allowlist_evaluation_packet)
    intent = _validate_intent_adapter(source)
    source_raw = source.model_dump(mode="json")
    if (
        candidate.source_endpoint_allowlist_evaluation_id
        != source.promotion_live_adapter_dry_run_endpoint_allowlist_evaluation_id
        or candidate.source_endpoint_allowlist_evaluation_hash
        != source.promotion_live_adapter_dry_run_endpoint_allowlist_evaluation_hash
    ):
        _fail("PLADRCA_SOURCE_SUMMARY_MISMATCH")
    copied = (
        "source_dispatch_readiness_id",
        "source_dispatch_readiness_hash",
        "source_live_adapter_dry_run_request_id",
        "source_live_adapter_dry_run_request_hash",
        "request_descriptor",
        "execution_intent",
        "execution_intent_id",
        "execution_intent_hash",
        "adapter_contract_descriptor",
        "adapter_contract_id",
        "adapter_contract_hash",
        "adapter_contract_version",
        *LINEAGE_FIELDS,
        "endpoint_candidate",
        "endpoint_candidate_digest",
        "allowlist_snapshot",
        "allowlist_snapshot_hash",
        "allowlist_evaluation_result",
        "allowlist_evaluation_digest",
        "endpoint_identity_binding",
        "endpoint_identity_binding_digest",
    )
    for field in copied:
        if _json_value(getattr(candidate, field)) != _json_value(source_raw[field]):
            _fail("PLADRCA_SOURCE_FIELD_MISMATCH")
    reference = _reference(candidate.credential_reference)
    _bind_reference(reference, source, intent)
    reference_raw = reference.model_dump(mode="json")
    reference_digest = _digest(REFERENCE_DOMAIN, reference_raw)
    if candidate.credential_reference_digest != reference_digest:
        _fail("PLADRCA_REFERENCE_DIGEST_MISMATCH")
    snapshot = _snapshot(candidate.credential_policy_snapshot)
    if candidate.credential_policy_snapshot_hash != snapshot.credential_policy_snapshot_hash:
        _fail("PLADRCA_POLICY_HASH_MISMATCH")
    result = _evaluation(reference, snapshot)
    result_digest = _digest(RESULT_DOMAIN, result)
    if (
        _json_value(candidate.credential_authorization_result) != result
        or candidate.credential_authorization_result_digest != result_digest
    ):
        _fail("PLADRCA_RESULT_MISMATCH")
    binding = _scope_binding(
        source, reference, reference_digest, snapshot, result, result_digest
    )
    if (
        candidate.credential_scope_binding != binding
        or candidate.credential_scope_binding_digest
        != _digest(SCOPE_BINDING_DOMAIN, binding)
    ):
        _fail("PLADRCA_SCOPE_BINDING_MISMATCH")
    checks = _checks(
        source.promotion_live_adapter_dry_run_endpoint_allowlist_evaluation_hash,
        result["authorized"],
    )
    if (
        _json_value(candidate.credential_authorization_checks) != checks
        or candidate.credential_authorization_check_digest
        != _digest(CHECKS_DOMAIN, checks)
    ):
        _fail("PLADRCA_CHECKS_MISMATCH")
    requirements = _requirements()
    if (
        _json_value(candidate.future_requirements) != requirements
        or candidate.future_requirement_digest
        != _digest(FUTURE_REQUIREMENTS_DOMAIN, requirements)
    ):
        _fail("PLADRCA_REQUIREMENTS_MISMATCH")
    authorized = result["authorized"]
    if (
        candidate.fail_closed is authorized
        or candidate.ready_for_promotion_native_operator_dispatch_review
        is not authorized
    ):
        _fail("PLADRCA_OUTCOME_STATE_MISMATCH")
    evaluated = _aware(
        candidate.credential_authorization_evaluated_at,
        "PLADRCA_EVALUATED_AT_INVALID",
    )
    if (
        _aware(reference.declared_at, "PLADRCA_DECLARED_AT_INVALID") > evaluated
        or _aware(
            snapshot.credential_policy_generated_at,
            "PLADRCA_POLICY_GENERATED_AT_INVALID",
        )
        > evaluated
        or evaluated
        < _aware(
            source.endpoint_allowlist_evaluated_at,
            "PLADRCA_SOURCE_TIME_INVALID",
        )
    ):
        _fail("PLADRCA_TIMESTAMP_ORDER_INVALID")
    if any(getattr(candidate, field) for field in EFFECT_FIELDS):
        _fail("PLADRCA_EFFECT_STATE_INVALID")
    digest = _packet_hash(raw)
    if (
        candidate.promotion_live_adapter_dry_run_credential_authorization_evaluation_hash
        != digest
        or candidate.promotion_live_adapter_dry_run_credential_authorization_evaluation_id
        != f"pladrca:v1:sha256:{digest}"
    ):
        _fail("PLADRCA_PACKET_IDENTITY_MISMATCH")
    return candidate
