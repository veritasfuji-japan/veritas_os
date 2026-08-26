"""Production HTTPS verification for external effect reconciliation.

The verifier in this module treats reconciliation evidence as an untrusted
claim.  It retrieves a fresh acknowledgement from one deployment-controlled
HTTPS origin and validates its integrity, lineage, and interpretation before
creating :class:`VerifiedReconciliationEvidence`.
"""

from __future__ import annotations

import hashlib
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Mapping, Protocol
from urllib.parse import quote, urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from veritas_os.policy.bind_effect_reconciliation import (
    ReconciliationClaim,
    ReconciliationEvidence,
    VerifiedReconciliationEvidence,
)
from veritas_os.security.hash import sha256_of_canonical_json


class TrustedHttpsReconciliationError(RuntimeError):
    """Stable fail-closed error for acknowledgement verification failures."""


class ReconciliationCredentialProvider(Protocol):
    """Deployment credential boundary used only when making the HTTPS request."""

    async def authorization_headers(self) -> Mapping[str, str]:
        """Return secret request headers without persisting them in evidence."""


@dataclass(frozen=True)
class TrustedReconciliationEndpoint:
    """Deployment-controlled origin and acknowledgement path configuration."""

    scheme: str
    host: str
    port: int
    path_prefix: str
    source_type: str
    source_identity: str
    ca_file: str | None = None

    def validate(self) -> None:
        """Reject malformed or insecure endpoint trust configuration."""
        if self.scheme != "https" or not self.host or not (1 <= self.port <= 65535):
            raise TrustedHttpsReconciliationError("RHRV_ENDPOINT_INVALID")
        if (
            not self.path_prefix.startswith("/")
            or self.path_prefix.endswith("/")
            or "?" in self.path_prefix
            or "#" in self.path_prefix
            or not self.source_type
            or not self.source_identity
        ):
            raise TrustedHttpsReconciliationError("RHRV_ENDPOINT_INVALID")
        parsed = urlsplit(f"https://{self.host}:{self.port}{self.path_prefix}")
        if parsed.hostname != self.host or parsed.port != self.port:
            raise TrustedHttpsReconciliationError("RHRV_ENDPOINT_INVALID")
        if self.ca_file is not None and not Path(self.ca_file).is_file():
            raise TrustedHttpsReconciliationError("RHRV_CA_TRUST_INVALID")


@dataclass(frozen=True)
class ApprovedReconciliationVerifier:
    """Deployment-owned approval for an exact verifier policy hash."""

    verifier_id: str
    verifier_policy_hash: str


@dataclass(frozen=True)
class ReconciliationVerifierPolicy:
    """Deployment-controlled allowlist of reconciliation verifier provenance."""

    approved_verifiers: tuple[ApprovedReconciliationVerifier, ...]

    def approves(self, verifier_id: str, policy_hash: str) -> bool:
        """Return whether the exact verifier identity and policy are approved."""
        return any(
            item.verifier_id == verifier_id
            and item.verifier_policy_hash == policy_hash
            and _is_hash(item.verifier_policy_hash)
            for item in self.approved_verifiers
        )


class _Acknowledgement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    external_operation_reference: str = Field(min_length=1)
    status: str = Field(min_length=1)
    source_identity: str = Field(min_length=1)
    veritas_operation_id: str | None = None
    authorization_id: str | None = None
    consumption_id: str | None = None


def reconciliation_observation_digest(evidence: ReconciliationEvidence) -> str:
    """Hash all v1 observation fields except ``observation_digest`` itself."""
    payload = evidence.model_dump(mode="json")
    payload.pop("observation_digest")
    return sha256_of_canonical_json(payload)


def _is_hash(value: str) -> bool:
    return len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


