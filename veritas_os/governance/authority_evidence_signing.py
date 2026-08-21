"""Optional Ed25519 backend for AuthorityEvidence artifact verification."""

from __future__ import annotations

import base64
import binascii
import hashlib
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
    """Verify against deployment-controlled keys, never artifact public keys."""

    trusted_public_keys: dict[str, bytes]
    trusted_issuers: dict[str, str]
    verifier_id: str
    trust_level: str = "production"
    verifier_policy_id: str = "authority-verifier-v1"

    def policy_hash(self) -> str:
        """Return identity bound to deployment policy and trusted key bytes."""
        keys = [
            {
                "key_id": key_id,
                "public_key_sha256": hashlib.sha256(
                    self.trusted_public_keys[key_id]
                ).hexdigest(),
            }
            for key_id in sorted(self.trusted_public_keys)
        ]
        return sha256_of_canonical_json(
            {
                "id": self.verifier_policy_id,
                "algorithm": "Ed25519",
                "domain": "authority-evidence-verifier",
                "version": "v1",
                "verifier_id": self.verifier_id,
                "trust_level": self.trust_level,
                "keys": keys,
                "issuers": self.trusted_issuers,
            }
        )

    def verify(
        self, artifact: dict[str, Any]
    ) -> AuthorityEvidenceSignatureVerificationResult:
        """Cryptographically verify the complete security-relevant envelope."""
        signer = artifact.get("signer")
        signer = signer if isinstance(signer, dict) else {}
        key_id = str(signer.get("key_id", ""))
        key = self.trusted_public_keys.get(key_id)
        issuer = self.trusted_issuers.get(key_id)
        if key is None or issuer is None:
            return AuthorityEvidenceSignatureVerificationResult(
                False, reason="untrusted_key"
            )
        try:
            signature = base64.urlsafe_b64decode(str(artifact.get("signature", "")))
            Ed25519PublicKey.from_public_bytes(key).verify(
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
