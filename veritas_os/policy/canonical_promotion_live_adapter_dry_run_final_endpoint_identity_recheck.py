"""Recheck exact promotion-native endpoint metadata without external effects.

This deterministic, content-addressed boundary consumes only the final endpoint
identity recheck lifecycle requirement.  It compares caller-supplied endpoint
metadata with the endpoint and exact Bind context already committed by the
verified source packet.  It never resolves DNS, opens a connection, verifies a
TLS peer, accesses credentials, grants authority, dispatches, or performs Bind.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

from veritas_os.policy.canonical_promotion_live_adapter_dry_run_bind_context_hash_derivation import (
    AUTHORIZATION_REQUIREMENTS as SOURCE_AUTHORIZATION_REQUIREMENTS,
    DOMAINS as SOURCE_DOMAINS,
    EFFECT_FIELDS,
    INVOCATION_REQUIREMENTS,
    PRESERVED_FIELDS as UPSTREAM_PRESERVED_FIELDS,
    STATE as SOURCE_STATE,
    STATUS as SOURCE_STATUS,
    CanonicalPromotionLiveAdapterDryRunBindContextHashDerivationError,
    CanonicalPromotionLiveAdapterDryRunBindContextHashDerivationPacket,
    verify_canonical_promotion_live_adapter_dry_run_bind_context_hash_derivation_packet,
)
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_endpoint_allowlist import (
    CANDIDATE_DOMAIN,
    EXACT_FIELDS,
    IDENTITY_DOMAIN,
    PROHIBITED_KEYS,
    EndpointCandidate,
)

FORMAT_VERSION = (
    "canonical-promotion-live-adapter-dry-run-final-endpoint-identity-recheck/v1"
)
MECHANISM = "exact_local_bind_context_bound_endpoint_metadata_recheck_only/v1"
STATUS = "PROMOTION_NATIVE_FINAL_ENDPOINT_IDENTITY_RECHECKED_NOT_AUTHORIZED"
STATE = "RECHECKED_FOR_FUTURE_FINAL_CREDENTIAL_SCOPE_RECHECK"
CHECK_MODE = "deterministic_local_exact_endpoint_metadata_recheck_only"
PREFIX = "veritas.promotion-live-adapter-dry-run-final-endpoint-identity-recheck"
HASH_PATTERN = r"^[0-9a-f]{64}$"
DOMAINS = {
    name: f"{PREFIX}.{name}/v1"
    for name in (
        "binding",
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
    "source_bind_context_hash_derivation_verified",
    "source_bind_context_identity_bound",
    "exact_bind_context_hash_recomputed",
    "rechecked_endpoint_candidate_closed_schema_valid",
    "rechecked_endpoint_candidate_exact_match",
    "rechecked_endpoint_candidate_digest_match",
    "source_endpoint_identity_binding_digest_verified",
    "rechecked_endpoint_identity_binding_bound_to_bind_context",
    "endpoint_adapter_contract_exact_match",
    "endpoint_target_system_exact_match",
    "endpoint_target_resource_scope_exact_match",
    "endpoint_declared_timestamp_not_future",
    "future_authorization_requirements_preserved",
    "future_invocation_requirements_preserved",
    "execution_authority_absent",
    "bind_authorization_absent",
    "endpoint_resolution_absent",
    "dns_access_absent",
    "network_access_absent",
    "external_effect_absent",
)
BIND_CONTEXT_EVIDENCE_FIELDS = (
    "bind_context_derived_at",
    "exact_bind_context",
    "bind_context_hash",
    "bind_context_hash_derivation_result",
    "bind_context_hash_derivation_result_digest",
    "bind_context_hash_derivation_context",
    "bind_context_hash_derivation_context_digest",
    "bind_context_hash_derivation_checks",
    "bind_context_hash_derivation_check_digest",
    "bind_context_hash_derivation_status",
    "bind_context_hash_derivation_state",
)
PRESERVED_FIELDS = tuple(
    dict.fromkeys((*UPSTREAM_PRESERVED_FIELDS, *BIND_CONTEXT_EVIDENCE_FIELDS))
)


class CanonicalPromotionLiveAdapterDryRunFinalEndpointIdentityRecheckError(
    ValueError
):
    """Stable fail-closed error for invalid final endpoint recheck evidence."""


class FinalEndpointIdentityRecheckResult(BaseModel):
    """Truthful local endpoint comparison result with no runtime claims."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    source_bind_context_hash_derivation_verified: Literal[True]
    source_bind_context_identity_bound: Literal[True]
    exact_bind_context_hash_recomputed: Literal[True]
    rechecked_endpoint_candidate_closed_schema_valid: Literal[True]
    rechecked_endpoint_candidate_exact_match: Literal[True]
    rechecked_endpoint_candidate_digest_match: Literal[True]
    source_endpoint_identity_binding_digest_verified: Literal[True]
    rechecked_endpoint_identity_binding_bound_to_bind_context: Literal[True]
    endpoint_adapter_contract_exact_match: Literal[True]
    endpoint_target_system_exact_match: Literal[True]
    endpoint_target_resource_scope_exact_match: Literal[True]
    endpoint_declared_timestamp_not_future: Literal[True]
    future_authorization_requirements_preserved: Literal[True]
    future_invocation_requirements_preserved: Literal[True]
    execution_authority_absent: Literal[True]
    bind_authorization_absent: Literal[True]
    endpoint_resolution_absent: Literal[True]
    dns_access_absent: Literal[True]
    network_access_absent: Literal[True]
    external_effect_absent: Literal[True]
    bind_context_hash: str = Field(pattern=HASH_PATTERN)
    endpoint_candidate_digest: str = Field(pattern=HASH_PATTERN)
    endpoint_identity_binding_digest: str = Field(pattern=HASH_PATTERN)
    final_endpoint_identity_binding_digest: str = Field(pattern=HASH_PATTERN)
    recheck_mode: Literal[CHECK_MODE]
    endpoint_rechecked: Literal[True]
    local_endpoint_metadata_rechecked: Literal[True]
    trusted_clock_verified: Literal[False]
    endpoint_resolution_performed: Literal[False]
    external_endpoint_identity_verified: Literal[False]
    dns_identity_verified: Literal[False]
    tls_peer_identity_verified: Literal[False]
    endpoint_liveness_verified: Literal[False]
    network_path_verified: Literal[False]
    external_policy_freshness_verified: Literal[False]
    credential_scope_rechecked: Literal[False]
    revocation_verified: Literal[False]


