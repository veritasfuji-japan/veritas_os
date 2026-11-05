"""Synthetic fail-closed tests for explicit NeoMundi RGC v0.1 COMPLETE profile.

No production observation, signing key, or NeoMundi public key is committed.
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from veritas_os.governance.external_measurement_evidence import (
    ApprovedExternalMeasurementProvider,
    ExternalMeasurementTrustPolicy,
    verify_external_measurement_artifact_to_evidence,
)
from veritas_os.governance.neomundi_rgc_v01_complete import (
    NEOMUNDI_RGC_V01_COMPLETE_VERIFIER_ID,
    NeoMundiRgcV01CompleteVerifier,
)
from veritas_os.governance.neomundi_rgc_v02 import NeoMundiRgcV02Verifier

NOW = datetime(2026, 10, 20, 10, 0, tzinfo=UTC)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _material() -> tuple[Ed25519PrivateKey, dict[str, Any]]:
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return private, {
        "keys": [
            {
                "kty": "OKP",
                "crv": "Ed25519",
                "kid": "synthetic-only-key",
                "alg": "EdDSA",
                "x": _b64(public),
            }
        ]
    }


def _artifact() -> dict[str, Any]:
    return {
        "identity": {
            "schema_version": "0.1.0",
            "request_id": "synthetic-legacy-request",
            "trace_id": "00-" + ("a" * 32) + "-" + ("b" * 16) + "-01",
            "timestamp": (NOW - timedelta(seconds=30)).isoformat(),
            "system_id": "synthetic-runtime",
            "model": "local",
            "mode": "OBS",
        },
        "provenance": {
            "measurement_version": "3.3.0",
            "normalizer_version": "1.0.0",
            "checks_emitted": 3,
            "source_batch_id": None,
            "canonicalization_method": "sorted-json-utf8",
        },
        "observation": {
            "runtime_scope": "single_request",
            "observation_window": None,
            "measurement_status": "complete",
            "measurement_coverage": 1.0,
            "observed_signals": {
                "stability_score": 0.9,
                "coherence_score": 0.8,
                "factual_hallucination_score": 0.0,
                "semantic_instability_score": 0.0,
                "semantic_risk": 0.0,
                "signal_status": {
                    name: "measured"
                    for name in (
                        "stability_score",
                        "coherence_score",
                        "factual_hallucination_score",
                        "semantic_instability_score",
                        "semantic_risk",
                    )
                },
                "observation_class": "within_bounds",
                "observation_class_scope": "measured_domain",
                "confidence": 1.0,
            },
            "temporal_boundary": {
                "record_scope": "single_record",
                "inference_requires": "Any property listed in `does_not_establish` requires a series of records correlated over time; it can never be inferred from this record alone.",
                "establishes": [],
                "does_not_establish": [
                    "frequency",
                    "persistence",
                    "recurrence",
                    "drift",
                ],
            },
            "limitations": ["One observation; not a factuality guarantee."],
            "epistemic_principle": "Absence of evidence is only meaningful over the measured domain.",
            "measurement_boundary": "This contract measures a single observed runtime signal. It does not evaluate ground truth, does not certify third-party data, and carries no execution authority. Every statement it makes is bounded by the measured domain declared in observed_signals.signal_status: absence of evidence is only meaningful over that domain, and this record establishes no temporal property on its own.",
        },
        "governance": {
            "governance_boundary": {
                "authorization_status": "not_applicable",
                "execution_permission_changed": False,
            },
            "advisory": {
                "review_recommendation": "not_indicated",
                "review_trigger": [],
                "recommended_review_type": [],
                "interpretation_policy": {
                    "policy_id": "synthetic-advisory",
                    "policy_version": "0.1.0",
                },
            },
        },
        "integrity": {
            "payload_hash": "",
            "hash_algorithm": "sha256",
            "canonicalization": "sorted-json-utf8",
            "signature": "",
            "signer_identity": "synthetic-signer",
            "key_id": "synthetic-only-key",
            "confidentiality_class": "controlled",
            "retention_reference": None,
        },
    }


def _sign(
    artifact: dict[str, Any],
    private: Ed25519PrivateKey,
    *,
    claim_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sections = {
        k: artifact[k] for k in ("identity", "provenance", "observation", "governance")
    }
    canonical = json.dumps(
        sections, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    artifact["integrity"]["payload_hash"] = hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()
    claims = {
        "payload_hash": artifact["integrity"]["payload_hash"],
        "hash_algorithm": "sha256",
        "schema_version": artifact["identity"]["schema_version"],
        "request_id": artifact["identity"]["request_id"],
        "timestamp": artifact["identity"]["timestamp"],
    }
    claims.update(claim_overrides or {})
    header = _b64(
        json.dumps(
            {"alg": "EdDSA", "kid": "synthetic-only-key"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    payload = _b64(
        json.dumps(claims, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    digest = _b64(private.sign(f"{header}.{payload}".encode("ascii")))
    artifact["integrity"]["signature"] = f"{header}.{payload}.{digest}"
    return artifact


def _verifier(jwks: dict[str, Any]) -> NeoMundiRgcV01CompleteVerifier:
    return NeoMundiRgcV01CompleteVerifier(
        trusted_jwks=jwks,
        verifier_policy_id="synthetic-legacy-complete-policy",
        accepted_measurement_versions=("3.3.0",),
        verifier_trust_level="poc",
    )


class _Replay:
    def __init__(self) -> None:
        self.seen: set[str] = set()

    def consume_once(self, replay_key: str, *, observed_at: datetime) -> bool:
        assert observed_at.tzinfo is not None
        if replay_key in self.seen:
            return False
        self.seen.add(replay_key)
        return True


def _policy(
    verifier: NeoMundiRgcV01CompleteVerifier,
) -> ExternalMeasurementTrustPolicy:
    return ExternalMeasurementTrustPolicy(
        policy_id="synthetic-legacy-evidence-policy",
        approved_providers=[
            ApprovedExternalMeasurementProvider(
                provider_id="neomundi",
                verifier_id=NEOMUNDI_RGC_V01_COMPLETE_VERIFIER_ID,
                verifier_trust_level=verifier.verifier_trust_level,
                verifier_policy_id=verifier.verifier_policy_id,
                verifier_policy_hash=verifier.verifier_policy_hash,
            )
        ],
        max_age_seconds=60,
        max_future_skew_seconds=5,
        require_expiry=False,
    )


def test_explicit_signed_legacy_complete_is_measurement_only() -> None:
    private, jwks = _material()
    artifact = _sign(_artifact(), private)
    verifier = _verifier(jwks)
    result = verifier.verify(artifact)

    assert result.verified
    assert result.semantic_consistent
    assert result.reason == "neomundi_rgc_v01_complete_verified"
    assert result.evidence is not None
    assert result.evidence.artifact_version == "0.1.0"
    assert result.evidence.provenance["measurement_version"] == "3.3.0"
    assert result.evidence.metadata["authority_imported"] is False
    assert result.evidence.metadata["execution_permission_imported"] is False
    assert result.evidence.metadata["local_execution_established"] is False
    assert result.evidence.metadata["factuality_certified"] is False

    existing = NeoMundiRgcV02Verifier(
        trusted_jwks=jwks,
        verifier_policy_id="synthetic-v02-policy",
    )
    assert existing.verify(artifact).reason == "neomundi_rgc_version_unsupported"


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (
            lambda a: a["identity"].__setitem__("schema_version", "0.2.0"),
            "neomundi_v01_schema_version_unsupported",
        ),
        (
            lambda a: a["provenance"].__setitem__("measurement_version", "3.3.1"),
            "neomundi_v01_measurement_version_unapproved",
        ),
        (
            lambda a: a["observation"].__setitem__("measurement_status", "partial"),
            "neomundi_v01_partial_or_unknown_forbidden",
        ),
        (
            lambda a: a["observation"].__setitem__("measurement_coverage", 0.5),
            "neomundi_v01_complete_coverage_invalid",
        ),
        (
            lambda a: a["observation"]["observed_signals"]["signal_status"].__setitem__(
                "semantic_risk", "not_measured"
            ),
            "neomundi_v01_unmeasured_forbidden",
        ),
        (
            lambda a: a["observation"]["observed_signals"]["signal_status"].pop(
                "semantic_risk"
            ),
            "neomundi_v01_signal_status_incomplete",
        ),
        (
            lambda a: a["observation"]["observed_signals"].__setitem__(
                "coherence_score", None
            ),
            "neomundi_v01_measured_signal_invalid",
        ),
        (
            lambda a: a["observation"]["observed_signals"].__setitem__(
                "coherence_score", 10**400
            ),
            "neomundi_v01_measured_signal_invalid",
        ),
        (
            lambda a: a["observation"]["observed_signals"].__setitem__(
                "observation_class_scope", "global"
            ),
            "neomundi_v01_measurement_domain_missing",
        ),
        (
            lambda a: a["observation"]["temporal_boundary"].__setitem__(
                "establishes", ["drift"]
            ),
            "neomundi_v01_temporal_overclaim",
        ),
        (
            lambda a: a["governance"]["governance_boundary"].__setitem__(
                "execution_permission_changed", True
            ),
            "neomundi_v01_authority_boundary_invalid",
        ),
        (
            lambda a: a["governance"]["governance_boundary"].pop(
                "execution_permission_changed"
            ),
            "neomundi_v01_authority_boundary_invalid",
        ),
        (
            lambda a: a["integrity"].__setitem__("canonicalization", "JCS"),
            "neomundi_v01_hash_profile_invalid",
        ),
    ],
)
def test_legacy_profile_fails_closed_even_if_resigned(
    mutation: Any, reason: str
) -> None:
    private, jwks = _material()
    artifact = _artifact()
    mutation(artifact)
    _sign(artifact, private)
    assert _verifier(jwks).verify(artifact).reason == reason


def test_mutating_signed_observation_fails_payload_hash() -> None:
    private, jwks = _material()
    artifact = _sign(_artifact(), private)
    artifact["observation"]["observed_signals"]["coherence_score"] = 0.2
    assert (
        _verifier(jwks).verify(artifact).reason == "neomundi_v01_payload_hash_mismatch"
    )


def test_signed_claim_version_must_match_document() -> None:
    private, jwks = _material()
    artifact = _sign(_artifact(), private, claim_overrides={"schema_version": "0.2.0"})
    assert (
        _verifier(jwks).verify(artifact).reason
        == "neomundi_rgc_signed_claim_schema_version_mismatch"
    )


def test_policy_version_pin_changes_verifier_identity() -> None:
    _, jwks = _material()
    original = _verifier(jwks)
    other = NeoMundiRgcV01CompleteVerifier(
        trusted_jwks=jwks,
        verifier_policy_id=original.verifier_policy_id,
        accepted_measurement_versions=("3.3.1",),
        verifier_trust_level=original.verifier_trust_level,
    )
    assert original.verifier_policy_hash != other.verifier_policy_hash
    with pytest.raises(ValueError, match="neomundi_v01_measurement_allowlist_invalid"):
        NeoMundiRgcV01CompleteVerifier(
            trusted_jwks=jwks,
            verifier_policy_id="synthetic",
            accepted_measurement_versions=(),
        )


def test_generic_boundary_accepts_once_then_rejects_replay() -> None:
    private, jwks = _material()
    artifact = _sign(_artifact(), private)
    verifier = _verifier(jwks)
    replay = _Replay()
    policy = _policy(verifier)
    proof = verify_external_measurement_artifact_to_evidence(
        artifact,
        provider_verifier=verifier,
        trust_policy=policy,
        replay_guard=replay,
        now=NOW,
    )
    assert proof.evidence.artifact_version == "0.1.0"
    assert proof.evidence.metadata["authority_imported"] is False
    with pytest.raises(ValueError, match="external_measurement_replay_detected"):
        verify_external_measurement_artifact_to_evidence(
            artifact,
            provider_verifier=verifier,
            trust_policy=policy,
            replay_guard=replay,
            now=NOW,
        )


def test_generic_boundary_rejects_old_observation_and_wrong_policy() -> None:
    private, jwks = _material()
    artifact = _sign(_artifact(), private)
    verifier = _verifier(jwks)
    policy = _policy(verifier)
    with pytest.raises(ValueError, match="external_measurement_stale"):
        verify_external_measurement_artifact_to_evidence(
            artifact,
            provider_verifier=verifier,
            trust_policy=policy,
            replay_guard=_Replay(),
            now=NOW + timedelta(days=1),
        )

    other = NeoMundiRgcV01CompleteVerifier(
        trusted_jwks=jwks,
        verifier_policy_id="synthetic-legacy-complete-policy",
        accepted_measurement_versions=("3.3.1",),
        verifier_trust_level="poc",
    )
    with pytest.raises(
        ValueError, match="external_measurement_verifier_binding_mismatch"
    ):
        verify_external_measurement_artifact_to_evidence(
            artifact,
            provider_verifier=verifier,
            trust_policy=_policy(other),
            replay_guard=_Replay(),
            now=NOW,
        )


def test_s1_rejects_flagged_without_review() -> None:
    private, jwks = _material()
    artifact = _artifact()

    artifact["observation"]["observed_signals"]["observation_class"] = "flagged"

    # Re-sign to isolate S1 semantics from signature validity.
    _sign(artifact, private)

    result = _verifier(jwks).verify(artifact)

    assert not result.verified
    assert not result.semantic_consistent
    assert result.evidence is None
    assert result.reason == "neomundi_v01_s1_contract_violation"


@pytest.mark.parametrize(
    ("content", "missing", "expected"),
    [
        (
            b'{"type":"object"}',
            False,
            "neomundi_v01_s1_schema_hash_mismatch",
        ),
        (
            None,
            True,
            "neomundi_v01_s1_schema_unavailable",
        ),
    ],
)
def test_s1_schema_resource_failure_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    content: bytes | None,
    missing: bool,
    expected: str,
) -> None:
    from veritas_os.governance import neomundi_rgc_v01_s1_schema as s1

    private, jwks = _material()
    artifact = _sign(_artifact(), private)
    verifier = _verifier(jwks)

    assert verifier.verify(artifact).verified

    class FakeResource:
        def joinpath(self, name: str) -> "FakeResource":
            return self

        def read_bytes(self) -> bytes:
            if missing:
                raise FileNotFoundError("simulated missing schema")
            assert content is not None
            return content

    monkeypatch.setattr(
        s1,
        "files",
        lambda package: FakeResource(),
    )

    result = verifier.verify(artifact)

    assert not result.verified
    assert not result.semantic_consistent
    assert result.evidence is None
    assert result.reason == expected


def test_s1_rejection_does_not_consume_replay() -> None:
    private, jwks = _material()
    artifact = _artifact()

    artifact["observation"]["observed_signals"]["observation_class"] = "flagged"

    _sign(artifact, private)

    verifier = _verifier(jwks)
    policy = _policy(verifier)

    class TrackingReplay(_Replay):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        def consume_once(
            self,
            replay_key: str,
            *,
            observed_at: datetime,
        ) -> bool:
            self.calls += 1
            return super().consume_once(
                replay_key,
                observed_at=observed_at,
            )

    replay = TrackingReplay()

    result = verifier.verify(artifact)
    assert not result.verified
    assert result.reason == "neomundi_v01_s1_contract_violation"

    with pytest.raises(
        ValueError,
        match="^external_measurement_provider_verification_failed$",
    ):
        verify_external_measurement_artifact_to_evidence(
            artifact,
            provider_verifier=verifier,
            trust_policy=policy,
            replay_guard=replay,
            now=NOW,
        )

    assert replay.calls == 0
    assert replay.seen == set()
