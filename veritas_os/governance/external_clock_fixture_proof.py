"""Deterministic proof fixture for the external UTC clock evidence boundary.

This module is synthetic and side-effect-free. It exercises the standalone
external-clock trust boundary with fixed inputs so CI can produce reviewer
artifacts that are reproducible and later bound to the exact checked-out source
SHA. It does not contact a live clock provider and does not replace any runtime
clock callback.
"""

from __future__ import annotations

from dataclasses import asdict, replace
import json
from pathlib import Path
from typing import Any

from veritas_os.governance.external_clock_evidence import (
    ApprovedExternalClockProvider,
    ExternalClockChallenge,
    ExternalClockEvidence,
    ExternalClockProviderVerificationResult,
    ExternalClockTrustPolicy,
    VerifiedExternalClockEvidence,
    register_external_clock_challenge,
    validate_verified_external_clock_evidence,
    verify_external_clock_artifact_to_evidence,
)
from veritas_os.security.hash import sha256_of_canonical_json

PROOF_ID = "veritas-external-clock-fixture-proof-v1"
SCHEMA_VERSION = "veritas-external-clock-fixture-proof/v1"
FIXTURE_ID = "external_utc_clock_challenge_bound_fixture_v1"
FIXTURE_CHALLENGE_ID = "external-clock-fixture-challenge-v1"
FIXTURE_NONCE = "external-clock-fixture-nonce-000000000000000000000001"
FIXTURE_UTC_TIME = "2026-09-15T00:00:00+00:00"


class ExternalClockFixtureProofError(RuntimeError):
    """Raised when the deterministic fixture contract is violated."""


class _FixtureMonotonic:
    def __init__(self) -> None:
        self._values = iter((1000.0, 1000.125))

    def __call__(self) -> float:
        try:
            return next(self._values)
        except StopIteration as exc:
            raise ExternalClockFixtureProofError(
                "fixture monotonic clock was called more than twice"
            ) from exc


class _FixtureVerifier:
    def __init__(self, challenge: ExternalClockChallenge) -> None:
        self._challenge = challenge

    def verify(
        self, artifact: dict[str, Any]
    ) -> ExternalClockProviderVerificationResult:
        if artifact.get("challenge_id") != self._challenge.challenge_id:
            return ExternalClockProviderVerificationResult(
                verified=False,
                reason="fixture_challenge_id_mismatch",
            )
        if artifact.get("challenge_nonce_hash") != self._challenge.challenge_nonce_hash:
            return ExternalClockProviderVerificationResult(
                verified=False,
                reason="fixture_challenge_nonce_mismatch",
            )

        evidence = ExternalClockEvidence(
            evidence_id="external-clock-evidence-fixture-001",
            provider_id="clock-provider.fixture",
            artifact_id="clock-artifact-fixture-001",
            artifact_type="signed_utc_observation",
            artifact_version="v1",
            payload_hash=sha256_of_canonical_json(artifact),
            challenge_id=self._challenge.challenge_id,
            challenge_nonce_hash=self._challenge.challenge_nonce_hash,
            utc_time=FIXTURE_UTC_TIME,
            uncertainty_ms=10,
            source_clock_id="fixture-clock-source-001",
            provenance={
                "fixture": True,
                "provider_artifact_mode": "synthetic",
            },
            metadata={
                "purpose": "source-bound-reviewer-proof",
                "execution_authority": False,
            },
        )
        return ExternalClockProviderVerificationResult(
            verified=True,
            evidence=evidence,
            verifier_id="fixture-clock-verifier-v1",
            verifier_trust_level="fixture-only",
            verifier_policy_id="fixture-clock-verifier-policy-v1",
            verifier_policy_hash="b" * 64,
            key_id="fixture-key-001",
            algorithm="Ed25519-fixture",
            semantic_consistent=True,
            reason="synthetic_fixture_verified",
        )


def fixture_trust_policy() -> ExternalClockTrustPolicy:
    """Return the deterministic independent trust policy used by the fixture."""
    return ExternalClockTrustPolicy(
        policy_id="external-clock-fixture-trust-policy-v1",
        approved_providers=[
            ApprovedExternalClockProvider(
                provider_id="clock-provider.fixture",
                verifier_id="fixture-clock-verifier-v1",
                verifier_trust_level="fixture-only",
                verifier_policy_id="fixture-clock-verifier-policy-v1",
                verifier_policy_hash="b" * 64,
                require_signature_identity=True,
            )
        ],
        max_uncertainty_ms=50,
        max_monotonic_rtt_ms=250.0,
    )


