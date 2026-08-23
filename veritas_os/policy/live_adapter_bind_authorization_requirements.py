"""Requirement proofs and issuer pre-binding for Real Bind Authorization v1."""

from __future__ import annotations

from datetime import datetime

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
            "verified_human_approval" if governance.human_approval_proof else "action_contract",
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
            zip(AUTHORIZATION_REQUIREMENTS, rows), 1
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
