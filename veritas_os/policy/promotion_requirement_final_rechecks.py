"""Reverify requirement-aware Gate and exact endpoint/credential metadata.

Freshness means local verification at an independently supplied time, not a
claim of live policy, revocation, TLS, or credential-provider verification.
The caller supplies trusted source/policy and current reference metadata.
No credential material, network access, authorization, or effect is produced.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from veritas_os.governance.action_contracts import ActionClassContract
from veritas_os.policy.human_approval_requirement_resolution import _json, _timestamp
from veritas_os.policy.promotion_requirement_bind_readiness import (
    verify_promotion_requirement_bind_gate_packet as verify_gate,
)
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_authority_evidence_linkage import (
    CanonicalPromotionLiveAdapterDryRunAuthorityEvidenceLinkageReviewPacket,
)
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_final_endpoint_identity_recheck import (
    _candidate as validate_endpoint,
)
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_final_credential_scope_recheck import (
    _reference as validate_reference,
    _scope as validate_scope,
)
from veritas_os.security.hash import sha256_of_canonical_json

CONTEXT_FIELDS = (
    "execution_intent_id",
    "execution_intent_hash",
    "adapter_contract_id",
    "adapter_contract_hash",
    "adapter_contract_version",
    "endpoint_candidate_digest",
    "endpoint_identity_binding_digest",
    "credential_reference_digest",
    "credential_scope_binding_digest",
    "credential_policy_snapshot_hash",
    "credential_authorization_result_digest",
)
ABSENT_FIELDS = (
    "human_approval_created",
    "human_approval_proven",
    "authority_evidence_proven",
    "execution_authority_created",
    "bind_authorization_created",
    "bind_invoked",
    "bind_receipt_created",
    "credential_material_accessed",
    "network_used",
    "external_effect_occurred",
    "ready_for_real_bind",
)


class PromotionRequirementRecheckError(ValueError):
    """Invalid or mismatched independently supplied verification inputs."""


class ExactRequirementBindContext(BaseModel):
    """Commit native identities and independent policy without legacy fields."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    gate_packet_hash: str
    authority_source_hash: str
    action_contract_digest: str
    requirement_resolution_hash: str
    required_human_approval: bool
    execution_intent_id: str
    execution_intent_hash: str
    adapter_contract_id: str
    adapter_contract_hash: str
    adapter_contract_version: str
    endpoint_candidate_digest: str
    endpoint_identity_binding_digest: str
    credential_reference_digest: str
    credential_scope_binding_digest: str
    credential_policy_snapshot_hash: str
    credential_authorization_result_digest: str


