"""Provider-neutral external UTC clock evidence trust boundary.

External clock artifacts are evidence inputs only. They do not become authority,
approval, Bind authorization, execution permission, or a runtime clock by being
verified here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import hashlib
import math
from threading import Lock
import time
from typing import Any, Callable, Protocol

from veritas_os.security.hash import sha256_of_canonical_json

EXTERNAL_CLOCK_VERIFICATION_SOURCE = "external_clock_provider_verifier"
_MIN_NONCE_BYTES = 32


@dataclass(frozen=True)
class ExternalClockChallenge:
    """In-process freshness challenge bound to a monotonic start value."""

    challenge_id: str
    challenge_nonce_hash: str
    started_monotonic: float


@dataclass
class _ExternalClockChallengeState:
    challenge: ExternalClockChallenge
    consumed: bool = False


_REGISTERED_EXTERNAL_CLOCK_CHALLENGES: dict[str, _ExternalClockChallengeState] = {}
_EXTERNAL_CLOCK_CHALLENGE_LOCK = Lock()
_VERIFIED_EXTERNAL_CLOCK_REGISTRY: dict[int, str] = {}


@dataclass(frozen=True)
class ExternalClockEvidence:
    """Provider-neutral normalized UTC evidence; never execution authority."""

    evidence_id: str
    provider_id: str
    artifact_id: str
    artifact_type: str
    artifact_version: str
    payload_hash: str
    challenge_id: str
    challenge_nonce_hash: str
    utc_time: str
    uncertainty_ms: int
    source_clock_id: str
    provenance: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-compatible normalized clock evidence fields."""
        return {
            "evidence_id": self.evidence_id,
            "provider_id": self.provider_id,
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "artifact_version": self.artifact_version,
            "payload_hash": self.payload_hash,
            "challenge_id": self.challenge_id,
            "challenge_nonce_hash": self.challenge_nonce_hash,
            "utc_time": self.utc_time,
            "uncertainty_ms": self.uncertainty_ms,
            "source_clock_id": self.source_clock_id,
            "provenance": dict(self.provenance),
            "metadata": dict(self.metadata),
        }

    def deterministic_digest(self) -> str:
        """Return stable content identity for normalized clock evidence."""
        return sha256_of_canonical_json(self.to_dict())


@dataclass(frozen=True)
class ExternalClockProviderVerificationResult:
    """Result emitted by a VERITAS-controlled provider-specific verifier."""

    verified: bool
    evidence: ExternalClockEvidence | None = None
    verifier_id: str | None = None
    verifier_trust_level: str | None = None
    verifier_policy_id: str | None = None
    verifier_policy_hash: str | None = None
    key_id: str | None = None
    algorithm: str | None = None
    semantic_consistent: bool = False
    reason: str | None = None


class ExternalClockProviderVerifier(Protocol):
    """Provider-specific verification seam owned by VERITAS deployment policy."""

    def verify(
        self, artifact: dict[str, Any]
    ) -> ExternalClockProviderVerificationResult:
        """Authenticate and normalize one provider-native clock artifact."""
        ...


@dataclass(frozen=True)
class ApprovedExternalClockProvider:
    """Deployment-owned provider/verifier binding for external UTC evidence."""

    provider_id: str
    verifier_id: str
    verifier_trust_level: str
    verifier_policy_id: str
    verifier_policy_hash: str
    require_signature_identity: bool = True


@dataclass(frozen=True)
class ExternalClockTrustPolicy:
    """VERITAS-controlled trust, uncertainty, and monotonic RTT policy."""

    policy_id: str
    approved_providers: list[ApprovedExternalClockProvider]
    max_uncertainty_ms: int
    max_monotonic_rtt_ms: float

    def approved(
        self, provider_id: str, verifier_id: str
    ) -> ApprovedExternalClockProvider | None:
        """Return the exact independently configured provider/verifier binding."""
        return next(
            (
                item
                for item in self.approved_providers
                if item.provider_id == provider_id and item.verifier_id == verifier_id
            ),
            None,
        )

    def deterministic_hash(self) -> str:
        """Return stable identity for the effective external-clock trust policy."""
        return sha256_of_canonical_json(
            {
                "policy_id": self.policy_id,
                "approved_providers": sorted(
                    (
                        {
                            "provider_id": item.provider_id,
                            "verifier_id": item.verifier_id,
                            "verifier_trust_level": item.verifier_trust_level,
                            "verifier_policy_id": item.verifier_policy_id,
                            "verifier_policy_hash": item.verifier_policy_hash,
                            "require_signature_identity": item.require_signature_identity,
                        }
                        for item in self.approved_providers
                    ),
                    key=lambda item: (item["provider_id"], item["verifier_id"]),
                ),
                "max_uncertainty_ms": self.max_uncertainty_ms,
                "max_monotonic_rtt_ms": self.max_monotonic_rtt_ms,
            }
        )


