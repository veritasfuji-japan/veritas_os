"""Optional Ed25519 backend for authenticated Real Bind Authorization v1."""

from __future__ import annotations

import base64
import binascii
import hashlib
from dataclasses import dataclass
from typing import Any, Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from veritas_os.policy.live_adapter_bind_authorization import (
    AUTHORIZATION_ARTIFACT_TYPE,
    AUTHORIZATION_ARTIFACT_VERSION,
    AUTHORIZER_ARTIFACT_TYPE,
    AUTHORIZER_ARTIFACT_VERSION,
    BindAuthorizationSignatureVerificationResult,
    bind_authorization_artifact_signature_payload,
    bind_authorizer_decision_signature_payload,
)
from veritas_os.security.hash import sha256_of_canonical_json

Purpose = Literal["authorizer_decision", "authorization_issuer"]


@dataclass(frozen=True)
class TrustedEd25519BindAuthorizationVerifier:
    """Verify authorizer/issuer signatures against deployment-controlled keys."""

    trusted_public_keys: dict[str, bytes]
    trusted_identities: dict[str, str]
    trusted_roles: dict[str, str]
    verifier_id: str
    purpose: Purpose
    trust_level: str = "production"
    verifier_policy_id: str = "bind-authorization-verifier-v1"

    def policy_hash(self) -> str:
        """Bind verifier policy identity to the exact trusted public-key bytes."""
        keys = [
            {
                "key_id": key_id,
                "public_key_sha256": hashlib.sha256(
                    self.trusted_public_keys[key_id]
                ).hexdigest(),
                "identity": self.trusted_identities.get(key_id),
                "role": self.trusted_roles.get(key_id),
            }
            for key_id in sorted(self.trusted_public_keys)
        ]
        return sha256_of_canonical_json(
            {
                "id": self.verifier_policy_id,
                "algorithm": "Ed25519",
                "domain": "bind-authorization-verifier",
                "version": "v1",
                "purpose": self.purpose,
                "verifier_id": self.verifier_id,
                "trust_level": self.trust_level,
                "keys": keys,
            }
        )

    def _signature_payload(self, artifact: dict[str, Any]) -> str | None:
        if self.purpose == "authorizer_decision":
            if artifact.get("artifact_type") != AUTHORIZER_ARTIFACT_TYPE:
                return None
            if artifact.get("artifact_version") != AUTHORIZER_ARTIFACT_VERSION:
                return None
            return bind_authorizer_decision_signature_payload(artifact)
        if artifact.get("artifact_type") != AUTHORIZATION_ARTIFACT_TYPE:
            return None
        if artifact.get("artifact_version") != AUTHORIZATION_ARTIFACT_VERSION:
            return None
        return bind_authorization_artifact_signature_payload(artifact)

    def verify(
        self, artifact: dict[str, Any]
    ) -> BindAuthorizationSignatureVerificationResult:
        """Verify a domain-separated authorizer or authorization signature."""
        signer = artifact.get("signer")
        if self.purpose == "authorization_issuer":
            signer = artifact.get("authorization_issuer_signer")
        signer = signer if isinstance(signer, dict) else {}
        key_id = str(signer.get("key_id", ""))
        key = self.trusted_public_keys.get(key_id)
        identity = self.trusted_identities.get(key_id)
        role = self.trusted_roles.get(key_id)
        payload = self._signature_payload(artifact)
        if key is None or identity is None or role is None or payload is None:
            return BindAuthorizationSignatureVerificationResult(
                False, reason="untrusted_key_or_artifact"
            )
        signature_field = (
            "signature"
            if self.purpose == "authorizer_decision"
            else "authorization_signature"
        )
        try:
            signature = base64.urlsafe_b64decode(
                str(artifact.get(signature_field, ""))
            )
            Ed25519PublicKey.from_public_bytes(key).verify(
                signature, payload.encode("utf-8")
            )
        except (ValueError, TypeError, binascii.Error, InvalidSignature):
            return BindAuthorizationSignatureVerificationResult(
                False, reason="bad_signature"
            )
        return BindAuthorizationSignatureVerificationResult(
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
