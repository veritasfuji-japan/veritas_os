"""Tests for the NeoMundi real-observation intake manifest binding."""

from __future__ import annotations

import copy

import pytest

from veritas_os.governance.neomundi_real_observation_intake import (
    bind_neomundi_real_observation_intake,
)

ARTIFACT_HASH = "a" * 64
JWKS_HASH = "b" * 64
PROVENANCE_HASH = "c" * 64


def _artifact() -> dict[str, object]:
    return {
        "identity": {
            "schema_version": "0.2.0",
            "request_id": "req-neomundi-intake-001",
        },
        "integrity": {
            "key_id": "neomundi-intake-key",
            "signer_identity": "neomundi-real-signer",
        },
    }


def _manifest() -> dict[str, object]:
    return {
        "manifest_version": "1.0",
        "manifest_id": "neomundi-intake-001",
        "provider_id": "neomundi",
        "artifact_type": "neomundi_rgc",
        "artifact_version": "0.2.0",
        "artifact_id": "req-neomundi-intake-001",
        "expected_key_id": "neomundi-intake-key",
        "expected_signer_identity": "neomundi-real-signer",
        "artifact_file_sha256": ARTIFACT_HASH,
        "trusted_jwks_file_sha256": JWKS_HASH,
        "trusted_key_provenance_receipt_file_sha256": PROVENANCE_HASH,
        "handoff_reference": "NEOMUNDI-HANDOFF-001",
        "received_at": "2026-09-15T00:30:00+00:00",
    }


def _bind(manifest: dict[str, object], artifact: dict[str, object] | None = None):
    return bind_neomundi_real_observation_intake(
        manifest,
        artifact=artifact or _artifact(),
        artifact_file_sha256=ARTIFACT_HASH,
        trusted_jwks_file_sha256=JWKS_HASH,
        trusted_key_provenance_receipt_file_sha256=PROVENANCE_HASH,
    )


def test_intake_manifest_binds_exact_packet_and_identity() -> None:
    binding = _bind(_manifest())

    output = binding.to_dict()
    assert output["manifest_id"] == "neomundi-intake-001"
    assert output["artifact_id"] == "req-neomundi-intake-001"
    assert output["expected_key_id"] == "neomundi-intake-key"
    assert output["expected_signer_identity"] == "neomundi-real-signer"
    assert output["artifact_file_sha256"] == ARTIFACT_HASH
    assert output["trusted_jwks_file_sha256"] == JWKS_HASH
    assert output["trusted_key_provenance_receipt_file_sha256"] == PROVENANCE_HASH
    assert output["manifest_canonical_sha256"]
    assert output["packet_correlation_only"] is True
    assert output["trust_established_by_intake_manifest"] is False
    assert output["freshness_established_by_received_at"] is False
    assert output["execution_permission_created"] is False


def test_intake_manifest_rejects_artifact_file_hash_mismatch() -> None:
    manifest = _manifest()
    manifest["artifact_file_sha256"] = "d" * 64

    with pytest.raises(ValueError, match="neomundi_poc_intake_artifact_hash_mismatch"):
        _bind(manifest)


def test_intake_manifest_rejects_jwks_file_hash_mismatch() -> None:
    manifest = _manifest()
    manifest["trusted_jwks_file_sha256"] = "d" * 64

    with pytest.raises(ValueError, match="neomundi_poc_intake_jwks_hash_mismatch"):
        _bind(manifest)


def test_intake_manifest_rejects_provenance_file_hash_mismatch() -> None:
    manifest = _manifest()
    manifest["trusted_key_provenance_receipt_file_sha256"] = "d" * 64

    with pytest.raises(ValueError, match="neomundi_poc_intake_provenance_hash_mismatch"):
        _bind(manifest)


def test_intake_manifest_rejects_artifact_identity_mismatch() -> None:
    manifest = _manifest()
    manifest["artifact_id"] = "different-request"

    with pytest.raises(ValueError, match="neomundi_poc_intake_artifact_id_mismatch"):
        _bind(manifest)


def test_intake_manifest_rejects_key_id_and_signer_mismatch() -> None:
    manifest = _manifest()
    artifact = _artifact()
    artifact_integrity = copy.deepcopy(artifact["integrity"])
    assert isinstance(artifact_integrity, dict)
    artifact_integrity["key_id"] = "unexpected-key"
    artifact["integrity"] = artifact_integrity

    with pytest.raises(ValueError, match="neomundi_poc_intake_key_id_mismatch"):
        _bind(manifest, artifact)

    artifact = _artifact()
    artifact_integrity = copy.deepcopy(artifact["integrity"])
    assert isinstance(artifact_integrity, dict)
    artifact_integrity["signer_identity"] = "unexpected-signer"
    artifact["integrity"] = artifact_integrity

    with pytest.raises(ValueError, match="neomundi_poc_intake_signer_identity_mismatch"):
        _bind(manifest, artifact)


def test_intake_manifest_rejects_naive_received_at() -> None:
    manifest = _manifest()
    manifest["received_at"] = "2026-09-15T00:30:00"

    with pytest.raises(
        ValueError, match="neomundi_poc_intake_received_at_timezone_required"
    ):
        _bind(manifest)


def test_intake_manifest_rejects_unknown_fields() -> None:
    manifest = _manifest()
    manifest["extra"] = "not allowed"

    with pytest.raises(ValueError, match="neomundi_poc_intake_manifest_fields_invalid"):
        _bind(manifest)
