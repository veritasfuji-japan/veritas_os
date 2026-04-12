"""Tests for GcpKmsEd25519Signer and VaultTransitSigner in security/signing.py."""

from __future__ import annotations

import base64
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from veritas_os.security.signing import (
    GcpKmsEd25519Signer,
    VaultTransitSigner,
    build_trustlog_signer,
    FileEd25519Signer,
    AwsKmsEd25519Signer,
)


# ---------------------------------------------------------------------------
# GcpKmsEd25519Signer
# ---------------------------------------------------------------------------


class TestGcpKmsEd25519Signer:
    """Tests for Google Cloud KMS Ed25519 signer."""

    def test_requires_resource_name(self):
        with pytest.raises(ValueError, match="VERITAS_GCP_KMS_SIGN_RESOURCE"):
            GcpKmsEd25519Signer(resource_name="")

    def test_signer_type(self):
        s = GcpKmsEd25519Signer(
            resource_name="projects/p/locations/l/keyRings/r/cryptoKeys/k/cryptoKeyVersions/1",
            kms_client=MagicMock(),
        )
        assert s.signer_type == "gcp_kms"

    def test_signer_key_id(self):
        resource = "projects/p/locations/l/keyRings/r/cryptoKeys/k/cryptoKeyVersions/1"
        s = GcpKmsEd25519Signer(resource_name=resource, kms_client=MagicMock())
        assert s.signer_key_id() == resource

    def test_signer_key_version_parsed(self):
        resource = "projects/p/locations/l/keyRings/r/cryptoKeys/k/cryptoKeyVersions/3"
        s = GcpKmsEd25519Signer(resource_name=resource, kms_client=MagicMock())
        assert s.signer_key_version() == "3"

    def test_signer_key_version_unknown(self):
        s = GcpKmsEd25519Signer(resource_name="some/short/path", kms_client=MagicMock())
        assert s.signer_key_version() == "unknown"

    def test_signature_algorithm(self):
        s = GcpKmsEd25519Signer(resource_name="res/name", kms_client=MagicMock())
        assert s.signature_algorithm() == "eddsa_ed25519"

    def test_sign_payload_hash(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.signature = b"fake-signature-bytes"
        mock_client.asymmetric_sign.return_value = mock_response

        s = GcpKmsEd25519Signer(resource_name="res/name", kms_client=mock_client)
        result = s.sign_payload_hash("abc123hash")

        assert result == base64.urlsafe_b64encode(b"fake-signature-bytes").decode("ascii")
        mock_client.asymmetric_sign.assert_called_once()

    def test_verify_payload_signature_calls_public_key(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives import serialization

        # Generate a real key pair for verification test
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key()

        pem = public_key.public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        payload_hash = "test-hash-value"
        signature = private_key.sign(payload_hash.encode("utf-8"))
        sig_b64 = base64.urlsafe_b64encode(signature).decode("ascii")

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.pem = pem.decode("utf-8")
        mock_client.get_public_key.return_value = mock_response

        s = GcpKmsEd25519Signer(resource_name="res/name", kms_client=mock_client)
        assert s.verify_payload_signature(payload_hash, sig_b64) is True

    def test_verify_payload_signature_invalid(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives import serialization

        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        pem = public_key.public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.pem = pem.decode("utf-8")
        mock_client.get_public_key.return_value = mock_response

        s = GcpKmsEd25519Signer(resource_name="res/name", kms_client=mock_client)
        assert s.verify_payload_signature("hash", "aW52YWxpZA==") is False

    def test_public_key_fingerprint_returns_none_on_error(self):
        mock_client = MagicMock()
        mock_client.get_public_key.side_effect = RuntimeError("unavailable")
        s = GcpKmsEd25519Signer(resource_name="res/name", kms_client=mock_client)
        assert s.public_key_fingerprint() is None


# ---------------------------------------------------------------------------
# VaultTransitSigner
# ---------------------------------------------------------------------------


class TestVaultTransitSigner:
    """Tests for HashiCorp Vault Transit signer."""

    def test_signer_type(self):
        s = VaultTransitSigner(
            vault_addr="http://vault:8200",
            vault_token="s.token",
            key_name="my-key",
            client=MagicMock(),
        )
        assert s.signer_type == "vault"

    def test_signer_key_id(self):
        s = VaultTransitSigner(
            vault_addr="http://vault:8200",
            key_name="veritas-key",
            client=MagicMock(),
        )
        assert s.signer_key_id() == "vault-transit:veritas-key"

    def test_signer_key_version_explicit(self):
        s = VaultTransitSigner(
            vault_addr="http://vault:8200",
            key_name="k",
            key_version="3",
            client=MagicMock(),
        )
        assert s.signer_key_version() == "3"

    def test_signer_key_version_latest(self):
        s = VaultTransitSigner(
            vault_addr="http://vault:8200",
            key_name="k",
            client=MagicMock(),
        )
        assert s.signer_key_version() == "latest"

    def test_signature_algorithm(self):
        s = VaultTransitSigner(vault_addr="http://v", key_name="k", client=MagicMock())
        assert s.signature_algorithm() == "ed25519"

    def test_sign_payload_hash(self):
        mock_client = MagicMock()
        sig_b64 = base64.b64encode(b"sig-data").decode()
        mock_client.secrets.transit.sign_data.return_value = {
            "data": {"signature": f"vault:v1:{sig_b64}"}
        }
        s = VaultTransitSigner(
            vault_addr="http://v",
            key_name="k",
            client=mock_client,
        )
        result = s.sign_payload_hash("hash-input")
        assert result == sig_b64
        mock_client.secrets.transit.sign_data.assert_called_once()

    def test_verify_payload_signature(self):
        mock_client = MagicMock()
        mock_client.secrets.transit.verify_signed_data.return_value = {
            "data": {"valid": True}
        }
        s = VaultTransitSigner(
            vault_addr="http://v",
            key_name="k",
            client=mock_client,
        )
        assert s.verify_payload_signature("hash", "c2ln") is True

    def test_verify_payload_signature_invalid(self):
        mock_client = MagicMock()
        mock_client.secrets.transit.verify_signed_data.return_value = {
            "data": {"valid": False}
        }
        s = VaultTransitSigner(
            vault_addr="http://v",
            key_name="k",
            client=mock_client,
        )
        assert s.verify_payload_signature("hash", "c2ln") is False

    def test_verify_payload_signature_error(self):
        mock_client = MagicMock()
        mock_client.secrets.transit.verify_signed_data.side_effect = RuntimeError("down")
        s = VaultTransitSigner(
            vault_addr="http://v",
            key_name="k",
            client=mock_client,
        )
        assert s.verify_payload_signature("hash", "c2ln") is False

    def test_public_key_fingerprint_none(self):
        s = VaultTransitSigner(vault_addr="http://v", key_name="k", client=MagicMock())
        assert s.public_key_fingerprint() is None


# ---------------------------------------------------------------------------
# build_trustlog_signer factory — extended backends
# ---------------------------------------------------------------------------


class TestBuildTrustlogSignerExtended:
    """Test build_trustlog_signer with new backend names."""

    def test_file_backend(self, tmp_path):
        s = build_trustlog_signer(
            private_key_path=tmp_path / "priv",
            public_key_path=tmp_path / "pub",
            backend="file",
        )
        assert isinstance(s, FileEd25519Signer)

    def test_aws_kms_backend(self, tmp_path):
        s = build_trustlog_signer(
            private_key_path=tmp_path / "priv",
            public_key_path=tmp_path / "pub",
            backend="aws_kms",
            kms_key_id="alias/test",
        )
        assert isinstance(s, AwsKmsEd25519Signer)

    def test_gcp_kms_backend(self, tmp_path):
        with patch.dict(os.environ, {"VERITAS_GCP_KMS_SIGN_RESOURCE": "projects/p/locations/l/keyRings/r/cryptoKeys/k/cryptoKeyVersions/1"}):
            s = build_trustlog_signer(
                private_key_path=tmp_path / "priv",
                public_key_path=tmp_path / "pub",
                backend="gcp_kms",
            )
            assert isinstance(s, GcpKmsEd25519Signer)

    def test_vault_backend(self, tmp_path):
        s = build_trustlog_signer(
            private_key_path=tmp_path / "priv",
            public_key_path=tmp_path / "pub",
            backend="vault",
        )
        assert isinstance(s, VaultTransitSigner)

    def test_unknown_backend_raises(self, tmp_path):
        with pytest.raises(ValueError, match="Unsupported signer backend"):
            build_trustlog_signer(
                private_key_path=tmp_path / "priv",
                public_key_path=tmp_path / "pub",
                backend="unknown_backend",
            )

    def test_env_var_selection(self, tmp_path):
        with patch.dict(os.environ, {
            "VERITAS_TRUSTLOG_SIGNER_BACKEND": "vault",
        }):
            s = build_trustlog_signer(
                private_key_path=tmp_path / "priv",
                public_key_path=tmp_path / "pub",
            )
            assert isinstance(s, VaultTransitSigner)
