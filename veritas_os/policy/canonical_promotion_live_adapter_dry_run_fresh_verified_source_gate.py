"""Freshly re-verify a promotion-native Gate Review without granting authority.

This local, content-addressed boundary consumes only the fresh-source lifecycle
requirement.  It does not establish external freshness, derive a Bind context,
create or verify approval/authority proof, or perform an external effect.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

from veritas_os.policy.canonical_promotion_live_adapter_dry_run_bind_authorization_gate_review import (
    AUTHORIZATION_REQUIREMENTS as SOURCE_AUTHORIZATION_REQUIREMENTS,
    COPY_FIELDS as UPSTREAM_PRESERVED_FIELDS,
    EFFECT_FIELDS,
    INVOCATION_REQUIREMENTS,
    OUTCOMES as SOURCE_OUTCOMES,
    CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewError,
    CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewPacket,
    verify_canonical_promotion_live_adapter_dry_run_bind_authorization_gate_review_packet,
)

FORMAT_VERSION = (
    "canonical-promotion-live-adapter-dry-run-fresh-verified-source-gate/v1"
)
MECHANISM = "fresh_independent_promotion_native_source_reverification_only/v1"
STATUS = "PROMOTION_NATIVE_FRESH_VERIFIED_SOURCE_GATE_RECORDED_NOT_AUTHORIZED"
STATE = "VERIFIED_FOR_FUTURE_PROMOTION_NATIVE_BIND_CONTEXT_DERIVATION"
CHECK_MODE = "content_addressed_independent_source_reverification"
PREFIX = "veritas.promotion-live-adapter-dry-run-fresh-verified-source-gate"
DOMAINS = {
    name: f"{PREFIX}.{name}/v1"
    for name in ("result", "context", "checks", "authorization", "invocation", "packet")
}
AUTHORIZATION_REQUIREMENTS = SOURCE_AUTHORIZATION_REQUIREMENTS[1:]
CHECK_NAMES = (
    "source_gate_review_verified",
    "exact_gate_identity_preserved",
    "exact_execution_intent_preserved",
    "exact_adapter_binding_preserved",
    "exact_endpoint_binding_preserved",
    "exact_credential_scope_binding_preserved",
    "exact_operator_binding_preserved",
    "exact_bind_pre_dispatch_binding_preserved",
    "authority_reference_lineage_preserved",
    "human_approval_reference_lineage_preserved",
    "promotion_lineage_preserved",
    "fresh_verification_timestamp_valid",
)
GATE_EVIDENCE_FIELDS = (
    "source_final_bind_authorization_readiness_id",
    "source_final_bind_authorization_readiness_hash",
    "bind_authorization_gate_review_decision",
    "bind_authorization_gate_review_decision_digest",
    "bind_authorization_gate_review_result",
    "bind_authorization_gate_review_result_digest",
    "bind_authorization_gate_review_context",
    "bind_authorization_gate_review_context_digest",
    "bind_authorization_gate_review_checks",
    "bind_authorization_gate_review_check_digest",
)
PRESERVED_FIELDS = tuple(
    dict.fromkeys((*UPSTREAM_PRESERVED_FIELDS, *GATE_EVIDENCE_FIELDS))
)


class CanonicalPromotionLiveAdapterDryRunFreshVerifiedSourceGateError(ValueError):
    """Stable fail-closed error for invalid fresh-source evidence."""


class FreshVerificationResult(BaseModel):
    """Truthful local re-verification result with no authority semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    source_gate_review_verified: Literal[True]
    exact_gate_identity_preserved: Literal[True]
    exact_execution_intent_preserved: Literal[True]
    exact_adapter_binding_preserved: Literal[True]
    exact_endpoint_binding_preserved: Literal[True]
    exact_credential_scope_binding_preserved: Literal[True]
    exact_operator_binding_preserved: Literal[True]
    exact_bind_pre_dispatch_binding_preserved: Literal[True]
    authority_reference_lineage_preserved: Literal[True]
    human_approval_reference_lineage_preserved: Literal[True]
    promotion_lineage_preserved: Literal[True]
    fresh_verification_timestamp_valid: Literal[True]
    fresh_verified_at: str
    comparison_mode: Literal[CHECK_MODE]
    external_policy_freshness_verified: Literal[False]
    endpoint_rechecked: Literal[False]
    credential_scope_rechecked: Literal[False]
    revocation_verified: Literal[False]