class TrustedHttpsReconciliationVerifier:
    """Independently verify reconciliation through certificate-validated HTTPS.

    Endpoint, CA roots, status semantics, credentials, verifier identity, and
    verifier approval are deployment inputs. Redirects are disabled and the
    untrusted operation reference is encoded as one path segment.
    """

    def __init__(
        self,
        *,
        endpoint: TrustedReconciliationEndpoint,
        verifier_id: str,
        verifier_policy: ReconciliationVerifierPolicy,
        credential_provider: ReconciliationCredentialProvider | None = None,
        committed_statuses: tuple[str, ...] = ("committed",),
        no_effect_statuses: tuple[str, ...] = ("rejected", "not_applied"),
        unknown_statuses: tuple[str, ...] = ("pending", "unknown"),
        timeout_seconds: float = 10.0,
        interpretation_version: str = "https-acknowledgement/v1",
    ) -> None:
        endpoint.validate()
        if (
            not verifier_id
            or timeout_seconds <= 0
            or not interpretation_version
            or not committed_statuses
            or set(committed_statuses) & set(no_effect_statuses)
            or set(committed_statuses) & set(unknown_statuses)
            or set(no_effect_statuses) & set(unknown_statuses)
        ):
            raise TrustedHttpsReconciliationError("RHRV_POLICY_INVALID")
        self._endpoint = endpoint
        self._verifier_id = verifier_id
        self._verifier_policy = verifier_policy
        self._credential_provider = credential_provider
        self._committed_statuses = tuple(sorted(committed_statuses))
        self._no_effect_statuses = tuple(sorted(no_effect_statuses))
        self._unknown_statuses = tuple(sorted(unknown_statuses))
        self._timeout_seconds = timeout_seconds
        self._interpretation_version = interpretation_version
        if not self._verifier_policy.approves(verifier_id, self.policy_hash()):
            raise TrustedHttpsReconciliationError("RHRV_VERIFIER_NOT_APPROVED")

    @staticmethod
    def policy_hash_for_config(
        *,
        endpoint: TrustedReconciliationEndpoint,
        verifier_id: str,
        committed_statuses: tuple[str, ...] = ("committed",),
        no_effect_statuses: tuple[str, ...] = ("rejected", "not_applied"),
        unknown_statuses: tuple[str, ...] = ("pending", "unknown"),
        interpretation_version: str = "https-acknowledgement/v1",
    ) -> str:
        """Calculate the policy hash used in a deployment approval entry."""
        ca_digest = None
        if endpoint.ca_file:
            try:
                ca_digest = hashlib.sha256(
                    Path(endpoint.ca_file).read_bytes()
                ).hexdigest()
            except OSError:
                raise TrustedHttpsReconciliationError("RHRV_CA_TRUST_INVALID") from None
        return sha256_of_canonical_json(
            {
                "policy_version": "trusted-https-reconciliation-verifier/v1",
                "verifier_id": verifier_id,
                "scheme": endpoint.scheme,
                "host": endpoint.host,
                "port": endpoint.port,
                "path_prefix": endpoint.path_prefix,
                "source_type": endpoint.source_type,
                "source_identity": endpoint.source_identity,
                "ca_trust": "deployment_custom" if endpoint.ca_file else "system",
                "ca_bundle_sha256": ca_digest,
                "interpretation_version": interpretation_version,
                "committed_statuses": tuple(sorted(committed_statuses)),
                "no_effect_statuses": tuple(sorted(no_effect_statuses)),
                "unknown_statuses": tuple(sorted(unknown_statuses)),
            }
        )

    def policy_hash(self) -> str:
        """Return a stable hash of all non-secret security policy inputs."""
        return self.policy_hash_for_config(
            endpoint=self._endpoint,
            verifier_id=self._verifier_id,
            committed_statuses=self._committed_statuses,
            no_effect_statuses=self._no_effect_statuses,
            unknown_statuses=self._unknown_statuses,
            interpretation_version=self._interpretation_version,
        )

    async def verify(
        self, evidence: ReconciliationEvidence
    ) -> VerifiedReconciliationEvidence:
        """Fetch and validate an acknowledgement, failing closed on any error."""
        policy_hash = self.policy_hash()
        if not self._verifier_policy.approves(self._verifier_id, policy_hash):
            raise TrustedHttpsReconciliationError("RHRV_VERIFIER_NOT_APPROVED")
        self._validate_evidence(evidence)
        acknowledgement = await self._retrieve(
            evidence.external_operation_reference or ""
        )
        self._validate_acknowledgement(evidence, acknowledgement)
        ack_payload = acknowledgement.model_dump(mode="json", exclude_none=True)
        ack_digest = sha256_of_canonical_json(ack_payload)
        if evidence.external_ack_digest != ack_digest:
            raise TrustedHttpsReconciliationError("RHRV_ACK_DIGEST_MISMATCH")
        proof_hash = sha256_of_canonical_json(
            {
                "acknowledgement_digest": ack_digest,
                "observation_digest": evidence.observation_digest,
                "operation_id": evidence.operation_id,
                "external_operation_reference": evidence.external_operation_reference,
                "source_identity": evidence.source_identity,
                "verifier_id": self._verifier_id,
                "verifier_policy_hash": policy_hash,
                "verified_claim": evidence.claim.value,
                "verified_status": acknowledgement.status,
            }
        )
        return VerifiedReconciliationEvidence(
            evidence=evidence,
            verifier_id=self._verifier_id,
            verifier_policy_hash=policy_hash,
            verification_proof_hash=proof_hash,
            verified_at=datetime.now(UTC).isoformat(),
        )

    def _validate_evidence(self, evidence: ReconciliationEvidence) -> None:
        endpoint = self._endpoint
        if evidence.format_version != "bind-effect-reconciliation-evidence/v1":
            raise TrustedHttpsReconciliationError("RHRV_FORMAT_VERSION_UNSUPPORTED")
        if evidence.source_type != endpoint.source_type:
            raise TrustedHttpsReconciliationError("RHRV_SOURCE_TYPE_UNSUPPORTED")
        if evidence.source_identity != endpoint.source_identity:
            raise TrustedHttpsReconciliationError("RHRV_SOURCE_IDENTITY_MISMATCH")
        if (
            not evidence.external_operation_reference
            or not evidence.external_ack_digest
        ):
            raise TrustedHttpsReconciliationError("RHRV_ACK_BINDING_MISSING")
        try:
            observed_at = datetime.fromisoformat(evidence.observed_at)
        except ValueError:
            raise TrustedHttpsReconciliationError("RHRV_OBSERVED_AT_INVALID") from None
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise TrustedHttpsReconciliationError("RHRV_OBSERVED_AT_INVALID")
        if reconciliation_observation_digest(evidence) != evidence.observation_digest:
            raise TrustedHttpsReconciliationError("RHRV_OBSERVATION_DIGEST_MISMATCH")

    async def _retrieve(self, operation_reference: str) -> _Acknowledgement:
        headers: Mapping[str, str] = {}
        if self._credential_provider is not None:
            try:
                headers = await self._credential_provider.authorization_headers()
            except Exception:
                raise TrustedHttpsReconciliationError(
                    "RHRV_CREDENTIAL_FAILED"
                ) from None
        if any(
            not key
            or key.lower()
            in {"host", "content-length", "connection", "transfer-encoding"}
            or "\n" in key
            or "\r" in key
            or "\n" in value
            or "\r" in value
            for key, value in headers.items()
        ):
            raise TrustedHttpsReconciliationError("RHRV_CREDENTIAL_FAILED")
        endpoint = self._endpoint
        url = (
            f"https://{endpoint.host}:{endpoint.port}{endpoint.path_prefix}/"
            f"{quote(operation_reference, safe='')}"
        )
        context = ssl.create_default_context(cafile=endpoint.ca_file)
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        try:
            async with httpx.AsyncClient(
                verify=context,
                timeout=self._timeout_seconds,
                follow_redirects=False,
            ) as client:
                response = await client.get(url, headers=dict(headers))
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError
            return _Acknowledgement.model_validate(payload)
        except (httpx.HTTPError, ValueError, ValidationError):
            raise TrustedHttpsReconciliationError("RHRV_ACK_RETRIEVAL_FAILED") from None

    def _validate_acknowledgement(
        self,
        evidence: ReconciliationEvidence,
        acknowledgement: _Acknowledgement,
    ) -> None:
        if (
            acknowledgement.external_operation_reference
            != evidence.external_operation_reference
        ):
            raise TrustedHttpsReconciliationError("RHRV_OPERATION_REFERENCE_MISMATCH")
        if (
            acknowledgement.veritas_operation_id is not None
            and acknowledgement.veritas_operation_id != evidence.operation_id
        ):
            raise TrustedHttpsReconciliationError("RHRV_OPERATION_ID_MISMATCH")
        if acknowledgement.source_identity != evidence.source_identity:
            raise TrustedHttpsReconciliationError("RHRV_SOURCE_IDENTITY_MISMATCH")
        if (
            acknowledgement.authorization_id is not None
            and acknowledgement.authorization_id != evidence.authorization_id
        ):
            raise TrustedHttpsReconciliationError("RHRV_AUTHORIZATION_LINEAGE_MISMATCH")
        if (
            acknowledgement.consumption_id is not None
            and acknowledgement.consumption_id != evidence.consumption_id
        ):
            raise TrustedHttpsReconciliationError("RHRV_CONSUMPTION_LINEAGE_MISMATCH")
        expected_statuses = {
            ReconciliationClaim.CONFIRMED_EFFECT: self._committed_statuses,
            ReconciliationClaim.CONFIRMED_NO_EFFECT: self._no_effect_statuses,
            ReconciliationClaim.STILL_UNKNOWN: self._unknown_statuses,
        }[evidence.claim]
        all_statuses = (
            self._committed_statuses + self._no_effect_statuses + self._unknown_statuses
        )
        if acknowledgement.status not in all_statuses:
            raise TrustedHttpsReconciliationError("RHRV_STATUS_UNSUPPORTED")
        if acknowledgement.status not in expected_statuses:
            raise TrustedHttpsReconciliationError("RHRV_CLAIM_CONTRADICTED")


__all__ = [
    "ApprovedReconciliationVerifier",
    "ReconciliationCredentialProvider",
    "ReconciliationVerifierPolicy",
    "TrustedHttpsReconciliationError",
    "TrustedHttpsReconciliationVerifier",
    "TrustedReconciliationEndpoint",
    "reconciliation_observation_digest",
]
