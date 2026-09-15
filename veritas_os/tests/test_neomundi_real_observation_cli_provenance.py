"""Integration tests for the real-observation CLI provenance/intake ingress gates."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

NOW = "2026-09-15T00:00:00+00:00"


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _load_cli_module() -> ModuleType:
    root = Path(__file__).resolve().parents[2]
    path = root / "scripts" / "run_neomundi_real_observation_poc.py"
    spec = importlib.util.spec_from_file_location("neomundi_real_observation_cli", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _payload_hash(artifact: dict[str, Any]) -> str:
    payload = {
        "identity": artifact["identity"],
        "provenance": artifact["provenance"],
        "observation": artifact["observation"],
        "governance": artifact["governance"],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _material() -> tuple[Ed25519PrivateKey, bytes, dict[str, Any]]:
    private_key = Ed25519PrivateKey.generate()
    raw_public = private_key.public_key().public_bytes(
        Encoding.Raw,
        PublicFormat.Raw,
    )
    jwks = {
        "keys": [
            {
                "kty": "OKP",
                "crv": "Ed25519",
                "kid": "neomundi-cli-key",
                "alg": "EdDSA",
                "x": _b64url(raw_public),
            }
        ]
    }
    return private_key, raw_public, jwks


def _artifact() -> dict[str, Any]:
    return {
        "identity": {
            "schema_version": "0.2.0",
            "request_id": "req-neomundi-cli-provenance-001",
            "trace_id": "00-" + ("a" * 32) + "-" + ("b" * 16) + "-01",
            "timestamp": "2026-09-14T23:59:30+00:00",
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
            "key_id": "neomundi-cli-key",
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
    header = {"alg": "EdDSA", "typ": "JWT", "kid": "neomundi-cli-key"}
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


def _receipt(raw_public: bytes) -> dict[str, Any]:
    return {
        "receipt_type": "trusted_public_key_provenance",
        "algorithm": "Ed25519",
        "public_key_fingerprint_sha256": hashlib.sha256(raw_public).hexdigest(),
        "trust_channel": "operator_handoff",
        "received_at": "2026-09-15T00:00:00+00:00",
        "approved_by": "external-poc-operator",
        "approval_reference": "NEOMUNDI-POC-KEY-001",
        "notes": "Public key confirmed outside the RGC artifact.",
        "bundle_internal_key_used": False,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _intake_manifest(
    *,
    artifact_path: Path,
    jwks_path: Path,
    receipt_path: Path,
) -> dict[str, Any]:
    return {
        "manifest_version": "1.0",
        "manifest_id": "neomundi-cli-intake-001",
        "provider_id": "neomundi",
        "artifact_type": "neomundi_rgc",
        "artifact_version": "0.2.0",
        "artifact_id": "req-neomundi-cli-provenance-001",
        "expected_key_id": "neomundi-cli-key",
        "expected_signer_identity": "neomundi-poc-signer",
        "artifact_file_sha256": _file_sha256(artifact_path),
        "trusted_jwks_file_sha256": _file_sha256(jwks_path),
        "trusted_key_provenance_receipt_file_sha256": _file_sha256(receipt_path),
        "handoff_reference": "NEOMUNDI-HANDOFF-CLI-001",
        "received_at": "2026-09-15T00:00:00+00:00",
    }


def _argv(tmp_path: Path) -> tuple[list[str], bytes]:
    private_key, raw_public, jwks = _material()
    artifact = _sign(_artifact(), private_key)
    artifact_path = tmp_path / "artifact.json"
    jwks_path = tmp_path / "jwks.json"
    receipt_path = tmp_path / "provenance.json"
    intake_path = tmp_path / "intake.json"
    _write_json(artifact_path, artifact)
    _write_json(jwks_path, jwks)
    _write_json(receipt_path, _receipt(raw_public))
    _write_json(
        intake_path,
        _intake_manifest(
            artifact_path=artifact_path,
            jwks_path=jwks_path,
            receipt_path=receipt_path,
        ),
    )
    return [
        "--artifact",
        str(artifact_path),
        "--jwks",
        str(jwks_path),
        "--trusted-key-provenance",
        str(receipt_path),
        "--intake-manifest",
        str(intake_path),
        "--replay-state-dir",
        str(tmp_path / "replay"),
        "--output-dir",
        str(tmp_path / "output"),
        "--max-age-seconds",
        "3600",
        "--allow-no-expiry",
        "--now",
        NOW,
    ], raw_public


def test_cli_records_source_bound_key_provenance_and_intake(tmp_path: Path) -> None:
    cli = _load_cli_module()
    argv, raw_public = _argv(tmp_path)

    assert cli.main(argv) == 0

    output_dir = tmp_path / "output"
    report = json.loads((output_dir / "verification_report.json").read_text())
    manifest = json.loads((output_dir / "evidence_manifest.json").read_text())
    expected_fingerprint = hashlib.sha256(raw_public).hexdigest()

    intake = report["intake_manifest"]
    assert intake["accepted"] is True
    assert intake["manifest_id"] == "neomundi-cli-intake-001"
    assert intake["artifact_id"] == "req-neomundi-cli-provenance-001"
    assert intake["expected_key_id"] == "neomundi-cli-key"
    assert intake["expected_signer_identity"] == "neomundi-poc-signer"
    assert intake["packet_correlation_only"] is True
    assert intake["trust_established_by_intake_manifest"] is False
    assert intake["freshness_established_by_received_at"] is False
    assert intake["manifest_file_sha256"]

    binding = report["trusted_key_provenance"]
    assert binding["accepted"] is True
    assert binding["key_id"] == "neomundi-cli-key"
    assert binding["public_key_fingerprint_sha256"] == expected_fingerprint
    assert binding["out_of_band_trust_established_by_veritas"] is False
    assert "approved_by" not in binding
    assert "notes" not in binding
    assert "approval_reference" not in binding

    manifest_binding = manifest["verification"]["trusted_key_provenance"]
    assert manifest_binding["public_key_fingerprint_sha256"] == expected_fingerprint
    assert manifest["inputs"]["trusted_key_provenance_receipt_file_sha256"]
    assert manifest["inputs"]["trusted_key_provenance_receipt_canonical_sha256"]
    assert manifest["inputs"]["intake_manifest_file_sha256"]
    assert manifest["inputs"]["intake_manifest_canonical_sha256"]
    assert manifest["verification"]["intake_manifest"]["accepted"] is True
    assert manifest["outputs"]["verification_report_canonical_sha256"]


def test_cli_rejects_intake_hash_mismatch_before_replay_consumption(
    tmp_path: Path,
) -> None:
    cli = _load_cli_module()
    argv, _ = _argv(tmp_path)
    artifact_path = tmp_path / "artifact.json"
    artifact = json.loads(artifact_path.read_text())
    artifact["identity"]["system_id"] = "tampered-after-handoff"
    _write_json(artifact_path, artifact)

    assert cli.main(argv) == 2

    report = json.loads(
        (tmp_path / "output" / "verification_report.json").read_text()
    )
    assert report["status"] == "failed"
    assert report["stage"] == "intake_manifest"
    assert report["reason"] == "neomundi_poc_intake_artifact_hash_mismatch"
    assert report["intake_manifest"]["accepted"] is False
    replay_dir = tmp_path / "replay"
    assert not replay_dir.exists() or list(replay_dir.iterdir()) == []


def test_cli_rejects_mismatched_provenance_before_replay_consumption(
    tmp_path: Path,
) -> None:
    cli = _load_cli_module()
    argv, _ = _argv(tmp_path)
    receipt_path = tmp_path / "provenance.json"
    intake_path = tmp_path / "intake.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["public_key_fingerprint_sha256"] = "0" * 64
    _write_json(receipt_path, receipt)

    intake = json.loads(intake_path.read_text())
    intake["trusted_key_provenance_receipt_file_sha256"] = _file_sha256(receipt_path)
    _write_json(intake_path, intake)

    assert cli.main(argv) == 2

    report = json.loads(
        (tmp_path / "output" / "verification_report.json").read_text()
    )
    assert report["status"] == "failed"
    assert report["stage"] == "trusted_key_provenance"
    assert report["reason"] == "neomundi_poc_provenance_fingerprint_mismatch"
    assert report["intake_manifest"]["accepted"] is True
    assert report["trusted_key_provenance"]["accepted"] is False
    replay_dir = tmp_path / "replay"
    assert not replay_dir.exists() or list(replay_dir.iterdir()) == []
