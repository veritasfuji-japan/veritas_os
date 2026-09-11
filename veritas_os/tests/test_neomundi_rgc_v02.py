"""Tests for the NeoMundi RGC v0.2 external measurement adapter."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from veritas_os.governance.external_measurement_evidence import (
    ApprovedExternalMeasurementProvider,
    ExternalMeasurementTrustPolicy,
    verify_external_measurement_artifact_to_evidence,
)
from veritas_os.governance.neomundi_rgc_v02 import (
    NEOMUNDI_PROVIDER_ID,
    NEOMUNDI_RGC_V02_VERIFIER_ID,
    NeoMundiRgcV02Verifier,
)

NOW = datetime(2026, 9, 11, 2, 5, tzinfo=UTC)


class _ReplayGuard:
    def __init__(self) -> None:
        self.seen: set[str] = set()

    def consume_once(self, replay_key: str, *, observed_at: datetime) -> bool:
        assert observed_at.tzinfo is not None
        if replay_key in self.seen:
            return False
        self.seen.add(replay_key)
        return True


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _payload_hash(artifact: dict[str, Any]) -> str:
    payload = {
        "identity": artifact["identity"],
        "provenance": artifact["provenance"],
        "observation": artifact["observation"],
        "governance": artifact["governance"],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@pytest.fixture
def signing_material() -> tuple[Ed25519PrivateKey, dict[str, Any]]:
    private_key = Ed25519PrivateKey.generate()
    raw_public = private_key.public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw
    )
    jwks = {
        "keys": [
            {
                "kty": "OKP",
                "crv": "Ed25519",
                "kid": "neomundi-test-key",
                "alg": "EdDSA",
                "x": _b64url(raw_public),
            }
        ]
    }
    return private_key, jwks


def _artifact() -> dict[str, Any]:
    return {
        "identity": {
            "schema_version": "0.2.0",
            "request_id": "req-neomundi-001",
            "trace_id": "00-" + ("a" * 32) + "-" + ("b" * 16) + "-01",
            "timestamp": "2026-09-11T02:04:30+00:00",
            "system_id": "neomundi-poc",
            "model": "local",
            "mode": "poc",
        },
        "provenance": {
            "measurement_version": "measurement-0.2",
            "normalizer_version": "normalizer-0.2",
            "checks_emitted": 4,
            "source_batch_id": None,
            "canonicalization_method": "sorted-json-utf8",
        },
        "observation": {
            "runtime_scope": "single_request",
            "observation_window": None,
            "measurement_status": "complete",
            "measurement_coverage": 1.0,
            "observed_signals": {
                "stability_score": 0.91,
                "coherence_score": 0.88,
                "factual_hallucination_score": None,
                "semantic_instability_score": 0.12,
                "semantic_risk": 0.20,
                "signal_status": {
                    "stability_score": "measured",
                    "coherence_score": "measured",
                    "factual_hallucination_score": "not_measured",
                    "semantic_instability_score": "measured",
                    "semantic_risk": "measured",
                },
                "observation_class": "within_bounds",
                "confidence": 0.93,
            },
            "limitations": ["single request observation only"],
            "measurement_boundary": "declared runtime output signals",
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
                    "policy_id": "neomundi-reference",
                    "policy_version": "0.2",
                },
            },
        },
        "integrity": {
            "payload_hash": "",
            "hash_algorithm": "sha256",
            "canonicalization": "sorted-json-utf8",
            "signature": "",
            "signer_identity": "neomundi-test-signer",
            "key_id": "neomundi-test-key",
            "confidentiality_class": "controlled",
            "retention_reference": None,
        },
    }


def _sign(
    artifact: dict[str, Any],
    private_key: Ed25519PrivateKey,
    *,
    alg: str = "EdDSA",
    header_kid: str | None = "neomundi-test-key",
    claims_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    artifact["integrity"]["payload_hash"] = _payload_hash(artifact)
    claims = {
        "payload_hash": artifact["integrity"]["payload_hash"],
        "hash_algorithm": artifact["integrity"]["hash_algorithm"],
        "schema_version": artifact["identity"]["schema_version"],
        "request_id": artifact["identity"]["request_id"],
        "timestamp": artifact["identity"]["timestamp"],
    }
    claims.update(claims_override or {})
    header: dict[str, Any] = {"alg": alg, "typ": "JWT"}
    if header_kid is not None:
        header["kid"] = header_kid
    protected = _b64url(
        json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    payload = _b64url(
        json.dumps(claims, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    signature = _b64url(
        private_key.sign(f"{protected}.{payload}".encode("ascii"))
    )
    artifact["integrity"]["signature"] = f"{protected}.{payload}.{signature}"
    return artifact


def _verifier(jwks: dict[str, Any]) -> NeoMundiRgcV02Verifier:
    return NeoMundiRgcV02Verifier(
        trusted_jwks=jwks,
        verifier_policy_id="neomundi-rgc-poc-v02",
        verifier_trust_level="poc",
    )


def _valid(
    signing_material: tuple[Ed25519PrivateKey, dict[str, Any]]
) -> tuple[dict[str, Any], NeoMundiRgcV02Verifier]:
    private_key, jwks = signing_material
    artifact = _sign(_artifact(), private_key)
    return artifact, _verifier(jwks)


def test_valid_signed_rgc_v02_maps_to_measurement_only_evidence(
    signing_material: tuple[Ed25519PrivateKey, dict[str, Any]]
) -> None:
    artifact, verifier = _valid(signing_material)
    result = verifier.verify(artifact)

    assert result.verified is True
    assert result.semantic_consistent is True
    assert result.reason == "neomundi_rgc_v02_verified"
    assert result.key_id == "neomundi-test-key"
    assert result.algorithm == "EdDSA"
    assert result.evidence is not None
    assert result.evidence.provider_id == NEOMUNDI_PROVIDER_ID
    assert result.evidence.artifact_id == "req-neomundi-001"
    assert result.evidence.artifact_version == "0.2.0"
    assert result.evidence.expires_at is None
    assert result.evidence.observed_at == result.evidence.issued_at
    assert result.evidence.measured_scope["runtime_scope"] == "single_request"
    assert (
        result.evidence.semantic_facts["observed_signals"][
            "factual_hallucination_score"
        ]
        is None
    )
    assert result.evidence.metadata["authority_imported"] is False
    assert result.evidence.metadata["approval_imported"] is False
    assert result.evidence.metadata["execution_permission_imported"] is False
    assert not hasattr(result.evidence, "authority_evidence")
    assert not hasattr(result.evidence, "human_approval")
    assert not hasattr(result.evidence, "bind_authorization")
    assert not hasattr(result.evidence, "governance_decision")


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda a: a["identity"].pop("schema_version"), "neomundi_rgc_version_unsupported"),
        (
            lambda a: a["identity"].__setitem__("schema_version", "0.1.0"),
            "neomundi_rgc_version_unsupported",
        ),
        (
            lambda a: a["integrity"].pop("hash_algorithm"),
            "neomundi_rgc_hash_algorithm_missing",
        ),
        (
            lambda a: a["integrity"].__setitem__("hash_algorithm", "sha512"),
            "neomundi_rgc_hash_algorithm_invalid",
        ),
        (
            lambda a: a["integrity"].pop("canonicalization"),
            "neomundi_rgc_canonicalization_missing",
        ),
        (
            lambda a: a["integrity"].__setitem__("canonicalization", "json"),
            "neomundi_rgc_canonicalization_invalid",
        ),
        (
            lambda a: a["governance"]["governance_boundary"].pop(
                "execution_permission_changed"
            ),
            "neomundi_rgc_execution_permission_missing",
        ),
        (
            lambda a: a["governance"]["governance_boundary"].__setitem__(
                "execution_permission_changed", True
            ),
            "neomundi_rgc_execution_permission_invalid",
        ),
        (
            lambda a: a["governance"]["governance_boundary"].__setitem__(
                "authorization_status", "authorized"
            ),
            "neomundi_rgc_authorization_status_invalid",
        ),
        (
            lambda a: a["governance"]["advisory"].__setitem__(
                "review_recommendation", "deny"
            ),
            "neomundi_rgc_review_recommendation_invalid",
        ),
        (
            lambda a: a["observation"].__setitem__("measurement_coverage", 1.1),
            "neomundi_rgc_measurement_coverage_invalid",
        ),
        (
            lambda a: a["observation"].__setitem__("measurement_coverage", 0.9),
            "neomundi_rgc_measurement_semantics_invalid",
        ),
        (
            lambda a: a["observation"].pop("measurement_boundary"),
            "neomundi_rgc_measurement_boundary_missing",
        ),
        (
            lambda a: a["observation"].pop("limitations"),
            "neomundi_rgc_limitations_missing",
        ),
    ],
)
def test_security_relevant_structure_and_semantics_fail_closed(
    signing_material: tuple[Ed25519PrivateKey, dict[str, Any]],
    mutation,
    reason: str,
) -> None:
    artifact, verifier = _valid(signing_material)
    mutation(artifact)
    result = verifier.verify(artifact)
    assert result.verified is False
    assert result.reason == reason


@pytest.mark.parametrize(
    ("signal", "status", "value", "reason"),
    [
        (
            "stability_score",
            "measured",
            None,
            "neomundi_rgc_measured_signal_invalid",
        ),
        (
            "factual_hallucination_score",
            "not_measured",
            0.0,
            "neomundi_rgc_unmeasured_signal_must_be_null",
        ),
        (
            "factual_hallucination_score",
            "insufficient_coverage",
            0.1,
            "neomundi_rgc_unmeasured_signal_must_be_null",
        ),
        (
            "stability_score",
            "unknown",
            0.9,
            "neomundi_rgc_signal_status_invalid",
        ),
    ],
)
def test_signal_state_never_promotes_unknown_to_numeric_meaning(
    signing_material: tuple[Ed25519PrivateKey, dict[str, Any]],
    signal: str,
    status: str,
    value: Any,
    reason: str,
) -> None:
    artifact, verifier = _valid(signing_material)
    artifact["observation"]["observed_signals"]["signal_status"][signal] = status
    artifact["observation"]["observed_signals"][signal] = value

    result = verifier.verify(artifact)
    assert result.verified is False
    assert result.reason == reason


def test_valid_partial_not_assessed_preserves_explicit_nulls(
    signing_material: tuple[Ed25519PrivateKey, dict[str, Any]]
) -> None:
    private_key, jwks = signing_material
    artifact = _artifact()
    observation = artifact["observation"]
    observation["measurement_status"] = "partial"
    observation["measurement_coverage"] = 0.6
    signals = observation["observed_signals"]
    signals["observation_class"] = "not_assessed"
    signals["factual_hallucination_score"] = None
    signals["signal_status"]["factual_hallucination_score"] = "insufficient_coverage"
    _sign(artifact, private_key)

    result = _verifier(jwks).verify(artifact)

    assert result.verified is True
    assert result.evidence is not None
    assert result.evidence.semantic_facts["observation_class"] == "not_assessed"
    assert (
        result.evidence.semantic_facts["observed_signals"][
            "factual_hallucination_score"
        ]
        is None
    )


def test_tamper_after_signing_is_rejected_by_payload_identity(
    signing_material: tuple[Ed25519PrivateKey, dict[str, Any]]
) -> None:
    artifact, verifier = _valid(signing_material)
    artifact["observation"]["observed_signals"]["coherence_score"] = 0.2

    result = verifier.verify(artifact)

    assert result.verified is False
    assert result.reason == "neomundi_rgc_payload_hash_mismatch"


def test_unknown_key_is_not_bootstrapped_from_artifact(
    signing_material: tuple[Ed25519PrivateKey, dict[str, Any]]
) -> None:
    private_key, _ = signing_material
    artifact = _sign(_artifact(), private_key)
    verifier = NeoMundiRgcV02Verifier(
        trusted_jwks={
            "keys": [
                {
                    "kty": "OKP",
                    "crv": "Ed25519",
                    "kid": "other-key",
                    "alg": "EdDSA",
                    "x": _b64url(
                        Ed25519PrivateKey.generate()
                        .public_key()
                        .public_bytes(Encoding.Raw, PublicFormat.Raw)
                    ),
                }
            ]
        },
        verifier_policy_id="neomundi-rgc-poc-v02",
        verifier_trust_level="poc",
    )

    result = verifier.verify(artifact)

    assert result.verified is False
    assert result.reason == "neomundi_rgc_key_untrusted"


def test_jws_algorithm_and_kid_are_strictly_bound(
    signing_material: tuple[Ed25519PrivateKey, dict[str, Any]]
) -> None:
    private_key, jwks = signing_material

    bad_alg = _sign(_artifact(), private_key, alg="HS256")
    assert _verifier(jwks).verify(bad_alg).reason == "neomundi_rgc_jws_algorithm_invalid"

    bad_kid = _sign(_artifact(), private_key, header_kid="different-key")
    assert _verifier(jwks).verify(bad_kid).reason == "neomundi_rgc_jws_kid_mismatch"


@pytest.mark.parametrize(
    ("claim", "wrong_value", "reason"),
    [
        (
            "payload_hash",
            "0" * 64,
            "neomundi_rgc_signed_claim_payload_hash_mismatch",
        ),
        (
            "schema_version",
            "0.1.0",
            "neomundi_rgc_signed_claim_schema_version_mismatch",
        ),
        (
            "request_id",
            "other-request",
            "neomundi_rgc_signed_claim_request_id_mismatch",
        ),
        (
            "timestamp",
            "2026-09-11T02:04:00+00:00",
            "neomundi_rgc_signed_claim_timestamp_mismatch",
        ),
    ],
)
def test_signed_claims_must_exactly_match_received_contract(
    signing_material: tuple[Ed25519PrivateKey, dict[str, Any]],
    claim: str,
    wrong_value: str,
    reason: str,
) -> None:
    private_key, jwks = signing_material
    artifact = _sign(
        _artifact(),
        private_key,
        claims_override={claim: wrong_value},
    )

    result = _verifier(jwks).verify(artifact)

    assert result.verified is False
    assert result.reason == reason


def test_generic_boundary_accepts_once_then_rejects_replay(
    signing_material: tuple[Ed25519PrivateKey, dict[str, Any]]
) -> None:
    artifact, verifier = _valid(signing_material)
    policy = ExternalMeasurementTrustPolicy(
        policy_id="external-measurement-neomundi-poc-v1",
        approved_providers=[
            ApprovedExternalMeasurementProvider(
                provider_id=NEOMUNDI_PROVIDER_ID,
                verifier_id=NEOMUNDI_RGC_V02_VERIFIER_ID,
                verifier_trust_level=verifier.verifier_trust_level,
                verifier_policy_id=verifier.verifier_policy_id,
                verifier_policy_hash=verifier.verifier_policy_hash,
            )
        ],
        max_age_seconds=300,
        max_future_skew_seconds=5,
        require_expiry=False,
    )
    replay = _ReplayGuard()

    proof = verify_external_measurement_artifact_to_evidence(
        artifact,
        provider_verifier=verifier,
        trust_policy=policy,
        replay_guard=replay,
        now=NOW,
    )

    assert proof.evidence.provider_id == NEOMUNDI_PROVIDER_ID
    assert proof.evidence.metadata["evidence_role"] == "measurement_only"
    assert not hasattr(proof, "governance_decision")

    with pytest.raises(ValueError, match="external_measurement_replay_detected"):
        verify_external_measurement_artifact_to_evidence(
            artifact,
            provider_verifier=verifier,
            trust_policy=policy,
            replay_guard=replay,
            now=NOW,
        )


def test_generic_boundary_rejects_independent_policy_binding_mismatch(
    signing_material: tuple[Ed25519PrivateKey, dict[str, Any]]
) -> None:
    artifact, verifier = _valid(signing_material)
    policy = ExternalMeasurementTrustPolicy(
        policy_id="external-measurement-neomundi-poc-v1",
        approved_providers=[
            ApprovedExternalMeasurementProvider(
                provider_id=NEOMUNDI_PROVIDER_ID,
                verifier_id=NEOMUNDI_RGC_V02_VERIFIER_ID,
                verifier_trust_level=verifier.verifier_trust_level,
                verifier_policy_id=verifier.verifier_policy_id,
                verifier_policy_hash="f" * 64,
            )
        ],
        max_age_seconds=300,
        max_future_skew_seconds=5,
        require_expiry=False,
    )

    with pytest.raises(
        ValueError, match="external_measurement_verifier_binding_mismatch"
    ):
        verify_external_measurement_artifact_to_evidence(
            artifact,
            provider_verifier=verifier,
            trust_policy=policy,
            replay_guard=_ReplayGuard(),
            now=NOW,
        )


def test_trusted_jwks_policy_rejects_private_or_duplicate_key_material() -> None:
    with pytest.raises(ValueError, match="neomundi_rgc_private_jwk_not_allowed"):
        NeoMundiRgcV02Verifier(
            trusted_jwks={
                "keys": [
                    {
                        "kty": "OKP",
                        "crv": "Ed25519",
                        "kid": "key-1",
                        "x": "a" * 43,
                        "d": "secret",
                    }
                ]
            },
            verifier_policy_id="policy",
        )

    with pytest.raises(ValueError, match="neomundi_rgc_trusted_jwks_invalid"):
        NeoMundiRgcV02Verifier(
            trusted_jwks={
                "keys": [
                    {"kid": "key-1", "kty": "OKP", "crv": "Ed25519", "x": "a"},
                    {"kid": "key-1", "kty": "OKP", "crv": "Ed25519", "x": "b"},
                ]
            },
            verifier_policy_id="policy",
        )
