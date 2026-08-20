"""Authority evidence claims and cryptographically verified authority proofs.

``AuthorityEvidence`` is caller-supplied data.  Its content hash provides
identity/integrity only; neither that hash nor its legacy ``verification_result``
proves authenticity.  Strict runtime boundaries consume only proofs emitted by
``verify_authority_evidence_artifact_to_proof``.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Protocol

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from veritas_os.governance.action_contracts import ActionClassContract
from veritas_os.security.hash import canonical_json_dumps, sha256_of_canonical_json

SIGNED_AUTHORITY_ARTIFACT_TYPE = "authority_evidence"
SIGNED_AUTHORITY_ARTIFACT_VERSION = "v1"
AUTHORITY_SIGNATURE_DOMAIN = "VERITAS:authority-evidence:v1:"
AUTHORITY_VERIFICATION_SOURCE = "signed_authority_evidence_artifact"
_VERIFIED_PROOF_REGISTRY: dict[int, str] = {}


class VerificationResult(str, Enum):
    """Legacy caller-declared outcome; never authoritative in strict posture."""

    VALID = "valid"
    INVALID = "invalid"
    EXPIRED = "expired"
    MISSING = "missing"
    STALE = "stale"
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True)
class AuthorityEvidence:
    """Unsigned authority claims; callers can construct every field."""

    authority_evidence_id: str
    action_contract_id: str
    action_contract_version: str
    actor_identity: str
    actor_role: str
    authority_source_refs: list[str]
    role_or_policy_basis: list[str]
    scope_grants: list[str]
    scope_limitations: list[str]
    validity_window: dict[str, str]
    issued_at: str
    valid_from: str
    valid_until: str
    revalidated_at: str | None = None
    policy_snapshot_id: str | None = None
    action_contract_hash: str | None = None
    evidence_hash: str = ""
    verification_result: VerificationResult = VerificationResult.INDETERMINATE
    failure_reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return all compatibility fields as JSON data."""
        return {
            "authority_evidence_id": self.authority_evidence_id,
            "action_contract_id": self.action_contract_id,
            "action_contract_version": self.action_contract_version,
            "actor_identity": self.actor_identity,
            "actor_role": self.actor_role,
            "authority_source_refs": list(self.authority_source_refs),
            "role_or_policy_basis": list(self.role_or_policy_basis),
            "scope_grants": list(self.scope_grants),
            "scope_limitations": list(self.scope_limitations),
            "validity_window": dict(self.validity_window),
            "issued_at": self.issued_at,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "revalidated_at": self.revalidated_at,
            "policy_snapshot_id": self.policy_snapshot_id,
            "action_contract_hash": self.action_contract_hash,
            "evidence_hash": self.evidence_hash,
            "verification_result": self.verification_result.value,
            "failure_reasons": list(self.failure_reasons),
            "metadata": dict(self.metadata),
        }

    def claims_dict(self) -> dict[str, Any]:
        """Return exact signable claims, excluding caller trust conclusions."""
        payload = self.to_dict()
        for key in ("evidence_hash", "verification_result", "failure_reasons"):
            payload.pop(key, None)
        metadata = payload.get("metadata", {})
        payload["metadata"] = {
            key: value for key, value in metadata.items()
            if key not in {"verified", "signature_verified", "not_revoked",
                           "trusted_issuer", "verification_source", "revoked"}
        }
        return payload

    def to_dict_for_hash(self) -> dict[str, Any]:
        """Return the backward-compatible content-address payload.

        ``action_contract_hash`` was added after the v1 evidence identity was
        deployed.  Omitting its absent value preserves existing artifact and
        manifest hashes, while a supplied contract hash remains identity-bound.
        """
        payload = self.to_dict()
        payload["evidence_hash"] = ""
        if self.action_contract_hash is None:
            payload.pop("action_contract_hash", None)
        return payload

    def deterministic_serialization(self) -> str:
        """Serialize the legacy content identity deterministically."""
        return canonical_json_dumps(self.to_dict_for_hash())

    def deterministic_digest(self) -> str:
        """Return a content hash, which does not prove authenticity."""
        return sha256_of_canonical_json(self.to_dict_for_hash())


