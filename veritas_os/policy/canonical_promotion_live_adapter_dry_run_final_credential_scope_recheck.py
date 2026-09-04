"""Recheck exact credential metadata and scope without credential access.

This deterministic, content-addressed boundary consumes only the final
credential scope recheck lifecycle requirement.  It compares caller-supplied
complete credential metadata and the operation-required scope with the
credential reference, scope binding, and exact Bind context already committed
by the verified source packet.  Scope containment is never inferred: every
scope character must match.  The boundary never resolves credential material,
accesses a credential store, grants authority, dispatches, writes TrustLog, or
performs Bind.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

from veritas_os.policy.canonical_promotion_live_adapter_dry_run_credential_authorization import (
    PROHIBITED_KEYS,
    REFERENCE_DOMAIN,
    SCOPE_BINDING_DOMAIN,
    CredentialReference,
)
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_final_endpoint_identity_recheck import (
    AUTHORIZATION_REQUIREMENTS as SOURCE_AUTHORIZATION_REQUIREMENTS,
    EFFECT_FIELDS,
    INVOCATION_REQUIREMENTS,
    PRESERVED_FIELDS as UPSTREAM_PRESERVED_FIELDS,
    STATE as SOURCE_STATE,
    STATUS as SOURCE_STATUS,
    CanonicalPromotionLiveAdapterDryRunFinalEndpointIdentityRecheckError,
    CanonicalPromotionLiveAdapterDryRunFinalEndpointIdentityRecheckPacket,
    verify_canonical_promotion_live_adapter_dry_run_final_endpoint_identity_recheck_packet,
)
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_bind_context_hash_derivation import (
    DOMAINS as BIND_CONTEXT_DOMAINS,
)

FORMAT_VERSION = (
    "canonical-promotion-live-adapter-dry-run-final-credential-scope-recheck/v1"
)
MECHANISM = "exact_local_bind_context_bound_credential_scope_recheck_only/v1"
STATUS = "PROMOTION_NATIVE_FINAL_CREDENTIAL_SCOPE_RECHECKED_NOT_AUTHORIZED"
STATE = "RECHECKED_FOR_FUTURE_RUNTIME_RISK_REVIEW"
CHECK_MODE = "deterministic_local_exact_credential_metadata_scope_recheck_only"
SCOPE_MATCH_MODE = "exact_character_match_only_no_containment_inference"
PREFIX = "veritas.promotion-live-adapter-dry-run-final-credential-scope-recheck"
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
    "source_final_endpoint_identity_recheck_verified",
    "source_endpoint_identity_recheck_bound",
    "source_exact_bind_context_hash_recomputed",
    "caller_credential_reference_closed_schema_valid",
    "caller_credential_reference_exact_match",
    "caller_credential_reference_digest_verified",
    "source_credential_scope_binding_digest_verified",
    "credential_scope_binding_bound_to_bind_context",
    "required_credential_scope_non_empty",
    "required_credential_scope_exact_character_match",
    "credential_scope_containment_not_inferred",
    "credential_reference_swap_absent",
    "future_authorization_requirements_preserved",
    "future_invocation_requirements_preserved",
    "credential_resolution_absent",
    "credential_store_access_absent",
    "credential_material_access_absent",
    "execution_authority_absent",
    "bind_authorization_absent",
    "network_access_absent",
    "trustlog_write_absent",
    "external_effect_absent",
)
ENDPOINT_RECHECK_EVIDENCE_FIELDS = (
    "endpoint_identity_rechecked_at",
    "rechecked_endpoint_candidate",
    "rechecked_endpoint_candidate_digest",
    "final_endpoint_identity_binding",
    "final_endpoint_identity_binding_digest",
    "final_endpoint_identity_recheck_result",
    "final_endpoint_identity_recheck_result_digest",
    "final_endpoint_identity_recheck_context",
    "final_endpoint_identity_recheck_context_digest",
    "final_endpoint_identity_recheck_checks",
    "final_endpoint_identity_recheck_check_digest",
    "final_endpoint_identity_recheck_status",
    "final_endpoint_identity_recheck_state",
)
PRESERVED_FIELDS = tuple(
    dict.fromkeys((*UPSTREAM_PRESERVED_FIELDS, *ENDPOINT_RECHECK_EVIDENCE_FIELDS))
)


class CanonicalPromotionLiveAdapterDryRunFinalCredentialScopeRecheckError(ValueError):
    """Stable fail-closed error for invalid final credential recheck evidence."""


class FinalCredentialScopeRecheckResult(BaseModel):
    """Truthful exact credential metadata comparison with no runtime claims."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    source_final_endpoint_identity_recheck_verified: Literal[True]
    source_endpoint_identity_recheck_bound: Literal[True]
    source_exact_bind_context_hash_recomputed: Literal[True]
    caller_credential_reference_closed_schema_valid: Literal[True]
    caller_credential_reference_exact_match: Literal[True]
    caller_credential_reference_digest_verified: Literal[True]
    source_credential_scope_binding_digest_verified: Literal[True]
    credential_scope_binding_bound_to_bind_context: Literal[True]
    required_credential_scope_non_empty: Literal[True]
    required_credential_scope_exact_character_match: Literal[True]
    credential_scope_containment_not_inferred: Literal[True]
    credential_reference_swap_absent: Literal[True]
    future_authorization_requirements_preserved: Literal[True]
    future_invocation_requirements_preserved: Literal[True]
    credential_resolution_absent: Literal[True]
    credential_store_access_absent: Literal[True]
    credential_material_access_absent: Literal[True]
    execution_authority_absent: Literal[True]
    bind_authorization_absent: Literal[True]
    network_access_absent: Literal[True]
    trustlog_write_absent: Literal[True]
    external_effect_absent: Literal[True]
    bind_context_hash: str = Field(pattern=HASH_PATTERN)
    credential_reference_digest: str = Field(pattern=HASH_PATTERN)
    credential_scope_binding_digest: str = Field(pattern=HASH_PATTERN)
    final_credential_scope_binding_digest: str = Field(pattern=HASH_PATTERN)
    required_credential_scope: str = Field(min_length=1)
    bound_credential_scope: str = Field(min_length=1)
    recheck_mode: Literal[CHECK_MODE]
    scope_match_mode: Literal[SCOPE_MATCH_MODE]
    credential_reference_rechecked: Literal[True]
    credential_scope_rechecked: Literal[True]
    scope_containment_inferred: Literal[False]
    trusted_clock_verified: Literal[False]
    external_policy_freshness_verified: Literal[False]
    credential_resolved: Literal[False]
    credential_store_accessed: Literal[False]
    credential_material_accessed: Literal[False]
    revocation_verified: Literal[False]