@dataclass(frozen=True)
class VerifiedExternalClockEvidence:
    """Runtime-sealed UTC evidence proof; never execution authority."""

    evidence: ExternalClockEvidence
    evidence_hash: str
    key_id: str | None
    algorithm: str | None
    verifier_id: str
    verifier_trust_level: str
    verifier_policy_id: str
    verifier_policy_hash: str
    trust_policy_id: str
    trust_policy_hash: str
    challenge_id: str
    challenge_nonce_hash: str
    monotonic_rtt_ms: float
    verification_reason: str
    verification_source: str
    verification_proof_hash: str

    def proof_hash_payload(self) -> dict[str, Any]:
        """Return the exact data bound into the sealed verification proof."""
        return {
            "evidence": self.evidence.to_dict(),
            "evidence_hash": self.evidence_hash,
            "key_id": self.key_id,
            "algorithm": self.algorithm,
            "verifier_id": self.verifier_id,
            "verifier_trust_level": self.verifier_trust_level,
            "verifier_policy_id": self.verifier_policy_id,
            "verifier_policy_hash": self.verifier_policy_hash,
            "trust_policy_id": self.trust_policy_id,
            "trust_policy_hash": self.trust_policy_hash,
            "challenge_id": self.challenge_id,
            "challenge_nonce_hash": self.challenge_nonce_hash,
            "monotonic_rtt_ms": self.monotonic_rtt_ms,
            "verification_reason": self.verification_reason,
            "verification_source": self.verification_source,
        }


def _validate_sha256(value: str, reason: str) -> None:
    if len(value) != 64:
        raise ValueError(reason)
    try:
        int(value, 16)
    except (TypeError, ValueError) as exc:
        raise ValueError(reason) from exc