class FreshVerificationCheck(BaseModel):
    """An ordered local check that cannot perform an effect."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    ordinal: int = Field(ge=1)
    name: Literal[*CHECK_NAMES]
    passed: Literal[True]
    comparison_mode: Literal[CHECK_MODE]


class FutureRequirement(BaseModel):
    """A remaining requirement not satisfied by this packet."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    ordinal: int = Field(ge=1)
    name: Literal[*AUTHORIZATION_REQUIREMENTS, *INVOCATION_REQUIREMENTS]
    separate_future_artifact_required: Literal[True]
    satisfied_by_this_packet: Literal[False]


class _PacketBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    format_version: Literal[FORMAT_VERSION]
    promotion_live_adapter_dry_run_fresh_verified_source_gate_id: str
    promotion_live_adapter_dry_run_fresh_verified_source_gate_hash: str
    fresh_verified_source_gate_mechanism: Literal[MECHANISM]
    fresh_verified_at: str
    source_bind_authorization_gate_review_id: str
    source_bind_authorization_gate_review_hash: str
    source_bind_authorization_gate_review_packet: dict[str, Any]
    fresh_verification_result: FreshVerificationResult
    fresh_verification_result_digest: str
    fresh_verified_source_gate_context: dict[str, Any]
    fresh_verified_source_gate_context_digest: str
    fresh_verification_checks: tuple[FreshVerificationCheck, ...]
    fresh_verification_check_digest: str
    future_bind_authorization_requirements: tuple[FutureRequirement, ...]
    future_bind_authorization_requirement_digest: str
    future_bind_invocation_requirements: tuple[FutureRequirement, ...]
    future_bind_invocation_requirement_digest: str
    fresh_verified_source_gate_status: Literal[STATUS]
    fresh_verified_source_gate_state: Literal[STATE]
    ready_for_promotion_native_bind_context_derivation: Literal[True]
    fresh_verified_source_gate_still_required: Literal[False]
    bind_context_hash_derivation_still_required: Literal[True]
    bind_context_hash_derived: Literal[False]
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


CanonicalPromotionLiveAdapterDryRunFreshVerifiedSourceGatePacket = create_model(
    "CanonicalPromotionLiveAdapterDryRunFreshVerifiedSourceGatePacket",
    __base__=_PacketBase,
    **{
        name: (
            CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewPacket.model_fields[
                name
            ].annotation,
            ...,
        )
        for name in PRESERVED_FIELDS
    },
)


def _fail(code: str) -> None:
    raise CanonicalPromotionLiveAdapterDryRunFreshVerifiedSourceGateError(code)


