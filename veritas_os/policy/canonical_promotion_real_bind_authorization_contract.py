"""Freeze the promotion-native handoff into existing real Bind primitives.

This module does not create another governance evidence packet.  It verifies
the complete final credential-scope source and projects only the bindings that
a future runtime-risk review and Real Bind Authorization composition may
consume.  Requirement ownership is explicit so later work reuses the existing
authorization, consumption, Bind, reconciliation, and outcome implementations
instead of duplicating them.

The projection grants no authority, performs no I/O, and cannot dispatch or
invoke Bind.  A pre-authorization runtime-risk artifact remains the next step,
while ``execute_bind_adjudication`` must still perform its independent,
just-in-time adapter risk check immediately before any apply attempt.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from veritas_os.policy.bind_adapter_contract_selection import (
    BindAdapterContractSelectionError,
    BindAdapterContractDescriptor,
    verify_bind_adapter_contract_descriptor,
)
from veritas_os.policy.bind_artifacts import ExecutionIntent, hash_execution_intent
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_final_credential_scope_recheck import (
    AUTHORIZATION_REQUIREMENTS,
    EFFECT_FIELDS,
    FORMAT_VERSION as SOURCE_FORMAT_VERSION,
    INVOCATION_REQUIREMENTS,
    STATE as SOURCE_STATE,
    STATUS as SOURCE_STATUS,
    CanonicalPromotionLiveAdapterDryRunFinalCredentialScopeRecheckError,
    verify_canonical_promotion_live_adapter_dry_run_final_credential_scope_recheck_packet,
)
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_credential_authorization import (
    CredentialReference,
)

CONTRACT_VERSION = "canonical-promotion-real-bind-authorization-contract/v1"
NEXT_AUTHORIZATION_REQUIREMENT = "runtime_risk_review"
RUNTIME_RISK_ARTIFACT_OWNER = (
    "veritas_os.policy.canonical_promotion_live_adapter_dry_run_runtime_risk_review"
)
BIND_TIME_RISK_OWNER = "veritas_os.policy.bind_core.core"

_AUTHORIZATION_OWNERS = {
    "runtime_risk_review": RUNTIME_RISK_ARTIFACT_OWNER,
    "idempotency_and_replay_review": (
        "veritas_os.policy.live_adapter_bind_authorization_requirements"
    ),
    "signed_gate_bound_human_approval_issuance": (
        "veritas_os.policy.gate_bound_human_approval_issuance"
    ),
    "human_approval_receipt_verification": (
        "veritas_os.governance.human_approval_receipt"
    ),
    "cryptographic_authority_evidence_verification": (
        "veritas_os.governance.authority_evidence"
    ),
    "revocation_verification_where_applicable": (
        "veritas_os.governance.authority_evidence"
    ),
    "real_bind_authorization": ("veritas_os.policy.live_adapter_bind_authorization"),
}

_INVOCATION_OWNERS = {
    "authorization_consumption": (
        "veritas_os.policy.live_adapter_bind_authorization_consumption"
    ),
    "single_use_consumption": (
        "veritas_os.policy.live_adapter_bind_authorization_consumption"
    ),
    "credential_material_resolution": (
        "veritas_os.policy.live_adapter_bind_authorization_consumption"
    ),
    "authorization_header_construction": (
        "veritas_os.policy.live_adapter_bind_authorization_consumption"
    ),
    "network_dispatch": (
        "veritas_os.policy.live_adapter_bind_authorization_consumption"
    ),
    "bind_invocation": "veritas_os.policy.bind_core.core",
    "bind_receipt": "veritas_os.policy.bind_core.core",
    "trustlog_write": "veritas_os.policy.bind_core.core",
    "effect_state_handling": "veritas_os.policy.bind_effect_runtime",
    "reconciliation": "veritas_os.policy.bind_effect_reconciliation",
    "outcome_receipt": "veritas_os.policy.bind_outcome_lineage",
}


class CanonicalPromotionRealBindAuthorizationContractError(ValueError):
    """Stable fail-closed error for an invalid composition source."""


class RequirementRoute(BaseModel):
    """Freeze the existing implementation owner for one remaining requirement."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    ordinal: int = Field(ge=1)
    phase: Literal["authorization", "invocation"]
    requirement: Literal[*AUTHORIZATION_REQUIREMENTS, *INVOCATION_REQUIREMENTS]
    implementation_owner: str = Field(min_length=1)
    reuse_existing_implementation: bool
    separate_evidence_boundary_required: Literal[True]
    satisfied_by_contract: Literal[False]
    bind_time_recheck_required: bool


