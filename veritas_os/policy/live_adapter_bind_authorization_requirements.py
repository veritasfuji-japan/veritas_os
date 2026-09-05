"""Requirement proofs and issuer pre-binding for Real Bind Authorization v1."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from veritas_os.policy.canonical_promotion_live_adapter_dry_run_runtime_risk_review import (
    verify_canonical_promotion_live_adapter_dry_run_runtime_risk_review_packet,
)
from veritas_os.policy.canonical_promotion_real_bind_authorization_contract import (
    RequirementRoute,
)

from veritas_os.policy.live_adapter_bind_authorization_contracts import (
    COPIED_FIELDS,
    DOMAINS,
    UPSTREAM_HASH_FIELDS,
    BindAuthorizationSigner,
    BindAuthorizationTrustInputs,
    LiveAdapterBindAuthorizationError,
    _GovernanceOutcome,
)
from veritas_os.policy.live_adapter_bind_authorization_models import (
    AuthorizationRequirementProof,
    VerifiedSignatureBinding,
)
from veritas_os.policy.live_adapter_bind_authorization_codec import _digest, _timestamp
from veritas_os.policy.live_adapter_dry_run_bind_authorization_gate_review import (
    AUTHORIZATION_REQUIREMENTS,
    CanonicalLiveAdapterDryRunBindAuthorizationGateReviewPacket,
)


def _proof(
    ordinal: int,
    requirement: str,
    *,
    status: str,
    evidence_type: str,
    evidence_id: str,
    evidence_digest: str,
    verified_at: str,
    reason_code: str,
) -> AuthorizationRequirementProof:
    return AuthorizationRequirementProof(
        ordinal=ordinal,
        requirement=requirement,
        status=status,
        evidence_type=evidence_type,
        evidence_id=evidence_id,
        evidence_digest=evidence_digest,
        verified_at=verified_at,
        reason_code=reason_code,
    )


def _requirement_proofs(
    source: CanonicalLiveAdapterDryRunBindAuthorizationGateReviewPacket,
    governance: _GovernanceOutcome,
    authorizer_binding: VerifiedSignatureBinding,
    credential_grant_digest: str,
    header_grant_digest: str,
    idempotency_key: str,
    decision_digest: str,
    verified_at: str,
) -> tuple[AuthorizationRequirementProof, ...]:
    """Produce exact ordered evidence for all #2130 authorization requirements."""
    if len(AUTHORIZATION_REQUIREMENTS) != 11:
        raise LiveAdapterBindAuthorizationError("LABA_REQUIREMENTS_MISMATCH")

    human_digest = (
        governance.human_approval_proof.verification_proof_hash
        if governance.human_approval_proof is not None
        else _digest(
            DOMAINS["requirements"],
            {
                "requirement": "real_human_approval_verification_where_required",
                "status": "NOT_REQUIRED",
                "action_contract_id": governance.action_contract_id,
                "action_contract_digest": governance.action_contract_digest,
            },
        )
    )
    human_id = (
        governance.human_approval_proof.receipt.approval_receipt_id
        if governance.human_approval_proof is not None
        else governance.action_contract_id
    )
    endpoint_digest = _digest(
        DOMAINS["requirements"],
        {
            "endpoint_identity_binding_digest": source.endpoint_identity_binding_digest,
            "source_gate_review_hash": (
                source.live_adapter_dry_run_bind_authorization_gate_review_hash
            ),
        },
    )
    idempotency_digest = _digest(
        DOMAINS["requirements"], {"idempotency_key": idempotency_key}
    )
    replay_digest = _digest(
        DOMAINS["requirements"],
        {
            "single_use": True,
            "duplicate_dispatch_prohibited": True,
            "idempotency_key": idempotency_key,
            "source_gate_review_hash": (
                source.live_adapter_dry_run_bind_authorization_gate_review_hash
            ),
        },
    )
    authorizer_digest = _digest(
        DOMAINS["requirements"], authorizer_binding.model_dump(mode="json")
    )
    decision_boundary_digest = _digest(
        DOMAINS["requirements"],
        {
            "authorization_decision_digest": decision_digest,
            "authorizer_verification_digest": authorizer_digest,
            "bind_context_hash": governance.bind_context_hash,
        },
    )

    rows = (
        (
            "VERIFIED",
            "verified_authority_evidence",
            governance.authority_proof.authority_evidence.authority_evidence_id,
            governance.authority_proof.verification_proof_hash,
            "authority_signature_scope_revocation_and_provenance_verified",
        ),
        (
            governance.human_approval_status,
            "verified_human_approval"
            if governance.human_approval_proof
            else "action_contract",
            human_id,
            human_digest,
            (
                "human_approval_signature_context_and_provenance_verified"
                if governance.human_approval_proof
                else "human_approval_not_required_by_action_contract"
            ),
        ),
        (
            "VERIFIED",
            "runtime_authority_result",
            governance.action_contract_id,
            governance.runtime_result_digest,
            "runtime_authority_pass_commit",
        ),
        (
            "VERIFIED",
            "runtime_authority_result",
            governance.action_contract_id,
            governance.runtime_result_digest,
            "runtime_risk_and_fail_closed_predicates_passed",
        ),
        (
            "VERIFIED",
            "endpoint_identity_binding",
            source.endpoint_identity_binding_digest,
            endpoint_digest,
            "endpoint_identity_binding_preserved_from_verified_source",
        ),
        (
            "VERIFIED",
            "credential_resolution_grant",
            source.credential_reference_digest,
            credential_grant_digest,
            "future_credential_resolution_narrowly_authorized_after_consumption",
        ),
        (
            "VERIFIED",
            "authorization_header_construction_grant",
            source.credential_scope_binding_digest,
            header_grant_digest,
            "future_header_construction_narrowly_authorized_after_consumption",
        ),
        (
            "VERIFIED",
            "idempotency_binding",
            idempotency_key,
            idempotency_digest,
            "idempotency_key_binds_exact_authorization_context",
        ),
        (
            "VERIFIED",
            "single_use_replay_policy",
            idempotency_key,
            replay_digest,
            "single_use_and_duplicate_dispatch_prohibition_bound",
        ),
        (
            "VERIFIED",
            "signed_authorizer_decision",
            authorizer_binding.signer_identity,
            authorizer_digest,
            "explicit_human_go_authenticated_and_separate_from_gate_reviewer",
        ),
        (
            "VERIFIED",
            "real_bind_authorization_decision_boundary",
            source.live_adapter_dry_run_bind_authorization_gate_review_id,
            decision_boundary_digest,
            "authorization_decision_is_context_bound_and_non_effecting",
        ),
    )
    return tuple(
        _proof(
            ordinal,
            requirement,
            status=row[0],
            evidence_type=row[1],
            evidence_id=row[2],
            evidence_digest=row[3],
            verified_at=verified_at,
            reason_code=row[4],
        )
        for ordinal, (requirement, row) in enumerate(
            zip(AUTHORIZATION_REQUIREMENTS, rows, strict=True), 1
        )
    )


