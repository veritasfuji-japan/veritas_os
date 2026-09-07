"""Non-effecting issuance of signed Real Bind Authorization v1."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any

from veritas_os.policy.live_adapter_bind_authorization_contracts import (
    AUTHORIZATION_ARTIFACT_TYPE,
    AUTHORIZATION_ARTIFACT_VERSION,
    DOMAINS,
    EFFECT_FIELDS,
    FORMAT_VERSION,
    MECHANISM,
    STATUS,
    BindAuthorizationSigner,
    BindAuthorizationTrustInputs,
    LiveAdapterBindAuthorizationError,
    RealBindAuthorizationGovernanceInputs,
)
from veritas_os.policy.live_adapter_bind_authorization_models import (
    CanonicalLiveAdapterBindAuthorizationArtifact,
    SignatureSignerDescriptor,
)
from veritas_os.policy.live_adapter_bind_authorization_codec import (
    _artifact_hash,
    _digest,
    _json,
    _timestamp,
    bind_authorization_artifact_signature_payload,
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
    _verify_signed_decision,
    _window,
)
from veritas_os.policy.live_adapter_bind_authorization_requirements import (
    _approved_issuer_binding,
    _copied_source_fields,
    _requirement_proofs,
)
from veritas_os.security.hash import sha256_of_canonical_json


def build_live_adapter_bind_authorization_artifact(
    source_gate_review_packet: Any,
    signed_authorization_decision_artifact: Any,
    valid_from: datetime | str,
    valid_until: datetime | str,
    *,
    governance_inputs: RealBindAuthorizationGovernanceInputs,
    trust_inputs: BindAuthorizationTrustInputs,
    authorization_issuer_signer: BindAuthorizationSigner,
) -> CanonicalLiveAdapterBindAuthorizationArtifact:
    """Issue one signed authorization without consuming it or invoking Bind."""
    source = _source(
        _json(source_gate_review_packet), governance_inputs=governance_inputs
    )
    _validate_source(source)
    governance = _validate_real_governance_inputs(source, governance_inputs)

    normalized_start = _timestamp(valid_from)
    normalized_end = _timestamp(valid_until)
    decision_artifact, authorizer_binding = _verify_signed_decision(
        signed_authorization_decision_artifact,
        source=source,
        trust=trust_inputs,
        now=governance_inputs.verification_now,
        expected_valid_from=normalized_start,
        expected_valid_until=normalized_end,
    )
    authorized_at, start, end = _window(
        source,
        governance,
        decision_artifact.decision,
        normalized_start,
        normalized_end,
    )
    if governance_inputs.verification_now.astimezone(timezone.utc) >= datetime.fromisoformat(end):
        raise LiveAdapterBindAuthorizationError(
            "LABA_AUTHORIZATION_ISSUANCE_AFTER_VALIDITY"
        )

    decision_digest = _decision_hash(decision_artifact.decision)
    credential_grant, header_grant = _grants(
        source, governance.policy_snapshot_id, governance.bind_context_hash
    )
    credential_grant_digest = _digest(
        DOMAINS["credential_grant"], credential_grant.model_dump(mode="json")
    )
    header_grant_digest = _digest(
        DOMAINS["header_grant"], header_grant.model_dump(mode="json")
    )
    idempotency_key = _idempotency_key(
        source,
        decision_digest,
        start,
        end,
        governance.policy_snapshot_id,
        governance.bind_context_hash,
    )
    verified_at = _timestamp(governance_inputs.verification_now)
    requirement_proofs = _requirement_proofs(
        source,
        governance,
        authorizer_binding,
        credential_grant_digest,
        header_grant_digest,
        idempotency_key,
        decision_digest,
        verified_at,
    )
    issuer_binding = _approved_issuer_binding(
        authorization_issuer_signer,
        trust_inputs,
        governance_inputs.verification_now,
    )
    issuer_signer = SignatureSignerDescriptor(
        key_id=authorization_issuer_signer.key_id,
        algorithm=authorization_issuer_signer.algorithm,
        identity=authorization_issuer_signer.identity,
        role=authorization_issuer_signer.role,
    )

    human_artifact = governance_inputs.signed_human_approval_artifact
    raw: dict[str, Any] = {
        "format_version": FORMAT_VERSION,
        "artifact_type": AUTHORIZATION_ARTIFACT_TYPE,
        "artifact_version": AUTHORIZATION_ARTIFACT_VERSION,
        "live_adapter_bind_authorization_id": "laba:v1:sha256:" + "0" * 64,
        "live_adapter_bind_authorization_hash": "0" * 64,
        "authorization_mechanism": MECHANISM,
        **_copied_source_fields(source),
        "signed_authority_evidence_artifact": _json(
            governance_inputs.signed_authority_evidence_artifact
        ),
        "signed_authority_evidence_artifact_digest": sha256_of_canonical_json(
            _json(governance_inputs.signed_authority_evidence_artifact)
        ),
        "authority_verification_proof_digest": (
            governance.authority_proof.verification_proof_hash
        ),
        "human_approval_requirement_status": governance.human_approval_status,
        "signed_human_approval_artifact": (
            None if human_artifact is None else _json(human_artifact)
        ),
        "signed_human_approval_artifact_digest": (
            None
            if human_artifact is None
            else sha256_of_canonical_json(_json(human_artifact))
        ),
        "human_approval_verification_proof_digest": (
            None
            if governance.human_approval_proof is None
            else governance.human_approval_proof.verification_proof_hash
        ),
        "runtime_authority_status": governance.runtime_result.status,
        "runtime_authority_recommended_outcome": (
            governance.runtime_result.recommended_outcome
        ),
        "runtime_authority_result_digest": governance.runtime_result_digest,
        "bind_context_hash": governance.bind_context_hash,
        "authorization_decision_artifact": decision_artifact.model_dump(mode="json"),
        "authorization_decision": decision_artifact.decision.model_dump(mode="json"),
        "authorization_decision_digest": decision_digest,
        "authorizer_verification": authorizer_binding.model_dump(mode="json"),
        "credential_resolution_grant": credential_grant.model_dump(mode="json"),
        "credential_resolution_grant_digest": credential_grant_digest,
        "authorization_header_construction_grant": header_grant.model_dump(mode="json"),
        "authorization_header_construction_grant_digest": header_grant_digest,
        "authorization_requirement_proofs": [
            proof.model_dump(mode="json") for proof in requirement_proofs
        ],
        "authorization_requirement_proofs_digest": _digest(
            DOMAINS["requirements"],
            [proof.model_dump(mode="json") for proof in requirement_proofs],
        ),
        "authorized_at": authorized_at,
        "valid_from": start,
        "valid_until": end,
        "idempotency_key": idempotency_key,
        "single_use": True,
        "authorization_consumption_required": True,
        "replay_protection_required": True,
        "duplicate_dispatch_prohibited": True,
        "bind_authorization_status": STATUS,
        "bind_authorization_state": "AUTHORIZED",
        "bind_authorization_created": True,
        "execution_authority_created": False,
        "request_dispatch_state": "NOT_DISPATCHED",
        "bind_state": "NOT_BOUND",
        "bind_invocation_state": "NOT_INVOKED",
        "authorization_consumption_state": "NOT_CONSUMED",
        "execution_state": "NOT_EXECUTED",
        **{field: False for field in EFFECT_FIELDS},
        "authorization_issuer_signer": issuer_signer.model_dump(mode="json"),
        "authorization_issuer_verification": issuer_binding.model_dump(mode="json"),
        "authorization_signed_at": verified_at,
        "authorization_signature": "placeholder-signature",
    }

    digest = _artifact_hash(raw)
    raw["live_adapter_bind_authorization_hash"] = digest
    raw["live_adapter_bind_authorization_id"] = f"laba:v1:sha256:{digest}"
    raw["authorization_signature"] = ""
    signature = authorization_issuer_signer.sign(
        bind_authorization_artifact_signature_payload(raw).encode("utf-8")
    )
    raw["authorization_signature"] = base64.urlsafe_b64encode(signature).decode("ascii")

    artifact = CanonicalLiveAdapterBindAuthorizationArtifact.model_validate(raw)
    # Self-verify through the independent verifier boundary before returning.
    from veritas_os.policy.live_adapter_bind_authorization_verification import (
        verify_live_adapter_bind_authorization_artifact,
    )

    return verify_live_adapter_bind_authorization_artifact(
        artifact,
        governance_inputs=governance_inputs,
        trust_inputs=trust_inputs,
    )