def _timestamp(value: Any) -> str:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunFreshVerifiedSourceGateError(
            "CPLADFVS_TIMESTAMP_INVALID"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail("CPLADFVS_TIMESTAMP_INVALID")
    return parsed.astimezone(timezone.utc).isoformat()


def _json(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            _fail("CPLADFVS_JSON_INVALID")
        return value
    if isinstance(value, datetime):
        return _timestamp(value)
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _json(item) for key, item in value.items()}
    _fail("CPLADFVS_JSON_INVALID")


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
) -> CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewPacket:
    try:
        return verify_canonical_promotion_live_adapter_dry_run_bind_authorization_gate_review_packet(
            value
        )
    except (
        CanonicalPromotionLiveAdapterDryRunBindAuthorizationGateReviewError,
        TypeError,
        ValueError,
    ) as exc:
        raise CanonicalPromotionLiveAdapterDryRunFreshVerifiedSourceGateError(
            "CPLADFVS_SOURCE_INVALID"
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
    required = (
        source.gate_review_state == SOURCE_OUTCOMES[0],
        source.ready_for_promotion_native_fresh_verified_source_gate,
        not source.fail_closed,
        source.fresh_verified_source_gate_still_required,
        source.bind_authorization_state == "NOT_AUTHORIZED",
        not source.bind_context_hash_derived,
        source.request_dispatch_state == "NOT_DISPATCHED",
        source.bind_state == "NOT_BOUND",
        source.authority_state == "NOT_AUTHORIZED",
        source.human_approval_state == "NOT_APPROVED",
    )
    if not all(required) or any(getattr(source, name) for name in EFFECT_FIELDS):
        _fail("CPLADFVS_SOURCE_STATE_INVALID")
    authorization = tuple(
        item.name for item in source.future_bind_authorization_requirements
    )
    invocation = tuple(item.name for item in source.future_bind_invocation_requirements)
    if authorization != SOURCE_AUTHORIZATION_REQUIREMENTS:
        _fail("CPLADFVS_SOURCE_AUTHORIZATION_REQUIREMENTS_INVALID")
    if invocation != INVOCATION_REQUIREMENTS:
        _fail("CPLADFVS_SOURCE_INVOCATION_REQUIREMENTS_INVALID")


def _assemble(source: Any, verified_at: str) -> dict[str, Any]:
    source_raw = source.model_dump(mode="json")
    result = {name: True for name in CHECK_NAMES}
    result.update(
        {
            "fresh_verified_at": verified_at,
            "comparison_mode": CHECK_MODE,
            "external_policy_freshness_verified": False,
            "endpoint_rechecked": False,
            "credential_scope_rechecked": False,
            "revocation_verified": False,
        }
    )
    context = {
        "source_gate_review_id": source.promotion_live_adapter_dry_run_bind_authorization_gate_review_id,
        "source_gate_review_hash": source.promotion_live_adapter_dry_run_bind_authorization_gate_review_hash,
        "source_gate_review_context_digest": source.bind_authorization_gate_review_context_digest,
        "source_gate_review_decision_digest": source.bind_authorization_gate_review_decision_digest,
        "source_gate_review_result_digest": source.bind_authorization_gate_review_result_digest,
        "source_gate_review_check_digest": source.bind_authorization_gate_review_check_digest,
        "execution_intent_id": source.execution_intent_id,
        "execution_intent_hash": source.execution_intent_hash,
        "adapter_contract_id": source.adapter_contract_id,
        "adapter_contract_hash": source.adapter_contract_hash,
        "adapter_contract_version": source.adapter_contract_version,
        "endpoint_identity_binding_digest": source.endpoint_identity_binding_digest,
        "credential_reference_digest": source.credential_reference_digest,
        "credential_scope_binding_digest": source.credential_scope_binding_digest,
        "operator_review_binding_digest": source.operator_review_binding_digest,
        "bind_boundary_precondition_digest": source.bind_boundary_precondition_digest,
        "authority_linkage_context_digest": source.authority_evidence_linkage_context_digest,
        "human_approval_linkage_context_digest": source.human_approval_linkage_context_digest,
        "final_readiness_context_digest": source.final_readiness_context_digest,
        "final_readiness_id": source.source_final_bind_authorization_readiness_id,
        "final_readiness_hash": source.source_final_bind_authorization_readiness_hash,
        "source_promotion_id": source.source_promotion_id,
        "source_promotion_hash": source.source_promotion_hash,
        "source_decision_identity": _json(source.source_decision_identity),
        "candidate_identity": _json(source.candidate_identity),
        "policy_lineage": _json(source.policy_lineage),
        "approval_context": _json(source.approval_context),
        "fresh_verified_at": verified_at,
        "fresh_verification_result_digest": _digest(DOMAINS["result"], result),
    }
    checks = [
        {"ordinal": i, "name": name, "passed": True, "comparison_mode": CHECK_MODE}
        for i, name in enumerate(CHECK_NAMES, 1)
    ]
    authorization = _requirements(AUTHORIZATION_REQUIREMENTS)
    invocation = _requirements(INVOCATION_REQUIREMENTS)
    raw = {
        "format_version": FORMAT_VERSION,
        "fresh_verified_source_gate_mechanism": MECHANISM,
        "fresh_verified_at": verified_at,
        "source_bind_authorization_gate_review_id": source.promotion_live_adapter_dry_run_bind_authorization_gate_review_id,
        "source_bind_authorization_gate_review_hash": source.promotion_live_adapter_dry_run_bind_authorization_gate_review_hash,
        "source_bind_authorization_gate_review_packet": source_raw,
        **{name: source_raw[name] for name in PRESERVED_FIELDS},
        "fresh_verification_result": result,
        "fresh_verification_result_digest": context["fresh_verification_result_digest"],
        "fresh_verified_source_gate_context": context,
        "fresh_verified_source_gate_context_digest": _digest(
            DOMAINS["context"], context
        ),
        "fresh_verification_checks": checks,
        "fresh_verification_check_digest": _digest(DOMAINS["checks"], checks),
        "future_bind_authorization_requirements": authorization,
        "future_bind_authorization_requirement_digest": _digest(
            DOMAINS["authorization"], authorization
        ),
        "future_bind_invocation_requirements": invocation,
        "future_bind_invocation_requirement_digest": _digest(
            DOMAINS["invocation"], invocation
        ),
        "fresh_verified_source_gate_status": STATUS,
        "fresh_verified_source_gate_state": STATE,
        "ready_for_promotion_native_bind_context_derivation": True,
        "fresh_verified_source_gate_still_required": False,
        "bind_context_hash_derivation_still_required": True,
        "bind_context_hash_derived": False,
        "request_dispatch_state": "NOT_DISPATCHED",
        "bind_state": "NOT_BOUND",
        "authority_state": "NOT_AUTHORIZED",
        "human_approval_state": "NOT_APPROVED",
        "bind_authorization_state": "NOT_AUTHORIZED",
        "fail_closed": False,
        **{name: False for name in EFFECT_FIELDS},
    }
    omitted = {
        "promotion_live_adapter_dry_run_fresh_verified_source_gate_id",
        "promotion_live_adapter_dry_run_fresh_verified_source_gate_hash",
    }
    digest = _digest(
        DOMAINS["packet"], {k: v for k, v in raw.items() if k not in omitted}
    )
    raw["promotion_live_adapter_dry_run_fresh_verified_source_gate_hash"] = digest
    raw["promotion_live_adapter_dry_run_fresh_verified_source_gate_id"] = (
        f"pladfvsg:v1:sha256:{digest}"
    )
    return raw


def build_canonical_promotion_live_adapter_dry_run_fresh_verified_source_gate_packet(
    source_bind_authorization_gate_review_packet: Any,
    fresh_verified_at: datetime,
) -> CanonicalPromotionLiveAdapterDryRunFreshVerifiedSourceGatePacket:
    """Build fresh independent source verification with no execution authority."""

    source = _source(_json(source_bind_authorization_gate_review_packet))
    _validate_source(source)
    verified_at = _timestamp(fresh_verified_at)
    if verified_at < _timestamp(
        source.bind_authorization_gate_review_recorded_at
    ) or verified_at < _timestamp(
        source.bind_authorization_gate_review_decision.reviewed_at
    ):
        _fail("CPLADFVS_TIMESTAMP_ORDER_INVALID")
    return verify_canonical_promotion_live_adapter_dry_run_fresh_verified_source_gate_packet(
        _assemble(source, verified_at)
    )


def verify_canonical_promotion_live_adapter_dry_run_fresh_verified_source_gate_packet(
    raw: Any,
) -> CanonicalPromotionLiveAdapterDryRunFreshVerifiedSourceGatePacket:
    """Re-verify the embedded Gate Review and reconstruct every derived field."""

    try:
        value = raw.model_dump(mode="json") if isinstance(raw, BaseModel) else raw
        packet = CanonicalPromotionLiveAdapterDryRunFreshVerifiedSourceGatePacket.model_validate(
            _json(value)
        )
    except (ValidationError, TypeError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunFreshVerifiedSourceGateError(
            "CPLADFVS_PACKET_INVALID"
        ) from exc
    source = _source(packet.source_bind_authorization_gate_review_packet)
    _validate_source(source)
    verified_at = _timestamp(packet.fresh_verified_at)
    if verified_at < _timestamp(
        source.bind_authorization_gate_review_recorded_at
    ) or verified_at < _timestamp(
        source.bind_authorization_gate_review_decision.reviewed_at
    ):
        _fail("CPLADFVS_TIMESTAMP_ORDER_INVALID")
    if packet.model_dump(mode="json") != _assemble(source, verified_at):
        _fail("CPLADFVS_RECONSTRUCTION_MISMATCH")
    return packet