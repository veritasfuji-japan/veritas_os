"""Provider-neutral external measurement evidence trust boundary.

External measurement artifacts are evidence inputs only.  They do not become
AuthorityEvidence, HumanApproval, BindAuthorization, or a GovernanceDecision by
being signed or verified.

Provider-specific adapters are responsible for parsing and cryptographically
verifying their native artifact formats.  This module then applies
VERITAS-controlled trust, temporal, semantic, and replay checks before sealing a
``VerifiedExternalMeasurementEvidence`` object.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from veritas_os.security.hash import sha256_of_canonical_json

EXTERNAL_MEASUREMENT_VERIFICATION_SOURCE = "external_measurement_provider_verifier"
_VERIFIED_EXTERNAL_MEASUREMENT_REGISTRY: dict[int, str] = {}


@dataclass(frozen=True)
class ExternalMeasurementEvidence:
    """Provider-neutral normalized measurement facts; not execution authority."""

    evidence_id: str
    provider_id: str
    artifact_id: str
    artifact_type: str
    artifact_version: str
    payload_hash: str
    observed_at: str
    issued_at: str
    expires_at: str | None
    replay_token: str
    measured_scope: dict[str, Any]
    measurement_coverage: float | None = None
    semantic_facts: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-compatible normalized evidence fields."""
        return {
            "evidence_id": self.evidence_id,
            "provider_id": self.provider_id,
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "artifact_version": self.artifact_version,
            "payload_hash": self.payload_hash,
            "observed_at": self.observed_at,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "replay_token": self.replay_token,
            "measured_scope": dict(self.measured_scope),
            "measurement_coverage": self.measurement_coverage,
            "semantic_facts": dict(self.semantic_facts),
            "provenance": dict(self.provenance),
            "metadata": dict(self.metadata),
        }

    def deterministic_digest(self) -> str:
        """Return content identity for the normalized measurement evidence."""
        return sha256_of_canonical_json(self.to_dict())


@dataclass(frozen=True)
class ExternalMeasurementProviderVerificationResult:
    """Result emitted by a VERITAS-controlled provider-specific verifier."""

    verified: bool
    evidence: ExternalMeasurementEvidence | None = None
    verifier_id: str | None = None
    verifier_trust_level: str | None = None
    verifier_policy_id: str | None = None
    verifier_policy_hash: str | None = None
    key_id: str | None = None
    algorithm: str | None = None
    semantic_consistent: bool = False
    reason: str | None = None


class ExternalMeasurementProviderVerifier(Protocol):
    """Provider-specific verification seam owned by VERITAS deployment policy."""

    def verify(
        self, artifact: dict[str, Any]
    ) -> ExternalMeasurementProviderVerificationResult:
        """Verify a native provider artifact and return normalized evidence."""
        ...


@dataclass(frozen=True)
class ApprovedExternalMeasurementProvider:
    """Deployment-owned allowlist entry for one measurement provider verifier."""

    provider_id: str
    verifier_id: str
    verifier_trust_level: str
    verifier_policy_id: str
    verifier_policy_hash: str


@dataclass(frozen=True)
class ExternalMeasurementTrustPolicy:
    """VERITAS-controlled trust, freshness, and verifier policy."""

    policy_id: str
    approved_providers: list[ApprovedExternalMeasurementProvider]
    max_age_seconds: int
    max_future_skew_seconds: int = 0
    require_expiry: bool = True

    def approved(
        self, provider_id: str, verifier_id: str
    ) -> ApprovedExternalMeasurementProvider | None:
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
        """Return stable identity for the effective external-measurement policy."""
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
                        }
                        for item in self.approved_providers
                    ),
                    key=lambda item: (item["provider_id"], item["verifier_id"]),
                ),
                "max_age_seconds": self.max_age_seconds,
                "max_future_skew_seconds": self.max_future_skew_seconds,
                "require_expiry": self.require_expiry,
            }
        )


class ExternalMeasurementReplayGuard(Protocol):
    """Atomic single-use guard for accepted external measurement artifacts."""

    def consume_once(self, replay_key: str, *, observed_at: datetime) -> bool:
        """Return true only for the first accepted use of ``replay_key``."""
        ...