def _serialized_proof(proof: VerifiedExternalClockEvidence) -> dict[str, Any]:
    payload = asdict(proof)
    payload["runtime_trust_portable"] = False
    payload["execution_authority"] = False
    return payload


def build_external_clock_fixture_proof(
    *,
    challenge_id: str = FIXTURE_CHALLENGE_ID,
) -> dict[str, Any]:
    """Build one deterministic, side-effect-free external-clock fixture proof."""
    monotonic = _FixtureMonotonic()
    challenge = register_external_clock_challenge(
        challenge_id,
        FIXTURE_NONCE,
        monotonic_now=monotonic,
    )
    artifact = {
        "artifact_type": "synthetic_clock_provider_artifact",
        "artifact_version": "v1",
        "challenge_id": challenge.challenge_id,
        "challenge_nonce_hash": challenge.challenge_nonce_hash,
        "asserted_utc_time": FIXTURE_UTC_TIME,
        "asserted_uncertainty_ms": 10,
        "source_clock_id": "fixture-clock-source-001",
    }
    policy = fixture_trust_policy()
    proof = verify_external_clock_artifact_to_evidence(
        artifact,
        challenge=challenge,
        provider_verifier=_FixtureVerifier(challenge),
        trust_policy=policy,
        monotonic_now=monotonic,
    )
    validation_failures = validate_verified_external_clock_evidence(
        proof,
        trust_policy=policy,
    )
    if validation_failures:
        raise ExternalClockFixtureProofError(
            f"fixture proof failed validation: {validation_failures!r}"
        )
    if proof.monotonic_rtt_ms != 125.0:
        raise ExternalClockFixtureProofError(
            f"unexpected fixture RTT: {proof.monotonic_rtt_ms!r}"
        )

    forged = replace(proof, verification_reason="caller_mutated")
    forged_failures = validate_verified_external_clock_evidence(
        forged,
        trust_policy=policy,
    )
    tamper_detected = "external_clock_verification_proof_invalid" in forged_failures
    if not tamper_detected:
        raise ExternalClockFixtureProofError("fixture tamper check did not fail closed")

    proof_payload = _serialized_proof(proof)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "proof_id": PROOF_ID,
        "fixture_id": FIXTURE_ID,
        "proof_mode": "synthetic_deterministic_side_effect_free",
        "challenge_id": proof.challenge_id,
        "challenge_nonce_hash": proof.challenge_nonce_hash,
        "utc_time": proof.evidence.utc_time,
        "uncertainty_ms": proof.evidence.uncertainty_ms,
        "monotonic_rtt_ms": proof.monotonic_rtt_ms,
        "trust_policy_id": proof.trust_policy_id,
        "trust_policy_hash": proof.trust_policy_hash,
        "evidence_hash": proof.evidence_hash,
        "verification_proof_hash": proof.verification_proof_hash,
        "proof_payload_hash": sha256_of_canonical_json(proof_payload),
        "claim_boundary": {
            "synthetic": True,
            "deterministic": True,
            "side_effect_free": True,
            "live_clock_provider": False,
            "runtime_clock_replacement": False,
            "execution_authority": False,
            "production_external_utc_clock_trust": False,
        },
    }
    negative_report = {
        "passed": tamper_detected,
        "case": "caller_mutated_runtime_seal",
        "expected_failure": "external_clock_verification_proof_invalid",
        "observed_failures": forged_failures,
    }
    summary = {
        "proof_id": PROOF_ID,
        "fixture_id": FIXTURE_ID,
        "valid_proof": True,
        "validation_failures": validation_failures,
        "tamper_checks_passed": tamper_detected,
        "live_external_effects": False,
        "live_clock_provider": False,
        "runtime_clock_replacement": False,
        "execution_authority": False,
        "production_claim": False,
    }
    return {
        "manifest": manifest,
        "proof": proof_payload,
        "negative_test_report": negative_report,
        "summary": summary,
    }


def write_external_clock_fixture_artifacts(output_dir: Path) -> dict[str, Any]:
    """Write deterministic reviewer-facing fixture artifacts as canonical JSON files."""
    bundle = build_external_clock_fixture_proof()
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in bundle.items():
        path = output_dir / f"{name}.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    return bundle
