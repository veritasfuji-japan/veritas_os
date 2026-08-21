"""Real cryptographic AuthorityEvidence fixtures for governance tests."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from veritas_os.governance.action_contracts import ActionClassContract
from veritas_os.governance.authority_evidence import (
    ApprovedAuthorityEvidenceVerifier,
    AuthorityEvidence,
    AuthorityEvidenceSignerPolicy,
    AuthorityEvidenceVerifierPolicy,
    AuthorityRevocationPolicy,
    AuthorityRevocationVerificationResult,
    VerifiedAuthorityEvidence,
    authority_signature_payload,
    verify_authority_evidence_artifact_to_proof,
)
from veritas_os.governance.authority_evidence_signing import (
    TrustedEd25519AuthorityVerifier,
)
from veritas_os.security.hash import sha256_of_canonical_json


@dataclass(frozen=True)
class StrictAuthorityBundle:
    """Complete deployment-approved authority prerequisites for runtime tests."""

    proof: VerifiedAuthorityEvidence
    verifier_policy: AuthorityEvidenceVerifierPolicy
    revocation_policy: AuthorityRevocationPolicy


class _FreshRevocationChecker:
    def check(
        self,
        authority_evidence_id: str,
        *,
        now: datetime,
    ) -> AuthorityRevocationVerificationResult:
        """Return fresh non-revocation state from a test-controlled source."""
        return AuthorityRevocationVerificationResult(
            checked=True,
            revoked=False,
            checked_at=now.isoformat(),
            source_identity="test-revocation-source",
            source_version="v1",
            source_hash="a" * 64,
            reason="not_revoked",
        )


def build_strict_authority_bundle(
    *,
    authority: AuthorityEvidence,
    action_contract: ActionClassContract,
    actor_identity: str,
    requested_scope: list[str],
    policy_snapshot_id: str,
    now: datetime,
) -> StrictAuthorityBundle:
    """Create authority through the real Ed25519 verification boundary."""
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes_raw()
    claims = authority.claims_dict()
    claims["action_contract_hash"] = action_contract.deterministic_digest()
    claims_hash = sha256_of_canonical_json(claims)
    artifact = {
        "artifact_type": "authority_evidence",
        "artifact_version": "v1",
        "claims": claims,
        "claims_hash": claims_hash,
        "signer": {"key_id": "test-authority-key", "algorithm": "Ed25519"},
        "issuer_identity": "test-authority-issuer",
        "signed_at": now.isoformat(),
    }
    artifact["signature"] = base64.urlsafe_b64encode(
        private_key.sign(authority_signature_payload(artifact).encode("utf-8"))
    ).decode("ascii")
    verifier = TrustedEd25519AuthorityVerifier(
        {"test-authority-key": public_key},
        {"test-authority-key": "test-authority-issuer"},
        "test-authority-verifier",
    )
    signer_policy = AuthorityEvidenceSignerPolicy(
        "test-authority-signer-policy",
        ["test-authority-key"],
        ["Ed25519"],
        ["test-authority-issuer"],
    )
    revocation_policy = AuthorityRevocationPolicy(
        max_age_seconds=60,
        allowed_source_identities=["test-revocation-source"],
    )
    proof = verify_authority_evidence_artifact_to_proof(
        artifact,
        action_contract=action_contract,
        actor_identity=actor_identity,
        requested_scope=requested_scope,
        policy_snapshot_id=policy_snapshot_id,
        signature_verifier=verifier,
        signer_policy=signer_policy,
        revocation_checker=_FreshRevocationChecker(),
        revocation_policy=revocation_policy,
        now=now,
    )
    verifier_policy = AuthorityEvidenceVerifierPolicy([
        ApprovedAuthorityEvidenceVerifier(
            verifier_id="test-authority-verifier",
            trust_level="production",
            verifier_key_id="test-authority-key",
            verifier_policy_id="authority-verifier-v1",
            verifier_policy_hash=verifier.policy_hash(),
            signer_policy_id=signer_policy.policy_id,
            signer_policy_hash=signer_policy.deterministic_hash(),
        )
    ])
    return StrictAuthorityBundle(proof, verifier_policy, revocation_policy)
