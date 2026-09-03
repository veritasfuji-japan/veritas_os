"""Derive one exact promotion-native Bind context without granting authority.

This deterministic, content-addressed boundary consumes only the exact Bind
context hash derivation lifecycle requirement.  It derives the context solely
from an independently verified Fresh Verified Source Gate packet and performs
no endpoint, credential, approval, authority, dispatch, or external effect.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

from veritas_os.policy.canonical_promotion_live_adapter_dry_run_fresh_verified_source_gate import (
    AUTHORIZATION_REQUIREMENTS as SOURCE_AUTHORIZATION_REQUIREMENTS,
    EFFECT_FIELDS,
    INVOCATION_REQUIREMENTS,
    PRESERVED_FIELDS as UPSTREAM_PRESERVED_FIELDS,
    STATE as SOURCE_STATE,
    STATUS as SOURCE_STATUS,
    CanonicalPromotionLiveAdapterDryRunFreshVerifiedSourceGateError,
    CanonicalPromotionLiveAdapterDryRunFreshVerifiedSourceGatePacket,
    verify_canonical_promotion_live_adapter_dry_run_fresh_verified_source_gate_packet,
)

FORMAT_VERSION = (
    "canonical-promotion-live-adapter-dry-run-bind-context-hash-derivation/v1"
)
BIND_CONTEXT_VERSION = "promotion-native-exact-bind-context/v1"
MECHANISM = "exact_content_addressed_promotion_native_bind_context_derivation_only/v1"
STATUS = "PROMOTION_NATIVE_EXACT_BIND_CONTEXT_HASH_DERIVED_NOT_AUTHORIZED"
STATE = "DERIVED_FOR_FUTURE_FINAL_ENDPOINT_IDENTITY_RECHECK"
CHECK_MODE = "deterministic_local_exact_bind_context_hash_derivation_only"
PREFIX = "veritas.promotion-live-adapter-dry-run-bind-context-hash-derivation"
HASH_PATTERN = r"^[0-9a-f]{64}$"
DOMAINS = {
    name: f"{PREFIX}.{name}/v1"
    for name in (
        "bind-context",
        "result",
        "context",
        "checks",
        "authorization",
        "invocation",
        "packet",
    )
}
AUTHORIZATION_REQUIREMENTS = SOURCE_AUTHORIZATION_REQUIREMENTS[1:]
CHECK_NAMES = (
    "source_fresh_verified_source_gate_verified",
    "source_gate_identity_bound",
    "exact_execution_intent_bound",
    "exact_adapter_contract_bound",
    "exact_endpoint_identity_bound",
    "exact_credential_reference_bound",
    "exact_credential_scope_bound",
    "exact_operator_review_bound",
    "exact_bind_pre_dispatch_bound",
    "exact_policy_lineage_bound",
    "exact_approval_context_bound",
    "exact_authority_reference_lineage_bound",
    "exact_human_approval_reference_lineage_bound",
    "exact_promotion_lineage_bound",
    "future_authorization_requirements_preserved",
    "future_invocation_requirements_preserved",
    "execution_authority_absent",
    "bind_authorization_absent",
    "network_access_absent",
    "external_effect_absent",
)
FRESH_SOURCE_EVIDENCE_FIELDS = (
    "fresh_verified_at",
    "source_bind_authorization_gate_review_id",
    "source_bind_authorization_gate_review_hash",
    "fresh_verification_result",
    "fresh_verification_result_digest",
    "fresh_verified_source_gate_context",
    "fresh_verified_source_gate_context_digest",
    "fresh_verification_checks",
    "fresh_verification_check_digest",
    "fresh_verified_source_gate_status",
    "fresh_verified_source_gate_state",
)
PRESERVED_FIELDS = tuple(
    dict.fromkeys((*UPSTREAM_PRESERVED_FIELDS, *FRESH_SOURCE_EVIDENCE_FIELDS))
)


class CanonicalPromotionLiveAdapterDryRunBindContextHashDerivationError(ValueError):
    """Stable fail-closed error for invalid Bind context derivation evidence."""


class ExactBindContext(BaseModel):
    """Closed semantic context committed by the canonical Bind context hash."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    context_version: Literal[BIND_CONTEXT_VERSION]
    source_fresh_verified_source_gate_id: str = Field(min_length=1)
    source_fresh_verified_source_gate_hash: str = Field(pattern=HASH_PATTERN)
    source_bind_authorization_gate_review_id: str = Field(min_length=1)
    source_bind_authorization_gate_review_hash: str = Field(pattern=HASH_PATTERN)
    source_final_bind_authorization_readiness_id: str = Field(min_length=1)
    source_final_bind_authorization_readiness_hash: str = Field(pattern=HASH_PATTERN)
    source_human_approval_linkage_review_id: str = Field(min_length=1)
    source_human_approval_linkage_review_hash: str = Field(pattern=HASH_PATTERN)
    fresh_verified_at: str
    fresh_verification_result_digest: str = Field(pattern=HASH_PATTERN)
    fresh_verified_source_gate_context_digest: str = Field(pattern=HASH_PATTERN)
    fresh_verification_check_digest: str = Field(pattern=HASH_PATTERN)
    execution_intent_id: str = Field(min_length=1)
    execution_intent_hash: str = Field(pattern=HASH_PATTERN)
    adapter_contract_id: str = Field(min_length=1)
    adapter_contract_hash: str = Field(pattern=HASH_PATTERN)
    adapter_contract_version: str = Field(min_length=1)
    endpoint_candidate_digest: str = Field(pattern=HASH_PATTERN)
    endpoint_identity_binding_digest: str = Field(pattern=HASH_PATTERN)
    credential_reference_digest: str = Field(pattern=HASH_PATTERN)
    credential_policy_snapshot_hash: str = Field(pattern=HASH_PATTERN)
    credential_authorization_result_digest: str = Field(pattern=HASH_PATTERN)
    credential_scope_binding_digest: str = Field(pattern=HASH_PATTERN)
    operator_review_decision_digest: str = Field(pattern=HASH_PATTERN)
    operator_review_binding_digest: str = Field(pattern=HASH_PATTERN)
    bind_pre_dispatch_review_decision_digest: str = Field(pattern=HASH_PATTERN)
    bind_pre_dispatch_review_result_digest: str = Field(pattern=HASH_PATTERN)
    bind_boundary_precondition_digest: str = Field(pattern=HASH_PATTERN)
    authority_evidence_reference_bundle_digest: str = Field(pattern=HASH_PATTERN)
    authority_evidence_binding_matrix_digest: str = Field(pattern=HASH_PATTERN)
    authority_evidence_linkage_result_digest: str = Field(pattern=HASH_PATTERN)
    authority_evidence_linkage_context_digest: str = Field(pattern=HASH_PATTERN)
    human_approval_reference_bundle_digest: str = Field(pattern=HASH_PATTERN)
    human_approval_binding_matrix_digest: str = Field(pattern=HASH_PATTERN)
    human_approval_linkage_result_digest: str = Field(pattern=HASH_PATTERN)
    human_approval_linkage_context_digest: str = Field(pattern=HASH_PATTERN)
    final_bind_authorization_readiness_review_decision_digest: str = Field(
        pattern=HASH_PATTERN
    )
    final_bind_authorization_readiness_result_digest: str = Field(pattern=HASH_PATTERN)
    final_readiness_context_digest: str = Field(pattern=HASH_PATTERN)
    final_bind_authorization_readiness_check_digest: str = Field(pattern=HASH_PATTERN)
    bind_authorization_gate_review_decision_digest: str = Field(pattern=HASH_PATTERN)
    bind_authorization_gate_review_result_digest: str = Field(pattern=HASH_PATTERN)
    bind_authorization_gate_review_context_digest: str = Field(pattern=HASH_PATTERN)
    bind_authorization_gate_review_check_digest: str = Field(pattern=HASH_PATTERN)
    source_promotion_id: str = Field(min_length=1)
    source_promotion_hash: str = Field(pattern=HASH_PATTERN)
    source_decision_identity: dict[str, Any]
    candidate_identity: dict[str, Any]
    selected_action_lineage: dict[str, Any]
    policy_snapshot_lineage: dict[str, Any]
    approval_context: dict[str, Any]
    policy_lineage: dict[str, Any]