@dataclass(frozen=True)
class AuthorityEvidenceSignatureVerificationResult:
    """Deployment-verifier-derived signature and issuer identity."""

    verified: bool
    key_id: str | None = None
    algorithm: str | None = None
    issuer_identity: str | None = None
    issuer_role: str | None = None
    reason: str | None = None
    verifier_trust_level: str | None = None
    verifier_id: str | None = None
    verifier_key_id: str | None = None
    verifier_policy_id: str | None = None
    verifier_policy_hash: str | None = None


class AuthorityEvidenceSignatureVerifier(Protocol):
    """Cryptographic boundary backed by deployment-controlled trusted keys."""

    def verify(self, artifact: dict[str, Any]) -> AuthorityEvidenceSignatureVerificationResult:
        """Verify an artifact without using an artifact public key as trust anchor."""
        ...


@dataclass(frozen=True)
class TrustedEd25519AuthorityVerifier:
    """Offline Ed25519 verifier whose keys are supplied by deployment policy."""

    trusted_public_keys: dict[str, bytes]
    trusted_issuers: dict[str, str]
    verifier_id: str
    trust_level: str = "production"
    verifier_policy_id: str = "authority-verifier-v1"

    def verify(self, artifact: dict[str, Any]) -> AuthorityEvidenceSignatureVerificationResult:
        """Verify domain-separated claims using only configured public keys."""
        signer = artifact.get("signer") if isinstance(artifact.get("signer"), dict) else {}
        key_id = str(signer.get("key_id", ""))
        key = self.trusted_public_keys.get(key_id)
        issuer = self.trusted_issuers.get(key_id)
        if key is None or issuer is None:
            return AuthorityEvidenceSignatureVerificationResult(False, reason="untrusted_key")
        try:
            signature = base64.urlsafe_b64decode(str(artifact.get("signature", "")))
            digest = str(artifact.get("claims_hash", ""))
            Ed25519PublicKey.from_public_bytes(key).verify(
                signature, (AUTHORITY_SIGNATURE_DOMAIN + digest).encode()
            )
        except (ValueError, TypeError, binascii.Error, InvalidSignature):
            return AuthorityEvidenceSignatureVerificationResult(False, reason="bad_signature")
        return AuthorityEvidenceSignatureVerificationResult(
            True, key_id, "Ed25519", issuer, reason="signature_valid",
            verifier_trust_level=self.trust_level, verifier_id=self.verifier_id,
            verifier_key_id=key_id, verifier_policy_id=self.verifier_policy_id,
            verifier_policy_hash=sha256_of_canonical_json({
                "id": self.verifier_policy_id,
                "keys": sorted(self.trusted_public_keys),
                "issuers": self.trusted_issuers,
            }),
        )


@dataclass(frozen=True)
class AuthorityEvidenceSignerPolicy:
    """Allowlist binding signing keys, algorithms, and issuer identities."""

    policy_id: str
    allowed_key_ids: list[str]
    allowed_algorithms: list[str]
    allowed_issuer_identities: list[str]

    def deterministic_hash(self) -> str:
        """Return canonical signer-policy identity."""
        return sha256_of_canonical_json({
            "policy_id": self.policy_id,
            "allowed_key_ids": sorted(self.allowed_key_ids),
            "allowed_algorithms": sorted(self.allowed_algorithms),
            "allowed_issuer_identities": sorted(self.allowed_issuer_identities),
        })


@dataclass(frozen=True)
class AuthorityRevocationVerificationResult:
    """Verifier-derived revocation status from an offline trusted source."""

    checked: bool
    revoked: bool | None
    checked_at: str
    source_identity: str
    source_version: str
    source_hash: str
    reason: str


class AuthorityRevocationChecker(Protocol):
    """Offline revocation provider boundary (prefetched snapshots or HSM policy)."""

    def check(self, authority_evidence_id: str, *, now: datetime) -> AuthorityRevocationVerificationResult:
        """Return independently established revocation state."""
        ...


