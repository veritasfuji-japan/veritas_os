"""Tests for Ed25519 cryptographic signing of policy bundles."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from veritas_os.policy.compiler import compile_policy_to_bundle
from veritas_os.policy.runtime_adapter import (
    load_runtime_bundle,
    verify_manifest_signature,
)
from veritas_os.policy.signing import (
    generate_keypair,
    sign_manifest,
    verify_manifest_ed25519,
    sha256_manifest_hex,
)

EXAMPLES_DIR = Path("policies/examples")


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# --- signing module unit tests ---


def test_generate_keypair_produces_pem_bytes() -> None:
    private_pem, public_pem = generate_keypair()
    assert isinstance(private_pem, bytes)
    assert isinstance(public_pem, bytes)
    assert b"PRIVATE KEY" in private_pem
    assert b"PUBLIC KEY" in public_pem


def test_sign_and_verify_roundtrip() -> None:
    private_pem, public_pem = generate_keypair()
    data = b'{"policy_id":"test","version":"1.0"}'
    sig = sign_manifest(data, private_pem)
    assert isinstance(sig, str)
    assert verify_manifest_ed25519(data, sig, public_pem)


def test_verify_rejects_tampered_data() -> None:
    private_pem, public_pem = generate_keypair()
    data = b"original content"
    sig = sign_manifest(data, private_pem)
    assert not verify_manifest_ed25519(b"tampered content", sig, public_pem)


def test_verify_rejects_wrong_key() -> None:
    priv1, _ = generate_keypair()
    _, pub2 = generate_keypair()
    data = b"test data"
    sig = sign_manifest(data, priv1)
    assert not verify_manifest_ed25519(data, sig, pub2)


def test_sha256_manifest_hex_deterministic() -> None:
    data = b"stable content"
    assert sha256_manifest_hex(data) == sha256_manifest_hex(data)
    assert len(sha256_manifest_hex(data)) == 64


# --- compiler + Ed25519 integration tests ---


def test_compile_with_ed25519_signing_produces_signed_bundle(tmp_path: Path) -> None:
    private_pem, public_pem = generate_keypair()
    result = compile_policy_to_bundle(
        EXAMPLES_DIR / "external_tool_usage_denied.yaml",
        tmp_path,
        compiled_at="2026-04-03T00:00:00Z",
        signing_key=private_pem,
    )
    manifest = _load_json(result.manifest_path)

    assert manifest["signing"]["status"] == "signed-ed25519"
    assert manifest["signing"]["algorithm"] == "ed25519"
    assert manifest["signing"]["key_id"] == "ed25519"

    # UNSIGNED marker should NOT be present for Ed25519-signed bundles
    assert not (result.bundle_dir / "signatures" / "UNSIGNED").exists()

    # signature file should exist and be base64
    sig_path = result.bundle_dir / "manifest.sig"
    assert sig_path.exists()
    sig_text = sig_path.read_text(encoding="utf-8").strip()
    assert len(sig_text) > 20  # base64 encoded Ed25519 sig


def test_ed25519_signed_bundle_loads_with_public_key(tmp_path: Path) -> None:
    private_pem, public_pem = generate_keypair()
    result = compile_policy_to_bundle(
        EXAMPLES_DIR / "high_risk_route_requires_human_review.yaml",
        tmp_path,
        compiled_at="2026-04-03T01:00:00Z",
        signing_key=private_pem,
    )
    bundle = load_runtime_bundle(result.bundle_dir, public_key_pem=public_pem)
    assert bundle.semantic_hash == result.semantic_hash
    assert bundle.policy_id == "policy.high_risk_route.human_review"


def test_ed25519_signed_bundle_rejects_tampered_manifest(tmp_path: Path) -> None:
    private_pem, public_pem = generate_keypair()
    result = compile_policy_to_bundle(
        EXAMPLES_DIR / "external_tool_usage_denied.yaml",
        tmp_path,
        compiled_at="2026-04-03T02:00:00Z",
        signing_key=private_pem,
    )
    # Tamper with manifest
    manifest = _load_json(result.manifest_path)
    manifest["compiler_version"] = "tampered"
    result.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="signature verification failed"):
        load_runtime_bundle(result.bundle_dir, public_key_pem=public_pem)


def test_ed25519_signed_bundle_rejects_wrong_public_key(tmp_path: Path) -> None:
    priv1, _ = generate_keypair()
    _, pub2 = generate_keypair()
    result = compile_policy_to_bundle(
        EXAMPLES_DIR / "low_risk_route_allow.yaml",
        tmp_path,
        compiled_at="2026-04-03T03:00:00Z",
        signing_key=priv1,
    )
    with pytest.raises(ValueError, match="signature verification failed"):
        load_runtime_bundle(result.bundle_dir, public_key_pem=pub2)


def test_verify_manifest_signature_via_env_var(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private_pem, public_pem = generate_keypair()
    result = compile_policy_to_bundle(
        EXAMPLES_DIR / "anomaly_detection_escalate.yaml",
        tmp_path,
        compiled_at="2026-04-03T04:00:00Z",
        signing_key=private_pem,
    )
    key_file = tmp_path / "verify.pub"
    key_file.write_bytes(public_pem)
    monkeypatch.setenv("VERITAS_POLICY_VERIFY_KEY", str(key_file))

    assert verify_manifest_signature(result.bundle_dir) is True


def test_ed25519_bundle_without_key_logs_downgrade_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """When a bundle declares ed25519 but no public key is supplied, a warning
    about the security downgrade to SHA-256 must be emitted."""
    private_pem, _ = generate_keypair()
    result = compile_policy_to_bundle(
        EXAMPLES_DIR / "external_tool_usage_denied.yaml",
        tmp_path,
        compiled_at="2026-04-03T07:00:00Z",
        signing_key=private_pem,
    )
    import logging

    with caplog.at_level(logging.WARNING, logger="veritas_os.policy.runtime_adapter"):
        # No public_key_pem → SHA-256 fallback even though manifest says ed25519
        # SHA-256 will fail because the sig file contains a base64 ed25519 sig,
        # not a sha256 hex digest.
        ok = verify_manifest_signature(result.bundle_dir)
    assert not ok  # SHA-256 check fails for ed25519-signed bundles
    assert "falling back to SHA-256" in caplog.text


def test_legacy_bundle_still_loads_without_key(tmp_path: Path) -> None:
    """Legacy SHA-256 bundles continue to work when no key is provided."""
    result = compile_policy_to_bundle(
        EXAMPLES_DIR / "external_tool_usage_denied.yaml",
        tmp_path,
        compiled_at="2026-04-03T05:00:00Z",
    )
    manifest = _load_json(result.manifest_path)
    assert manifest["signing"]["status"] == "signed-local"
    assert manifest["signing"]["algorithm"] == "sha256"

    bundle = load_runtime_bundle(result.bundle_dir)
    assert bundle.semantic_hash == result.semantic_hash


def test_ed25519_compile_deterministic(tmp_path: Path) -> None:
    """Two compilations with the same key and timestamp produce same manifest content."""
    private_pem, _ = generate_keypair()
    fixed_at = "2026-04-03T06:00:00Z"
    r1 = compile_policy_to_bundle(
        EXAMPLES_DIR / "missing_mandatory_evidence_halt.yaml",
        tmp_path / "a",
        compiled_at=fixed_at,
        signing_key=private_pem,
    )
    r2 = compile_policy_to_bundle(
        EXAMPLES_DIR / "missing_mandatory_evidence_halt.yaml",
        tmp_path / "b",
        compiled_at=fixed_at,
        signing_key=private_pem,
    )
    assert r1.semantic_hash == r2.semantic_hash

    m1 = _load_json(r1.manifest_path)
    m2 = _load_json(r2.manifest_path)
    m1["source_files"] = m2["source_files"] = ["<redacted>"]
    assert m1 == m2