@dataclass(frozen=True)
class VerifiedExternalMeasurementEvidence:
    """Runtime-sealed external measurement proof; never execution authority."""

    evidence: ExternalMeasurementEvidence
    evidence_hash: str
    key_id: str
    algorithm: str
    verifier_id: str
    verifier_trust_level: str
    verifier_policy_id: str
    verifier_policy_hash: str
    trust_policy_id: str
    trust_policy_hash: str
    verified_at: str
    verification_reason: str
    verification_source: str
    replay_key: str
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
            "verified_at": self.verified_at,
            "verification_reason": self.verification_reason,
            "verification_source": self.verification_source,
            "replay_key": self.replay_key,
        }


def _aware_datetime(value: str, reason: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(reason) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(reason + "_timezone_required")
    return parsed


def _validate_payload_hash(value: str) -> None:
    if len(value) != 64:
        raise ValueError("external_measurement_payload_hash_invalid")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError("external_measurement_payload_hash_invalid") from exc


def _validate_normalized_evidence(
    evidence: ExternalMeasurementEvidence,
    *,
    policy: ExternalMeasurementTrustPolicy,
    now: datetime,
) -> datetime:
    for value, reason in (
        (evidence.evidence_id, "external_measurement_evidence_id_missing"),
        (evidence.provider_id, "external_measurement_provider_id_missing"),
        (evidence.artifact_id, "external_measurement_artifact_id_missing"),
        (evidence.artifact_type, "external_measurement_artifact_type_missing"),
        (evidence.artifact_version, "external_measurement_artifact_version_missing"),
        (evidence.replay_token, "external_measurement_replay_token_missing"),
    ):
        if not value.strip():
            raise ValueError(reason)
    _validate_payload_hash(evidence.payload_hash)
    if not evidence.measured_scope:
        raise ValueError("external_measurement_scope_missing")
    if evidence.measurement_coverage is not None and not (
        0.0 <= evidence.measurement_coverage <= 1.0
    ):
        raise ValueError("external_measurement_coverage_invalid")

    observed_at = _aware_datetime(
        evidence.observed_at, "external_measurement_observed_at_invalid"
    )
    issued_at = _aware_datetime(
        evidence.issued_at, "external_measurement_issued_at_invalid"
    )
    future_limit = now + timedelta(seconds=policy.max_future_skew_seconds)
    if observed_at > future_limit or issued_at > future_limit:
        raise ValueError("external_measurement_timestamp_future")
    if issued_at < observed_at:
        raise ValueError("external_measurement_timestamp_order_invalid")
    if now - observed_at > timedelta(seconds=policy.max_age_seconds):
        raise ValueError("external_measurement_stale")

    if evidence.expires_at is None:
        if policy.require_expiry:
            raise ValueError("external_measurement_expiry_missing")
    else:
        expires_at = _aware_datetime(
            evidence.expires_at, "external_measurement_expires_at_invalid"
        )
        if expires_at < issued_at:
            raise ValueError("external_measurement_expiry_order_invalid")
        if now >= expires_at:
            raise ValueError("external_measurement_expired")
    return observed_at


def _validate_verifier_binding(
    result: ExternalMeasurementProviderVerificationResult,
    approved: ApprovedExternalMeasurementProvider,
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
        raise ValueError("external_measurement_verifier_binding_mismatch")
    if not result.key_id or not result.algorithm:
        raise ValueError("external_measurement_signature_identity_missing")


def verify_external_measurement_artifact_to_evidence(
    artifact: dict[str, Any],
    *,
    provider_verifier: ExternalMeasurementProviderVerifier,
    trust_policy: ExternalMeasurementTrustPolicy,
    replay_guard: ExternalMeasurementReplayGuard,
    now: datetime | None = None,
) -> VerifiedExternalMeasurementEvidence:
    """Verify and seal one provider artifact as non-authoritative evidence.

    The provider artifact itself is never accepted as a trust anchor.  A
    VERITAS-controlled provider verifier must first authenticate and normalize
    it, after which this boundary applies independently configured trust,
    freshness, semantic-consistency, and replay requirements.
    """
    current = now or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("external_measurement_validation_now_timezone_required")
    if trust_policy.max_age_seconds < 0 or trust_policy.max_future_skew_seconds < 0:
        raise ValueError("external_measurement_trust_policy_invalid")

    result = provider_verifier.verify(artifact)
    if not result.verified:
        raise ValueError("external_measurement_provider_verification_failed")
    if result.evidence is None:
        raise ValueError("external_measurement_normalized_evidence_missing")
    if not result.semantic_consistent:
        raise ValueError("external_measurement_semantic_inconsistent")
    if not result.verifier_id:
        raise ValueError("external_measurement_verifier_id_missing")

    evidence = result.evidence
    approved = trust_policy.approved(evidence.provider_id, result.verifier_id)
    if approved is None:
        raise ValueError("external_measurement_provider_verifier_unapproved")
    _validate_verifier_binding(result, approved)
    observed_at = _validate_normalized_evidence(
        evidence, policy=trust_policy, now=current
    )

    replay_key = sha256_of_canonical_json(
        {
            "provider_id": evidence.provider_id,
            "artifact_id": evidence.artifact_id,
            "payload_hash": evidence.payload_hash,
            "replay_token": evidence.replay_token,
        }
    )
    if not replay_guard.consume_once(replay_key, observed_at=observed_at):
        raise ValueError("external_measurement_replay_detected")

    evidence_hash = evidence.deterministic_digest()
    proof_data = {
        "evidence": evidence,
        "evidence_hash": evidence_hash,
        "key_id": str(result.key_id),
        "algorithm": str(result.algorithm),
        "verifier_id": result.verifier_id,
        "verifier_trust_level": str(result.verifier_trust_level),
        "verifier_policy_id": str(result.verifier_policy_id),
        "verifier_policy_hash": str(result.verifier_policy_hash),
        "trust_policy_id": trust_policy.policy_id,
        "trust_policy_hash": trust_policy.deterministic_hash(),
        "verified_at": current.isoformat(),
        "verification_reason": str(result.reason or "verified"),
        "verification_source": EXTERNAL_MEASUREMENT_VERIFICATION_SOURCE,
        "replay_key": replay_key,
    }
    temporary = VerifiedExternalMeasurementEvidence(
        **proof_data, verification_proof_hash=""
    )
    proof_hash = sha256_of_canonical_json(temporary.proof_hash_payload())
    proof = VerifiedExternalMeasurementEvidence(
        **proof_data, verification_proof_hash=proof_hash
    )
    _VERIFIED_EXTERNAL_MEASUREMENT_REGISTRY[id(proof)] = proof_hash
    return proof


def validate_verified_external_measurement_evidence(
    proof: VerifiedExternalMeasurementEvidence,
    *,
    trust_policy: ExternalMeasurementTrustPolicy,
    now: datetime | None = None,
) -> list[str]:
    """Revalidate sealed proof integrity, trust binding, and current freshness."""
    failures: list[str] = []
    current = now or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        return ["external_measurement_validation_now_timezone_required"]

    expected_hash = sha256_of_canonical_json(proof.proof_hash_payload())
    if (
        proof.verification_proof_hash != expected_hash
        or _VERIFIED_EXTERNAL_MEASUREMENT_REGISTRY.get(id(proof)) != expected_hash
    ):
        failures.append("external_measurement_verification_proof_invalid")
    if proof.evidence_hash != proof.evidence.deterministic_digest():
        failures.append("external_measurement_evidence_hash_mismatch")
    if proof.trust_policy_id != trust_policy.policy_id:
        failures.append("external_measurement_trust_policy_id_mismatch")
    if proof.trust_policy_hash != trust_policy.deterministic_hash():
        failures.append("external_measurement_trust_policy_hash_mismatch")

    approved = trust_policy.approved(proof.evidence.provider_id, proof.verifier_id)
    if approved is None:
        failures.append("external_measurement_provider_verifier_unapproved")
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
            failures.append("external_measurement_verifier_binding_mismatch")

    try:
        _validate_normalized_evidence(proof.evidence, policy=trust_policy, now=current)
        _aware_datetime(proof.verified_at, "external_measurement_verified_at_invalid")
    except ValueError as exc:
        failures.append(str(exc))
    return failures
