"""Focused tests for NeoMundi trusted JWKS provenance binding."""

from __future__ import annotations

import base64
import hashlib
from typing import Any

import pytest

from veritas_os.governance.neomundi_jwks_provenance import (
    bind_neomundi_trusted_jwks_provenance,
)


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _material() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    raw_public = bytes(range(32))
    jwks = {
        "keys": [
            {
                "kty": "OKP",
                "crv": "Ed25519",
                "kid": "neomundi-real-key-1",
                "alg": "EdDSA",
                "x": _b64url(raw_public),
            }
        ]
    }
    artifact = {"integrity": {"key_id": "neomundi-real-key-1"}}
    receipt = {
        "receipt_type": "trusted_public_key_provenance",
        "algorithm": "Ed25519",
        "public_key_fingerprint_sha256": hashlib.sha256(raw_public).hexdigest(),
        "trust_channel": "signed_release",
        "received_at": "2026-09-15T00:00:00+00:00",
        "approved_by": "external-poc-operator",
        "approval_reference": "NEOMUNDI-POC-KEY-001",
        "notes": "Public verification key received through the recorded PoC handoff.",
        "bundle_internal_key_used": False,
    }
    return artifact, jwks, receipt


def test_binds_selected_jwks_key_to_provenance_fingerprint() -> None:
    artifact, jwks, receipt = _material()

    binding = bind_neomundi_trusted_jwks_provenance(
        artifact,
        trusted_jwks=jwks,
        provenance_receipt=receipt,
    )

    assert binding.key_id == "neomundi-real-key-1"
    assert binding.public_key_fingerprint_sha256 == receipt[
        "public_key_fingerprint_sha256"
    ]
    assert binding.trust_channel == "signed_release"
    assert binding.receipt_canonical_sha256
    serialized = binding.to_dict()
    assert serialized["out_of_band_trust_established_by_veritas"] is False
    assert "approved_by" not in serialized
    assert "notes" not in serialized
    assert "approval_reference" not in serialized


def test_rejects_fingerprint_mismatch() -> None:
    artifact, jwks, receipt = _material()
    receipt["public_key_fingerprint_sha256"] = "0" * 64

    with pytest.raises(
        ValueError, match="neomundi_poc_provenance_fingerprint_mismatch"
    ):
        bind_neomundi_trusted_jwks_provenance(
            artifact,
            trusted_jwks=jwks,
            provenance_receipt=receipt,
        )


def test_rejects_bundle_internal_key_as_trust_basis() -> None:
    artifact, jwks, receipt = _material()
    receipt["bundle_internal_key_used"] = True

    with pytest.raises(
        ValueError, match="neomundi_poc_provenance_bundle_internal_key_forbidden"
    ):
        bind_neomundi_trusted_jwks_provenance(
            artifact,
            trusted_jwks=jwks,
            provenance_receipt=receipt,
        )


def test_rejects_duplicate_selected_key_id() -> None:
    artifact, jwks, receipt = _material()
    jwks["keys"].append(dict(jwks["keys"][0]))

    with pytest.raises(
        ValueError, match="neomundi_poc_provenance_key_binding_invalid"
    ):
        bind_neomundi_trusted_jwks_provenance(
            artifact,
            trusted_jwks=jwks,
            provenance_receipt=receipt,
        )


def test_rejects_private_jwk_material() -> None:
    artifact, jwks, receipt = _material()
    jwks["keys"][0]["d"] = _b64url(b"private-material-do-not-accept!!"[:32])

    with pytest.raises(
        ValueError, match="neomundi_poc_provenance_private_jwk_forbidden"
    ):
        bind_neomundi_trusted_jwks_provenance(
            artifact,
            trusted_jwks=jwks,
            provenance_receipt=receipt,
        )


def test_rejects_naive_received_at() -> None:
    artifact, jwks, receipt = _material()
    receipt["received_at"] = "2026-09-15T00:00:00"

    with pytest.raises(
        ValueError, match="neomundi_poc_provenance_received_at_timezone_required"
    ):
        bind_neomundi_trusted_jwks_provenance(
            artifact,
            trusted_jwks=jwks,
            provenance_receipt=receipt,
        )


def test_rejects_receipt_schema_drift() -> None:
    artifact, jwks, receipt = _material()
    receipt["unexpected"] = "field"

    with pytest.raises(ValueError, match="neomundi_poc_provenance_receipt_invalid"):
        bind_neomundi_trusted_jwks_provenance(
            artifact,
            trusted_jwks=jwks,
            provenance_receipt=receipt,
        )
