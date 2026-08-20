"""Optional Ed25519 backend for AuthorityEvidence verification.

Importing core governance models does not import ``cryptography``. Applications
that select this backend must install the declared ``signing`` extra; a missing
backend dependency therefore fails explicitly at backend import/use time.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from veritas_os.governance.authority_evidence import (
    AuthorityEvidenceSignatureVerificationResult,
    authority_signature_payload,
)
from veritas_os.security.hash import sha256_of_canonical_json


@dataclass(frozen=True)
class TrustedEd25519AuthorityVerifier:
    """Ed25519 verifier configured exclusively with deployment trusted keys."""

    trusted_public_keys: dict[str, bytes]
    trusted_issuers: dict[str, str]
    verifier_id: str
    trust_level: str = "production"
    verifier_policy_id: str = "authority-verifier-v1"

    def policy_hash(self) -> str:
        """Return the identity of this verifier's trust configuration."""
        return sha256_of_canonical_json({
            "id": self.verifier_policy_id,
            "keys": sorted(self.trusted_public_keys),
            "issuers": self.trusted_issuers,
        })

    def verify(
        self, artifact: dict[str, Any]
    ) -> AuthorityEvidenceSignatureVerificationResult:
        """Verify the canonical envelope without trusting artifact public keys."""
        signer = artifact.get("signer")
        if not isinstance(signer, dict):
            return AuthorityEvidenceSignatureVerificationResult(
                False, reason="signer_missing"
            )
        key_id = str(signer.get("key_id", ""))
        public_key = self.trusted_public_keys.get(key_id)
        issuer = self.trusted_issuers.get(key_id)
        if public_key is None or issuer is None:
            return AuthorityEvidenceSignatureVerificationResult(
                False, reason="untrusted_key"
            )
        try:
            signature = base64.urlsafe_b64decode(
                str(artifact.get("signature", ""))
            )
            Ed25519PublicKey.from_public_bytes(public_key).verify(
                signature,
                authority_signature_payload(artifact).encode("utf-8"),
            )
        except (ValueError, TypeError, binascii.Error, InvalidSignature):
            return AuthorityEvidenceSignatureVerificationResult(
                False, reason="bad_signature"
            )
        return AuthorityEvidenceSignatureVerificationResult(
            verified=True,
            key_id=key_id,
            algorithm="Ed25519",
            issuer_identity=issuer,
            reason="signature_valid",
            verifier_trust_level=self.trust_level,
            verifier_id=self.verifier_id,
            verifier_key_id=key_id,
            verifier_policy_id=self.verifier_policy_id,
            verifier_policy_hash=self.policy_hash(),
        )