class FinalCredentialScopeRecheckCheck(BaseModel):
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
    promotion_live_adapter_dry_run_final_credential_scope_recheck_id: str = Field(
        min_length=1
    )
    promotion_live_adapter_dry_run_final_credential_scope_recheck_hash: str = Field(
        pattern=HASH_PATTERN
    )
    final_credential_scope_recheck_mechanism: Literal[MECHANISM]
    credential_scope_rechecked_at: str
    source_final_endpoint_identity_recheck_id: str = Field(min_length=1)
    source_final_endpoint_identity_recheck_hash: str = Field(pattern=HASH_PATTERN)
    source_final_endpoint_identity_recheck_packet: dict[str, Any]
    rechecked_credential_reference: CredentialReference
    rechecked_credential_reference_digest: str = Field(pattern=HASH_PATTERN)
    required_credential_scope: str = Field(min_length=1)
    final_credential_scope_binding: dict[str, Any]
    final_credential_scope_binding_digest: str = Field(pattern=HASH_PATTERN)
    final_credential_scope_recheck_result: FinalCredentialScopeRecheckResult
    final_credential_scope_recheck_result_digest: str = Field(pattern=HASH_PATTERN)
    final_credential_scope_recheck_context: dict[str, Any]
    final_credential_scope_recheck_context_digest: str = Field(pattern=HASH_PATTERN)
    final_credential_scope_recheck_checks: tuple[FinalCredentialScopeRecheckCheck, ...]
    final_credential_scope_recheck_check_digest: str = Field(pattern=HASH_PATTERN)
    future_bind_authorization_requirements: tuple[FutureRequirement, ...]
    future_bind_authorization_requirement_digest: str = Field(pattern=HASH_PATTERN)
    future_bind_invocation_requirements: tuple[FutureRequirement, ...]
    future_bind_invocation_requirement_digest: str = Field(pattern=HASH_PATTERN)
    final_credential_scope_recheck_status: Literal[STATUS]
    final_credential_scope_recheck_state: Literal[STATE]
    ready_for_promotion_native_runtime_risk_review: Literal[True]
    fresh_verified_source_gate_still_required: Literal[False]
    bind_context_hash_derivation_still_required: Literal[False]
    bind_context_hash_derived: Literal[True]
    final_endpoint_identity_recheck_still_required: Literal[False]
    final_endpoint_identity_rechecked: Literal[True]
    final_credential_scope_recheck_still_required: Literal[False]
    final_credential_scope_rechecked: Literal[True]
    runtime_risk_review_still_required: Literal[True]
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