def _approved_issuer_binding(
    signer: BindAuthorizationSigner,
    trust: BindAuthorizationTrustInputs,
    verified_at: datetime,
) -> VerifiedSignatureBinding:
    """Bind the final signer to an approved deployment verifier before signing."""
    policy = trust.authorization_issuer_signer_policy
    if policy.purpose != "authorization_issuer":
        raise LiveAdapterBindAuthorizationError("LABA_SIGNER_POLICY_PURPOSE_MISMATCH")
    if signer.key_id not in policy.allowed_key_ids:
        raise LiveAdapterBindAuthorizationError("LABA_SIGNER_KEY_UNAPPROVED")
    if signer.algorithm not in policy.allowed_algorithms:
        raise LiveAdapterBindAuthorizationError("LABA_SIGNER_ALGORITHM_UNAPPROVED")
    if signer.identity not in policy.allowed_identities:
        raise LiveAdapterBindAuthorizationError("LABA_SIGNER_IDENTITY_UNAPPROVED")
    if signer.role not in policy.allowed_roles:
        raise LiveAdapterBindAuthorizationError("LABA_SIGNER_ROLE_UNAPPROVED")

    approved = next(
        (
            item
            for item in trust.authorization_issuer_verifier_policy.approved_verifiers
            if item.purpose == "authorization_issuer"
            and item.trust_level == "production"
            and item.verifier_key_id == signer.key_id
            and item.signer_policy_id == policy.policy_id
            and item.signer_policy_hash == policy.deterministic_hash()
        ),
        None,
    )
    if approved is None:
        raise LiveAdapterBindAuthorizationError("LABA_VERIFIER_UNAPPROVED")

    return VerifiedSignatureBinding(
        purpose="authorization_issuer",
        key_id=signer.key_id,
        algorithm=signer.algorithm,
        signer_identity=signer.identity,
        signer_role=signer.role,
        signer_policy_id=policy.policy_id,
        signer_policy_hash=policy.deterministic_hash(),
        verifier_id=approved.verifier_id,
        verifier_trust_level="production",
        verifier_key_id=approved.verifier_key_id,
        verifier_policy_id=approved.verifier_policy_id,
        verifier_policy_hash=approved.verifier_policy_hash,
        verified_at=_timestamp(verified_at),
    )


