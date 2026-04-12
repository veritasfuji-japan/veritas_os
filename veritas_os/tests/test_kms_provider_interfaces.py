"""Tests for KMS/Vault provider interfaces and migration fallbacks."""

from __future__ import annotations

import base64

import pytest


def test_encryption_provider_fallback_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-env provider can use temporary env fallback during migration."""
    from veritas_os.logging import encryption

    key_b64 = encryption.generate_key()
    monkeypatch.setenv("VERITAS_ENCRYPTION_KEY_PROVIDER", "aws_kms")
    monkeypatch.setenv("VERITAS_ENCRYPTION_ALLOW_ENV_FALLBACK", "1")
    monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", key_b64)
    monkeypatch.delenv("VERITAS_ENCRYPTION_AWS_KMS_CIPHERTEXT_B64", raising=False)

    key = encryption._get_key_bytes()
    assert key is not None
    assert key == base64.urlsafe_b64decode(key_b64)


def test_encryption_unknown_provider_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unknown provider names must fail closed to avoid silent plaintext writes."""
    from veritas_os.logging.encryption import EncryptionKeyMissing, _get_key_bytes

    monkeypatch.setenv("VERITAS_ENCRYPTION_KEY_PROVIDER", "unsupported_provider")
    with pytest.raises(EncryptionKeyMissing):
        _get_key_bytes()


def test_build_trustlog_signer_supports_gcp_backend(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """GCP backend returns signer object without touching local key files."""
    from veritas_os.security.signing import build_trustlog_signer

    monkeypatch.setenv("VERITAS_TRUSTLOG_SIGNER_BACKEND", "gcp_kms")
    monkeypatch.setenv(
        "VERITAS_TRUSTLOG_GCP_KMS_KEY_NAME",
        "projects/p/locations/global/keyRings/r/cryptoKeys/k/cryptoKeyVersions/1",
    )

    signer = build_trustlog_signer(
        private_key_path=tmp_path / "priv.key",
        public_key_path=tmp_path / "pub.key",
    )
    assert signer.signer_type == "gcp_kms"


def test_build_trustlog_signer_supports_vault_backend(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Vault transit backend is available for env-key migration."""
    from veritas_os.security.signing import build_trustlog_signer

    monkeypatch.setenv("VERITAS_TRUSTLOG_SIGNER_BACKEND", "vault")
    monkeypatch.setenv("VERITAS_TRUSTLOG_VAULT_KEY_NAME", "trustlog-ed25519")

    signer = build_trustlog_signer(
        private_key_path=tmp_path / "priv.key",
        public_key_path=tmp_path / "pub.key",
    )
    assert signer.signer_type == "vault"