class FinalEndpointIdentityRecheckCheck(BaseModel):
    """An ordered local comparison check which performs no external effect."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    ordinal: int = Field(ge=1)
    name: Literal[*CHECK_NAMES]
    passed: Literal[True]
    comparison_mode: Literal[CHECK_MODE]


class FutureRequirement(BaseModel):
    """A remaining lifecycle requirement not satisfied by this packet."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    ordinal: int = Field(ge=1)
    name: Literal[*AUTHORIZATION_REQUIREMENTS, *INVOCATION_REQUIREMENTS]
    separate_future_artifact_required: Literal[True]
    satisfied_by_this_packet: Literal[False]


class _PacketBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    format_version: Literal[FORMAT_VERSION]
    promotion_live_adapter_dry_run_final_endpoint_identity_recheck_id: str = Field(
        min_length=1
    )
    promotion_live_adapter_dry_run_final_endpoint_identity_recheck_hash: str = Field(
        pattern=HASH_PATTERN
    )
    final_endpoint_identity_recheck_mechanism: Literal[MECHANISM]
    endpoint_identity_rechecked_at: str
    source_bind_context_hash_derivation_id: str = Field(min_length=1)
    source_bind_context_hash_derivation_hash: str = Field(pattern=HASH_PATTERN)
    source_bind_context_hash_derivation_packet: dict[str, Any]
    rechecked_endpoint_candidate: EndpointCandidate
    rechecked_endpoint_candidate_digest: str = Field(pattern=HASH_PATTERN)
    final_endpoint_identity_binding: dict[str, Any]
    final_endpoint_identity_binding_digest: str = Field(pattern=HASH_PATTERN)
    final_endpoint_identity_recheck_result: FinalEndpointIdentityRecheckResult
    final_endpoint_identity_recheck_result_digest: str = Field(pattern=HASH_PATTERN)
    final_endpoint_identity_recheck_context: dict[str, Any]
    final_endpoint_identity_recheck_context_digest: str = Field(pattern=HASH_PATTERN)
    final_endpoint_identity_recheck_checks: tuple[
        FinalEndpointIdentityRecheckCheck, ...
    ]
    final_endpoint_identity_recheck_check_digest: str = Field(pattern=HASH_PATTERN)
    future_bind_authorization_requirements: tuple[FutureRequirement, ...]
    future_bind_authorization_requirement_digest: str = Field(pattern=HASH_PATTERN)
    future_bind_invocation_requirements: tuple[FutureRequirement, ...]
    future_bind_invocation_requirement_digest: str = Field(pattern=HASH_PATTERN)
    final_endpoint_identity_recheck_status: Literal[STATUS]
    final_endpoint_identity_recheck_state: Literal[STATE]
    ready_for_promotion_native_final_credential_scope_recheck: Literal[True]
    fresh_verified_source_gate_still_required: Literal[False]
    bind_context_hash_derivation_still_required: Literal[False]
    bind_context_hash_derived: Literal[True]
    final_endpoint_identity_recheck_still_required: Literal[False]
    final_endpoint_identity_rechecked: Literal[True]
    final_credential_scope_recheck_still_required: Literal[True]
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