class BindContextHashDerivationResult(BaseModel):
    """Truthful derivation result that carries no authorization semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    source_fresh_verified_source_gate_verified: Literal[True]
    source_gate_identity_bound: Literal[True]
    exact_execution_intent_bound: Literal[True]
    exact_adapter_contract_bound: Literal[True]
    exact_endpoint_identity_bound: Literal[True]
    exact_credential_reference_bound: Literal[True]
    exact_credential_scope_bound: Literal[True]
    exact_operator_review_bound: Literal[True]
    exact_bind_pre_dispatch_bound: Literal[True]
    exact_policy_lineage_bound: Literal[True]
    exact_approval_context_bound: Literal[True]
    exact_authority_reference_lineage_bound: Literal[True]
    exact_human_approval_reference_lineage_bound: Literal[True]
    exact_promotion_lineage_bound: Literal[True]
    future_authorization_requirements_preserved: Literal[True]
    future_invocation_requirements_preserved: Literal[True]
    execution_authority_absent: Literal[True]
    bind_authorization_absent: Literal[True]
    network_access_absent: Literal[True]
    external_effect_absent: Literal[True]
    bind_context_hash: str = Field(pattern=HASH_PATTERN)
    derivation_mode: Literal[CHECK_MODE]
    external_policy_freshness_verified: Literal[False]
    endpoint_rechecked: Literal[False]
    credential_scope_rechecked: Literal[False]
    revocation_verified: Literal[False]


class BindContextHashDerivationCheck(BaseModel):
    """An ordered, local derivation check that cannot perform an effect."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    ordinal: int = Field(ge=1)
    name: Literal[*CHECK_NAMES]
    passed: Literal[True]
    comparison_mode: Literal[CHECK_MODE]