def _copied_source_fields(
    source: CanonicalLiveAdapterDryRunBindAuthorizationGateReviewPacket,
) -> dict[str, object]:
    """Copy all exact source fields and upstream hashes into the authorization."""
    raw = source.model_dump(mode="json")
    result: dict[str, object] = {
        "source_gate_review_id": (
            source.live_adapter_dry_run_bind_authorization_gate_review_id
        ),
        "source_gate_review_hash": (
            source.live_adapter_dry_run_bind_authorization_gate_review_hash
        ),
        "source_gate_review_packet": raw,
    }
    for field in UPSTREAM_HASH_FIELDS:
        result[field] = raw[field]
    for field in COPIED_FIELDS:
        result[field] = raw[field]
    return result


class PromotionIdempotencyReplayReview(BaseModel):
    """Inert review of replay requirements, never proof of an unused key.

    The final authorization key needs the signed decision and validity window
    and therefore cannot be issued at this stage. Atomic consumption remains
    mandatory before credential access. This artifact makes no store query,
    reservation, duplicate-absence claim, or execution-authority claim.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    format_version: Literal["promotion-idempotency-replay-review/v1"]
    review_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_runtime_risk_review_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_projection_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewed_at: str
    valid_until: str
    requirement: Literal["idempotency_and_replay_review"]
    requirement_satisfied: Literal[True]
    remaining_authorization_routes: tuple[RequirementRoute, ...]
    remaining_invocation_routes: tuple[RequirementRoute, ...]
    next_authorization_requirement: Literal["signed_gate_bound_human_approval_issuance"]
    final_authorization_key_required: Literal[True]
    final_authorization_key_owner: Literal[
        "veritas_os.policy.live_adapter_bind_authorization_checks"
    ]
    atomic_consumption_owner: Literal[
        "veritas_os.policy.live_adapter_bind_authorization_consumption"
    ]
    atomic_consumption_before_credentials_required: Literal[True]
    single_use_required: Literal[True]
    duplicate_dispatch_prohibited: Literal[True]
    bind_time_runtime_risk_recheck_required: Literal[True]
    duplicate_absence_verified: Literal[False]
    authorization_consumed: Literal[False]
    execution_authorized: Literal[False]
    bind_invoked: Literal[False]
    request_dispatched: Literal[False]


def _promotion_review_time(value: datetime) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise LiveAdapterBindAuthorizationError("LABA_PROMOTION_REVIEW_TIME_INVALID")
    return value.astimezone(timezone.utc)


def review_promotion_idempotency_and_replay(
    runtime_risk_review: Any,
    source_final_credential_scope_recheck_packet: Any,
    *,
    reviewed_at: datetime,
) -> PromotionIdempotencyReplayReview:
    """Verify a fresh passing source and preserve existing consumption owners.

    Raises:
        LiveAdapterBindAuthorizationError: Source is invalid, blocked, expired,
            or does not route through the existing replay/consumption owners.
    """
    current = _promotion_review_time(reviewed_at)
    try:
        source = (
            verify_canonical_promotion_live_adapter_dry_run_runtime_risk_review_packet(
                runtime_risk_review, source_final_credential_scope_recheck_packet
            )
        )
    except (TypeError, ValueError) as exc:
        raise LiveAdapterBindAuthorizationError(
            "LABA_PROMOTION_RISK_SOURCE_INVALID"
        ) from exc
    if (
        source.fail_closed
        or not source.runtime_risk_requirement_satisfied
        or not source.ready_for_remaining_real_bind_authorization_requirements
    ):
        raise LiveAdapterBindAuthorizationError("LABA_PROMOTION_RISK_NOT_PASSED")
    recorded = datetime.fromisoformat(source.runtime_risk_review_recorded_at)
    deadline = datetime.fromisoformat(source.runtime_risk_review_decision.valid_until)
    if not recorded <= current < deadline:
        raise LiveAdapterBindAuthorizationError("LABA_PROMOTION_RISK_NOT_FRESH")
    routes = source.remaining_authorization_routes
    invocation = {
        route.requirement: route for route in source.remaining_invocation_routes
    }
    owner = "veritas_os.policy.live_adapter_bind_authorization_consumption"
    if (
        len(routes) < 2
        or routes[0].requirement != "idempotency_and_replay_review"
        or routes[0].implementation_owner != __name__
        or routes[1].requirement != "signed_gate_bound_human_approval_issuance"
        or any(
            name not in invocation or invocation[name].implementation_owner != owner
            for name in ("authorization_consumption", "single_use_consumption")
        )
    ):
        raise LiveAdapterBindAuthorizationError("LABA_PROMOTION_REPLAY_ROUTE_INVALID")
    body = {
        "format_version": "promotion-idempotency-replay-review/v1",
        "source_runtime_risk_review_hash": source.promotion_live_adapter_dry_run_runtime_risk_review_hash,
        "source_projection_digest": source.source_authorization_projection_digest,
        "reviewed_at": current.isoformat(),
        "valid_until": deadline.astimezone(timezone.utc).isoformat(),
        "requirement": "idempotency_and_replay_review",
        "requirement_satisfied": True,
        "remaining_authorization_routes": routes[1:],
        "remaining_invocation_routes": source.remaining_invocation_routes,
        "next_authorization_requirement": routes[1].requirement,
        "final_authorization_key_required": True,
        "final_authorization_key_owner": "veritas_os.policy.live_adapter_bind_authorization_checks",
        "atomic_consumption_owner": owner,
        "atomic_consumption_before_credentials_required": True,
        "single_use_required": True,
        "duplicate_dispatch_prohibited": True,
        "bind_time_runtime_risk_recheck_required": True,
        "duplicate_absence_verified": False,
        "authorization_consumed": False,
        "execution_authorized": False,
        "bind_invoked": False,
        "request_dispatched": False,
    }
    candidate = PromotionIdempotencyReplayReview(review_hash="0" * 64, **body)
    canonical = candidate.model_dump(mode="json", exclude={"review_hash"})
    return candidate.model_copy(
        update={
            "review_hash": _digest("promotion-idempotency-replay-review/v1", canonical)
        }
    )


def verify_promotion_idempotency_replay_review(
    review: Any,
    runtime_risk_review: Any,
    source_final_credential_scope_recheck_packet: Any,
    *,
    now: datetime,
) -> PromotionIdempotencyReplayReview:
    """Reconstruct against full independent sources and check freshness now."""
    current = _promotion_review_time(now)
    try:
        raw = (
            review.model_dump(mode="json") if isinstance(review, BaseModel) else review
        )
        if not isinstance(raw, dict):
            raise ValueError("review must be a mapping")
        recorded = datetime.fromisoformat(raw["reviewed_at"])
        expected = review_promotion_idempotency_and_replay(
            runtime_risk_review,
            source_final_credential_scope_recheck_packet,
            reviewed_at=recorded,
        )
        if _digest("promotion-replay-verification/v1", raw) != _digest(
            "promotion-replay-verification/v1", expected.model_dump(mode="json")
        ):
            raise ValueError("review reconstruction mismatch")
        if not recorded <= current < datetime.fromisoformat(expected.valid_until):
            raise ValueError("review expired or not yet valid")
    except (KeyError, TypeError, ValueError) as exc:
        raise LiveAdapterBindAuthorizationError(
            "LABA_PROMOTION_REPLAY_REVIEW_INVALID"
        ) from exc
    return expected
