"""Tests for KMS key provider integration — encryption.py KeyProvider backends."""

from __future__ import annotations

import base64
import os
from unittest.mock import MagicMock, patch

import pytest

from veritas_os.logging.encryption import (
    AwsKmsKeyProvider,
    DecryptionError,
    EncryptionKeyMissing,
    EnvKeyProvider,
    GcpKmsKeyProvider,
    KeyProvider,
    VaultKeyProvider,
    build_key_provider,
    decrypt,
    encrypt,
    generate_key,
    get_key_provider,
    set_key_provider,
)


# ---------------------------------------------------------------------------
# KeyProvider protocol
# ---------------------------------------------------------------------------


class TestKeyProviderProtocol:
    """Verify that all providers conform to the KeyProvider protocol."""

    def test_env_provider_is_key_provider(self):
        assert isinstance(EnvKeyProvider(), KeyProvider)

    def test_aws_provider_is_key_provider(self):
        p = AwsKmsKeyProvider(kms_key_id="key", encrypted_key_b64="data", kms_client=MagicMock())
        assert isinstance(p, KeyProvider)

    def test_gcp_provider_is_key_provider(self):
        p = GcpKmsKeyProvider(resource_name="res", encrypted_key_b64="data", kms_client=MagicMock())
        assert isinstance(p, KeyProvider)

    def test_vault_provider_is_key_provider(self):
        p = VaultKeyProvider(vault_addr="http://v", secret_path="/s", client=MagicMock())
        assert isinstance(p, KeyProvider)


# ---------------------------------------------------------------------------
# EnvKeyProvider
# ---------------------------------------------------------------------------


class TestEnvKeyProvider:
    def test_get_key_bytes_present(self):
        key = base64.urlsafe_b64encode(os.urandom(32)).decode()
        with patch.dict(os.environ, {"VERITAS_ENCRYPTION_KEY": key}):
            p = EnvKeyProvider()
            result = p.get_key_bytes()
            assert result is not None
            assert len(result) == 32

    def test_get_key_bytes_absent(self):
        with patch.dict(os.environ, {}, clear=True):
            p = EnvKeyProvider()
            assert p.get_key_bytes() is None

    def test_is_available(self):
        key = generate_key()
        with patch.dict(os.environ, {"VERITAS_ENCRYPTION_KEY": key}):
            assert EnvKeyProvider().is_available()

    def test_is_not_available(self):
        with patch.dict(os.environ, {}, clear=True):
            assert not EnvKeyProvider().is_available()

    def test_provider_name(self):
        assert EnvKeyProvider().provider_name == "env"


# ---------------------------------------------------------------------------
# AwsKmsKeyProvider
# ---------------------------------------------------------------------------


class TestAwsKmsKeyProvider:
    def _make_provider(self, *, key_bytes: bytes = os.urandom(32)):
        encrypted = base64.b64encode(b"fake-ciphertext").decode()
        mock_client = MagicMock()
        mock_client.decrypt.return_value = {"Plaintext": key_bytes}
        return AwsKmsKeyProvider(
            kms_key_id="alias/test",
            encrypted_key_b64=encrypted,
            kms_client=mock_client,
        )

    def test_get_key_bytes_success(self):
        key = os.urandom(32)
        p = self._make_provider(key_bytes=key)
        result = p.get_key_bytes()
        assert result == key

    def test_get_key_bytes_wrong_length(self):
        p = self._make_provider(key_bytes=os.urandom(16))
        with pytest.raises(EncryptionKeyMissing, match="exactly 32 bytes"):
            p.get_key_bytes()

    def test_get_key_bytes_not_configured(self):
        p = AwsKmsKeyProvider(kms_key_id="", encrypted_key_b64="")
        assert p.get_key_bytes() is None

    def test_get_key_bytes_api_error(self):
        encrypted = base64.b64encode(b"fake").decode()
        mock_client = MagicMock()
        mock_client.decrypt.side_effect = RuntimeError("API error")
        p = AwsKmsKeyProvider(
            kms_key_id="alias/test",
            encrypted_key_b64=encrypted,
            kms_client=mock_client,
        )
        with pytest.raises(EncryptionKeyMissing, match="AWS KMS"):
            p.get_key_bytes()

    def test_is_available(self):
        p = AwsKmsKeyProvider(kms_key_id="id", encrypted_key_b64="data")
        assert p.is_available()

    def test_is_not_available(self):
        p = AwsKmsKeyProvider(kms_key_id="", encrypted_key_b64="")
        assert not p.is_available()

    def test_provider_name(self):
        p = AwsKmsKeyProvider(kms_key_id="id", encrypted_key_b64="d")
        assert p.provider_name == "aws_kms"


