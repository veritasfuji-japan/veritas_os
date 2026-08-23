"""Re-verification and temporal validation of Real Bind Authorization v1."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ValidationError

from veritas_os.policy.live_adapter_bind_authorization_contracts import (
    DOMAINS,
    BindAuthorizationTrustInputs,
    LiveAdapterBindAuthorizationError,
    RealBindAuthorizationGovernanceInputs,
)
from veritas_os.policy.live_adapter_bind_authorization_models import (
    CanonicalLiveAdapterBindAuthorizationArtifact,
)
from veritas_os.policy.live_adapter_bind_authorization_codec import (
    _artifact_hash,
    _digest,
    _json,
    _timestamp,
)
from veritas_os.policy.live_adapter_bind_authorization_governance import (
    _source,
    _validate_real_governance_inputs,
    _validate_source,
)
from veritas_os.policy.live_adapter_bind_authorization_checks import (
    _decision_hash,
    _grants,
    _idempotency_key,
    _signature_binding,
    _verify_signed_decision,
    _window,
)
from veritas_os.policy.live_adapter_bind_authorization_requirements import (
    _copied_source_fields,
    _requirement_proofs,
)
from veritas_os.security.hash import sha256_of_canonical_json


def _compare_exact_source(
    artifact: CanonicalLiveAdapterBindAuthorizationArtifact,
    source: Any,
) -> None:
    expected = _copied_source_fields(source)
    raw = artifact.model_dump(mode="json")
    for field, value in expected.items():
        if raw[field] != value:
            raise LiveAdapterBindAuthorizationError("LABA_SOURCE_COPY_MISMATCH:" + field)


def verify_live_adapter_bind_authorization_artifact(
    raw: Any,
    *,
    governance_inputs: RealBindAuthorizationGovernanceInputs,
    trust_inputs: BindAuthorizationTrustInputs,
) -> CanonicalLiveAdapterBindAuthorizationArtifact:
    """Re-verify source, governance, authorizer, grants, hashes and issuer signature."""
    try:
        value = raw.model_dump(mode="json") if isinstance(raw, BaseModel) else raw
        artifact = CanonicalLiveAdapterBindAuthorizationArtifact.model_validate(_json(value))
    except (ValidationError, TypeError, LiveAdapterBindAuthorizationError) as exc:
        raise LiveAdapterBindAuthorizationError("LABA_ARTIFACT_INVALID") from exc

    source = _source(artifact.source_gate_review_packet)
    _validate_source(source)
    _compare_exact_source(artifact, source)

    dumped = artifact.model_dump(mode="json")
    expected_hash = _artifact_hash(dumped)
    if artifact.live_adapter_bind_authorization_hash != expected_hash:
        raise LiveAdapterBindAuthorizationError("LABA_ARTIFACT_HASH_MISMATCH")
    if artifact.live_adapter_bind_authorization_id != f"laba:v1:sha256:{expected_hash}":
        raise LiveAdapterBindAuthorizationError("LABA_ARTIFACT_ID_MISMATCH")

    if artifact.signed_authority_evidence_artifact != _json(
        governance_inputs.signed_authority_evidence_artifact
    ):
        raise LiveAdapterBindAuthorizationError("LABA_AUTHORITY_ARTIFACT_INPUT_MISMATCH")
    if artifact.signed_authority_evidence_artifact_digest != sha256_of_canonical_json(
        artifact.signed_authority_evidence_artifact
    ):
        raise LiveAdapterBindAuthorizationError("LABA_AUTHORITY_ARTIFACT_DIGEST_MISMATCH")

    expected_human = (
        None
        if governance_inputs.signed_human_approval_artifact is None
        else _json(governance_inputs.signed_human_approval_artifact)
    )
    if artifact.signed_human_approval_artifact != expected_human:
        raise LiveAdapterBindAuthorizationError("LABA_HUMAN_APPROVAL_ARTIFACT_INPUT_MISMATCH")
    if artifact.signed_human_approval_artifact is None:
        if artifact.signed_human_approval_artifact_digest is not None:
            raise LiveAdapterBindAuthorizationError(
                "LABA_HUMAN_APPROVAL_ARTIFACT_DIGEST_MISMATCH"
            )
    elif artifact.signed_human_approval_artifact_digest != sha256_of_canonical_json(
        artifact.signed_human_approval_artifact
    ):
        raise LiveAdapterBindAuthorizationError(
            "LABA_HUMAN_APPROVAL_ARTIFACT_DIGEST_MISMATCH"
        )

    governance = _validate_real_governance_inputs(source, governance_inputs)
    if (
        artifact.authority_verification_proof_digest
        != governance.authority_proof.verification_proof_hash
        or artifact.human_approval_requirement_status != governance.human_approval_status
        or artifact.human_approval_verification_proof_digest
        != (
            None
            if governance.human_approval_proof is None
            else governance.human_approval_proof.verification_proof_hash
        )
        or artifact.runtime_authority_status != governance.runtime_result.status
        or artifact.runtime_authority_recommended_outcome
        != governance.runtime_result.recommended_outcome
        or artifact.runtime_authority_result_digest != governance.runtime_result_digest
        or artifact.bind_context_hash != governance.bind_context_hash
    ):
        raise LiveAdapterBindAuthorizationError("LABA_GOVERNANCE_PROOF_MISMATCH")

    decision_artifact, authorizer_binding = _verify_signed_decision(
        artifact.authorization_decision_artifact,
        source=source,
        trust=trust_inputs,
        now=governance_inputs.verification_now,
        expected_valid_from=artifact.valid_from,
        expected_valid_until=artifact.valid_until,
    )
    if artifact.authorization_decision != decision_artifact.decision:
        raise LiveAdapterBindAuthorizationError("LABA_AUTHORIZER_DECISION_COPY_MISMATCH")
    decision_digest = _decision_hash(decision_artifact.decision)
    if (
        artifact.authorization_decision_digest != decision_digest
        or artifact.authorizer_verification != authorizer_binding
    ):
        raise LiveAdapterBindAuthorizationError("LABA_AUTHORIZER_VERIFICATION_MISMATCH")

    authorized_at, start, end = _window(
        source,
        governance,
        decision_artifact.decision,
        artifact.valid_from,
        artifact.valid_until,
    )
    if artifact.authorized_at != authorized_at:
        raise LiveAdapterBindAuthorizationError("LABA_AUTHORIZED_AT_MISMATCH")

    credential_grant, header_grant = _grants(
        source, governance.policy_snapshot_id, governance.bind_context_hash
    )
    credential_digest = _digest(
        DOMAINS["credential_grant"], credential_grant.model_dump(mode="json")
    )
    header_digest = _digest(
        DOMAINS["header_grant"], header_grant.model_dump(mode="json")
    )
    if (
        artifact.credential_resolution_grant != credential_grant
        or artifact.credential_resolution_grant_digest != credential_digest
        or artifact.authorization_header_construction_grant != header_grant
        or artifact.authorization_header_construction_grant_digest != header_digest
    ):
        raise LiveAdapterBindAuthorizationError("LABA_GRANT_MISMATCH")

    idempotency_key = _idempotency_key(
        source,
        decision_digest,
        start,
        end,
        governance.policy_snapshot_id,
        governance.bind_context_hash,
    )
    if artifact.idempotency_key != idempotency_key:
        raise LiveAdapterBindAuthorizationError("LABA_IDEMPOTENCY_MISMATCH")

    expected_requirements = _requirement_proofs(
        source,
        governance,
        authorizer_binding,
        credential_digest,
        header_digest,
        idempotency_key,
        decision_digest,
        _timestamp(governance_inputs.verification_now),
    )
    if artifact.authorization_requirement_proofs != expected_requirements:
        raise LiveAdapterBindAuthorizationError("LABA_REQUIREMENT_PROOFS_MISMATCH")
    if artifact.authorization_requirement_proofs_digest != _digest(
        DOMAINS["requirements"],
        [item.model_dump(mode="json") for item in expected_requirements],
    ):
        raise LiveAdapterBindAuthorizationError("LABA_REQUIREMENT_PROOFS_DIGEST_MISMATCH")

    final_result = trust_inputs.authorization_issuer_signature_verifier.verify(dumped)
    issuer_binding = _signature_binding(
        purpose="authorization_issuer",
        result=final_result,
        signer_policy=trust_inputs.authorization_issuer_signer_policy,
        verifier_policy=trust_inputs.authorization_issuer_verifier_policy,
        verified_at=governance_inputs.verification_now,
    )
    if (
        artifact.authorization_issuer_signer.key_id != issuer_binding.key_id
        or artifact.authorization_issuer_signer.algorithm != issuer_binding.algorithm
        or artifact.authorization_issuer_signer.identity != issuer_binding.signer_identity
        or artifact.authorization_issuer_signer.role != issuer_binding.signer_role
        or artifact.authorization_issuer_verification != issuer_binding
    ):
        raise LiveAdapterBindAuthorizationError("LABA_AUTHORIZATION_ISSUER_MISMATCH")

    signed_at = datetime.fromisoformat(_timestamp(artifact.authorization_signed_at))
    if signed_at > governance_inputs.verification_now.astimezone(timezone.utc):
        raise LiveAdapterBindAuthorizationError("LABA_AUTHORIZATION_SIGNED_AT_FUTURE")
    if not (
        datetime.fromisoformat(artifact.authorized_at)
        <= signed_at
        < datetime.fromisoformat(artifact.valid_until)
    ):
        raise LiveAdapterBindAuthorizationError("LABA_AUTHORIZATION_SIGNATURE_TIME_INVALID")
    return artifact


def validate_live_adapter_bind_authorization_temporal_validity(
    artifact: Any,
    *,
    now: datetime | str,
    governance_inputs: RealBindAuthorizationGovernanceInputs,
    trust_inputs: BindAuthorizationTrustInputs,
) -> CanonicalLiveAdapterBindAuthorizationArtifact:
    """Verify an authorization and enforce its validity window at a supplied time."""
    verified = verify_live_adapter_bind_authorization_artifact(
        artifact,
        governance_inputs=governance_inputs,
        trust_inputs=trust_inputs,
    )
    current = datetime.fromisoformat(_timestamp(now))
    if not (
        datetime.fromisoformat(verified.valid_from)
        <= current
        < datetime.fromisoformat(verified.valid_until)
    ):
        raise LiveAdapterBindAuthorizationError("LABA_NOT_CURRENTLY_VALID")
    return verified