@dataclass(frozen=True)
class VerifiedAuthorityEvidence:
    """Verifier-derived, runtime-sealed authority proof; not bind authorization."""

    authority_evidence: AuthorityEvidence
    claims_hash: str
    artifact_type: str
    artifact_version: str
    action_contract_hash: str
    signer_key_id: str
    signer_algorithm: str
    issuer_identity: str
    signer_policy_id: str
    signer_policy_hash: str
    verifier_id: str
    verifier_trust_level: str
    verifier_policy_id: str
    verifier_policy_hash: str
    signature_verification_reason: str
    signed_at: str
    verified_at: str
    revocation: AuthorityRevocationVerificationResult
    verification_source: str
    verification_proof_hash: str

    def proof_hash_payload(self) -> dict[str, Any]:
        """Return canonical proof data, including exact claims and revocation."""
        return {
            "claims": self.authority_evidence.claims_dict(),
            "claims_hash": self.claims_hash,
            "artifact_type": self.artifact_type,
            "artifact_version": self.artifact_version,
            "action_contract_hash": self.action_contract_hash,
            "signer_key_id": self.signer_key_id,
            "signer_algorithm": self.signer_algorithm,
            "issuer_identity": self.issuer_identity,
            "signer_policy_id": self.signer_policy_id,
            "signer_policy_hash": self.signer_policy_hash,
            "verifier_id": self.verifier_id,
            "verifier_trust_level": self.verifier_trust_level,
            "verifier_policy_id": self.verifier_policy_id,
            "verifier_policy_hash": self.verifier_policy_hash,
            "signature_verification_reason": self.signature_verification_reason,
            "signed_at": self.signed_at, "verified_at": self.verified_at,
            "revocation": self.revocation.__dict__,
            "verification_source": self.verification_source,
        }


@dataclass(frozen=True)
class AuthorityEvidenceValidationResult:
    """Deterministic validation result for raw claim shape and time state."""

    is_valid: bool
    failure_reasons: list[str] = field(default_factory=list)


