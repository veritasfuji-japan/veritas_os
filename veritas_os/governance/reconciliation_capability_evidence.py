"""Downstream reconciliation capability evidence and verifier trust boundary.

Raw reconciliation capability artifacts remain descriptive evidence only. They
do not authenticate themselves and do not create execution eligibility,
execution permission, retry permission, or a terminal external-effect claim.

A deployment-controlled verifier may seal one raw artifact into
``VerifiedReconciliationCapabilityEvidence``. Runtime enforcement must validate
that sealed proof against independently configured verifier trust before relying
on the underlying capability classification.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from veritas_os.security.hash import sha256_of_canonical_json

_HASH = r"^[0-9a-f]{64}$"


class ReconciliationCapabilityClass(StrEnum):
    """Descriptive target capability classes from the architecture boundary."""

    AUTHORITATIVE_QUERY = "AUTHORITATIVE_QUERY"
    AUTHORITATIVE_EVIDENCE = "AUTHORITATIVE_EVIDENCE"
    HEURISTIC_ONLY = "HEURISTIC_ONLY"
    UNAVAILABLE_OR_UNVERIFIED = "UNAVAILABLE_OR_UNVERIFIED"


def _parse_aware_timestamp(value: str, reason: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(reason) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(reason)
    return parsed


class ReconciliationCapabilityEvidence(BaseModel):
    """Immutable capability assessment; never execution authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format_version: Literal["reconciliation-capability-evidence/v1"] = (
        "reconciliation-capability-evidence/v1"
    )
    artifact_type: Literal["reconciliation_capability_evidence"] = (
        "reconciliation_capability_evidence"
    )
    artifact_version: Literal["v1"] = "v1"

    evidence_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    endpoint_identity_binding_digest: str = Field(pattern=_HASH)
    target_configuration_digest: str = Field(pattern=_HASH)
    capability_class: ReconciliationCapabilityClass

    correlation_identity_type: str | None = None
    correlation_identity_pre_dispatch: bool
    correlation_identity_caller_controlled: bool
    exact_attempt_lookup_available: bool
    exact_lineage_binding_supported: bool
    downstream_durability_supported: bool
    non_mutating_observation_supported: bool
    authoritative_evidence_available: bool

    source_type: str = Field(min_length=1)
    source_identity: str = Field(min_length=1)
    source_digest: str = Field(pattern=_HASH)

    verifier_id: str | None = None
    verifier_policy_id: str | None = None
    verifier_policy_hash: str | None = Field(default=None, pattern=_HASH)

    assessed_at: str = Field(min_length=1)
    valid_until: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    execution_eligibility_decision_created: Literal[False] = False
    execution_permission_created: Literal[False] = False
    retry_permission_created: Literal[False] = False
    terminal_effect_claim_created: Literal[False] = False

    @model_validator(mode="after")
    def validate_semantics(self) -> "ReconciliationCapabilityEvidence":
        """Fail closed on internally inconsistent capability evidence."""
        assessed = _parse_aware_timestamp(
            self.assessed_at,
            "reconciliation_capability_assessed_at_invalid",
        )
        if self.valid_until is not None:
            valid_until = _parse_aware_timestamp(
                self.valid_until,
                "reconciliation_capability_valid_until_invalid",
            )
            if valid_until <= assessed:
                raise ValueError(
                    "reconciliation_capability_valid_until_not_after_assessed_at"
                )

        verifier_values = (
            self.verifier_id,
            self.verifier_policy_id,
            self.verifier_policy_hash,
        )
        if any(value is not None for value in verifier_values) and not all(
            isinstance(value, str) and value.strip() for value in verifier_values
        ):
            raise ValueError("reconciliation_capability_verifier_binding_incomplete")

        if self.capability_class in {
            ReconciliationCapabilityClass.AUTHORITATIVE_QUERY,
            ReconciliationCapabilityClass.AUTHORITATIVE_EVIDENCE,
        }:
            if not all(
                (
                    self.exact_lineage_binding_supported,
                    self.downstream_durability_supported,
                    self.non_mutating_observation_supported,
                )
            ):
                raise ValueError(
                    "reconciliation_capability_authoritative_properties_missing"
                )
            if not all(
                isinstance(value, str) and value.strip() for value in verifier_values
            ):
                raise ValueError(
                    "reconciliation_capability_authoritative_verifier_missing"
                )

        if self.capability_class is ReconciliationCapabilityClass.AUTHORITATIVE_QUERY:
            if (
                not self.correlation_identity_pre_dispatch
                or not self.exact_attempt_lookup_available
                or not self.correlation_identity_type
                or not self.correlation_identity_type.strip()
            ):
                raise ValueError(
                    "reconciliation_capability_authoritative_query_invalid"
                )

        if (
            self.capability_class
            is ReconciliationCapabilityClass.AUTHORITATIVE_EVIDENCE
            and not self.authoritative_evidence_available
        ):
            raise ValueError(
                "reconciliation_capability_authoritative_evidence_invalid"
            )

        if self.capability_class is ReconciliationCapabilityClass.HEURISTIC_ONLY:
            if (
                self.exact_attempt_lookup_available
                or self.authoritative_evidence_available
            ):
                raise ValueError("reconciliation_capability_heuristic_class_conflict")

        return self

    def deterministic_digest(self) -> str:
        """Return stable content identity for this non-authorizing artifact."""
        return sha256_of_canonical_json(self.model_dump(mode="json"))