# ---------------------------------------------------------------------------
# GcpKmsKeyProvider
# ---------------------------------------------------------------------------


class TestGcpKmsKeyProvider:
    def _make_provider(self, *, key_bytes: bytes = os.urandom(32)):
        encrypted = base64.b64encode(b"fake-ciphertext").decode()
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.plaintext = key_bytes
        mock_client.decrypt.return_value = mock_response
        return GcpKmsKeyProvider(
            resource_name="projects/p/locations/l/keyRings/r/cryptoKeys/k",
            encrypted_key_b64=encrypted,
            kms_client=mock_client,
        )

    def test_get_key_bytes_success(self):
        key = os.urandom(32)
        p = self._make_provider(key_bytes=key)
        result = p.get_key_bytes()
        assert result == key

    def test_get_key_bytes_wrong_length(self):
        p = self._make_provider(key_bytes=os.urandom(16))
        with pytest.raises(EncryptionKeyMissing, match="exactly 32 bytes"):
            p.get_key_bytes()

    def test_get_key_bytes_not_configured(self):
        p = GcpKmsKeyProvider(resource_name="", encrypted_key_b64="")
        assert p.get_key_bytes() is None

    def test_get_key_bytes_api_error(self):
        encrypted = base64.b64encode(b"fake").decode()
        mock_client = MagicMock()
        mock_client.decrypt.side_effect = RuntimeError("GCP error")
        p = GcpKmsKeyProvider(
            resource_name="projects/p/locations/l/keyRings/r/cryptoKeys/k",
            encrypted_key_b64=encrypted,
            kms_client=mock_client,
        )
        with pytest.raises(EncryptionKeyMissing, match="GCP KMS"):
            p.get_key_bytes()

    def test_is_available(self):
        p = GcpKmsKeyProvider(resource_name="res", encrypted_key_b64="data")
        assert p.is_available()

    def test_is_not_available(self):
        p = GcpKmsKeyProvider(resource_name="", encrypted_key_b64="")
        assert not p.is_available()

    def test_provider_name(self):
        p = GcpKmsKeyProvider(resource_name="res", encrypted_key_b64="d")
        assert p.provider_name == "gcp_kms"


# ---------------------------------------------------------------------------
# VaultKeyProvider
# ---------------------------------------------------------------------------


class TestVaultKeyProvider:
    def _make_provider(self, *, key_bytes: bytes = os.urandom(32)):
        key_b64 = base64.b64encode(key_bytes).decode()
        mock_client = MagicMock()
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {"encryption_key": key_b64}}
        }
        return VaultKeyProvider(
            vault_addr="http://vault:8200",
            vault_token="s.test-token",
            secret_path="secret/data/veritas/encryption",
            client=mock_client,
        )

    def test_get_key_bytes_success(self):
        key = os.urandom(32)
        p = self._make_provider(key_bytes=key)
        result = p.get_key_bytes()
        assert result == key

    def test_get_key_bytes_wrong_length(self):
        p = self._make_provider(key_bytes=os.urandom(16))
        with pytest.raises(EncryptionKeyMissing, match="exactly 32 bytes"):
            p.get_key_bytes()

    def test_get_key_bytes_not_configured(self):
        p = VaultKeyProvider(vault_addr="", secret_path="")
        assert p.get_key_bytes() is None

    def test_get_key_bytes_missing_key_field(self):
        mock_client = MagicMock()
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {"other_key": "value"}}
        }
        p = VaultKeyProvider(
            vault_addr="http://vault:8200",
            secret_path="secret/path",
            client=mock_client,
        )
        assert p.get_key_bytes() is None

    def test_get_key_bytes_api_error(self):
        mock_client = MagicMock()
        mock_client.secrets.kv.v2.read_secret_version.side_effect = RuntimeError("Vault error")
        p = VaultKeyProvider(
            vault_addr="http://vault:8200",
            secret_path="secret/path",
            client=mock_client,
        )
        with pytest.raises(EncryptionKeyMissing, match="Vault"):
            p.get_key_bytes()

    def test_is_available(self):
        p = VaultKeyProvider(vault_addr="http://v", secret_path="/s")
        assert p.is_available()

    def test_is_not_available(self):
        p = VaultKeyProvider(vault_addr="", secret_path="")
        assert not p.is_available()

    def test_provider_name(self):
        p = VaultKeyProvider(vault_addr="http://v", secret_path="/s")
        assert p.provider_name == "vault"