CanonicalPromotionLiveAdapterDryRunFinalCredentialScopeRecheckPacket = create_model(
    "CanonicalPromotionLiveAdapterDryRunFinalCredentialScopeRecheckPacket",
    __base__=_PacketBase,
    **{
        name: (
            CanonicalPromotionLiveAdapterDryRunFinalEndpointIdentityRecheckPacket.model_fields[
                name
            ].annotation,
            ...,
        )
        for name in PRESERVED_FIELDS
    },
)


def _fail(code: str) -> None:
    raise CanonicalPromotionLiveAdapterDryRunFinalCredentialScopeRecheckError(code)


def _timestamp(value: Any) -> str:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunFinalCredentialScopeRecheckError(
            "CPLADFCSR_TIMESTAMP_INVALID"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail("CPLADFCSR_TIMESTAMP_INVALID")
    return parsed.astimezone(timezone.utc).isoformat()


def _json(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            _fail("CPLADFCSR_JSON_INVALID")
        return value
    if isinstance(value, datetime):
        return _timestamp(value)
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _json(item) for key, item in value.items()}
    _fail("CPLADFCSR_JSON_INVALID")


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
) -> CanonicalPromotionLiveAdapterDryRunFinalEndpointIdentityRecheckPacket:
    try:
        return verify_canonical_promotion_live_adapter_dry_run_final_endpoint_identity_recheck_packet(
            value
        )
    except (
        CanonicalPromotionLiveAdapterDryRunFinalEndpointIdentityRecheckError,
        TypeError,
        ValueError,
    ) as exc:
        raise CanonicalPromotionLiveAdapterDryRunFinalCredentialScopeRecheckError(
            "CPLADFCSR_SOURCE_INVALID"
        ) from exc


def _reference(value: Any) -> CredentialReference:
    raw = _json(value)
    if isinstance(raw, dict) and any(
        key.lower().replace("-", "_") in PROHIBITED_KEYS for key in raw
    ):
        _fail("CPLADFCSR_SENSITIVE_INPUT")
    try:
        return CredentialReference.model_validate(raw)
    except ValidationError as exc:
        raise CanonicalPromotionLiveAdapterDryRunFinalCredentialScopeRecheckError(
            "CPLADFCSR_CREDENTIAL_REFERENCE_INVALID"
        ) from exc