RECONCILIATION_CAPABILITY_VERIFICATION_SOURCE = (
    "reconciliation_capability_evidence_verifier"
)
_VERIFIED_RECONCILIATION_CAPABILITY_REGISTRY: dict[int, str] = {}


@dataclass(frozen=True)
class ReconciliationCapabilityVerificationResult:
    """Result emitted by a deployment-controlled capability verifier."""

    verified: bool
    evidence_digest: str | None = None
    verifier_id: str | None = None
    verifier_policy_id: str | None = None
    verifier_policy_hash: str | None = None
    verification_material_digest: str | None = None
    semantic_consistent: bool = False
    reason: str | None = None


class ReconciliationCapabilityEvidenceVerifier(Protocol):
    """Verifier seam owned by deployment policy, never by request data."""

    def verify(
        self,
        evidence: ReconciliationCapabilityEvidence,
    ) -> ReconciliationCapabilityVerificationResult:
        """Authenticate and assess one normalized capability artifact."""
        ...


@dataclass(frozen=True)
class ApprovedReconciliationCapabilityVerifier:
    """Deployment-owned verifier/policy binding."""

    verifier_id: str
    verifier_policy_id: str
    verifier_policy_hash: str


@dataclass(frozen=True)
class ReconciliationCapabilityVerifierTrustPolicy:
    """Independent trust policy for capability verification."""

    policy_id: str
    approved_verifiers: tuple[ApprovedReconciliationCapabilityVerifier, ...]

    def approved(
        self,
        verifier_id: str,
    ) -> ApprovedReconciliationCapabilityVerifier | None:
        """Return the exact configured verifier binding, if approved."""
        return next(
            (
                item
                for item in self.approved_verifiers
                if item.verifier_id == verifier_id
            ),
            None,
        )

    def deterministic_hash(self) -> str:
        """Return stable identity for the configured verifier trust."""
        return sha256_of_canonical_json(
            {
                "policy_id": self.policy_id,
                "approved_verifiers": sorted(
                    (
                        {
                            "verifier_id": item.verifier_id,
                            "verifier_policy_id": item.verifier_policy_id,
                            "verifier_policy_hash": item.verifier_policy_hash,
                        }
                        for item in self.approved_verifiers
                    ),
                    key=lambda item: item["verifier_id"],
                ),
            }
        )