def _aware_datetime(value: str, reason: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(reason) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(reason + "_timezone_required")
    return parsed


def is_present(authority_evidence: AuthorityEvidence | None) -> bool:
    """Return whether raw claims exist (not whether they are authentic)."""
    return authority_evidence is not None


def is_expired(authority_evidence: AuthorityEvidence, *, now: datetime | None = None) -> bool:
    """Return expiry safely using timezone-aware instants."""
    now_dt = now or datetime.now(UTC)
    if now_dt.tzinfo is None or now_dt.utcoffset() is None:
        raise ValueError("validation_now_timezone_required")
    return now_dt >= _aware_datetime(authority_evidence.valid_until, "valid_until_invalid")


def is_indeterminate(authority_evidence: AuthorityEvidence) -> bool:
    """Return legacy caller state without treating it as verified."""
    return authority_evidence.verification_result == VerificationResult.INDETERMINATE


def is_scope_granting(authority_evidence: AuthorityEvidence, scope: str) -> bool:
    """Return whether raw claims grant and do not limit a scope."""
    return scope in authority_evidence.scope_grants and scope not in authority_evidence.scope_limitations


def validate_authority_evidence(authority_evidence: AuthorityEvidence | None, *,
                                policy_snapshot_required: bool = False,
                                now: datetime | None = None) -> AuthorityEvidenceValidationResult:
    """Validate raw claims deterministically; this does not authenticate them."""
    if authority_evidence is None:
        return AuthorityEvidenceValidationResult(False, ["authority_evidence_missing"])
    failures: list[str] = []
    if not authority_evidence.actor_identity.strip():
        failures.append("actor_identity_missing")
    if not authority_evidence.authority_source_refs:
        failures.append("authority_source_refs_missing")
    if policy_snapshot_required and not (authority_evidence.policy_snapshot_id or "").strip():
        failures.append("policy_snapshot_id_missing")
    if authority_evidence.verification_result != VerificationResult.VALID:
        failures.append(f"verification_result_{authority_evidence.verification_result.value}")
    try:
        issued = _aware_datetime(authority_evidence.issued_at, "issued_at_invalid")
        valid_from = _aware_datetime(authority_evidence.valid_from, "valid_from_invalid")
        valid_until = _aware_datetime(authority_evidence.valid_until, "valid_until_invalid")
        current = now or datetime.now(UTC)
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("validation_now_timezone_required")
        if not issued <= valid_from < valid_until:
            failures.append("validity_window_order_invalid")
        elif current < valid_from:
            failures.append("authority_not_yet_valid")
        elif current >= valid_until:
            failures.append("authority_expired")
        if authority_evidence.revalidated_at:
            _aware_datetime(authority_evidence.revalidated_at, "revalidated_at_invalid")
    except ValueError as exc:
        failures.append(str(exc))
    return AuthorityEvidenceValidationResult(not failures, failures)


def is_valid(authority_evidence: AuthorityEvidence | None, **kwargs: Any) -> bool:
    """Return raw claim validation only, not authenticity verification."""
    return validate_authority_evidence(authority_evidence, **kwargs).is_valid


def verify_authority_evidence_artifact_to_proof(
    artifact: dict[str, Any], *, action_contract: ActionClassContract,
    actor_identity: str, requested_scope: list[str], policy_snapshot_id: str,
    signature_verifier: AuthorityEvidenceSignatureVerifier,
    signer_policy: AuthorityEvidenceSignerPolicy,
    revocation_checker: AuthorityRevocationChecker, now: datetime | None = None,
) -> VerifiedAuthorityEvidence:
    """Authenticate exact claims and emit an all-or-nothing sealed proof."""
    current = now or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("validation_now_timezone_required")
    if artifact.get("artifact_type") != SIGNED_AUTHORITY_ARTIFACT_TYPE:
        raise ValueError("authority_artifact_type_invalid")
    if artifact.get("artifact_version") != SIGNED_AUTHORITY_ARTIFACT_VERSION:
        raise ValueError("authority_artifact_version_invalid")
    claims = artifact.get("claims")
    if not isinstance(claims, dict):
        raise ValueError("authority_claims_missing")
    clean = dict(claims)
    for key in ("evidence_hash", "verification_result", "failure_reasons",
                "verified", "signature_verified", "not_revoked", "revoked"):
        clean.pop(key, None)
    try:
        evidence = AuthorityEvidence(**clean)
    except (TypeError, ValueError) as exc:
        raise ValueError("authority_claims_invalid") from exc
    claims_hash = sha256_of_canonical_json(evidence.claims_dict())
    if artifact.get("claims_hash") != claims_hash:
        raise ValueError("authority_claims_hash_mismatch")
    result = signature_verifier.verify(artifact)
    if not result.verified:
        raise ValueError("authority_signature_invalid")
    if result.key_id not in signer_policy.allowed_key_ids:
        raise ValueError("authority_signer_key_unapproved")
    if result.algorithm not in signer_policy.allowed_algorithms:
        raise ValueError("authority_signer_algorithm_unapproved")
    if result.issuer_identity not in signer_policy.allowed_issuer_identities:
        raise ValueError("authority_issuer_unapproved")
    signer_claim = artifact.get("signer", {})
    if signer_claim.get("key_id") != result.key_id or signer_claim.get("algorithm") != result.algorithm:
        raise ValueError("authority_signer_claim_mismatch")
    if artifact.get("issuer_identity") not in (None, result.issuer_identity):
        raise ValueError("authority_issuer_claim_mismatch")
    contract_hash = action_contract.deterministic_digest()
    if evidence.action_contract_id != action_contract.id:
        raise ValueError("authority_action_contract_id_mismatch")
    if evidence.action_contract_version != action_contract.version:
        raise ValueError("authority_action_contract_version_mismatch")
    if evidence.action_contract_hash != contract_hash:
        raise ValueError("authority_action_contract_hash_mismatch")
    if evidence.actor_identity != actor_identity:
        raise ValueError("authority_actor_identity_mismatch")
    if evidence.policy_snapshot_id != policy_snapshot_id:
        raise ValueError("authority_policy_snapshot_mismatch")
    if any(scope not in evidence.scope_grants for scope in requested_scope):
        raise ValueError("authority_scope_not_granted")
    if any(scope in evidence.scope_limitations or scope in action_contract.prohibited_scope
           for scope in requested_scope):
        raise ValueError("authority_prohibited_scope")
    validation = validate_authority_evidence(evidence, policy_snapshot_required=True, now=current)
    temporal_failures = [reason for reason in validation.failure_reasons
                         if not reason.startswith("verification_result_")]
    if temporal_failures:
        raise ValueError(temporal_failures[0])
    signed_at = artifact.get("signed_at")
    _aware_datetime(signed_at, "authority_signed_at_invalid")
    revocation = revocation_checker.check(evidence.authority_evidence_id, now=current)
    if not revocation.checked or revocation.revoked is not False:
        raise ValueError("authority_revocation_status_unestablished")
    proof_data = dict(
        authority_evidence=evidence, claims_hash=claims_hash,
        artifact_type=SIGNED_AUTHORITY_ARTIFACT_TYPE,
        artifact_version=SIGNED_AUTHORITY_ARTIFACT_VERSION,
        action_contract_hash=contract_hash, signer_key_id=str(result.key_id),
        signer_algorithm=str(result.algorithm), issuer_identity=str(result.issuer_identity),
        signer_policy_id=signer_policy.policy_id,
        signer_policy_hash=signer_policy.deterministic_hash(),
        verifier_id=str(result.verifier_id), verifier_trust_level=str(result.verifier_trust_level),
        verifier_policy_id=str(result.verifier_policy_id),
        verifier_policy_hash=str(result.verifier_policy_hash),
        signature_verification_reason=str(result.reason), signed_at=signed_at,
        verified_at=current.isoformat(), revocation=revocation,
        verification_source=AUTHORITY_VERIFICATION_SOURCE,
    )
    temporary = VerifiedAuthorityEvidence(**proof_data, verification_proof_hash="")
    proof_hash = sha256_of_canonical_json(temporary.proof_hash_payload())
    proof = VerifiedAuthorityEvidence(**proof_data, verification_proof_hash=proof_hash)
    _VERIFIED_PROOF_REGISTRY[id(proof)] = proof_hash
    return proof


def validate_verified_authority_evidence(
    proof: VerifiedAuthorityEvidence, *, action_contract: ActionClassContract,
    actor_identity: str, requested_scope: list[str], policy_snapshot_id: str,
    now: datetime | None = None, require_production_verifier: bool = False,
) -> AuthorityEvidenceValidationResult:
    """Revalidate proof integrity, process provenance, context, time, and revocation."""
    failures: list[str] = []
    expected = sha256_of_canonical_json(proof.proof_hash_payload())
    if proof.verification_proof_hash != expected or _VERIFIED_PROOF_REGISTRY.get(id(proof)) != expected:
        failures.append("authority_verification_proof_invalid")
    if proof.claims_hash != sha256_of_canonical_json(proof.authority_evidence.claims_dict()):
        failures.append("authority_claims_hash_mismatch")
    if proof.action_contract_hash != action_contract.deterministic_digest():
        failures.append("authority_action_contract_hash_mismatch")
    if proof.authority_evidence.actor_identity != actor_identity:
        failures.append("authority_actor_identity_mismatch")
    if proof.authority_evidence.policy_snapshot_id != policy_snapshot_id:
        failures.append("authority_policy_snapshot_mismatch")
    if any(not is_scope_granting(proof.authority_evidence, scope) for scope in requested_scope):
        failures.append("authority_scope_not_granted")
    if not proof.revocation.checked or proof.revocation.revoked is not False:
        failures.append("authority_revocation_status_unestablished")
    if require_production_verifier and proof.verifier_trust_level != "production":
        failures.append("authority_production_verifier_required")
    raw = validate_authority_evidence(proof.authority_evidence, now=now)
    failures.extend(reason for reason in raw.failure_reasons
                    if not reason.startswith("verification_result_"))
    return AuthorityEvidenceValidationResult(not failures, failures)