def _validate_policy(policy: ExternalClockTrustPolicy) -> None:
    if not policy.policy_id.strip():
        raise ValueError("external_clock_trust_policy_id_missing")
    if (
        isinstance(policy.max_uncertainty_ms, bool)
        or policy.max_uncertainty_ms < 0
        or not math.isfinite(float(policy.max_monotonic_rtt_ms))
        or policy.max_monotonic_rtt_ms < 0
    ):
        raise ValueError("external_clock_trust_policy_invalid")


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("external_clock_utc_time_invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("external_clock_utc_time_timezone_required")
    if parsed.utcoffset() != timedelta(0):
        raise ValueError("external_clock_utc_time_not_utc")
    return parsed


def _validate_evidence(
    evidence: ExternalClockEvidence,
    *,
    policy: ExternalClockTrustPolicy,
) -> None:
    for value, reason in (
        (evidence.evidence_id, "external_clock_evidence_id_missing"),
        (evidence.provider_id, "external_clock_provider_id_missing"),
        (evidence.artifact_id, "external_clock_artifact_id_missing"),
        (evidence.artifact_type, "external_clock_artifact_type_missing"),
        (evidence.artifact_version, "external_clock_artifact_version_missing"),
        (evidence.challenge_id, "external_clock_challenge_id_missing"),
        (evidence.source_clock_id, "external_clock_source_clock_id_missing"),
    ):
        if not value.strip():
            raise ValueError(reason)

    _validate_sha256(evidence.payload_hash, "external_clock_payload_hash_invalid")
    _validate_sha256(
        evidence.challenge_nonce_hash, "external_clock_challenge_nonce_hash_invalid"
    )
    _parse_utc(evidence.utc_time)

    if (
        isinstance(evidence.uncertainty_ms, bool)
        or not isinstance(evidence.uncertainty_ms, int)
        or evidence.uncertainty_ms < 0
    ):
        raise ValueError("external_clock_uncertainty_invalid")
    if evidence.uncertainty_ms > policy.max_uncertainty_ms:
        raise ValueError("external_clock_uncertainty_excessive")


def _validate_verifier_binding(
    result: ExternalClockProviderVerificationResult,
    approved: ApprovedExternalClockProvider,
) -> None:
    expected = (
        approved.verifier_trust_level,
        approved.verifier_policy_id,
        approved.verifier_policy_hash,
    )
    actual = (
        result.verifier_trust_level,
        result.verifier_policy_id,
        result.verifier_policy_hash,
    )
    if actual != expected:
        raise ValueError("external_clock_verifier_binding_mismatch")
    if approved.require_signature_identity and (not result.key_id or not result.algorithm):
        raise ValueError("external_clock_signature_identity_missing")


def register_external_clock_challenge(
    challenge_id: str,
    nonce: str,
    *,
    monotonic_now: Callable[[], float] = time.monotonic,
) -> ExternalClockChallenge:
    """Register a single-use challenge without relying on the local wall clock."""
    if not challenge_id.strip():
        raise ValueError("external_clock_challenge_id_missing")
    if len(nonce.encode("utf-8")) < _MIN_NONCE_BYTES:
        raise ValueError("external_clock_challenge_nonce_too_short")

    started = float(monotonic_now())
    if not math.isfinite(started) or started < 0:
        raise ValueError("external_clock_challenge_monotonic_invalid")

    challenge = ExternalClockChallenge(
        challenge_id=challenge_id,
        challenge_nonce_hash=hashlib.sha256(nonce.encode("utf-8")).hexdigest(),
        started_monotonic=started,
    )
    with _EXTERNAL_CLOCK_CHALLENGE_LOCK:
        if challenge_id in _REGISTERED_EXTERNAL_CLOCK_CHALLENGES:
            raise ValueError("external_clock_challenge_duplicate")
        _REGISTERED_EXTERNAL_CLOCK_CHALLENGES[challenge_id] = (
            _ExternalClockChallengeState(challenge=challenge)
        )
    return challenge


def verify_external_clock_artifact_to_evidence(
    artifact: dict[str, Any],
    *,
    challenge: ExternalClockChallenge,
    provider_verifier: ExternalClockProviderVerifier,
    trust_policy: ExternalClockTrustPolicy,
    monotonic_now: Callable[[], float] = time.monotonic,
) -> VerifiedExternalClockEvidence:
    """Verify and seal one provider artifact as non-authoritative UTC evidence."""
    _validate_policy(trust_policy)

    with _EXTERNAL_CLOCK_CHALLENGE_LOCK:
        state = _REGISTERED_EXTERNAL_CLOCK_CHALLENGES.get(challenge.challenge_id)
        if state is None or state.challenge is not challenge:
            raise ValueError("external_clock_challenge_invalid")
        if state.consumed:
            raise ValueError("external_clock_challenge_replay")

    result = provider_verifier.verify(artifact)
    if not result.verified:
        raise ValueError("external_clock_provider_verification_failed")
    if result.evidence is None:
        raise ValueError("external_clock_normalized_evidence_missing")
    if not result.semantic_consistent:
        raise ValueError("external_clock_semantic_inconsistent")
    if not result.verifier_id:
        raise ValueError("external_clock_verifier_id_missing")

    evidence = result.evidence
    approved = trust_policy.approved(evidence.provider_id, result.verifier_id)
    if approved is None:
        raise ValueError("external_clock_provider_verifier_unapproved")
    _validate_verifier_binding(result, approved)
    _validate_evidence(evidence, policy=trust_policy)

    if evidence.challenge_id != challenge.challenge_id:
        raise ValueError("external_clock_challenge_identifier_mismatch")
    if evidence.challenge_nonce_hash != challenge.challenge_nonce_hash:
        raise ValueError("external_clock_challenge_nonce_mismatch")

    finished = float(monotonic_now())
    if not math.isfinite(finished):
        raise ValueError("external_clock_monotonic_rtt_invalid")
    monotonic_rtt_ms = (finished - challenge.started_monotonic) * 1000.0
    if monotonic_rtt_ms < 0:
        raise ValueError("external_clock_monotonic_rtt_negative")
    if monotonic_rtt_ms > trust_policy.max_monotonic_rtt_ms:
        raise ValueError("external_clock_monotonic_rtt_excessive")

    proof_data = {
        "evidence": evidence,
        "evidence_hash": evidence.deterministic_digest(),
        "key_id": result.key_id,
        "algorithm": result.algorithm,
        "verifier_id": result.verifier_id,
        "verifier_trust_level": str(result.verifier_trust_level),
        "verifier_policy_id": str(result.verifier_policy_id),
        "verifier_policy_hash": str(result.verifier_policy_hash),
        "trust_policy_id": trust_policy.policy_id,
        "trust_policy_hash": trust_policy.deterministic_hash(),
        "challenge_id": challenge.challenge_id,
        "challenge_nonce_hash": challenge.challenge_nonce_hash,
        "monotonic_rtt_ms": monotonic_rtt_ms,
        "verification_reason": str(result.reason or "verified"),
        "verification_source": EXTERNAL_CLOCK_VERIFICATION_SOURCE,
    }
    temporary = VerifiedExternalClockEvidence(
        **proof_data, verification_proof_hash=""
    )
    proof_hash = sha256_of_canonical_json(temporary.proof_hash_payload())
    proof = VerifiedExternalClockEvidence(
        **proof_data, verification_proof_hash=proof_hash
    )

    with _EXTERNAL_CLOCK_CHALLENGE_LOCK:
        current = _REGISTERED_EXTERNAL_CLOCK_CHALLENGES.get(challenge.challenge_id)
        if current is None or current.challenge is not challenge or current.consumed:
            raise ValueError("external_clock_challenge_replay")
        current.consumed = True

    _VERIFIED_EXTERNAL_CLOCK_REGISTRY[id(proof)] = proof_hash
    return proof


def validate_verified_external_clock_evidence(
    proof: VerifiedExternalClockEvidence,
    *,
    trust_policy: ExternalClockTrustPolicy,
) -> list[str]:
    """Revalidate runtime seal, trust binding, and standalone clock constraints."""
    failures: list[str] = []
    try:
        _validate_policy(trust_policy)
    except ValueError as exc:
        return [str(exc)]

    expected_hash = sha256_of_canonical_json(proof.proof_hash_payload())
    if (
        proof.verification_proof_hash != expected_hash
        or _VERIFIED_EXTERNAL_CLOCK_REGISTRY.get(id(proof)) != expected_hash
    ):
        failures.append("external_clock_verification_proof_invalid")

    if proof.evidence_hash != proof.evidence.deterministic_digest():
        failures.append("external_clock_evidence_hash_mismatch")
    if proof.trust_policy_id != trust_policy.policy_id:
        failures.append("external_clock_trust_policy_id_mismatch")
    if proof.trust_policy_hash != trust_policy.deterministic_hash():
        failures.append("external_clock_trust_policy_hash_mismatch")

    approved = trust_policy.approved(proof.evidence.provider_id, proof.verifier_id)
    if approved is None:
        failures.append("external_clock_provider_verifier_unapproved")
    else:
        expected_binding = (
            approved.verifier_trust_level,
            approved.verifier_policy_id,
            approved.verifier_policy_hash,
        )
        actual_binding = (
            proof.verifier_trust_level,
            proof.verifier_policy_id,
            proof.verifier_policy_hash,
        )
        if actual_binding != expected_binding:
            failures.append("external_clock_verifier_binding_mismatch")
        if approved.require_signature_identity and (
            not proof.key_id or not proof.algorithm
        ):
            failures.append("external_clock_signature_identity_missing")

    try:
        _validate_evidence(proof.evidence, policy=trust_policy)
    except ValueError as exc:
        failures.append(str(exc))

    if proof.challenge_id != proof.evidence.challenge_id:
        failures.append("external_clock_challenge_identifier_mismatch")
    if proof.challenge_nonce_hash != proof.evidence.challenge_nonce_hash:
        failures.append("external_clock_challenge_nonce_mismatch")
    if (
        not math.isfinite(float(proof.monotonic_rtt_ms))
        or proof.monotonic_rtt_ms < 0
    ):
        failures.append("external_clock_monotonic_rtt_invalid")
    elif proof.monotonic_rtt_ms > trust_policy.max_monotonic_rtt_ms:
        failures.append("external_clock_monotonic_rtt_excessive")

    return failures
