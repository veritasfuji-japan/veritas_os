"""Tests for the provider-neutral external UTC clock evidence boundary."""

from __future__ import annotations

from dataclasses import replace
import hashlib
from typing import Any

import pytest

import veritas_os.governance.external_clock_evidence as clock_boundary
from veritas_os.governance.external_clock_evidence import (
    ApprovedExternalClockProvider,
    ExternalClockChallenge,
    ExternalClockEvidence,
    ExternalClockProviderVerificationResult,
    ExternalClockTrustPolicy,
    validate_verified_external_clock_evidence,
    verify_external_clock_artifact_to_evidence,
)

NONCE = "n" * 32
START = 100.0
FINISH = 100.1


class _Verifier:
    def __init__(self, result: ExternalClockProviderVerificationResult) -> None:
        self.result = result
        self.calls = 0

    def verify(
        self, artifact: dict[str, Any]
    ) -> ExternalClockProviderVerificationResult:
        self.calls += 1
        assert artifact == {"native": "clock-artifact"}
        return self.result


@pytest.fixture(autouse=True)
def _reset_runtime_seals() -> None:
    with clock_boundary._EXTERNAL_CLOCK_CHALLENGE_LOCK:
        clock_boundary._REGISTERED_EXTERNAL_CLOCK_CHALLENGES.clear()
    clock_boundary._VERIFIED_EXTERNAL_CLOCK_REGISTRY.clear()
    yield
    with clock_boundary._EXTERNAL_CLOCK_CHALLENGE_LOCK:
        clock_boundary._REGISTERED_EXTERNAL_CLOCK_CHALLENGES.clear()
    clock_boundary._VERIFIED_EXTERNAL_CLOCK_REGISTRY.clear()


def _register(
    *,
    challenge_id: str = "challenge-001",
    nonce: str = NONCE,
    started: float = START,
) -> ExternalClockChallenge:
    return clock_boundary.register_external_clock_challenge(
        challenge_id,
        nonce,
        monotonic_now=lambda: started,
    )


def _evidence(
    challenge: ExternalClockChallenge,
    **changes: Any,
) -> ExternalClockEvidence:
    base = ExternalClockEvidence(
        evidence_id="clock-evidence-001",
        provider_id="clock.example",
        artifact_id="clock-artifact-001",
        artifact_type="signed_utc_sample",
        artifact_version="v1",
        payload_hash="a" * 64,
        challenge_id=challenge.challenge_id,
        challenge_nonce_hash=challenge.challenge_nonce_hash,
        utc_time="2026-09-15T00:00:00Z",
        uncertainty_ms=5,
        source_clock_id="clock-source-001",
        provenance={"source": "provider-signed-artifact"},
        metadata={"purpose": "boundary-test"},
    )
    return replace(base, **changes)


def _result(
    challenge: ExternalClockChallenge,
    **changes: Any,
) -> ExternalClockProviderVerificationResult:
    base = ExternalClockProviderVerificationResult(
        verified=True,
        evidence=_evidence(challenge),
        verifier_id="clock-verifier-v1",
        verifier_trust_level="production",
        verifier_policy_id="clock-provider-policy-v1",
        verifier_policy_hash="b" * 64,
        key_id="clock-key-001",
        algorithm="Ed25519",
        semantic_consistent=True,
        reason="signature_and_semantics_verified",
    )
    return replace(base, **changes)


def _policy(**changes: Any) -> ExternalClockTrustPolicy:
    base = ExternalClockTrustPolicy(
        policy_id="external-clock-trust-v1",
        approved_providers=[
            ApprovedExternalClockProvider(
                provider_id="clock.example",
                verifier_id="clock-verifier-v1",
                verifier_trust_level="production",
                verifier_policy_id="clock-provider-policy-v1",
                verifier_policy_hash="b" * 64,
                require_signature_identity=True,
            )
        ],
        max_uncertainty_ms=25,
        max_monotonic_rtt_ms=250.0,
    )
    return replace(base, **changes)


def _verify(
    *,
    challenge: ExternalClockChallenge | None = None,
    result: ExternalClockProviderVerificationResult | None = None,
    policy: ExternalClockTrustPolicy | None = None,
    finished: float = FINISH,
):
    active_challenge = challenge or _register()
    verifier = _Verifier(result or _result(active_challenge))
    proof = verify_external_clock_artifact_to_evidence(
        {"native": "clock-artifact"},
        challenge=active_challenge,
        provider_verifier=verifier,
        trust_policy=policy or _policy(),
        monotonic_now=lambda: finished,
    )
    return proof, active_challenge, verifier


def test_success_seals_challenge_bound_non_authoritative_clock_evidence() -> None:
    proof, challenge, verifier = _verify()

    assert verifier.calls == 1
    assert proof.challenge_id == challenge.challenge_id
    assert proof.challenge_nonce_hash == challenge.challenge_nonce_hash
    assert proof.evidence.utc_time.endswith("Z")
    assert proof.monotonic_rtt_ms == pytest.approx(100.0)
    assert len(proof.evidence_hash) == 64
    assert len(proof.verification_proof_hash) == 64
    assert validate_verified_external_clock_evidence(
        proof, trust_policy=_policy()
    ) == []

    assert not hasattr(proof, "authority_evidence")
    assert not hasattr(proof, "human_approval")
    assert not hasattr(proof, "bind_authorization")
    assert not hasattr(proof, "execution_permission")
    assert not hasattr(proof, "runtime_clock")