def _scope(value: Any) -> str:
    if not isinstance(value, str) or not value:
        _fail("CPLADFCSR_REQUIRED_SCOPE_INVALID")
    return value


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
    result = source.final_endpoint_identity_recheck_result
    required = (
        source.final_endpoint_identity_recheck_status == SOURCE_STATUS,
        source.final_endpoint_identity_recheck_state == SOURCE_STATE,
        source.ready_for_promotion_native_final_credential_scope_recheck,
        not source.fail_closed,
        not source.fresh_verified_source_gate_still_required,
        not source.bind_context_hash_derivation_still_required,
        source.bind_context_hash_derived,
        not source.final_endpoint_identity_recheck_still_required,
        source.final_endpoint_identity_rechecked,
        source.final_credential_scope_recheck_still_required,
        source.bind_authorization_state == "NOT_AUTHORIZED",
        source.request_dispatch_state == "NOT_DISPATCHED",
        source.bind_state == "NOT_BOUND",
        source.authority_state == "NOT_AUTHORIZED",
        source.human_approval_state == "NOT_APPROVED",
        result.bind_context_hash == source.bind_context_hash,
        result.endpoint_rechecked,
        not result.credential_scope_rechecked,
        not result.revocation_verified,
        not result.external_policy_freshness_verified,
    )
    if not all(required) or any(getattr(source, name) for name in EFFECT_FIELDS):
        _fail("CPLADFCSR_SOURCE_STATE_INVALID")
    authorization = tuple(
        item.name for item in source.future_bind_authorization_requirements
    )
    invocation = tuple(item.name for item in source.future_bind_invocation_requirements)
    if authorization != SOURCE_AUTHORIZATION_REQUIREMENTS:
        _fail("CPLADFCSR_SOURCE_AUTHORIZATION_REQUIREMENTS_INVALID")
    if invocation != INVOCATION_REQUIREMENTS:
        _fail("CPLADFCSR_SOURCE_INVOCATION_REQUIREMENTS_INVALID")
    context = source.exact_bind_context.model_dump(mode="json")
    if source.bind_context_hash != _digest(
        BIND_CONTEXT_DOMAINS["bind-context"], context
    ):
        _fail("CPLADFCSR_BIND_CONTEXT_HASH_INVALID")


def _validate_reference_and_scope(
    source: Any,
    reference: CredentialReference,
    required_scope: str,
) -> None:
    reference_raw = reference.model_dump(mode="json")
    source_reference = _reference(source.credential_reference)
    source_reference_raw = source_reference.model_dump(mode="json")
    if reference_raw != source_reference_raw:
        _fail("CPLADFCSR_CREDENTIAL_REFERENCE_MISMATCH")
    reference_digest = _digest(REFERENCE_DOMAIN, reference_raw)
    context = source.exact_bind_context
    binding = _json(source.credential_scope_binding)
    binding_digest = _digest(SCOPE_BINDING_DOMAIN, binding)
    required = (
        reference_digest == source.credential_reference_digest,
        reference_digest == context.credential_reference_digest,
        binding_digest == source.credential_scope_binding_digest,
        binding_digest == context.credential_scope_binding_digest,
        binding.get("credential_reference_id") == reference.credential_reference_id,
        binding.get("credential_reference_digest") == reference_digest,
        binding.get("credential_kind") == reference.credential_kind,
        binding.get("credential_provider_type") == reference.credential_provider_type,
        binding.get("credential_scope") == reference.credential_scope,
        binding.get("credential_environment") == reference.credential_environment,
        binding.get("credential_purpose") == reference.credential_purpose,
        binding.get("target_system") == reference.target_system,
        binding.get("target_resource_scope") == reference.target_resource_scope,
        binding.get("execution_intent_id") == context.execution_intent_id,
        binding.get("execution_intent_hash") == context.execution_intent_hash,
        binding.get("adapter_contract_id") == context.adapter_contract_id,
        binding.get("adapter_contract_hash") == context.adapter_contract_hash,
        binding.get("endpoint_candidate_digest") == context.endpoint_candidate_digest,
        binding.get("endpoint_identity_binding_digest")
        == context.endpoint_identity_binding_digest,
        binding.get("credential_policy_snapshot_hash")
        == context.credential_policy_snapshot_hash,
        binding.get("credential_authorization_result_digest")
        == context.credential_authorization_result_digest,
    )
    if not all(required):
        _fail("CPLADFCSR_CREDENTIAL_BINDING_MISMATCH")
    if required_scope != reference.credential_scope:
        _fail("CPLADFCSR_REQUIRED_SCOPE_MISMATCH")