CanonicalPromotionLiveAdapterDryRunFinalEndpointIdentityRecheckPacket = create_model(
    "CanonicalPromotionLiveAdapterDryRunFinalEndpointIdentityRecheckPacket",
    __base__=_PacketBase,
    **{
        name: (
            CanonicalPromotionLiveAdapterDryRunBindContextHashDerivationPacket.model_fields[
                name
            ].annotation,
            ...,
        )
        for name in PRESERVED_FIELDS
    },
)


def _fail(code: str) -> None:
    raise CanonicalPromotionLiveAdapterDryRunFinalEndpointIdentityRecheckError(code)


def _timestamp(value: Any) -> str:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunFinalEndpointIdentityRecheckError(
            "CPLADFEIR_TIMESTAMP_INVALID"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail("CPLADFEIR_TIMESTAMP_INVALID")
    return parsed.astimezone(timezone.utc).isoformat()


def _json(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            _fail("CPLADFEIR_JSON_INVALID")
        return value
    if isinstance(value, datetime):
        return _timestamp(value)
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _json(item) for key, item in value.items()}
    _fail("CPLADFEIR_JSON_INVALID")


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
) -> CanonicalPromotionLiveAdapterDryRunBindContextHashDerivationPacket:
    try:
        return verify_canonical_promotion_live_adapter_dry_run_bind_context_hash_derivation_packet(
            value
        )
    except (
        CanonicalPromotionLiveAdapterDryRunBindContextHashDerivationError,
        TypeError,
        ValueError,
    ) as exc:
        raise CanonicalPromotionLiveAdapterDryRunFinalEndpointIdentityRecheckError(
            "CPLADFEIR_SOURCE_INVALID"
        ) from exc


