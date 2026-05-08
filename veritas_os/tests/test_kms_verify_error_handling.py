"""Regression tests for KMS verify error handling boundaries."""

import base64

import pytest
from cryptography.exceptions import InvalidSignature

from veritas_os.security import signing


class _InvalidPublicKey:
    def verify(self, signature: bytes, message: bytes) -> None:
        raise InvalidSignature


class _ValueErrorPublicKey:
    def verify(self, signature: bytes, message: bytes) -> None:
        raise ValueError("invalid key material")


class _TypeErrorPublicKey:
    def verify(self, signature: bytes, message: bytes) -> None:
        raise TypeError("wrong signature type")


class _PassingProvider:
    provider_name = "passing"

    def __init__(self) -> None:
        self.verify_called = False

    def sign(self, payload_hash: str) -> bytes:
        return b"signature"

    def verify(self, payload_hash: str, signature: bytes) -> bool:
        self.verify_called = True
        return True

    def key_id(self) -> str:
        return "id"

    def key_version(self) -> str:
        return "v1"

    def algorithm(self) -> str:
        return "eddsa_ed25519"

    def public_key_fingerprint(self) -> str:
        return "fp"


class _BrokenProvider(_PassingProvider):
    provider_name = "broken"

    def verify(self, payload_hash: str, signature: bytes) -> bool:
        raise AttributeError("provider misconfigured")


def test_gcp_kms_verify_propagates_attribute_error(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = signing.GcpKmsEd25519Provider(
        kms_key_name="projects/p/locations/l/keyRings/r/cryptoKeys/k",
        kms_client=object(),
    )

    def _broken_load_public_key() -> object:
        raise AttributeError("broken kms client")

    monkeypatch.setattr(provider, "_load_public_key", _broken_load_public_key)

    with pytest.raises(AttributeError, match="broken kms client"):
        provider.verify("a" * 64, b"signature")


def test_gcp_kms_verify_returns_false_on_invalid_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = signing.GcpKmsEd25519Provider(
        kms_key_name="projects/p/locations/l/keyRings/r/cryptoKeys/k",
        kms_client=object(),
    )
    monkeypatch.setattr(provider, "_load_public_key", lambda: _InvalidPublicKey())

    assert provider.verify("a" * 64, b"signature") is False


@pytest.mark.parametrize("public_key", [_ValueErrorPublicKey(), _TypeErrorPublicKey()])
def test_gcp_kms_verify_returns_false_for_value_and_type_errors(
    monkeypatch: pytest.MonkeyPatch,
    public_key: object,
) -> None:
    provider = signing.GcpKmsEd25519Provider(
        kms_key_name="projects/p/locations/l/keyRings/r/cryptoKeys/k",
        kms_client=object(),
    )
    monkeypatch.setattr(provider, "_load_public_key", lambda: public_key)

    assert provider.verify("a" * 64, b"signature") is False


def test_aws_kms_verify_propagates_attribute_error(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = signing.AwsKmsEd25519Provider(
        kms_key_id="arn:aws:kms:us-east-1:111122223333:key/example",
        kms_client=object(),
    )

    def _broken_load_public_key() -> object:
        raise AttributeError("broken aws kms client")

    monkeypatch.setattr(provider, "_load_public_key", _broken_load_public_key)

    with pytest.raises(AttributeError, match="broken aws kms client"):
        provider.verify("a" * 64, b"signature")


def test_kms_signer_verify_payload_signature_propagates_attribute_error() -> None:
    signer = signing.KmsEd25519Signer(_BrokenProvider())
    signature_b64 = base64.urlsafe_b64encode(b"signature").decode("ascii")

    with pytest.raises(AttributeError, match="provider misconfigured"):
        signer.verify_payload_signature("a" * 64, signature_b64)


def test_kms_signer_verify_payload_signature_returns_false_on_malformed_base64() -> None:
    provider = _PassingProvider()
    signer = signing.KmsEd25519Signer(provider)

    assert signer.verify_payload_signature("a" * 64, "not base64 ???") is False
    assert provider.verify_called is False