def _binding(
    source: Any,
    reference: CredentialReference,
    required_scope: str,
) -> dict[str, Any]:
    return {
        "source_final_endpoint_identity_recheck_id": (
            source.promotion_live_adapter_dry_run_final_endpoint_identity_recheck_id
        ),
        "source_final_endpoint_identity_recheck_hash": (
            source.promotion_live_adapter_dry_run_final_endpoint_identity_recheck_hash
        ),
        "source_bind_context_hash_derivation_id": (
            source.source_bind_context_hash_derivation_id
        ),
        "source_bind_context_hash_derivation_hash": (
            source.source_bind_context_hash_derivation_hash
        ),
        "bind_context_hash": source.bind_context_hash,
        "execution_intent_id": source.exact_bind_context.execution_intent_id,
        "execution_intent_hash": source.exact_bind_context.execution_intent_hash,
        "adapter_contract_id": source.exact_bind_context.adapter_contract_id,
        "adapter_contract_hash": source.exact_bind_context.adapter_contract_hash,
        "final_endpoint_identity_binding_digest": (
            source.final_endpoint_identity_binding_digest
        ),
        "credential_reference_id": reference.credential_reference_id,
        "credential_reference_digest": source.credential_reference_digest,
        "credential_scope_binding_digest": source.credential_scope_binding_digest,
        "required_credential_scope": required_scope,
        "bound_credential_scope": reference.credential_scope,
        "scope_match_mode": SCOPE_MATCH_MODE,
        "scope_containment_inferred": False,
    }


