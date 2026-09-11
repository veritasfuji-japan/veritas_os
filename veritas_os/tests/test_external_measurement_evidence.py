"""Tests for the provider-neutral external measurement evidence boundary."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from veritas_os.governance.external_measurement_evidence import (
    ApprovedExternalMeasurementProvider,
    ExternalMeasurementEvidence,
    ExternalMeasurementProviderVerificationResult,
    ExternalMeasurementTrustPolicy,
    validate_verified_external_measurement_evidence,
    verify_external_measurement_artifact_to_evidence,
)

NOW = datetime(2026, 9, 11, 0, 0, tzinfo=UTC)


class _Verifier:
    def __init__(self, result: ExternalMeasurementProviderVerificationResult) -> None:
        self.result = result
        self.calls = 0

    def verify(
        self, artifact: dict[str, Any]
    ) -> ExternalMeasurementProviderVerificationResult:
        self.calls += 1
        assert artifact == {"native": "provider-artifact"}
        return self.result


class _ReplayGuard:
    def __init__(self) -> None:
        self.seen: set[str] = set()
        self.calls = 0

    def consume_once(self, replay_key: str, *, observed_at: datetime) -> bool:
        self.calls += 1
        assert observed_at.tzinfo is not None
        if replay_key in self.seen:
            return False
        self.seen.add(replay_key)
        return True


def _evidence(**changes: Any) -> ExternalMeasurementEvidence:
    base = ExternalMeasurementEvidence(
        evidence_id="eme-001",
        provider_id="provider.example",
        artifact_id="artifact-001",
        artifact_type="measurement_observation",
        artifact_version="v1",
        payload_hash="a" * 64,
        observed_at=(NOW - timedelta(seconds=20)).isoformat(),
        issued_at=(NOW - timedelta(seconds=10)).isoformat(),
        expires_at=(NOW + timedelta(minutes=5)).isoformat(),
        replay_token="nonce-001",
        measured_scope={"request_id": "request-001", "domain": "runtime"},
        measurement_coverage=0.75,
        semantic_facts={"status": "observed"},
        provenance={"source": "signed-provider-artifact"},
        metadata={"purpose": "interop-test"},
    )
    return replace(base, **changes)


def _result(**changes: Any) -> ExternalMeasurementProviderVerificationResult:
    base = ExternalMeasurementProviderVerificationResult(
        verified=True,
        evidence=_evidence(),
        verifier_id="provider-verifier-v1",
        verifier_trust_level="production",
        verifier_policy_id="provider-policy-v1",
        verifier_policy_hash="b" * 64,
        key_id="key-001",
        algorithm="Ed25519",
        semantic_consistent=True,
        reason="signature_and_semantics_verified",
    )
    return replace(base, **changes)


def _policy(**changes: Any) -> ExternalMeasurementTrustPolicy:
    base = ExternalMeasurementTrustPolicy(
        policy_id="external-measurement-trust-v1",
        approved_providers=[
            ApprovedExternalMeasurementProvider(
                provider_id="provider.example",
                verifier_id="provider-verifier-v1",
                verifier_trust_level="production",
                verifier_policy_id="provider-policy-v1",
                verifier_policy_hash="b" * 64,
            )
        ],
        max_age_seconds=300,
        max_future_skew_seconds=5,
        require_expiry=True,
    )
    return replace(base, **changes)


def _verify(
    result: ExternalMeasurementProviderVerificationResult | None = None,
    *,
    policy: ExternalMeasurementTrustPolicy | None = None,
    replay: _ReplayGuard | None = None,
):
    verifier = _Verifier(result or _result())
    replay_guard = replay or _ReplayGuard()
    proof = verify_external_measurement_artifact_to_evidence(
        {"native": "provider-artifact"},
        provider_verifier=verifier,
        trust_policy=policy or _policy(),
        replay_guard=replay_guard,
        now=NOW,
    )
    return proof, verifier, replay_guard


def test_success_seals_provider_neutral_non_authoritative_evidence() -> None:
    proof, verifier, replay = _verify()

    assert verifier.calls == 1
    assert replay.calls == 1
    assert proof.evidence.provider_id == "provider.example"
    assert proof.evidence.measurement_coverage == 0.75
    assert proof.verifier_id == "provider-verifier-v1"
    assert proof.verification_source == "external_measurement_provider_verifier"
    assert len(proof.evidence_hash) == 64
    assert len(proof.verification_proof_hash) == 64
    assert len(proof.replay_key) == 64
    assert validate_verified_external_measurement_evidence(
        proof, trust_policy=_policy(), now=NOW
    ) == []

    # Measurement evidence is structurally separate from authority/approval/bind state.
    assert not hasattr(proof, "authority_evidence")
    assert not hasattr(proof, "human_approval")
    assert not hasattr(proof, "bind_authorization")
    assert not hasattr(proof, "governance_decision")


def test_unapproved_provider_or_verifier_fails_closed_before_replay_consumption() -> None:
    replay = _ReplayGuard()
    verifier = _Verifier(_result())
    policy = _policy(approved_providers=[])

    with pytest.raises(
        ValueError, match="external_measurement_provider_verifier_unapproved"
    ):
        verify_external_measurement_artifact_to_evidence(
            {"native": "provider-artifact"},
            provider_verifier=verifier,
            trust_policy=policy,
            replay_guard=replay,
            now=NOW,
        )

    assert verifier.calls == 1
    assert replay.calls == 0


def test_verifier_binding_must_match_independent_trust_policy() -> None:
    bad = _result(verifier_policy_hash="c" * 64)

    with pytest.raises(
        ValueError, match="external_measurement_verifier_binding_mismatch"
    ):
        _verify(bad)


def test_provider_verification_and_semantic_consistency_are_both_required() -> None:
    with pytest.raises(
        ValueError, match="external_measurement_provider_verification_failed"
    ):
        _verify(_result(verified=False))

    with pytest.raises(ValueError, match="external_measurement_semantic_inconsistent"):
        _verify(_result(semantic_consistent=False))


def test_stale_future_and_expired_measurements_fail_closed() -> None:
    stale = _result(
        evidence=_evidence(observed_at=(NOW - timedelta(minutes=6)).isoformat())
    )
    with pytest.raises(ValueError, match="external_measurement_stale"):
        _verify(stale)

    future = _result(
        evidence=_evidence(observed_at=(NOW + timedelta(seconds=6)).isoformat())
    )
    with pytest.raises(ValueError, match="external_measurement_timestamp_future"):
        _verify(future)

    expired = _result(
        evidence=_evidence(expires_at=(NOW - timedelta(seconds=1)).isoformat())
    )
    with pytest.raises(ValueError, match="external_measurement_expired"):
        _verify(expired)


def test_scope_payload_hash_and_coverage_are_validated() -> None:
    with pytest.raises(ValueError, match="external_measurement_scope_missing"):
        _verify(_result(evidence=_evidence(measured_scope={})))

    with pytest.raises(ValueError, match="external_measurement_payload_hash_invalid"):
        _verify(_result(evidence=_evidence(payload_hash="not-a-sha256")))

    with pytest.raises(ValueError, match="external_measurement_coverage_invalid"):
        _verify(_result(evidence=_evidence(measurement_coverage=1.01)))


def test_replay_guard_is_atomic_boundary_and_second_use_is_rejected() -> None:
    replay = _ReplayGuard()
    first, _, _ = _verify(replay=replay)
    assert first.evidence.artifact_id == "artifact-001"

    with pytest.raises(ValueError, match="external_measurement_replay_detected"):
        _verify(replay=replay)

    assert replay.calls == 2


def test_forged_or_mutated_verified_object_is_not_portable_trust() -> None:
    proof, _, _ = _verify()
    forged = replace(proof, verification_reason="caller_mutated")

    failures = validate_verified_external_measurement_evidence(
        forged, trust_policy=_policy(), now=NOW
    )

    assert "external_measurement_verification_proof_invalid" in failures


def test_revalidation_detects_policy_change_and_evidence_mutation() -> None:
    proof, _, _ = _verify()
    changed_policy = _policy(max_age_seconds=60)

    assert "external_measurement_trust_policy_hash_mismatch" in (
        validate_verified_external_measurement_evidence(
            proof, trust_policy=changed_policy, now=NOW
        )
    )

    mutated = replace(
        proof,
        evidence=replace(proof.evidence, semantic_facts={"status": "rewritten"}),
    )
    failures = validate_verified_external_measurement_evidence(
        mutated, trust_policy=_policy(), now=NOW
    )
    assert "external_measurement_verification_proof_invalid" in failures
    assert "external_measurement_evidence_hash_mismatch" in failures


def test_trust_policy_hash_is_order_independent_for_provider_allowlist() -> None:
    first = ApprovedExternalMeasurementProvider(
        provider_id="a.example",
        verifier_id="a-v1",
        verifier_trust_level="production",
        verifier_policy_id="a-policy",
        verifier_policy_hash="1" * 64,
    )
    second = ApprovedExternalMeasurementProvider(
        provider_id="b.example",
        verifier_id="b-v1",
        verifier_trust_level="production",
        verifier_policy_id="b-policy",
        verifier_policy_hash="2" * 64,
    )
    left = _policy(approved_providers=[first, second])
    right = _policy(approved_providers=[second, first])

    assert left.deterministic_hash() == right.deterministic_hash()
