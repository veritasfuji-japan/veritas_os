"""Verified reconciliation capability evidence trust-boundary tests."""

from datetime import datetime

import pytest

from veritas_os.governance import reconciliation_capability_evidence as module
from veritas_os.security.hash import sha256_of_canonical_json
from veritas_os.tests.test_reconciliation_capability_evidence import _query_payload

_VERIFIER_ID = "reconciliation-capability-verifier/v1"
_VERIFIER_POLICY_ID = "reconciliation-capability-policy/v1"
_VERIFIER_POLICY_HASH = "d" * 64
_TRUST_POLICY_ID = "reconciliation-capability-trust/v1"


class ControlledVerifier:
    """Synthetic deployment verifier; production code remains unchanged."""

    def __init__(
        self,
        *,
        verified: bool = True,
        semantic_consistent: bool = True,
        verifier_id: str = _VERIFIER_ID,
        verifier_policy_id: str = _VERIFIER_POLICY_ID,
        verifier_policy_hash: str = _VERIFIER_POLICY_HASH,
        evidence_digest_override: str | None = None,
    ) -> None:
        self.verified = verified
        self.semantic_consistent = semantic_consistent
        self.verifier_id = verifier_id
        self.verifier_policy_id = verifier_policy_id
        self.verifier_policy_hash = verifier_policy_hash
        self.evidence_digest_override = evidence_digest_override

    def verify(
        self,
        evidence: module.ReconciliationCapabilityEvidence,
    ) -> module.ReconciliationCapabilityVerificationResult:
        evidence_digest = (
            self.evidence_digest_override or evidence.deterministic_digest()
        )
        material = sha256_of_canonical_json(
            {
                "domain": "test.reconciliation-capability-verification/v1",
                "evidence_digest": evidence_digest,
                "verifier_id": self.verifier_id,
                "verifier_policy_id": self.verifier_policy_id,
                "verifier_policy_hash": self.verifier_policy_hash,
            }
        )
        return module.ReconciliationCapabilityVerificationResult(
            verified=self.verified,
            evidence_digest=evidence_digest,
            verifier_id=self.verifier_id,
            verifier_policy_id=self.verifier_policy_id,
            verifier_policy_hash=self.verifier_policy_hash,
            verification_material_digest=material,
            semantic_consistent=self.semantic_consistent,
            reason="controlled-test-verification",
        )


def _trust_policy(
    *,
    verifier_id: str = _VERIFIER_ID,
    verifier_policy_id: str = _VERIFIER_POLICY_ID,
    verifier_policy_hash: str = _VERIFIER_POLICY_HASH,
) -> module.ReconciliationCapabilityVerifierTrustPolicy:
    return module.ReconciliationCapabilityVerifierTrustPolicy(
        policy_id=_TRUST_POLICY_ID,
        approved_verifiers=(
            module.ApprovedReconciliationCapabilityVerifier(
                verifier_id=verifier_id,
                verifier_policy_id=verifier_policy_id,
                verifier_policy_hash=verifier_policy_hash,
            ),
        ),
    )


def _evidence() -> module.ReconciliationCapabilityEvidence:
    return module.ReconciliationCapabilityEvidence(**_query_payload())


def _verification_time() -> datetime:
    return datetime.fromisoformat("2026-09-20T00:00:00+00:00")


def test_controlled_verifier_creates_runtime_sealed_non_authorizing_proof() -> None:
    evidence = _evidence()
    trust_policy = _trust_policy()

    proof = module.verify_reconciliation_capability_evidence_to_proof(
        evidence,
        verifier=ControlledVerifier(),
        trust_policy=trust_policy,
        verified_at=_verification_time(),
    )

    assert proof.evidence == evidence
    assert proof.evidence_digest == evidence.deterministic_digest()
    assert proof.verifier_id == _VERIFIER_ID
    assert proof.verifier_policy_id == _VERIFIER_POLICY_ID
    assert proof.verifier_policy_hash == _VERIFIER_POLICY_HASH
    assert proof.trust_policy_id == _TRUST_POLICY_ID
    assert proof.trust_policy_hash == trust_policy.deterministic_hash()
    assert proof.execution_eligibility_decision_created is False
    assert proof.execution_permission_created is False
    assert proof.retry_permission_created is False
    assert proof.terminal_effect_claim_created is False

    assert (
        module.validate_verified_reconciliation_capability_evidence(
            proof,
            trust_policy=trust_policy,
            current_endpoint_identity_binding_digest=(
                evidence.endpoint_identity_binding_digest
            ),
            current_target_configuration_digest=(
                evidence.target_configuration_digest
            ),
            verification_time=_verification_time(),
            require_authoritative=True,
            expected_evidence_digest=evidence.deterministic_digest(),
        )
        == []
    )