def _candidate(value: Any) -> EndpointCandidate:
    raw = _json(value)
    if isinstance(raw, dict) and any(
        key.lower().replace("-", "_") in PROHIBITED_KEYS for key in raw
    ):
        _fail("CPLADFEIR_SENSITIVE_INPUT")
    try:
        return EndpointCandidate.model_validate(raw)
    except ValidationError as exc:
        raise CanonicalPromotionLiveAdapterDryRunFinalEndpointIdentityRecheckError(
            "CPLADFEIR_ENDPOINT_CANDIDATE_INVALID"
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
    result = source.bind_context_hash_derivation_result
    required = (
        source.bind_context_hash_derivation_status == SOURCE_STATUS,
        source.bind_context_hash_derivation_state == SOURCE_STATE,
        source.ready_for_promotion_native_final_endpoint_identity_recheck,
        not source.fail_closed,
        not source.fresh_verified_source_gate_still_required,
        not source.bind_context_hash_derivation_still_required,
        source.bind_context_hash_derived,
        source.final_endpoint_identity_recheck_still_required,
        source.bind_authorization_state == "NOT_AUTHORIZED",
        source.request_dispatch_state == "NOT_DISPATCHED",
        source.bind_state == "NOT_BOUND",
        source.authority_state == "NOT_AUTHORIZED",
        source.human_approval_state == "NOT_APPROVED",
        result.bind_context_hash == source.bind_context_hash,
        not result.endpoint_rechecked,
        not result.credential_scope_rechecked,
        not result.revocation_verified,
        not result.external_policy_freshness_verified,
    )
    if not all(required) or any(getattr(source, name) for name in EFFECT_FIELDS):
        _fail("CPLADFEIR_SOURCE_STATE_INVALID")
    authorization = tuple(
        item.name for item in source.future_bind_authorization_requirements
    )
    invocation = tuple(item.name for item in source.future_bind_invocation_requirements)
    if authorization != SOURCE_AUTHORIZATION_REQUIREMENTS:
        _fail("CPLADFEIR_SOURCE_AUTHORIZATION_REQUIREMENTS_INVALID")
    if invocation != INVOCATION_REQUIREMENTS:
        _fail("CPLADFEIR_SOURCE_INVOCATION_REQUIREMENTS_INVALID")
    context = source.exact_bind_context.model_dump(mode="json")
    if source.bind_context_hash != _digest(SOURCE_DOMAINS["bind-context"], context):
        _fail("CPLADFEIR_BIND_CONTEXT_HASH_INVALID")


def _validate_candidate(source: Any, candidate: EndpointCandidate) -> None:
    candidate_raw = candidate.model_dump(mode="json")
    source_candidate = EndpointCandidate.model_validate(_json(source.endpoint_candidate))
    source_candidate_raw = source_candidate.model_dump(mode="json")
    if candidate_raw != source_candidate_raw:
        _fail("CPLADFEIR_ENDPOINT_IDENTITY_MISMATCH")
    candidate_digest = _digest(CANDIDATE_DOMAIN, candidate_raw)
    context = source.exact_bind_context
    required = (
        candidate_digest == source.endpoint_candidate_digest,
        candidate_digest == context.endpoint_candidate_digest,
        candidate.adapter_contract_id == context.adapter_contract_id,
        candidate.target_system == source.execution_intent["target_system"],
        candidate.target_resource_scope == source.execution_intent["target_resource"],
    )
    if not all(required):
        _fail("CPLADFEIR_ENDPOINT_BINDING_MISMATCH")
    identity = _json(source.endpoint_identity_binding)
    identity_digest = _digest(IDENTITY_DOMAIN, identity)
    if (
        identity_digest != source.endpoint_identity_binding_digest
        or identity_digest != context.endpoint_identity_binding_digest
    ):
        _fail("CPLADFEIR_ENDPOINT_IDENTITY_BINDING_INVALID")


def _binding(source: Any, candidate: EndpointCandidate) -> dict[str, Any]:
    return {
        "source_bind_context_hash_derivation_id": (
            source.promotion_live_adapter_dry_run_bind_context_hash_derivation_id
        ),
        "source_bind_context_hash_derivation_hash": (
            source.promotion_live_adapter_dry_run_bind_context_hash_derivation_hash
        ),
        "bind_context_hash": source.bind_context_hash,
        "execution_intent_id": source.exact_bind_context.execution_intent_id,
        "execution_intent_hash": source.exact_bind_context.execution_intent_hash,
        "adapter_contract_id": source.exact_bind_context.adapter_contract_id,
        "adapter_contract_hash": source.exact_bind_context.adapter_contract_hash,
        "endpoint_candidate_id": candidate.endpoint_candidate_id,
        "endpoint_candidate_digest": source.endpoint_candidate_digest,
        "endpoint_identity_binding_digest": source.endpoint_identity_binding_digest,
        "exact_endpoint_metadata": {
            field: getattr(candidate, field) for field in EXACT_FIELDS
        },
    }


def _assemble(source: Any, candidate: EndpointCandidate, rechecked_at: str) -> dict[str, Any]:
    source_raw = source.model_dump(mode="json")
    candidate_raw = candidate.model_dump(mode="json")
    candidate_digest = _digest(CANDIDATE_DOMAIN, candidate_raw)
    binding = _binding(source, candidate)
    binding_digest = _digest(DOMAINS["binding"], binding)
    result = {name: True for name in CHECK_NAMES}
    result.update(
        {
            "bind_context_hash": source.bind_context_hash,
            "endpoint_candidate_digest": candidate_digest,
            "endpoint_identity_binding_digest": source.endpoint_identity_binding_digest,
            "final_endpoint_identity_binding_digest": binding_digest,
            "recheck_mode": CHECK_MODE,
            "endpoint_rechecked": True,
            "local_endpoint_metadata_rechecked": True,
            "trusted_clock_verified": False,
            "endpoint_resolution_performed": False,
            "external_endpoint_identity_verified": False,
            "dns_identity_verified": False,
            "tls_peer_identity_verified": False,
            "endpoint_liveness_verified": False,
            "network_path_verified": False,
            "external_policy_freshness_verified": False,
            "credential_scope_rechecked": False,
            "revocation_verified": False,
        }
    )
    result_digest = _digest(DOMAINS["result"], result)
    context = {
        "source_bind_context_hash_derivation_id": (
            source.promotion_live_adapter_dry_run_bind_context_hash_derivation_id
        ),
        "source_bind_context_hash_derivation_hash": (
            source.promotion_live_adapter_dry_run_bind_context_hash_derivation_hash
        ),
        "bind_context_hash": source.bind_context_hash,
        "rechecked_endpoint_candidate_digest": candidate_digest,
        "final_endpoint_identity_binding_digest": binding_digest,
        "endpoint_identity_rechecked_at": rechecked_at,
        "final_endpoint_identity_recheck_result_digest": result_digest,
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
        "final_endpoint_identity_recheck_mechanism": MECHANISM,
        "endpoint_identity_rechecked_at": rechecked_at,
        "source_bind_context_hash_derivation_id": (
            source.promotion_live_adapter_dry_run_bind_context_hash_derivation_id
        ),
        "source_bind_context_hash_derivation_hash": (
            source.promotion_live_adapter_dry_run_bind_context_hash_derivation_hash
        ),
        "source_bind_context_hash_derivation_packet": source_raw,
        **{name: source_raw[name] for name in PRESERVED_FIELDS},
        "rechecked_endpoint_candidate": candidate_raw,
        "rechecked_endpoint_candidate_digest": candidate_digest,
        "final_endpoint_identity_binding": binding,
        "final_endpoint_identity_binding_digest": binding_digest,
        "final_endpoint_identity_recheck_result": result,
        "final_endpoint_identity_recheck_result_digest": result_digest,
        "final_endpoint_identity_recheck_context": context,
        "final_endpoint_identity_recheck_context_digest": _digest(
            DOMAINS["context"], context
        ),
        "final_endpoint_identity_recheck_checks": checks,
        "final_endpoint_identity_recheck_check_digest": _digest(
            DOMAINS["checks"], checks
        ),
        "future_bind_authorization_requirements": authorization,
        "future_bind_authorization_requirement_digest": _digest(
            DOMAINS["authorization"], authorization
        ),
        "future_bind_invocation_requirements": invocation,
        "future_bind_invocation_requirement_digest": _digest(
            DOMAINS["invocation"], invocation
        ),
        "final_endpoint_identity_recheck_status": STATUS,
        "final_endpoint_identity_recheck_state": STATE,
        "ready_for_promotion_native_final_credential_scope_recheck": True,
        "fresh_verified_source_gate_still_required": False,
        "bind_context_hash_derivation_still_required": False,
        "bind_context_hash_derived": True,
        "final_endpoint_identity_recheck_still_required": False,
        "final_endpoint_identity_rechecked": True,
        "final_credential_scope_recheck_still_required": True,
        "request_dispatch_state": "NOT_DISPATCHED",
        "bind_state": "NOT_BOUND",
        "authority_state": "NOT_AUTHORIZED",
        "human_approval_state": "NOT_APPROVED",
        "bind_authorization_state": "NOT_AUTHORIZED",
        "fail_closed": False,
        **{name: False for name in EFFECT_FIELDS},
    }
    omitted = {
        "promotion_live_adapter_dry_run_final_endpoint_identity_recheck_id",
        "promotion_live_adapter_dry_run_final_endpoint_identity_recheck_hash",
    }
    digest = _digest(
        DOMAINS["packet"],
        {key: value for key, value in raw.items() if key not in omitted},
    )
    raw["promotion_live_adapter_dry_run_final_endpoint_identity_recheck_hash"] = digest
    raw["promotion_live_adapter_dry_run_final_endpoint_identity_recheck_id"] = (
        f"pladfeir:v1:sha256:{digest}"
    )
    return raw


def build_canonical_promotion_live_adapter_dry_run_final_endpoint_identity_recheck_packet(
    source_bind_context_hash_derivation_packet: Any,
    endpoint_candidate: Any,
    endpoint_identity_rechecked_at: datetime,
) -> CanonicalPromotionLiveAdapterDryRunFinalEndpointIdentityRecheckPacket:
    """Build exact local final endpoint recheck evidence without authority."""

    source = _source(_json(source_bind_context_hash_derivation_packet))
    _validate_source(source)
    candidate = _candidate(endpoint_candidate)
    _validate_candidate(source, candidate)
    rechecked_at = _timestamp(endpoint_identity_rechecked_at)
    if (
        rechecked_at < _timestamp(source.bind_context_derived_at)
        or rechecked_at < _timestamp(candidate.declared_at)
    ):
        _fail("CPLADFEIR_TIMESTAMP_ORDER_INVALID")
    return verify_canonical_promotion_live_adapter_dry_run_final_endpoint_identity_recheck_packet(
        _assemble(source, candidate, rechecked_at)
    )


def verify_canonical_promotion_live_adapter_dry_run_final_endpoint_identity_recheck_packet(
    raw: Any,
) -> CanonicalPromotionLiveAdapterDryRunFinalEndpointIdentityRecheckPacket:
    """Re-verify the source and reconstruct every endpoint comparison field."""

    try:
        value = raw.model_dump(mode="json") if isinstance(raw, BaseModel) else raw
        packet = CanonicalPromotionLiveAdapterDryRunFinalEndpointIdentityRecheckPacket.model_validate(
            _json(value)
        )
    except (ValidationError, TypeError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunFinalEndpointIdentityRecheckError(
            "CPLADFEIR_PACKET_INVALID"
        ) from exc
    source = _source(packet.source_bind_context_hash_derivation_packet)
    _validate_source(source)
    candidate = _candidate(packet.rechecked_endpoint_candidate)
    _validate_candidate(source, candidate)
    rechecked_at = _timestamp(packet.endpoint_identity_rechecked_at)
    if (
        rechecked_at < _timestamp(source.bind_context_derived_at)
        or rechecked_at < _timestamp(candidate.declared_at)
    ):
        _fail("CPLADFEIR_TIMESTAMP_ORDER_INVALID")
    if packet.model_dump(mode="json") != _assemble(source, candidate, rechecked_at):
        _fail("CPLADFEIR_RECONSTRUCTION_MISMATCH")
    return packet