def _assemble(
    source: Any,
    reference: CredentialReference,
    required_scope: str,
    rechecked_at: str,
) -> dict[str, Any]:
    source_raw = source.model_dump(mode="json")
    reference_raw = reference.model_dump(mode="json")
    reference_digest = _digest(REFERENCE_DOMAIN, reference_raw)
    binding = _binding(source, reference, required_scope)
    binding_digest = _digest(DOMAINS["binding"], binding)
    result = {name: True for name in CHECK_NAMES}
    result.update(
        {
            "bind_context_hash": source.bind_context_hash,
            "credential_reference_digest": reference_digest,
            "credential_scope_binding_digest": (source.credential_scope_binding_digest),
            "final_credential_scope_binding_digest": binding_digest,
            "required_credential_scope": required_scope,
            "bound_credential_scope": reference.credential_scope,
            "recheck_mode": CHECK_MODE,
            "scope_match_mode": SCOPE_MATCH_MODE,
            "credential_reference_rechecked": True,
            "credential_scope_rechecked": True,
            "scope_containment_inferred": False,
            "trusted_clock_verified": False,
            "external_policy_freshness_verified": False,
            "credential_resolved": False,
            "credential_store_accessed": False,
            "credential_material_accessed": False,
            "revocation_verified": False,
        }
    )
    result_digest = _digest(DOMAINS["result"], result)
    context = {
        "source_final_endpoint_identity_recheck_id": (
            source.promotion_live_adapter_dry_run_final_endpoint_identity_recheck_id
        ),
        "source_final_endpoint_identity_recheck_hash": (
            source.promotion_live_adapter_dry_run_final_endpoint_identity_recheck_hash
        ),
        "source_bind_context_hash_derivation_hash": (
            source.source_bind_context_hash_derivation_hash
        ),
        "bind_context_hash": source.bind_context_hash,
        "credential_reference_digest": reference_digest,
        "credential_scope_binding_digest": source.credential_scope_binding_digest,
        "required_credential_scope": required_scope,
        "credential_scope_rechecked_at": rechecked_at,
        "final_credential_scope_binding_digest": binding_digest,
        "final_credential_scope_recheck_result_digest": result_digest,
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
        "final_credential_scope_recheck_mechanism": MECHANISM,
        "credential_scope_rechecked_at": rechecked_at,
        "source_final_endpoint_identity_recheck_id": (
            source.promotion_live_adapter_dry_run_final_endpoint_identity_recheck_id
        ),
        "source_final_endpoint_identity_recheck_hash": (
            source.promotion_live_adapter_dry_run_final_endpoint_identity_recheck_hash
        ),
        "source_final_endpoint_identity_recheck_packet": source_raw,
        **{name: source_raw[name] for name in PRESERVED_FIELDS},
        "rechecked_credential_reference": reference_raw,
        "rechecked_credential_reference_digest": reference_digest,
        "required_credential_scope": required_scope,
        "final_credential_scope_binding": binding,
        "final_credential_scope_binding_digest": binding_digest,
        "final_credential_scope_recheck_result": result,
        "final_credential_scope_recheck_result_digest": result_digest,
        "final_credential_scope_recheck_context": context,
        "final_credential_scope_recheck_context_digest": _digest(
            DOMAINS["context"], context
        ),
        "final_credential_scope_recheck_checks": checks,
        "final_credential_scope_recheck_check_digest": _digest(
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
        "final_credential_scope_recheck_status": STATUS,
        "final_credential_scope_recheck_state": STATE,
        "ready_for_promotion_native_runtime_risk_review": True,
        "fresh_verified_source_gate_still_required": False,
        "bind_context_hash_derivation_still_required": False,
        "bind_context_hash_derived": True,
        "final_endpoint_identity_recheck_still_required": False,
        "final_endpoint_identity_rechecked": True,
        "final_credential_scope_recheck_still_required": False,
        "final_credential_scope_rechecked": True,
        "runtime_risk_review_still_required": True,
        "request_dispatch_state": "NOT_DISPATCHED",
        "bind_state": "NOT_BOUND",
        "authority_state": "NOT_AUTHORIZED",
        "human_approval_state": "NOT_APPROVED",
        "bind_authorization_state": "NOT_AUTHORIZED",
        "fail_closed": False,
        **{name: False for name in EFFECT_FIELDS},
    }
    omitted = {
        "promotion_live_adapter_dry_run_final_credential_scope_recheck_id",
        "promotion_live_adapter_dry_run_final_credential_scope_recheck_hash",
    }
    digest = _digest(
        DOMAINS["packet"],
        {key: value for key, value in raw.items() if key not in omitted},
    )
    raw["promotion_live_adapter_dry_run_final_credential_scope_recheck_hash"] = digest
    raw["promotion_live_adapter_dry_run_final_credential_scope_recheck_id"] = (
        f"pladfcsr:v1:sha256:{digest}"
    )
    return raw


def build_canonical_promotion_live_adapter_dry_run_final_credential_scope_recheck_packet(
    source_final_endpoint_identity_recheck_packet: Any,
    credential_reference: Any,
    required_credential_scope: str,
    credential_scope_rechecked_at: datetime,
) -> CanonicalPromotionLiveAdapterDryRunFinalCredentialScopeRecheckPacket:
    """Build exact local final credential scope evidence without authority."""

    source = _source(_json(source_final_endpoint_identity_recheck_packet))
    _validate_source(source)
    reference = _reference(credential_reference)
    required_scope = _scope(required_credential_scope)
    _validate_reference_and_scope(source, reference, required_scope)
    rechecked_at = _timestamp(credential_scope_rechecked_at)
    if rechecked_at < _timestamp(
        source.endpoint_identity_rechecked_at
    ) or rechecked_at < _timestamp(reference.declared_at):
        _fail("CPLADFCSR_TIMESTAMP_ORDER_INVALID")
    return verify_canonical_promotion_live_adapter_dry_run_final_credential_scope_recheck_packet(
        _assemble(source, reference, required_scope, rechecked_at)
    )


def verify_canonical_promotion_live_adapter_dry_run_final_credential_scope_recheck_packet(
    raw: Any,
) -> CanonicalPromotionLiveAdapterDryRunFinalCredentialScopeRecheckPacket:
    """Re-verify the source and reconstruct every credential comparison field."""

    try:
        value = raw.model_dump(mode="json") if isinstance(raw, BaseModel) else raw
        packet = CanonicalPromotionLiveAdapterDryRunFinalCredentialScopeRecheckPacket.model_validate(
            _json(value)
        )
    except (ValidationError, TypeError) as exc:
        raise CanonicalPromotionLiveAdapterDryRunFinalCredentialScopeRecheckError(
            "CPLADFCSR_PACKET_INVALID"
        ) from exc
    source = _source(packet.source_final_endpoint_identity_recheck_packet)
    _validate_source(source)
    reference = _reference(packet.rechecked_credential_reference)
    required_scope = _scope(packet.required_credential_scope)
    _validate_reference_and_scope(source, reference, required_scope)
    rechecked_at = _timestamp(packet.credential_scope_rechecked_at)
    if rechecked_at < _timestamp(
        source.endpoint_identity_rechecked_at
    ) or rechecked_at < _timestamp(reference.declared_at):
        _fail("CPLADFCSR_TIMESTAMP_ORDER_INVALID")
    if packet.model_dump(mode="json") != _assemble(
        source, reference, required_scope, rechecked_at
    ):
        _fail("CPLADFCSR_RECONSTRUCTION_MISMATCH")
    return packet