class VerifiedPromotionAuthorizationSource(BaseModel):
    """Small verified projection of the deeply nested promotion source."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    contract_version: Literal[CONTRACT_VERSION]
    source_format_version: Literal[SOURCE_FORMAT_VERSION]
    source_final_credential_scope_recheck_id: str = Field(
        pattern=r"^pladfcsr:v1:sha256:[0-9a-f]{64}$"
    )
    source_final_credential_scope_recheck_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_intent: dict[str, Any]
    execution_intent_id: str = Field(pattern=r"^ei:v1:sha256:[0-9a-f]{64}$")
    execution_intent_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    adapter_contract_descriptor: BindAdapterContractDescriptor
    adapter_contract_id: str = Field(
        pattern=r"^adapter-contract:v1:sha256:[0-9a-f]{64}$"
    )
    adapter_contract_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    adapter_contract_version: Literal["bind-adapter-contract/v1"]
    bind_context_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    endpoint_identity_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    final_endpoint_identity_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    credential_reference: CredentialReference
    credential_reference_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    credential_scope_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    final_credential_scope_binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_evidence_reference_bundle: dict[str, Any]
    authority_evidence_reference_bundle_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    human_approval_reference_bundle: dict[str, Any]
    human_approval_reference_bundle_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authorization_routes: tuple[RequirementRoute, ...]
    invocation_routes: tuple[RequirementRoute, ...]
    next_authorization_requirement: Literal[NEXT_AUTHORIZATION_REQUIREMENT]
    preauthorization_runtime_risk_artifact_required: Literal[True]
    bind_time_runtime_risk_recheck_required: Literal[True]
    bind_time_runtime_risk_owner: Literal[BIND_TIME_RISK_OWNER]
    execution_authorized: Literal[False]
    bind_authorization_issued: Literal[False]
    request_dispatched: Literal[False]
    bind_invoked: Literal[False]
    external_effect_used: Literal[False]


def _fail(code: str) -> None:
    raise CanonicalPromotionRealBindAuthorizationContractError(code)


def _mapping(value: Any, code: str) -> dict[str, Any]:
    raw = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    if not isinstance(raw, dict):
        _fail(code)
    return raw


def _routes(
    requirements: tuple[str, ...],
    owners: dict[str, str],
    *,
    phase: Literal["authorization", "invocation"],
) -> tuple[RequirementRoute, ...]:
    if set(requirements) != set(owners) or len(requirements) != len(owners):
        _fail("CPRBAC_REQUIREMENT_OWNER_MISMATCH")
    return tuple(
        RequirementRoute(
            ordinal=ordinal,
            phase=phase,
            requirement=requirement,
            implementation_owner=owners[requirement],
            reuse_existing_implementation=(
                requirement != NEXT_AUTHORIZATION_REQUIREMENT
            ),
            separate_evidence_boundary_required=True,
            satisfied_by_contract=False,
            bind_time_recheck_required=(requirement == NEXT_AUTHORIZATION_REQUIREMENT),
        )
        for ordinal, requirement in enumerate(requirements, 1)
    )


def _intent(source: Any) -> ExecutionIntent:
    raw = source.execution_intent
    try:
        intent = ExecutionIntent(**raw)
    except (TypeError, ValueError) as exc:
        raise CanonicalPromotionRealBindAuthorizationContractError(
            "CPRBAC_EXECUTION_INTENT_INVALID"
        ) from exc
    if (
        intent.to_dict() != raw
        or intent.execution_intent_id != source.execution_intent_id
        or hash_execution_intent(intent) != source.execution_intent_hash
    ):
        _fail("CPRBAC_EXECUTION_INTENT_MISMATCH")
    return intent


def _validate_source_state(source: Any) -> None:
    authorization_requirements = tuple(
        item.name for item in source.future_bind_authorization_requirements
    )
    invocation_requirements = tuple(
        item.name for item in source.future_bind_invocation_requirements
    )
    requirement_flags_valid = all(
        item.separate_future_artifact_required and not item.satisfied_by_this_packet
        for item in (
            *source.future_bind_authorization_requirements,
            *source.future_bind_invocation_requirements,
        )
    )
    state_valid = (
        source.format_version == SOURCE_FORMAT_VERSION
        and source.final_credential_scope_recheck_status == SOURCE_STATUS
        and source.final_credential_scope_recheck_state == SOURCE_STATE
        and source.ready_for_promotion_native_runtime_risk_review
        and source.runtime_risk_review_still_required
        and not source.fail_closed
        and source.request_dispatch_state == "NOT_DISPATCHED"
        and source.bind_state == "NOT_BOUND"
        and source.authority_state == "NOT_AUTHORIZED"
        and source.human_approval_state == "NOT_APPROVED"
        and source.bind_authorization_state == "NOT_AUTHORIZED"
        and not any(getattr(source, field) for field in EFFECT_FIELDS)
    )
    if not state_valid:
        _fail("CPRBAC_SOURCE_STATE_INVALID")
    if (
        authorization_requirements != AUTHORIZATION_REQUIREMENTS
        or invocation_requirements != INVOCATION_REQUIREMENTS
        or not requirement_flags_valid
        or authorization_requirements[0] != NEXT_AUTHORIZATION_REQUIREMENT
    ):
        _fail("CPRBAC_REQUIREMENTS_MISMATCH")


def _validate_bindings(
    source: Any,
    intent: ExecutionIntent,
    descriptor: BindAdapterContractDescriptor,
) -> None:
    context = source.exact_bind_context
    final_endpoint = source.final_endpoint_identity_binding
    final_credential = source.final_credential_scope_binding
    reference = source.rechecked_credential_reference
    valid = (
        context.execution_intent_id == intent.execution_intent_id
        and context.execution_intent_hash == source.execution_intent_hash
        and context.adapter_contract_id == descriptor.adapter_contract_id
        and context.adapter_contract_hash == descriptor.adapter_contract_hash
        and context.endpoint_identity_binding_digest
        == source.endpoint_identity_binding_digest
        and context.credential_reference_digest == source.credential_reference_digest
        and context.credential_scope_binding_digest
        == source.credential_scope_binding_digest
        and final_endpoint.get("bind_context_hash") == source.bind_context_hash
        and final_endpoint.get("endpoint_identity_binding_digest")
        == source.endpoint_identity_binding_digest
        and final_credential.get("bind_context_hash") == source.bind_context_hash
        and final_credential.get("final_endpoint_identity_binding_digest")
        == source.final_endpoint_identity_binding_digest
        and final_credential.get("credential_reference_id")
        == reference.credential_reference_id
        and final_credential.get("credential_reference_digest")
        == source.credential_reference_digest
        and final_credential.get("credential_scope_binding_digest")
        == source.credential_scope_binding_digest
        and final_credential.get("required_credential_scope")
        == source.required_credential_scope
        and final_credential.get("bound_credential_scope") == reference.credential_scope
    )
    if not valid:
        _fail("CPRBAC_BINDING_MISMATCH")


def project_verified_promotion_authorization_source(
    source_final_credential_scope_recheck_packet: Any,
) -> VerifiedPromotionAuthorizationSource:
    """Verify and project the source without authorizing or invoking anything."""

    try:
        source = verify_canonical_promotion_live_adapter_dry_run_final_credential_scope_recheck_packet(
            source_final_credential_scope_recheck_packet
        )
    except (
        CanonicalPromotionLiveAdapterDryRunFinalCredentialScopeRecheckError,
        TypeError,
        ValueError,
    ) as exc:
        raise CanonicalPromotionRealBindAuthorizationContractError(
            "CPRBAC_SOURCE_INVALID"
        ) from exc

    _validate_source_state(source)
    intent = _intent(source)
    try:
        descriptor = verify_bind_adapter_contract_descriptor(
            source.adapter_contract_descriptor,
            intent,
        )
    except BindAdapterContractSelectionError as exc:
        raise CanonicalPromotionRealBindAuthorizationContractError(
            "CPRBAC_ADAPTER_CONTRACT_INVALID"
        ) from exc
    if (
        descriptor.adapter_contract_id != source.adapter_contract_id
        or descriptor.adapter_contract_hash != source.adapter_contract_hash
        or descriptor.adapter_contract_version != source.adapter_contract_version
    ):
        _fail("CPRBAC_ADAPTER_CONTRACT_MISMATCH")
    _validate_bindings(source, intent, descriptor)

    return VerifiedPromotionAuthorizationSource(
        contract_version=CONTRACT_VERSION,
        source_format_version=source.format_version,
        source_final_credential_scope_recheck_id=(
            source.promotion_live_adapter_dry_run_final_credential_scope_recheck_id
        ),
        source_final_credential_scope_recheck_hash=(
            source.promotion_live_adapter_dry_run_final_credential_scope_recheck_hash
        ),
        execution_intent=intent.to_dict(),
        execution_intent_id=intent.execution_intent_id,
        execution_intent_hash=source.execution_intent_hash,
        adapter_contract_descriptor=descriptor,
        adapter_contract_id=descriptor.adapter_contract_id,
        adapter_contract_hash=descriptor.adapter_contract_hash,
        adapter_contract_version=descriptor.adapter_contract_version,
        bind_context_hash=source.bind_context_hash,
        endpoint_identity_binding_digest=source.endpoint_identity_binding_digest,
        final_endpoint_identity_binding_digest=(
            source.final_endpoint_identity_binding_digest
        ),
        credential_reference=source.rechecked_credential_reference,
        credential_reference_digest=source.credential_reference_digest,
        credential_scope_binding_digest=source.credential_scope_binding_digest,
        final_credential_scope_binding_digest=(
            source.final_credential_scope_binding_digest
        ),
        authority_evidence_reference_bundle=_mapping(
            source.authority_evidence_reference_bundle,
            "CPRBAC_AUTHORITY_REFERENCE_BUNDLE_INVALID",
        ),
        authority_evidence_reference_bundle_digest=(
            source.authority_evidence_reference_bundle_digest
        ),
        human_approval_reference_bundle=_mapping(
            source.human_approval_reference_bundle,
            "CPRBAC_HUMAN_APPROVAL_REFERENCE_BUNDLE_INVALID",
        ),
        human_approval_reference_bundle_digest=(
            source.human_approval_reference_bundle_digest
        ),
        authorization_routes=_routes(
            AUTHORIZATION_REQUIREMENTS,
            _AUTHORIZATION_OWNERS,
            phase="authorization",
        ),
        invocation_routes=_routes(
            INVOCATION_REQUIREMENTS,
            _INVOCATION_OWNERS,
            phase="invocation",
        ),
        next_authorization_requirement=NEXT_AUTHORIZATION_REQUIREMENT,
        preauthorization_runtime_risk_artifact_required=True,
        bind_time_runtime_risk_recheck_required=True,
        bind_time_runtime_risk_owner=BIND_TIME_RISK_OWNER,
        execution_authorized=False,
        bind_authorization_issued=False,
        request_dispatched=False,
        bind_invoked=False,
        external_effect_used=False,
    )


__all__ = [
    "BIND_TIME_RISK_OWNER",
    "CONTRACT_VERSION",
    "NEXT_AUTHORIZATION_REQUIREMENT",
    "RUNTIME_RISK_ARTIFACT_OWNER",
    "CanonicalPromotionRealBindAuthorizationContractError",
    "RequirementRoute",
    "VerifiedPromotionAuthorizationSource",
    "project_verified_promotion_authorization_source",
]