class VerifiedReconciliationCapabilityEvidence(BaseModel):
    """Runtime-sealed capability proof; still never execution authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format_version: Literal["verified-reconciliation-capability-evidence/v1"] = (
        "verified-reconciliation-capability-evidence/v1"
    )
    artifact_type: Literal["verified_reconciliation_capability_evidence"] = (
        "verified_reconciliation_capability_evidence"
    )
    artifact_version: Literal["v1"] = "v1"

    evidence: ReconciliationCapabilityEvidence
    evidence_digest: str = Field(pattern=_HASH)
    verifier_id: str = Field(min_length=1)
    verifier_policy_id: str = Field(min_length=1)
    verifier_policy_hash: str = Field(pattern=_HASH)
    trust_policy_id: str = Field(min_length=1)
    trust_policy_hash: str = Field(pattern=_HASH)
    verification_material_digest: str = Field(pattern=_HASH)
    verified_at: str = Field(min_length=1)
    verification_reason: str = Field(min_length=1)
    verification_source: Literal[
        "reconciliation_capability_evidence_verifier"
    ] = RECONCILIATION_CAPABILITY_VERIFICATION_SOURCE
    verification_proof_hash: str = Field(pattern=_HASH)

    execution_eligibility_decision_created: Literal[False] = False
    execution_permission_created: Literal[False] = False
    retry_permission_created: Literal[False] = False
    terminal_effect_claim_created: Literal[False] = False

    @model_validator(mode="after")
    def validate_proof_shape(self) -> "VerifiedReconciliationCapabilityEvidence":
        """Validate deterministic internal bindings without trusting the proof."""
        _parse_aware_timestamp(
            self.verified_at,
            "reconciliation_capability_verified_at_invalid",
        )
        if self.evidence_digest != self.evidence.deterministic_digest():
            raise ValueError("reconciliation_capability_verified_evidence_mismatch")
        return self

    def proof_hash_payload(self) -> dict[str, Any]:
        """Return the exact payload sealed by the runtime helper."""
        payload = self.model_dump(mode="json")
        payload.pop("verification_proof_hash", None)
        return payload

    def deterministic_digest(self) -> str:
        """Return stable identity for the sealed proof artifact."""
        return sha256_of_canonical_json(self.model_dump(mode="json"))


def _validate_hash_value(value: str | None, reason: str) -> None:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(reason)
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(reason) from exc
    if value != value.lower():
        raise ValueError(reason)


def _validate_verifier_trust_policy(
    policy: ReconciliationCapabilityVerifierTrustPolicy,
) -> None:
    if type(policy) is not ReconciliationCapabilityVerifierTrustPolicy:
        raise ValueError("reconciliation_capability_verifier_trust_policy_invalid")
    if not policy.policy_id.strip() or not policy.approved_verifiers:
        raise ValueError("reconciliation_capability_verifier_trust_policy_invalid")

    verifier_ids: set[str] = set()
    for item in policy.approved_verifiers:
        if (
            type(item) is not ApprovedReconciliationCapabilityVerifier
            or not item.verifier_id.strip()
            or not item.verifier_policy_id.strip()
        ):
            raise ValueError(
                "reconciliation_capability_verifier_trust_policy_invalid"
            )
        _validate_hash_value(
            item.verifier_policy_hash,
            "reconciliation_capability_verifier_trust_policy_invalid",
        )
        if item.verifier_id in verifier_ids:
            raise ValueError(
                "reconciliation_capability_verifier_trust_policy_invalid"
            )
        verifier_ids.add(item.verifier_id)


def verify_reconciliation_capability_evidence_to_proof(
    evidence: ReconciliationCapabilityEvidence,
    *,
    verifier: ReconciliationCapabilityEvidenceVerifier,
    trust_policy: ReconciliationCapabilityVerifierTrustPolicy,
    verified_at: datetime,
) -> VerifiedReconciliationCapabilityEvidence:
    """Verify and runtime-seal one non-authorizing capability artifact."""
    if type(evidence) is not ReconciliationCapabilityEvidence:
        raise ValueError("reconciliation_capability_evidence_required")
    if verified_at.tzinfo is None or verified_at.utcoffset() is None:
        raise ValueError("reconciliation_capability_verified_at_invalid")
    _validate_verifier_trust_policy(trust_policy)

    result = verifier.verify(evidence)
    if type(result) is not ReconciliationCapabilityVerificationResult:
        raise ValueError("reconciliation_capability_verification_result_invalid")
    if not result.verified:
        raise ValueError("reconciliation_capability_verification_failed")
    if not result.semantic_consistent:
        raise ValueError("reconciliation_capability_verification_inconsistent")

    evidence_digest = evidence.deterministic_digest()
    if result.evidence_digest != evidence_digest:
        raise ValueError("reconciliation_capability_verified_evidence_mismatch")

    verifier_values = (
        result.verifier_id,
        result.verifier_policy_id,
        result.verifier_policy_hash,
    )
    if not all(isinstance(value, str) and value.strip() for value in verifier_values):
        raise ValueError("reconciliation_capability_verified_verifier_missing")
    _validate_hash_value(
        result.verifier_policy_hash,
        "reconciliation_capability_verified_verifier_invalid",
    )
    _validate_hash_value(
        result.verification_material_digest,
        "reconciliation_capability_verification_material_invalid",
    )

    approved = trust_policy.approved(str(result.verifier_id))
    if approved is None:
        raise ValueError("reconciliation_capability_verifier_unapproved")
    if (
        approved.verifier_policy_id,
        approved.verifier_policy_hash,
    ) != (
        result.verifier_policy_id,
        result.verifier_policy_hash,
    ):
        raise ValueError("reconciliation_capability_verifier_binding_mismatch")

    declared = (
        evidence.verifier_id,
        evidence.verifier_policy_id,
        evidence.verifier_policy_hash,
    )
    if any(value is not None for value in declared) and declared != verifier_values:
        raise ValueError("reconciliation_capability_verifier_declaration_mismatch")

    proof_data = {
        "evidence": evidence,
        "evidence_digest": evidence_digest,
        "verifier_id": str(result.verifier_id),
        "verifier_policy_id": str(result.verifier_policy_id),
        "verifier_policy_hash": str(result.verifier_policy_hash),
        "trust_policy_id": trust_policy.policy_id,
        "trust_policy_hash": trust_policy.deterministic_hash(),
        "verification_material_digest": str(result.verification_material_digest),
        "verified_at": verified_at.isoformat(),
        "verification_reason": str(result.reason or "verified"),
        "verification_source": RECONCILIATION_CAPABILITY_VERIFICATION_SOURCE,
    }
    temporary = VerifiedReconciliationCapabilityEvidence(
        **proof_data,
        verification_proof_hash="0" * 64,
    )
    proof_hash = sha256_of_canonical_json(temporary.proof_hash_payload())
    proof = VerifiedReconciliationCapabilityEvidence(
        **proof_data,
        verification_proof_hash=proof_hash,
    )
    _VERIFIED_RECONCILIATION_CAPABILITY_REGISTRY[id(proof)] = proof_hash
    return proof


def validate_verified_reconciliation_capability_evidence(
    proof: VerifiedReconciliationCapabilityEvidence,
    *,
    trust_policy: ReconciliationCapabilityVerifierTrustPolicy,
    current_endpoint_identity_binding_digest: str,
    current_target_configuration_digest: str,
    verification_time: datetime,
    require_authoritative: bool = False,
    expected_evidence_digest: str | None = None,
) -> list[str]:
    """Revalidate runtime seal, verifier trust, and current target bindings."""
    if type(proof) is not VerifiedReconciliationCapabilityEvidence:
        return ["reconciliation_capability_verified_proof_required"]
    if verification_time.tzinfo is None or verification_time.utcoffset() is None:
        raise ValueError("reconciliation_capability_verification_time_invalid")

    try:
        _validate_verifier_trust_policy(trust_policy)
    except ValueError as exc:
        return [str(exc)]

    failures: list[str] = []
    expected_proof_hash = sha256_of_canonical_json(proof.proof_hash_payload())
    if (
        proof.verification_proof_hash != expected_proof_hash
        or _VERIFIED_RECONCILIATION_CAPABILITY_REGISTRY.get(id(proof))
        != expected_proof_hash
    ):
        failures.append("reconciliation_capability_verification_proof_invalid")

    if proof.evidence_digest != proof.evidence.deterministic_digest():
        failures.append("reconciliation_capability_verified_evidence_mismatch")
    if proof.trust_policy_id != trust_policy.policy_id:
        failures.append("reconciliation_capability_trust_policy_id_mismatch")
    if proof.trust_policy_hash != trust_policy.deterministic_hash():
        failures.append("reconciliation_capability_trust_policy_hash_mismatch")

    approved = trust_policy.approved(proof.verifier_id)
    if approved is None:
        failures.append("reconciliation_capability_verifier_unapproved")
    elif (
        approved.verifier_policy_id,
        approved.verifier_policy_hash,
    ) != (
        proof.verifier_policy_id,
        proof.verifier_policy_hash,
    ):
        failures.append("reconciliation_capability_verifier_binding_mismatch")

    verified_at = _parse_aware_timestamp(
        proof.verified_at,
        "reconciliation_capability_verified_at_invalid",
    )
    if verified_at > verification_time:
        failures.append("reconciliation_capability_verification_from_future")

    failures.extend(
        validate_reconciliation_capability_for_current_target(
            proof.evidence,
            current_endpoint_identity_binding_digest=(
                current_endpoint_identity_binding_digest
            ),
            current_target_configuration_digest=current_target_configuration_digest,
            verification_time=verification_time,
            require_authoritative=require_authoritative,
            expected_verifier_id=proof.verifier_id,
            expected_verifier_policy_id=proof.verifier_policy_id,
            expected_verifier_policy_hash=proof.verifier_policy_hash,
            expected_evidence_digest=expected_evidence_digest,
        )
    )
    return failures

def validate_reconciliation_capability_for_current_target(
    evidence: ReconciliationCapabilityEvidence,
    *,
    current_endpoint_identity_binding_digest: str,
    current_target_configuration_digest: str,
    verification_time: datetime,
    require_authoritative: bool = False,
    expected_verifier_id: str | None = None,
    expected_verifier_policy_id: str | None = None,
    expected_verifier_policy_hash: str | None = None,
    expected_evidence_digest: str | None = None,
) -> list[str]:
    """Recheck one capability artifact against current target context.

    This validator is deliberately non-authorizing.  It returns deterministic
    failure reasons only; it does not create execution eligibility, execution
    permission, retry permission, or an external-effect claim.

    Expected verifier values and the expected evidence digest are trust anchors
    supplied by the caller from an independently controlled source.  The artifact
    must not be treated as self-authenticating merely because those fields exist.
    """
    if verification_time.tzinfo is None or verification_time.utcoffset() is None:
        raise ValueError("reconciliation_capability_verification_time_invalid")

    expected_verifier_values = (
        expected_verifier_id,
        expected_verifier_policy_id,
        expected_verifier_policy_hash,
    )
    if any(value is not None for value in expected_verifier_values) and not all(
        isinstance(value, str) and value.strip() for value in expected_verifier_values
    ):
        raise ValueError("reconciliation_capability_expected_verifier_binding_incomplete")

    failures: list[str] = []

    if (
        evidence.endpoint_identity_binding_digest
        != current_endpoint_identity_binding_digest
    ):
        failures.append("reconciliation_capability_endpoint_identity_changed")

    if evidence.target_configuration_digest != current_target_configuration_digest:
        failures.append("reconciliation_capability_target_configuration_changed")

    assessed_at = _parse_aware_timestamp(
        evidence.assessed_at,
        "reconciliation_capability_assessed_at_invalid",
    )
    if assessed_at > verification_time:
        failures.append("reconciliation_capability_assessment_from_future")

    if evidence.valid_until is not None:
        valid_until = _parse_aware_timestamp(
            evidence.valid_until,
            "reconciliation_capability_valid_until_invalid",
        )
        if verification_time >= valid_until:
            failures.append("reconciliation_capability_evidence_expired")

    if require_authoritative and evidence.capability_class not in {
        ReconciliationCapabilityClass.AUTHORITATIVE_QUERY,
        ReconciliationCapabilityClass.AUTHORITATIVE_EVIDENCE,
    }:
        failures.append("reconciliation_capability_not_authoritative")

    if all(
        isinstance(value, str) and value.strip() for value in expected_verifier_values
    ):
        actual_verifier_values = (
            evidence.verifier_id,
            evidence.verifier_policy_id,
            evidence.verifier_policy_hash,
        )
        if actual_verifier_values != expected_verifier_values:
            failures.append("reconciliation_capability_verifier_binding_mismatch")

    if (
        expected_evidence_digest is not None
        and evidence.deterministic_digest() != expected_evidence_digest
    ):
        failures.append("reconciliation_capability_evidence_digest_mismatch")

    return failures