# ---------------------------------------------------------------------------
# build_key_provider factory
# ---------------------------------------------------------------------------


class TestBuildKeyProvider:
    def test_default_is_env(self):
        with patch.dict(os.environ, {}, clear=True):
            p = build_key_provider()
            assert p.provider_name == "env"

    def test_env_explicit(self):
        p = build_key_provider(backend="env")
        assert p.provider_name == "env"

    def test_aws_kms(self):
        p = build_key_provider(backend="aws_kms")
        assert p.provider_name == "aws_kms"

    def test_gcp_kms(self):
        p = build_key_provider(backend="gcp_kms")
        assert p.provider_name == "gcp_kms"

    def test_vault(self):
        p = build_key_provider(backend="vault")
        assert p.provider_name == "vault"

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown key provider"):
            build_key_provider(backend="unknown")

    def test_env_var_selection(self):
        with patch.dict(os.environ, {"VERITAS_KEY_PROVIDER": "aws_kms"}):
            p = build_key_provider()
            assert p.provider_name == "aws_kms"


# ---------------------------------------------------------------------------
# set/get_key_provider + encrypt/decrypt integration
# ---------------------------------------------------------------------------


class TestKeyProviderIntegration:
    def test_set_and_get_provider(self):
        from veritas_os.logging import encryption as enc_mod

        original = enc_mod._active_key_provider
        try:
            custom = EnvKeyProvider()
            set_key_provider(custom)
            assert get_key_provider() is custom
        finally:
            enc_mod._active_key_provider = original

    def test_encrypt_decrypt_with_custom_provider(self):
        from veritas_os.logging import encryption as enc_mod

        original = enc_mod._active_key_provider
        try:
            key = os.urandom(32)
            mock_provider = MagicMock(spec=KeyProvider)
            mock_provider.provider_name = "mock"
            mock_provider.get_key_bytes.return_value = key
            mock_provider.is_available.return_value = True

            set_key_provider(mock_provider)

            ciphertext = encrypt("hello world")
            assert ciphertext.startswith("ENC:")

            plaintext = decrypt(ciphertext)
            assert plaintext == "hello world"
        finally:
            enc_mod._active_key_provider = original

    def test_encrypt_raises_when_no_key(self):
        from veritas_os.logging import encryption as enc_mod

        original = enc_mod._active_key_provider
        try:
            mock_provider = MagicMock(spec=KeyProvider)
            mock_provider.provider_name = "mock"
            mock_provider.get_key_bytes.return_value = None
            set_key_provider(mock_provider)

            with pytest.raises(EncryptionKeyMissing):
                encrypt("hello")
        finally:
            enc_mod._active_key_provider = original

    def test_decrypt_raises_when_no_key(self):
        from veritas_os.logging import encryption as enc_mod

        original = enc_mod._active_key_provider
        try:
            mock_provider = MagicMock(spec=KeyProvider)
            mock_provider.provider_name = "mock"
            mock_provider.get_key_bytes.return_value = None
            set_key_provider(mock_provider)

            with pytest.raises(EncryptionKeyMissing):
                decrypt("ENC:hmac-ctr:dGVzdA==")
        finally:
            enc_mod._active_key_provider = original