class FutureRequirement(BaseModel):
    """A remaining requirement not satisfied by this derivation packet."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    ordinal: int = Field(ge=1)
    name: Literal[*AUTHORIZATION_REQUIREMENTS, *INVOCATION_REQUIREMENTS]
    separate_future_artifact_required: Literal[True]
    satisfied_by_this_packet: Literal[False]


class _PacketBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    format_version: Literal[FORMAT_VERSION]
    promotion_live_adapter_dry_run_bind_context_hash_derivation_id: str = Field(
        min_length=1
    )
    promotion_live_adapter_dry_run_bind_context_hash_derivation_hash: str = Field(
        pattern=HASH_PATTERN
    )
    bind_context_hash_derivation_mechanism: Literal[MECHANISM]
    bind_context_derived_at: str
    source_fresh_verified_source_gate_id: str = Field(min_length=1)
    source_fresh_verified_source_gate_hash: str = Field(pattern=HASH_PATTERN)
    source_fresh_verified_source_gate_packet: dict[str, Any]
    exact_bind_context: ExactBindContext
    bind_context_hash: str = Field(pattern=HASH_PATTERN)
    bind_context_hash_derivation_result: BindContextHashDerivationResult
    bind_context_hash_derivation_result_digest: str = Field(pattern=HASH_PATTERN)
    bind_context_hash_derivation_context: dict[str, Any]
    bind_context_hash_derivation_context_digest: str = Field(pattern=HASH_PATTERN)
    bind_context_hash_derivation_checks: tuple[BindContextHashDerivationCheck, ...]
    bind_context_hash_derivation_check_digest: str = Field(pattern=HASH_PATTERN)
    future_bind_authorization_requirements: tuple[FutureRequirement, ...]
    future_bind_authorization_requirement_digest: str = Field(pattern=HASH_PATTERN)
    future_bind_invocation_requirements: tuple[FutureRequirement, ...]
    future_bind_invocation_requirement_digest: str = Field(pattern=HASH_PATTERN)
    bind_context_hash_derivation_status: Literal[STATUS]
    bind_context_hash_derivation_state: Literal[STATE]
    ready_for_promotion_native_final_endpoint_identity_recheck: Literal[True]
    fresh_verified_source_gate_still_required: Literal[False]
    bind_context_hash_derivation_still_required: Literal[False]
    bind_context_hash_derived: Literal[True]
    final_endpoint_identity_recheck_still_required: Literal[True]
    request_dispatch_state: Literal["NOT_DISPATCHED"]
    bind_state: Literal["NOT_BOUND"]
    authority_state: Literal["NOT_AUTHORIZED"]
    human_approval_state: Literal["NOT_APPROVED"]
    bind_authorization_state: Literal["NOT_AUTHORIZED"]
    fail_closed: Literal[False]
    human_approval_created: Literal[False]
    human_approval_externally_verified: Literal[False]
    human_approval_proven: Literal[False]
    authority_evidence_created: Literal[False]
    authority_evidence_externally_verified: Literal[False]
    authority_evidence_proven: Literal[False]
    execution_authority_created: Literal[False]
    execution_authorized: Literal[False]
    bind_authorization_created: Literal[False]
    bind_authorization_issued: Literal[False]
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
    ready_for_real_bind: Literal[False]
    ready_for_network_dispatch: Literal[False]


CanonicalPromotionLiveAdapterDryRunBindContextHashDerivationPacket = create_model(
    "CanonicalPromotionLiveAdapterDryRunBindContextHashDerivationPacket",
    __base__=_PacketBase,
    **{
        name: (
            CanonicalPromotionLiveAdapterDryRunFreshVerifiedSourceGatePacket.model_fields[
                name
            ].annotation,
            ...,
        )
        for name in PRESERVED_FIELDS
    },
)


def _fail(code: str) -> None:
    raise CanonicalPromotionLiveAdapterDryRunBindContextHashDerivationError(code)


def _timestamp(value: Any) -> str:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunBindContextHashDerivationError(
            "CPLADBCHD_TIMESTAMP_INVALID"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail("CPLADBCHD_TIMESTAMP_INVALID")
    return parsed.astimezone(timezone.utc).isoformat()


def _json(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            _fail("CPLADBCHD_JSON_INVALID")
        return value
    if isinstance(value, datetime):
        return _timestamp(value)
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _json(item) for key, item in value.items()}
    _fail("CPLADBCHD_JSON_INVALID")


def _digest(domain: str, value: Any) -> str:
    encoded = json.dumps(
        {"domain": domain, "value": _json(value)},
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _source(
    value: Any,
) -> CanonicalPromotionLiveAdapterDryRunFreshVerifiedSourceGatePacket:
    try:
        return verify_canonical_promotion_live_adapter_dry_run_fresh_verified_source_gate_packet(
            value
        )
    except (
        CanonicalPromotionLiveAdapterDryRunFreshVerifiedSourceGateError,
        TypeError,
        ValueError,
    ) as exc:
        raise CanonicalPromotionLiveAdapterDryRunBindContextHashDerivationError(
            "CPLADBCHD_SOURCE_INVALID"
        ) from exc


def _requirements(names: tuple[str, ...]) -> list[dict[str, Any]]:
    return [
        {
            "ordinal": ordinal,
            "name": name,
            "separate_future_artifact_required": True,
            "satisfied_by_this_packet": False,
        }
        for ordinal, name in enumerate(names, 1)
    ]


def _validate_source(source: Any) -> None:
    freshness = source.fresh_verification_result
    required = (
        source.fresh_verified_source_gate_status == SOURCE_STATUS,
        source.fresh_verified_source_gate_state == SOURCE_STATE,
        source.ready_for_promotion_native_bind_context_derivation,
        not source.fail_closed,
        not source.fresh_verified_source_gate_still_required,
        source.bind_context_hash_derivation_still_required,
        not source.bind_context_hash_derived,
        source.bind_authorization_state == "NOT_AUTHORIZED",
        source.request_dispatch_state == "NOT_DISPATCHED",
        source.bind_state == "NOT_BOUND",
        source.authority_state == "NOT_AUTHORIZED",
        source.human_approval_state == "NOT_APPROVED",
        not freshness.external_policy_freshness_verified,
        not freshness.endpoint_rechecked,
        not freshness.credential_scope_rechecked,
        not freshness.revocation_verified,
    )
    if not all(required) or any(getattr(source, name) for name in EFFECT_FIELDS):
        _fail("CPLADBCHD_SOURCE_STATE_INVALID")
    authorization = tuple(
        item.name for item in source.future_bind_authorization_requirements
    )
    invocation = tuple(item.name for item in source.future_bind_invocation_requirements)
    if authorization != SOURCE_AUTHORIZATION_REQUIREMENTS:
        _fail("CPLADBCHD_SOURCE_AUTHORIZATION_REQUIREMENTS_INVALID")
    if invocation != INVOCATION_REQUIREMENTS:
        _fail("CPLADBCHD_SOURCE_INVOCATION_REQUIREMENTS_INVALID")


def _exact_bind_context(source: Any) -> dict[str, Any]:
    return {
        "context_version": BIND_CONTEXT_VERSION,
        "source_fresh_verified_source_gate_id": (
            source.promotion_live_adapter_dry_run_fresh_verified_source_gate_id
        ),
        "source_fresh_verified_source_gate_hash": (
            source.promotion_live_adapter_dry_run_fresh_verified_source_gate_hash
        ),
        "source_bind_authorization_gate_review_id": (
            source.source_bind_authorization_gate_review_id
        ),
        "source_bind_authorization_gate_review_hash": (
            source.source_bind_authorization_gate_review_hash
        ),
        "source_final_bind_authorization_readiness_id": (
            source.source_final_bind_authorization_readiness_id
        ),
        "source_final_bind_authorization_readiness_hash": (
            source.source_final_bind_authorization_readiness_hash
        ),
        "source_human_approval_linkage_review_id": (
            source.source_human_approval_linkage_review_id
        ),
        "source_human_approval_linkage_review_hash": (
            source.source_human_approval_linkage_review_hash
        ),
        "fresh_verified_at": source.fresh_verified_at,
        "fresh_verification_result_digest": (source.fresh_verification_result_digest),
        "fresh_verified_source_gate_context_digest": (
            source.fresh_verified_source_gate_context_digest
        ),
        "fresh_verification_check_digest": source.fresh_verification_check_digest,
        "execution_intent_id": source.execution_intent_id,
        "execution_intent_hash": source.execution_intent_hash,
        "adapter_contract_id": source.adapter_contract_id,
        "adapter_contract_hash": source.adapter_contract_hash,
        "adapter_contract_version": source.adapter_contract_version,
        "endpoint_candidate_digest": source.endpoint_candidate_digest,
        "endpoint_identity_binding_digest": (source.endpoint_identity_binding_digest),
        "credential_reference_digest": source.credential_reference_digest,
        "credential_policy_snapshot_hash": source.credential_policy_snapshot_hash,
        "credential_authorization_result_digest": (
            source.credential_authorization_result_digest
        ),
        "credential_scope_binding_digest": source.credential_scope_binding_digest,
        "operator_review_decision_digest": source.operator_review_decision_digest,
        "operator_review_binding_digest": source.operator_review_binding_digest,
        "bind_pre_dispatch_review_decision_digest": (
            source.bind_pre_dispatch_review_decision_digest
        ),
        "bind_pre_dispatch_review_result_digest": (
            source.bind_pre_dispatch_review_result_digest
        ),
        "bind_boundary_precondition_digest": (source.bind_boundary_precondition_digest),
        "authority_evidence_reference_bundle_digest": (
            source.authority_evidence_reference_bundle_digest
        ),
        "authority_evidence_binding_matrix_digest": (
            source.authority_evidence_binding_matrix_digest
        ),
        "authority_evidence_linkage_result_digest": (
            source.authority_evidence_linkage_result_digest
        ),
        "authority_evidence_linkage_context_digest": (
            source.authority_evidence_linkage_context_digest
        ),
        "human_approval_reference_bundle_digest": (
            source.human_approval_reference_bundle_digest
        ),
        "human_approval_binding_matrix_digest": (
            source.human_approval_binding_matrix_digest
        ),
        "human_approval_linkage_result_digest": (
            source.human_approval_linkage_result_digest
        ),
        "human_approval_linkage_context_digest": (
            source.human_approval_linkage_context_digest
        ),
        "final_bind_authorization_readiness_review_decision_digest": (
            source.final_bind_authorization_readiness_review_decision_digest
        ),
        "final_bind_authorization_readiness_result_digest": (
            source.final_bind_authorization_readiness_result_digest
        ),
        "final_readiness_context_digest": source.final_readiness_context_digest,
        "final_bind_authorization_readiness_check_digest": (
            source.final_bind_authorization_readiness_check_digest
        ),
        "bind_authorization_gate_review_decision_digest": (
            source.bind_authorization_gate_review_decision_digest
        ),
        "bind_authorization_gate_review_result_digest": (
            source.bind_authorization_gate_review_result_digest
        ),
        "bind_authorization_gate_review_context_digest": (
            source.bind_authorization_gate_review_context_digest
        ),
        "bind_authorization_gate_review_check_digest": (
            source.bind_authorization_gate_review_check_digest
        ),
        "source_promotion_id": source.source_promotion_id,
        "source_promotion_hash": source.source_promotion_hash,
        "source_decision_identity": _json(source.source_decision_identity),
        "candidate_identity": _json(source.candidate_identity),
        "selected_action_lineage": _json(source.selected_action_lineage),
        "policy_snapshot_lineage": _json(source.policy_snapshot_lineage),
        "approval_context": _json(source.approval_context),
        "policy_lineage": _json(source.policy_lineage),
    }


def _assemble(source: Any, derived_at: str) -> dict[str, Any]:
    source_raw = source.model_dump(mode="json")
    bind_context = _exact_bind_context(source)
    bind_context_hash = _digest(DOMAINS["bind-context"], bind_context)
    result = {name: True for name in CHECK_NAMES}
    result.update(
        {
            "bind_context_hash": bind_context_hash,
            "derivation_mode": CHECK_MODE,
            "external_policy_freshness_verified": False,
            "endpoint_rechecked": False,
            "credential_scope_rechecked": False,
            "revocation_verified": False,
        }
    )
    result_digest = _digest(DOMAINS["result"], result)
    context = {
        "source_fresh_verified_source_gate_id": (
            source.promotion_live_adapter_dry_run_fresh_verified_source_gate_id
        ),
        "source_fresh_verified_source_gate_hash": (
            source.promotion_live_adapter_dry_run_fresh_verified_source_gate_hash
        ),
        "source_fresh_verified_source_gate_context_digest": (
            source.fresh_verified_source_gate_context_digest
        ),
        "bind_context_hash": bind_context_hash,
        "bind_context_derived_at": derived_at,
        "bind_context_hash_derivation_result_digest": result_digest,
    }
    checks = [
        {
            "ordinal": ordinal,
            "name": name,
            "passed": True,
            "comparison_mode": CHECK_MODE,
        }
        for ordinal, name in enumerate(CHECK_NAMES, 1)
    ]
    authorization = _requirements(AUTHORIZATION_REQUIREMENTS)
    invocation = _requirements(INVOCATION_REQUIREMENTS)
    raw = {
        "format_version": FORMAT_VERSION,
        "bind_context_hash_derivation_mechanism": MECHANISM,
        "bind_context_derived_at": derived_at,
        "source_fresh_verified_source_gate_id": (
            source.promotion_live_adapter_dry_run_fresh_verified_source_gate_id
        ),
        "source_fresh_verified_source_gate_hash": (
            source.promotion_live_adapter_dry_run_fresh_verified_source_gate_hash
        ),
        "source_fresh_verified_source_gate_packet": source_raw,
        **{name: source_raw[name] for name in PRESERVED_FIELDS},
        "exact_bind_context": bind_context,
        "bind_context_hash": bind_context_hash,
        "bind_context_hash_derivation_result": result,
        "bind_context_hash_derivation_result_digest": result_digest,
        "bind_context_hash_derivation_context": context,
        "bind_context_hash_derivation_context_digest": _digest(
            DOMAINS["context"], context
        ),
        "bind_context_hash_derivation_checks": checks,
        "bind_context_hash_derivation_check_digest": _digest(DOMAINS["checks"], checks),
        "future_bind_authorization_requirements": authorization,
        "future_bind_authorization_requirement_digest": _digest(
            DOMAINS["authorization"], authorization
        ),
        "future_bind_invocation_requirements": invocation,
        "future_bind_invocation_requirement_digest": _digest(
            DOMAINS["invocation"], invocation
        ),
        "bind_context_hash_derivation_status": STATUS,
        "bind_context_hash_derivation_state": STATE,
        "ready_for_promotion_native_final_endpoint_identity_recheck": True,
        "fresh_verified_source_gate_still_required": False,
        "bind_context_hash_derivation_still_required": False,
        "bind_context_hash_derived": True,
        "final_endpoint_identity_recheck_still_required": True,
        "request_dispatch_state": "NOT_DISPATCHED",
        "bind_state": "NOT_BOUND",
        "authority_state": "NOT_AUTHORIZED",
        "human_approval_state": "NOT_APPROVED",
        "bind_authorization_state": "NOT_AUTHORIZED",
        "fail_closed": False,
        **{name: False for name in EFFECT_FIELDS},
    }
    omitted = {
        "promotion_live_adapter_dry_run_bind_context_hash_derivation_id",
        "promotion_live_adapter_dry_run_bind_context_hash_derivation_hash",
    }
    digest = _digest(
        DOMAINS["packet"],
        {key: value for key, value in raw.items() if key not in omitted},
    )
    raw["promotion_live_adapter_dry_run_bind_context_hash_derivation_hash"] = digest
    raw["promotion_live_adapter_dry_run_bind_context_hash_derivation_id"] = (
        f"pladbchd:v1:sha256:{digest}"
    )
    return raw


def build_canonical_promotion_live_adapter_dry_run_bind_context_hash_derivation_packet(
    source_fresh_verified_source_gate_packet: Any,
    bind_context_derived_at: datetime,
) -> CanonicalPromotionLiveAdapterDryRunBindContextHashDerivationPacket:
    """Build an exact source-derived Bind context with no execution authority.

    Args:
        source_fresh_verified_source_gate_packet: Exact verified source packet.
        bind_context_derived_at: Explicit, timezone-aware derivation timestamp.

    Returns:
        A verified, content-addressed Bind context derivation packet.

    Raises:
        CanonicalPromotionLiveAdapterDryRunBindContextHashDerivationError: If
            the source, lifecycle state, timestamp, or reconstruction is invalid.
    """

    source = _source(_json(source_fresh_verified_source_gate_packet))
    _validate_source(source)
    derived_at = _timestamp(bind_context_derived_at)
    if derived_at < _timestamp(source.fresh_verified_at):
        _fail("CPLADBCHD_TIMESTAMP_ORDER_INVALID")
    return verify_canonical_promotion_live_adapter_dry_run_bind_context_hash_derivation_packet(
        _assemble(source, derived_at)
    )


def verify_canonical_promotion_live_adapter_dry_run_bind_context_hash_derivation_packet(
    raw: Any,
) -> CanonicalPromotionLiveAdapterDryRunBindContextHashDerivationPacket:
    """Re-verify the source and reconstruct every derived context field."""

    try:
        value = raw.model_dump(mode="json") if isinstance(raw, BaseModel) else raw
        packet = CanonicalPromotionLiveAdapterDryRunBindContextHashDerivationPacket.model_validate(
            _json(value)
        )
    except (ValidationError, TypeError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunBindContextHashDerivationError(
            "CPLADBCHD_PACKET_INVALID"
        ) from exc
    source = _source(packet.source_fresh_verified_source_gate_packet)
    _validate_source(source)
    derived_at = _timestamp(packet.bind_context_derived_at)
    if derived_at < _timestamp(source.fresh_verified_at):
        _fail("CPLADBCHD_TIMESTAMP_ORDER_INVALID")
    if packet.model_dump(mode="json") != _assemble(source, derived_at):
        _fail("CPLADBCHD_RECONSTRUCTION_MISMATCH")
    return packet
