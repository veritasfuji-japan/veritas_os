"""Tests for the reproducible NeoMundi real-observation PoC runner."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from veritas_os.governance.neomundi_real_observation_poc import (
    NeoMundiRealObservationPocError,
    run_neomundi_real_observation_poc,
)

NOW = datetime(2026, 9, 11, 6, 0, tzinfo=UTC)


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


def _material() -> tuple[Ed25519PrivateKey, dict[str, Any]]:
    private_key = Ed25519PrivateKey.generate()
    raw_public = private_key.public_key().public_bytes(
        Encoding.Raw,
        PublicFormat.Raw,
    )
    return private_key, {
        "keys": [
            {
                "kty": "OKP",
                "crv": "Ed25519",
                "kid": "neomundi-poc-key",
                "alg": "EdDSA",
                "x": _b64url(raw_public),
            }
        ]
    }


def _artifact(timestamp: str = "2026-09-11T05:59:30+00:00") -> dict[str, Any]:
    return {
        "identity": {
            "schema_version": "0.2.0",
            "request_id": "req-neomundi-real-poc-001",
            "trace_id": "00-" + ("a" * 32) + "-" + ("b" * 16) + "-01",
            "timestamp": timestamp,
            "system_id": "neomundi-real-poc",
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
            "signer_identity": "neomundi-poc-signer",
            "key_id": "neomundi-poc-key",
            "confidentiality_class": "controlled",
            "retention_reference": None,
        },
    }


def _sign(artifact: dict[str, Any], private_key: Ed25519PrivateKey) -> dict[str, Any]:
    artifact["integrity"]["payload_hash"] = _payload_hash(artifact)
    claims = {
        "payload_hash": artifact["integrity"]["payload_hash"],
        "hash_algorithm": artifact["integrity"]["hash_algorithm"],
        "schema_version": artifact["identity"]["schema_version"],
        "request_id": artifact["identity"]["request_id"],
        "timestamp": artifact["identity"]["timestamp"],
    }
    header = {"alg": "EdDSA", "typ": "JWT", "kid": "neomundi-poc-key"}
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


def _run(
    artifact: dict[str, Any],
    jwks: dict[str, Any],
    replay_state_dir: Path,
    *,
    now: datetime = NOW,
    allow_no_expiry: bool = True,
    max_age_seconds: int = 3600,
) -> dict[str, dict[str, Any]]:
    return run_neomundi_real_observation_poc(
        artifact,
        trusted_jwks=jwks,
        replay_state_dir=replay_state_dir,
        verifier_policy_id="neomundi-rgc-v02-real-observation-poc",
        verifier_trust_level="external-poc",
        trust_policy_id="neomundi-rgc-v02-external-poc",
        max_age_seconds=max_age_seconds,
        max_future_skew_seconds=60,
        allow_no_expiry=allow_no_expiry,
        now=now,
        source_artifact_file_sha256="a" * 64,
        trusted_jwks_file_sha256="b" * 64,
    )


def test_real_observation_runner_seals_measurement_only_evidence(tmp_path: Path) -> None:
    private_key, jwks = _material()
    artifact = _sign(_artifact(), private_key)

    outputs = _run(artifact, jwks, tmp_path / "replay")

    report = outputs["verification_report"]
    proof = outputs["verified_external_measurement_evidence"]
    manifest = outputs["evidence_manifest"]

    assert report["status"] == "verified"
    assert report["provider_verification"]["reason"] == "neomundi_rgc_v02_verified"
    assert report["generic_boundary"]["accepted"] is True
    assert report["generic_boundary"]["require_expiry"] is False
    assert report["claim_boundary"]["measurement_only"] is True
    assert report["claim_boundary"]["authority_created"] is False
    assert report["claim_boundary"]["bind_authorization_created"] is False
    assert report["claim_boundary"]["governance_decision_created"] is False
    assert proof["evidence"]["provider_id"] == "neomundi"
    assert proof["evidence"]["artifact_id"] == "req-neomundi-real-poc-001"
    assert proof["evidence"]["metadata"]["authority_imported"] is False
    assert manifest["inputs"]["artifact_file_sha256"] == "a" * 64
    assert manifest["inputs"]["trusted_jwks_file_sha256"] == "b" * 64
    assert manifest["verification"]["verification_proof_hash"]
    assert manifest["outputs"]["verification_report_canonical_sha256"]


def test_real_observation_runner_rejects_replay_across_runs(tmp_path: Path) -> None:
    private_key, jwks = _material()
    artifact = _sign(_artifact(), private_key)
    replay_dir = tmp_path / "replay"

    _run(artifact, jwks, replay_dir)

    with pytest.raises(NeoMundiRealObservationPocError) as caught:
        _run(artifact, jwks, replay_dir)

    assert caught.value.reason == "external_measurement_replay_detected"
    assert caught.value.report["stage"] == "generic_external_measurement_boundary"


def test_real_observation_runner_preserves_provider_failure_reason(tmp_path: Path) -> None:
    private_key, jwks = _material()
    artifact = _sign(_artifact(), private_key)
    artifact["observation"]["measurement_boundary"] = "tampered after signing"

    with pytest.raises(NeoMundiRealObservationPocError) as caught:
        _run(artifact, jwks, tmp_path / "replay")

    assert caught.value.reason == "neomundi_rgc_payload_hash_mismatch"
    assert caught.value.report["stage"] == "provider_verification"


def test_real_observation_runner_rejects_stale_observation(tmp_path: Path) -> None:
    private_key, jwks = _material()
    stale = (NOW - timedelta(hours=2)).isoformat()
    artifact = _sign(_artifact(stale), private_key)

    with pytest.raises(NeoMundiRealObservationPocError) as caught:
        _run(
            artifact,
            jwks,
            tmp_path / "replay",
            max_age_seconds=3600,
        )

    assert caught.value.reason == "external_measurement_stale"
    assert caught.value.report["stage"] == "generic_external_measurement_boundary"


def test_real_observation_runner_requires_explicit_no_expiry_ack(tmp_path: Path) -> None:
    private_key, jwks = _material()
    artifact = _sign(_artifact(), private_key)

    with pytest.raises(NeoMundiRealObservationPocError) as caught:
        _run(
            artifact,
            jwks,
            tmp_path / "replay",
            allow_no_expiry=False,
        )

    assert caught.value.reason == "external_measurement_expiry_missing"
    assert caught.value.report["stage"] == "generic_external_measurement_boundary"