def test_caller_constructed_lookalike_is_not_a_runtime_sealed_proof() -> None:
    evidence = _evidence()
    trust_policy = _trust_policy()
    real = module.verify_reconciliation_capability_evidence_to_proof(
        evidence,
        verifier=ControlledVerifier(),
        trust_policy=trust_policy,
        verified_at=_verification_time(),
    )
    forged = module.VerifiedReconciliationCapabilityEvidence(
        **real.model_dump(mode="json")
    )

    failures = module.validate_verified_reconciliation_capability_evidence(
        forged,
        trust_policy=trust_policy,
        current_endpoint_identity_binding_digest=(
            evidence.endpoint_identity_binding_digest
        ),
        current_target_configuration_digest=evidence.target_configuration_digest,
        verification_time=_verification_time(),
        require_authoritative=True,
        expected_evidence_digest=evidence.deterministic_digest(),
    )

    assert "reconciliation_capability_verification_proof_invalid" in failures


def test_substituted_evidence_invalidates_sealed_proof() -> None:
    evidence = _evidence()
    trust_policy = _trust_policy()
    proof = module.verify_reconciliation_capability_evidence_to_proof(
        evidence,
        verifier=ControlledVerifier(),
        trust_policy=trust_policy,
        verified_at=_verification_time(),
    )
    changed_payload = _query_payload()
    changed_payload["target_configuration_digest"] = "e" * 64
    changed = module.ReconciliationCapabilityEvidence(**changed_payload)
    substituted = proof.model_copy(
        update={
            "evidence": changed,
            "evidence_digest": changed.deterministic_digest(),
        }
    )

    failures = module.validate_verified_reconciliation_capability_evidence(
        substituted,
        trust_policy=trust_policy,
        current_endpoint_identity_binding_digest=(
            changed.endpoint_identity_binding_digest
        ),
        current_target_configuration_digest=changed.target_configuration_digest,
        verification_time=_verification_time(),
        require_authoritative=True,
        expected_evidence_digest=changed.deterministic_digest(),
    )

    assert "reconciliation_capability_verification_proof_invalid" in failures


@pytest.mark.parametrize(
    ("verifier", "reason"),
    [
        (
            ControlledVerifier(verified=False),
            "reconciliation_capability_verification_failed",
        ),
        (
            ControlledVerifier(semantic_consistent=False),
            "reconciliation_capability_verification_inconsistent",
        ),
        (
            ControlledVerifier(evidence_digest_override="0" * 64),
            "reconciliation_capability_verified_evidence_mismatch",
        ),
    ],
)
def test_verifier_failure_modes_fail_closed(verifier, reason) -> None:
    with pytest.raises(ValueError, match=reason):
        module.verify_reconciliation_capability_evidence_to_proof(
            _evidence(),
            verifier=verifier,
            trust_policy=_trust_policy(),
            verified_at=_verification_time(),
        )


def test_unapproved_verifier_and_policy_binding_mismatch_fail_closed() -> None:
    with pytest.raises(
        ValueError,
        match="reconciliation_capability_verifier_unapproved",
    ):
        module.verify_reconciliation_capability_evidence_to_proof(
            _evidence(),
            verifier=ControlledVerifier(verifier_id="other-verifier"),
            trust_policy=_trust_policy(),
            verified_at=_verification_time(),
        )

    changed_policy = _trust_policy(verifier_policy_hash="e" * 64)
    with pytest.raises(
        ValueError,
        match="reconciliation_capability_verifier_binding_mismatch",
    ):
        module.verify_reconciliation_capability_evidence_to_proof(
            _evidence(),
            verifier=ControlledVerifier(),
            trust_policy=changed_policy,
            verified_at=_verification_time(),
        )


def test_caller_declared_verifier_fields_do_not_replace_actual_verifier() -> None:
    with pytest.raises(
        ValueError,
        match="reconciliation_capability_verifier_declaration_mismatch",
    ):
        module.verify_reconciliation_capability_evidence_to_proof(
            _evidence(),
            verifier=ControlledVerifier(
                verifier_id="different-verifier",
                verifier_policy_id="different-policy",
                verifier_policy_hash="e" * 64,
            ),
            trust_policy=_trust_policy(
                verifier_id="different-verifier",
                verifier_policy_id="different-policy",
                verifier_policy_hash="e" * 64,
            ),
            verified_at=_verification_time(),
        )


def test_verified_proof_fails_under_different_trust_policy() -> None:
    evidence = _evidence()
    proof = module.verify_reconciliation_capability_evidence_to_proof(
        evidence,
        verifier=ControlledVerifier(),
        trust_policy=_trust_policy(),
        verified_at=_verification_time(),
    )
    other_policy = module.ReconciliationCapabilityVerifierTrustPolicy(
        policy_id="different-trust-policy",
        approved_verifiers=_trust_policy().approved_verifiers,
    )

    failures = module.validate_verified_reconciliation_capability_evidence(
        proof,
        trust_policy=other_policy,
        current_endpoint_identity_binding_digest=(
            evidence.endpoint_identity_binding_digest
        ),
        current_target_configuration_digest=evidence.target_configuration_digest,
        verification_time=_verification_time(),
        require_authoritative=True,
        expected_evidence_digest=evidence.deterministic_digest(),
    )

    assert "reconciliation_capability_trust_policy_id_mismatch" in failures
    assert "reconciliation_capability_trust_policy_hash_mismatch" in failures
