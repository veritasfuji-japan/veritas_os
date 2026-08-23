"""Authenticated authorizer, grants and idempotency checks for Real Bind Authorization v1."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import ValidationError

from veritas_os.policy.live_adapter_bind_authorization_contracts import (
    DOMAINS,
    BindAuthorizationSignatureVerificationResult,
    BindAuthorizationSignerPolicy,
    BindAuthorizationTrustInputs,
    BindAuthorizationVerifierPolicy,
    LiveAdapterBindAuthorizationError,
    SignaturePurpose,
    _GovernanceOutcome,
)
from veritas_os.policy.live_adapter_bind_authorization_models import (
    AuthorizationHeaderConstructionGrant,
    BindAuthorizationDecision,
    CredentialResolutionGrant,
    SignedBindAuthorizationDecisionArtifact,
    VerifiedSignatureBinding,
)
from veritas_os.policy.live_adapter_bind_authorization_codec import (
    _digest,
    _json,
    _timestamp,
)
from veritas_os.policy.live_adapter_dry_run_bind_authorization_gate_review import (
    CanonicalLiveAdapterDryRunBindAuthorizationGateReviewPacket,
)


def _decision_hash(decision: BindAuthorizationDecision) -> str:
    return _digest(DOMAINS["decision"], decision.model_dump(mode="json"))


def _signature_binding(
    *,
    purpose: SignaturePurpose,
    result: BindAuthorizationSignatureVerificationResult,
    signer_policy: BindAuthorizationSignerPolicy,
    verifier_policy: BindAuthorizationVerifierPolicy,
    verified_at: datetime,
) -> VerifiedSignatureBinding:
    """Validate deployment-controlled signer/verifier provenance fail closed."""
    if result.verified is not True:
        raise LiveAdapterBindAuthorizationError("LABA_SIGNATURE_INVALID")
    values = (
        result.key_id,
        result.algorithm,
        result.signer_identity,
        result.signer_role,
        result.verifier_id,
        result.verifier_trust_level,
        result.verifier_key_id,
        result.verifier_policy_id,
        result.verifier_policy_hash,
    )
    if any(not str(value or "").strip() for value in values):
        raise LiveAdapterBindAuthorizationError(
            "LABA_SIGNATURE_VERIFIER_METADATA_INCOMPLETE"
        )
    if result.verifier_trust_level != "production":
        raise LiveAdapterBindAuthorizationError("LABA_PRODUCTION_VERIFIER_REQUIRED")
    if signer_policy.purpose != purpose:
        raise LiveAdapterBindAuthorizationError("LABA_SIGNER_POLICY_PURPOSE_MISMATCH")
    if result.key_id not in signer_policy.allowed_key_ids:
        raise LiveAdapterBindAuthorizationError("LABA_SIGNER_KEY_UNAPPROVED")
    if result.algorithm not in signer_policy.allowed_algorithms:
        raise LiveAdapterBindAuthorizationError("LABA_SIGNER_ALGORITHM_UNAPPROVED")
    if result.signer_identity not in signer_policy.allowed_identities:
        raise LiveAdapterBindAuthorizationError("LABA_SIGNER_IDENTITY_UNAPPROVED")
    if result.signer_role not in signer_policy.allowed_roles:
        raise LiveAdapterBindAuthorizationError("LABA_SIGNER_ROLE_UNAPPROVED")

    approved = verifier_policy.approved_by_id(str(result.verifier_id))
    if approved is None:
        raise LiveAdapterBindAuthorizationError("LABA_VERIFIER_UNAPPROVED")
    if approved.purpose != purpose or approved.trust_level != "production":
        raise LiveAdapterBindAuthorizationError("LABA_VERIFIER_POLICY_MISMATCH")
    expected = (
        approved.verifier_key_id,
        approved.verifier_policy_id,
        approved.verifier_policy_hash,
        approved.signer_policy_id,
        approved.signer_policy_hash,
    )
    actual = (
        result.verifier_key_id,
        result.verifier_policy_id,
        result.verifier_policy_hash,
        signer_policy.policy_id,
        signer_policy.deterministic_hash(),
    )
    if actual != expected:
        raise LiveAdapterBindAuthorizationError("LABA_VERIFIER_POLICY_MISMATCH")

    return VerifiedSignatureBinding(
        purpose=purpose,
        key_id=str(result.key_id),
        algorithm=str(result.algorithm),
        signer_identity=str(result.signer_identity),
        signer_role=str(result.signer_role),
        signer_policy_id=signer_policy.policy_id,
        signer_policy_hash=signer_policy.deterministic_hash(),
        verifier_id=str(result.verifier_id),
        verifier_trust_level="production",
        verifier_key_id=str(result.verifier_key_id),
        verifier_policy_id=str(result.verifier_policy_id),
        verifier_policy_hash=str(result.verifier_policy_hash),
        verified_at=_timestamp(verified_at),
    )


def _verify_signed_decision(
    raw: Any,
    *,
    source: CanonicalLiveAdapterDryRunBindAuthorizationGateReviewPacket,
    trust: BindAuthorizationTrustInputs,
    now: datetime,
    expected_valid_from: str,
    expected_valid_until: str,
) -> tuple[SignedBindAuthorizationDecisionArtifact, VerifiedSignatureBinding]:
    """Authenticate an exact GO decision and enforce reviewer/authorizer separation."""
    try:
        artifact = SignedBindAuthorizationDecisionArtifact.model_validate(_json(raw))
    except (ValidationError, TypeError, LiveAdapterBindAuthorizationError) as exc:
        raise LiveAdapterBindAuthorizationError(
            "LABA_AUTHORIZER_DECISION_ARTIFACT_INVALID"
        ) from exc

    decision = artifact.decision
    expected_hash = _decision_hash(decision)
    if artifact.decision_hash != expected_hash:
        raise LiveAdapterBindAuthorizationError("LABA_AUTHORIZER_DECISION_HASH_MISMATCH")

    current = now.astimezone(timezone.utc)
    signed_at = datetime.fromisoformat(_timestamp(artifact.signed_at))
    authorized_at = datetime.fromisoformat(_timestamp(decision.authorized_at))
    if signed_at > current:
        raise LiveAdapterBindAuthorizationError("LABA_AUTHORIZER_SIGNED_AT_FUTURE")
    if signed_at < authorized_at:
        raise LiveAdapterBindAuthorizationError("LABA_AUTHORIZER_SIGNED_BEFORE_DECISION")
    if signed_at >= datetime.fromisoformat(_timestamp(decision.valid_until)):
        raise LiveAdapterBindAuthorizationError("LABA_AUTHORIZER_SIGNED_AFTER_VALIDITY")

    expected_context = {
        "source_gate_review_id": (
            source.live_adapter_dry_run_bind_authorization_gate_review_id
        ),
        "source_gate_review_hash": (
            source.live_adapter_dry_run_bind_authorization_gate_review_hash
        ),
        "execution_intent_id": source.execution_intent_id,
        "execution_intent_hash": source.execution_intent_hash,
        "adapter_contract_id": source.adapter_contract_id,
        "adapter_contract_hash": source.adapter_contract_hash,
        "endpoint_identity_binding_digest": source.endpoint_identity_binding_digest,
        "credential_reference_digest": source.credential_reference_digest,
        "credential_scope_binding_digest": source.credential_scope_binding_digest,
        "policy_snapshot_id": str(source.execution_intent.get("policy_snapshot_id") or ""),
        "valid_from": expected_valid_from,
        "valid_until": expected_valid_until,
    }
    for field, expected in expected_context.items():
        if getattr(decision, field) != expected:
            raise LiveAdapterBindAuthorizationError(
                "LABA_AUTHORIZER_DECISION_CONTEXT_MISMATCH:" + field
            )

    result = trust.authorizer_signature_verifier.verify(artifact.model_dump(mode="json"))
    binding = _signature_binding(
        purpose="authorizer_decision",
        result=result,
        signer_policy=trust.authorizer_signer_policy,
        verifier_policy=trust.authorizer_verifier_policy,
        verified_at=now,
    )
    if (
        artifact.signer.key_id != binding.key_id
        or artifact.signer.algorithm != binding.algorithm
        or artifact.signer.identity != binding.signer_identity
        or artifact.signer.role != binding.signer_role
        or decision.authorizer_id != binding.signer_identity
        or decision.authorizer_role != binding.signer_role
    ):
        raise LiveAdapterBindAuthorizationError("LABA_AUTHORIZER_SIGNER_CLAIM_MISMATCH")

    reviewer = source.bind_authorization_gate_review_decision.reviewer_id.strip()
    if reviewer == binding.signer_identity.strip():
        raise LiveAdapterBindAuthorizationError(
            "LABA_REVIEWER_AUTHORIZER_SEPARATION_VIOLATION"
        )
    return artifact, binding


def _window(
    source: CanonicalLiveAdapterDryRunBindAuthorizationGateReviewPacket,
    governance: _GovernanceOutcome,
    decision: BindAuthorizationDecision,
    valid_from: Any,
    valid_until: Any,
) -> tuple[str, str, str]:
    """Validate authorization lifetime against source, intent, authority, and approval."""
    authorized_at = _timestamp(decision.authorized_at)
    start = _timestamp(valid_from)
    end = _timestamp(valid_until)
    authorized_dt = datetime.fromisoformat(authorized_at)
    start_dt = datetime.fromisoformat(start)
    end_dt = datetime.fromisoformat(end)
    if end_dt <= start_dt or not start_dt <= authorized_dt < end_dt:
        raise LiveAdapterBindAuthorizationError("LABA_VALIDITY_WINDOW_INVALID")

    reviewed_at = datetime.fromisoformat(
        _timestamp(source.bind_authorization_gate_review_decision.reviewed_at)
    )
    if start_dt < reviewed_at:
        raise LiveAdapterBindAuthorizationError("LABA_VALIDITY_PRECEDES_GATE_REVIEW")

    intent = source.execution_intent
    ttl = intent.get("ttl_seconds")
    decision_ts = intent.get("decision_ts")
    if ttl is not None:
        if not isinstance(ttl, int) or ttl <= 0 or not decision_ts:
            raise LiveAdapterBindAuthorizationError("LABA_INTENT_TTL_INVALID")
        intent_start = datetime.fromisoformat(_timestamp(decision_ts))
        intent_end = intent_start + timedelta(seconds=ttl)
        if start_dt < intent_start or end_dt > intent_end:
            raise LiveAdapterBindAuthorizationError("LABA_VALIDITY_EXCEEDS_INTENT")

    authority = governance.authority_proof.authority_evidence
    authority_start = datetime.fromisoformat(_timestamp(authority.valid_from))
    authority_end = datetime.fromisoformat(_timestamp(authority.valid_until))
    if start_dt < authority_start or end_dt > authority_end:
        raise LiveAdapterBindAuthorizationError("LABA_VALIDITY_EXCEEDS_AUTHORITY")

    if governance.human_approval_proof is not None:
        approval_end = datetime.fromisoformat(
            _timestamp(governance.human_approval_proof.receipt.expires_at)
        )
        if end_dt > approval_end:
            raise LiveAdapterBindAuthorizationError(
                "LABA_VALIDITY_EXCEEDS_HUMAN_APPROVAL"
            )

    if decision.valid_from != start or decision.valid_until != end:
        raise LiveAdapterBindAuthorizationError("LABA_AUTHORIZER_DECISION_WINDOW_MISMATCH")
    return authorized_at, start, end


def _grants(
    source: CanonicalLiveAdapterDryRunBindAuthorizationGateReviewPacket,
    policy_snapshot_id: str,
    bind_context_hash: str,
) -> tuple[CredentialResolutionGrant, AuthorizationHeaderConstructionGrant]:
    """Derive narrow future permissions; neither grant performs the operation now."""
    credential = CredentialResolutionGrant(
        grant_version="credential-resolution-grant/v1",
        allowed=True,
        credential_reference_digest=source.credential_reference_digest,
        credential_scope_binding_digest=source.credential_scope_binding_digest,
        execution_intent_id=source.execution_intent_id,
        execution_intent_hash=source.execution_intent_hash,
        adapter_contract_hash=source.adapter_contract_hash,
        endpoint_identity_binding_digest=source.endpoint_identity_binding_digest,
        policy_snapshot_id=policy_snapshot_id,
        source_gate_review_hash=(
            source.live_adapter_dry_run_bind_authorization_gate_review_hash
        ),
        bind_context_hash=bind_context_hash,
        consumption_required=True,
    )
    header = AuthorizationHeaderConstructionGrant(
        grant_version="authorization-header-construction-grant/v1",
        allowed=True,
        credential_reference_digest=source.credential_reference_digest,
        credential_scope_binding_digest=source.credential_scope_binding_digest,
        execution_intent_hash=source.execution_intent_hash,
        adapter_contract_hash=source.adapter_contract_hash,
        endpoint_identity_binding_digest=source.endpoint_identity_binding_digest,
        policy_snapshot_id=policy_snapshot_id,
        source_gate_review_hash=(
            source.live_adapter_dry_run_bind_authorization_gate_review_hash
        ),
        bind_context_hash=bind_context_hash,
        consumption_required=True,
    )
    return credential, header


def _idempotency_key(
    source: CanonicalLiveAdapterDryRunBindAuthorizationGateReviewPacket,
    decision_digest: str,
    valid_from: str,
    valid_until: str,
    policy_snapshot_id: str,
    bind_context_hash: str,
) -> str:
    digest = _digest(
        DOMAINS["idempotency"],
        {
            "source_gate_review_hash": (
                source.live_adapter_dry_run_bind_authorization_gate_review_hash
            ),
            "execution_intent_hash": source.execution_intent_hash,
            "adapter_contract_hash": source.adapter_contract_hash,
            "endpoint_identity_binding_digest": source.endpoint_identity_binding_digest,
            "credential_reference_digest": source.credential_reference_digest,
            "credential_scope_binding_digest": source.credential_scope_binding_digest,
            "authorization_decision_digest": decision_digest,
            "valid_from": valid_from,
            "valid_until": valid_until,
            "policy_snapshot_id": policy_snapshot_id,
            "bind_context_hash": bind_context_hash,
        },
    )
    return f"laba-idem:v1:sha256:{digest}"