class _RecheckPacket(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    packet_id: str
    packet_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_packet: dict[str, Any]
    source_packet_id: str
    source_packet_hash: str
    exact_bind_context: ExactRequirementBindContext
    bind_context_hash: str
    execution_intent: dict[str, Any]
    required_human_approval: bool
    future_authorization_requirements: list[str]
    future_invocation_requirements: list[str]
    fail_closed: Literal[False]
    human_approval_created: Literal[False]
    human_approval_proven: Literal[False]
    authority_evidence_proven: Literal[False]
    execution_authority_created: Literal[False]
    bind_authorization_created: Literal[False]
    bind_invoked: Literal[False]
    bind_receipt_created: Literal[False]
    credential_material_accessed: Literal[False]
    network_used: Literal[False]
    external_effect_occurred: Literal[False]
    ready_for_real_bind: Literal[False]
    external_policy_freshness_verified: Literal[False]
    revocation_verified: Literal[False]
    tls_peer_verified: Literal[False]
    credential_provider_verified: Literal[False]


class PromotionRequirementFreshSourcePacket(_RecheckPacket):
    """Full Gate reverification and exact context derivation at caller time."""

    format_version: Literal["promotion-requirement-fresh-source/v1"]
    fresh_verified_at: str
    fresh_source_reverified: Literal[True]
    bind_context_hash_derived: Literal[True]
    endpoint_rechecked: Literal[False]
    credential_scope_rechecked: Literal[False]


class PromotionRequirementFinalRecheckPacket(_RecheckPacket):
    """Exact local endpoint and credential checks against fresh bound context."""

    format_version: Literal["promotion-requirement-final-recheck/v1"]
    rechecked_at: str
    rechecked_endpoint_candidate: dict[str, Any]
    rechecked_credential_reference: dict[str, Any]
    required_credential_scope: str
    endpoint_rechecked: Literal[True]
    credential_scope_rechecked: Literal[True]
    scope_containment_inferred: Literal[False]


def _digest(domain: str, value: Any) -> str:
    return sha256_of_canonical_json({"domain": domain, "value": _json(value)})


def _packet_hash(raw: dict[str, Any]) -> str:
    return _digest(
        "veritas." + raw["format_version"],
        {k: v for k, v in raw.items() if k not in {"packet_id", "packet_hash"}},
    )


def _seal(raw: dict[str, Any]) -> dict[str, Any]:
    digest = _packet_hash(raw)
    return {
        **raw,
        "packet_hash": digest,
        "packet_id": f"{raw['format_version']}:sha256:{digest}",
    }


def _ordered(*timestamps: Any) -> None:
    times = [datetime.fromisoformat(_timestamp(value)) for value in timestamps]
    if any(left > right for left, right in zip(times, times[1:], strict=False)):
        raise PromotionRequirementRecheckError("PRRC_TIMESTAMP_ORDER")


def _remaining(requirements: list[str], completed: tuple[str, ...]) -> list[str]:
    if requirements[: len(completed)] != list(completed):
        raise PromotionRequirementRecheckError("PRRC_REQUIREMENT_ORDER")
    return requirements[len(completed) :]


def _common(source: Any, context: ExactRequirementBindContext) -> dict[str, Any]:
    return {
        "source_packet": source.model_dump(mode="json"),
        "source_packet_id": source.packet_id,
        "source_packet_hash": source.packet_hash,
        "exact_bind_context": context.model_dump(mode="json"),
        "bind_context_hash": _digest(
            "veritas.requirement-exact-bind-context/v1", context
        ),
        "execution_intent": source.execution_intent,
        "required_human_approval": source.required_human_approval,
        "future_invocation_requirements": source.future_invocation_requirements,
        "fail_closed": False,
        **{name: getattr(source, name) for name in ABSENT_FIELDS},
        "external_policy_freshness_verified": False,
        "revocation_verified": False,
        "tls_peer_verified": False,
        "credential_provider_verified": False,
    }


def _authority_from_rebuilt_gate(
    gate: dict[str, Any],
) -> CanonicalPromotionLiveAdapterDryRunAuthorityEvidenceLinkageReviewPacket:
    """Project a child only after the parent verifier fully reconstructs it.

    This helper performs no admission. Both callers first run the complete gate
    chain against their mandatory external source and contract. An input packet,
    matching hash, model type, or embedded snapshot never substitutes for that.
    """
    satisfaction = gate["source_packet"]["source_packet"]
    return CanonicalPromotionLiveAdapterDryRunAuthorityEvidenceLinkageReviewPacket.model_validate(
        satisfaction["source_authority_evidence_linkage_review_packet"],
    )


def build_promotion_requirement_fresh_source_packet(
    gate: Any,
    fresh_verified_at: datetime,
    *,
    expected_source: Any,
    expected_contract: ActionClassContract,
) -> PromotionRequirementFreshSourcePacket:
    """Reverify Gate using external anchors and derive its exact Bind context."""
    verified = verify_gate(
        gate, expected_source=expected_source, expected_contract=expected_contract
    )
    if verified.fail_closed or not verified.ready_for_fresh_verified_source_gate:
        raise PromotionRequirementRecheckError("PRRC_GATE_REJECTED")
    source = _authority_from_rebuilt_gate(verified.model_dump(mode="json"))
    _ordered(verified.recorded_at, fresh_verified_at)
    context = ExactRequirementBindContext(
        gate_packet_hash=verified.packet_hash,
        authority_source_hash=verified.source_authority_evidence_linkage_review_hash,
        action_contract_digest=verified.action_contract_digest,
        requirement_resolution_hash=verified.requirement_resolution_hash,
        required_human_approval=verified.required_human_approval,
        **{name: getattr(source, name) for name in CONTEXT_FIELDS},
    )
    return PromotionRequirementFreshSourcePacket.model_validate(
        _seal(
            {
                **_common(verified, context),
                "format_version": "promotion-requirement-fresh-source/v1",
                "fresh_verified_at": _timestamp(fresh_verified_at),
                "future_authorization_requirements": _remaining(
                    verified.future_authorization_requirements,
                    (
                        "fresh_verified_source_gate",
                        "exact_bind_context_hash_derivation",
                    ),
                ),
                "fresh_source_reverified": True,
                "bind_context_hash_derived": True,
                "endpoint_rechecked": False,
                "credential_scope_rechecked": False,
            }
        )
    )


def verify_promotion_requirement_fresh_source_packet(
    packet: Any,
    *,
    expected_source: Any,
    expected_contract: ActionClassContract,
    expected_verified_at: datetime,
) -> PromotionRequirementFreshSourcePacket:
    """Return reconstruction against external source, policy, and time."""
    candidate = PromotionRequirementFreshSourcePacket.model_validate(_json(packet))
    rebuilt = build_promotion_requirement_fresh_source_packet(
        candidate.source_packet,
        expected_verified_at,
        expected_source=expected_source,
        expected_contract=expected_contract,
    )
    # Input was normalized before schema validation; builders return JSON-valued
    # fields. Compare every field without recursively normalizing both again.
    if candidate.model_dump(mode="python") != rebuilt.model_dump(mode="python"):
        raise PromotionRequirementRecheckError("PRRC_RECONSTRUCTION_MISMATCH")
    return rebuilt


def build_promotion_requirement_final_recheck_packet(
    fresh: Any,
    rechecked_at: datetime,
    *,
    expected_source: Any,
    expected_contract: ActionClassContract,
    expected_verified_at: datetime,
    current_endpoint: Any,
    current_credential_reference: Any,
    required_credential_scope: str,
) -> PromotionRequirementFinalRecheckPacket:
    """Compare external current metadata exactly; never resolve credentials."""
    verified = verify_promotion_requirement_fresh_source_packet(
        fresh,
        expected_source=expected_source,
        expected_contract=expected_contract,
        expected_verified_at=expected_verified_at,
    )
    source = _authority_from_rebuilt_gate(verified.source_packet)
    endpoint = validate_endpoint(current_endpoint)
    reference = validate_reference(current_credential_reference)
    scope = validate_scope(required_credential_scope)
    if endpoint.model_dump(mode="json") != _json(source.endpoint_candidate):
        raise PromotionRequirementRecheckError("PRRC_ENDPOINT_MISMATCH")
    if reference.model_dump(mode="json") != _json(source.credential_reference):
        raise PromotionRequirementRecheckError("PRRC_CREDENTIAL_MISMATCH")
    if scope != reference.credential_scope:
        raise PromotionRequirementRecheckError("PRRC_SCOPE_MISMATCH")
    _ordered(verified.fresh_verified_at, rechecked_at)
    _ordered(endpoint.declared_at, rechecked_at)
    _ordered(reference.declared_at, rechecked_at)
    return PromotionRequirementFinalRecheckPacket.model_validate(
        _seal(
            {
                **_common(verified, verified.exact_bind_context),
                "format_version": "promotion-requirement-final-recheck/v1",
                "rechecked_at": _timestamp(rechecked_at),
                "rechecked_endpoint_candidate": endpoint.model_dump(mode="json"),
                "rechecked_credential_reference": reference.model_dump(mode="json"),
                "required_credential_scope": scope,
                "future_authorization_requirements": _remaining(
                    verified.future_authorization_requirements,
                    (
                        "final_endpoint_identity_recheck",
                        "final_credential_scope_recheck",
                    ),
                ),
                "endpoint_rechecked": True,
                "credential_scope_rechecked": True,
                "scope_containment_inferred": False,
            }
        )
    )


def verify_promotion_requirement_final_recheck_packet(
    packet: Any,
    *,
    expected_source: Any,
    expected_contract: ActionClassContract,
    expected_verified_at: datetime,
    expected_rechecked_at: datetime,
    current_endpoint: Any,
    current_credential_reference: Any,
    required_credential_scope: str,
) -> PromotionRequirementFinalRecheckPacket:
    """Rebuild all fields without treating embedded recheck values as current."""
    candidate = PromotionRequirementFinalRecheckPacket.model_validate(_json(packet))
    rebuilt = build_promotion_requirement_final_recheck_packet(
        candidate.source_packet,
        expected_rechecked_at,
        expected_source=expected_source,
        expected_contract=expected_contract,
        expected_verified_at=expected_verified_at,
        current_endpoint=current_endpoint,
        current_credential_reference=current_credential_reference,
        required_credential_scope=required_credential_scope,
    )
    # Input was normalized before schema validation; builders return JSON-valued
    # fields. Compare every field without recursively normalizing both again.
    if candidate.model_dump(mode="python") != rebuilt.model_dump(mode="python"):
        raise PromotionRequirementRecheckError("PRRC_RECONSTRUCTION_MISMATCH")
    return rebuilt
