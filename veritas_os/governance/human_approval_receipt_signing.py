"""Ed25519 signing preimage and trusted Human Approval verification backend."""

from __future__ import annotations

import base64
import binascii
import hashlib
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from veritas_os.governance.human_approval_receipt import (
    HumanApprovalSignatureVerificationResult,
)
from veritas_os.security.hash import canonical_json_dumps, sha256_of_canonical_json

SIGNATURE_DOMAIN = "VERITAS:human-approval-receipt:ed25519:v1"


def human_approval_signature_payload(artifact: dict[str, Any]) -> str:
    """Return the canonical, security-relevant Human Approval envelope.

    Verifier-derived fields are deliberately excluded. The signed envelope
    binds the immutable artifact identity, exact receipt, receipt hash, signer
    declarations, and signing time without creating another receipt model.
    """
    if not isinstance(artifact, dict):
        raise ValueError("human_approval_signature_envelope_invalid")
    signer = artifact.get("signer")
    receipt = artifact.get("receipt")
    if not isinstance(signer, dict) or not isinstance(receipt, dict):
        raise ValueError("human_approval_signature_envelope_invalid")
    required = (
        "artifact_type",
        "artifact_version",
        "receipt_hash",
        "signed_at",
    )
    if any(not isinstance(artifact.get(field), str) for field in required):
        raise ValueError("human_approval_signature_envelope_invalid")
    return canonical_json_dumps(
        {
            "domain": SIGNATURE_DOMAIN,
            "artifact_type": artifact["artifact_type"],
            "artifact_version": artifact["artifact_version"],
            "receipt_hash": artifact["receipt_hash"],
            "receipt": receipt,
            "signer": signer,
            "signed_at": artifact["signed_at"],
        }
    )


@dataclass(frozen=True)
class TrustedEd25519HumanApprovalVerifier:
    """Verify Human Approval signatures against deployment-controlled trust."""

    trusted_public_keys: dict[str, bytes]
    trusted_signer_identities: dict[str, str]
    trusted_signer_roles: dict[str, str]
    verifier_id: str
    trust_level: str = "production"
    verifier_policy_id: str = "human-approval-ed25519-verifier-v1"

    def policy_hash(self) -> str:
        """Return a stable identity for keys and trusted signer mappings."""
        keys = [
            {
                "key_id": key_id,
                "public_key_sha256": hashlib.sha256(
                    self.trusted_public_keys[key_id]
                ).hexdigest(),
                "signer_identity": self.trusted_signer_identities.get(key_id),
                "signer_role": self.trusted_signer_roles.get(key_id),
            }
            for key_id in sorted(self.trusted_public_keys)
        ]
        return sha256_of_canonical_json(
            {
                "id": self.verifier_policy_id,
                "algorithm": "Ed25519",
                "domain": "human-approval-ed25519-verifier",
                "version": "v1",
                "verifier_id": self.verifier_id,
                "trust_level": self.trust_level,
                "keys": keys,
            }
        )

    def verify(
        self,
        artifact: dict[str, Any],
    ) -> HumanApprovalSignatureVerificationResult:
        """Cryptographically verify the envelope and return trusted metadata."""
        if not isinstance(artifact, dict):
            return self._failure("malformed_envelope")
        signer = artifact.get("signer")
        if not isinstance(signer, dict):
            return self._failure("malformed_envelope")
        key_id = signer.get("key_id")
        algorithm = signer.get("algorithm")
        if not isinstance(key_id, str) or not key_id:
            return self._failure("untrusted_key")
        if algorithm != "Ed25519":
            return self._failure("unsupported_algorithm")
        key = self.trusted_public_keys.get(key_id)
        identity = self.trusted_signer_identities.get(key_id)
        role = self.trusted_signer_roles.get(key_id)
        if key is None or identity is None or role is None:
            return self._failure("untrusted_key")
        signature_value = artifact.get("signature")
        if not isinstance(signature_value, str) or not signature_value:
            return self._failure("missing_signature")
        try:
            payload = human_approval_signature_payload(artifact).encode("utf-8")
        except (ValueError, TypeError):
            return self._failure("malformed_envelope")
        try:
            signature = base64.b64decode(
                signature_value.encode("ascii"), altchars=b"-_", validate=True
            )
            public_key = Ed25519PublicKey.from_public_bytes(key)
            public_key.verify(signature, payload)
        except (ValueError, TypeError, UnicodeEncodeError, binascii.Error):
            return self._failure("malformed_signature")
        except InvalidSignature:
            return self._failure("invalid_signature")
        return HumanApprovalSignatureVerificationResult(
            verified=True,
            key_id=key_id,
            algorithm="Ed25519",
            signer_identity=identity,
            signer_role=role,
            reason="signature_valid",
            verifier_trust_level=self.trust_level,
            verifier_id=self.verifier_id,
            verifier_key_id=key_id,
            verifier_policy_id=self.verifier_policy_id,
            verifier_policy_hash=self.policy_hash(),
        )

    def _failure(self, reason: str) -> HumanApprovalSignatureVerificationResult:
        """Return a non-verifying result without trusting artifact metadata."""
        return HumanApprovalSignatureVerificationResult(
            verified=False,
            reason=reason,
            verifier_trust_level=self.trust_level,
            verifier_id=self.verifier_id,
            verifier_policy_id=self.verifier_policy_id,
            verifier_policy_hash=self.policy_hash(),
        )


__all__ = [
    "TrustedEd25519HumanApprovalVerifier",
    "human_approval_signature_payload",
]