def test_provider_verification_and_semantic_consistency_fail_closed() -> None:
    challenge = _register()
    with pytest.raises(
        ValueError, match="external_clock_provider_verification_failed"
    ):
        _verify(challenge=challenge, result=_result(challenge, verified=False))

    challenge = _register(challenge_id="challenge-002")
    with pytest.raises(ValueError, match="external_clock_semantic_inconsistent"):
        _verify(
            challenge=challenge,
            result=_result(challenge, semantic_consistent=False),
        )


def test_unapproved_provider_and_verifier_policy_binding_fail_closed() -> None:
    challenge = _register()
    with pytest.raises(
        ValueError, match="external_clock_provider_verifier_unapproved"
    ):
        _verify(challenge=challenge, policy=_policy(approved_providers=[]))

    challenge = _register(challenge_id="challenge-002")
    with pytest.raises(ValueError, match="external_clock_verifier_binding_mismatch"):
        _verify(
            challenge=challenge,
            result=_result(challenge, verifier_policy_hash="c" * 64),
        )


def test_required_signature_identity_metadata_fails_closed() -> None:
    challenge = _register()
    with pytest.raises(ValueError, match="external_clock_signature_identity_missing"):
        _verify(
            challenge=challenge,
            result=_result(challenge, key_id=None, algorithm=None),
        )


def test_malformed_payload_hash_fails_closed() -> None:
    challenge = _register()
    with pytest.raises(ValueError, match="external_clock_payload_hash_invalid"):
        _verify(
            challenge=challenge,
            result=_result(
                challenge,
                evidence=_evidence(challenge, payload_hash="not-a-sha256"),
            ),
        )


def test_missing_or_forged_challenge_is_not_runtime_trust() -> None:
    forged = ExternalClockChallenge(
        challenge_id="forged",
        challenge_nonce_hash=hashlib.sha256(NONCE.encode("utf-8")).hexdigest(),
        started_monotonic=START,
    )
    with pytest.raises(ValueError, match="external_clock_challenge_invalid"):
        _verify(challenge=forged, result=_result(forged))


def test_challenge_identifier_and_nonce_mismatch_fail_closed() -> None:
    challenge = _register()
    with pytest.raises(
        ValueError, match="external_clock_challenge_identifier_mismatch"
    ):
        _verify(
            challenge=challenge,
            result=_result(
                challenge,
                evidence=_evidence(challenge, challenge_id="different-challenge"),
            ),
        )

    challenge = _register(challenge_id="challenge-002")
    with pytest.raises(ValueError, match="external_clock_challenge_nonce_mismatch"):
        _verify(
            challenge=challenge,
            result=_result(
                challenge,
                evidence=_evidence(challenge, challenge_nonce_hash="f" * 64),
            ),
        )


def test_challenge_is_single_use_after_success() -> None:
    challenge = _register()
    result = _result(challenge)
    _verify(challenge=challenge, result=result)

    with pytest.raises(ValueError, match="external_clock_challenge_replay"):
        _verify(challenge=challenge, result=result)


def test_utc_time_must_be_timezone_aware_and_utc() -> None:
    challenge = _register()
    with pytest.raises(
        ValueError, match="external_clock_utc_time_timezone_required"
    ):
        _verify(
            challenge=challenge,
            result=_result(
                challenge,
                evidence=_evidence(challenge, utc_time="2026-09-15T00:00:00"),
            ),
        )

    challenge = _register(challenge_id="challenge-002")
    with pytest.raises(ValueError, match="external_clock_utc_time_not_utc"):
        _verify(
            challenge=challenge,
            result=_result(
                challenge,
                evidence=_evidence(
                    challenge,
                    utc_time="2026-09-15T09:00:00+09:00",
                ),
            ),
        )


def test_uncertainty_must_be_valid_and_within_independent_policy() -> None:
    challenge = _register()
    with pytest.raises(ValueError, match="external_clock_uncertainty_invalid"):
        _verify(
            challenge=challenge,
            result=_result(
                challenge,
                evidence=_evidence(challenge, uncertainty_ms=-1),
            ),
        )

    challenge = _register(challenge_id="challenge-002")
    with pytest.raises(ValueError, match="external_clock_uncertainty_excessive"):
        _verify(
            challenge=challenge,
            result=_result(
                challenge,
                evidence=_evidence(challenge, uncertainty_ms=26),
            ),
        )


def test_monotonic_rtt_must_be_non_negative_and_within_policy() -> None:
    challenge = _register()
    with pytest.raises(ValueError, match="external_clock_monotonic_rtt_negative"):
        _verify(challenge=challenge, finished=START - 0.001)

    challenge = _register(challenge_id="challenge-002")
    with pytest.raises(ValueError, match="external_clock_monotonic_rtt_excessive"):
        _verify(challenge=challenge, finished=START + 0.251)


def test_policy_change_and_forged_proof_are_detected_on_revalidation() -> None:
    proof, _, _ = _verify()

    changed_policy = _policy(max_uncertainty_ms=20)
    failures = validate_verified_external_clock_evidence(
        proof, trust_policy=changed_policy
    )
    assert "external_clock_trust_policy_hash_mismatch" in failures

    forged = replace(proof, verification_reason="caller-mutated")
    failures = validate_verified_external_clock_evidence(
        forged, trust_policy=_policy()
    )
    assert "external_clock_verification_proof_invalid" in failures


def test_challenge_registration_rejects_short_nonce_and_duplicate_identifier() -> None:
    with pytest.raises(ValueError, match="external_clock_challenge_nonce_too_short"):
        _register(nonce="short")

    _register()
    with pytest.raises(ValueError, match="external_clock_challenge_duplicate"):
        _register()
