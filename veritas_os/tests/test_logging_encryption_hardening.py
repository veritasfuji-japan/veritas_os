from __future__ import annotations

import base64

import pytest

from veritas_os.logging import encryption


def _set_valid_key(monkeypatch: pytest.MonkeyPatch, raw: bytes | None = None) -> bytes:
    key = raw or (b"K" * 32)
    monkeypatch.setenv(
        "VERITAS_ENCRYPTION_KEY",
        base64.urlsafe_b64encode(key).decode("ascii"),
    )
    return key


class TestEncryptionKeyGuards:
    def test_is_encryption_disabled_for_invalid_base64_key(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", "%%%invalid%%")

        assert encryption.is_encryption_enabled() is False

    def test_is_encryption_disabled_for_wrong_key_length(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv(
            "VERITAS_ENCRYPTION_KEY",
            base64.urlsafe_b64encode(b"short-key").decode("ascii"),
        )

        assert encryption.is_encryption_enabled() is False

    def test_encrypt_raises_when_key_missing(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("VERITAS_ENCRYPTION_KEY", raising=False)

        with pytest.raises(encryption.EncryptionKeyMissing):
            encryption.encrypt("sensitive")

    def test_decrypt_raises_when_key_missing_for_encrypted_input(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("VERITAS_ENCRYPTION_KEY", raising=False)

        with pytest.raises(encryption.EncryptionKeyMissing):
            encryption.decrypt("ENC:hmac-ctr:Zm9v")


class TestEncryptDecryptFlow:
    def test_encrypt_decrypt_roundtrip_hmac_ctr(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_valid_key(monkeypatch)
        monkeypatch.setattr(encryption, "_USE_REAL_AES", False)

        ciphertext = encryption.encrypt("機密ログ")

        assert ciphertext.startswith("ENC:hmac-ctr:")
        assert encryption.decrypt(ciphertext) == "機密ログ"

    def test_plaintext_passthrough_when_prefix_mismatch(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_valid_key(monkeypatch)

        assert encryption.decrypt("NOT_ENC:payload") == "NOT_ENC:payload"

    def test_malformed_encrypted_input_fails_closed(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_valid_key(monkeypatch)

        with pytest.raises(encryption.DecryptionError):
            encryption.decrypt("ENC:hmac-ctr:@@@")

    def test_corrupted_ciphertext_fails_closed(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_valid_key(monkeypatch, raw=b"A" * 32)
        monkeypatch.setattr(encryption, "_USE_REAL_AES", False)

        ciphertext = encryption.encrypt("integrity")
        corrupted = ciphertext[:-1] + ("A" if ciphertext[-1] != "A" else "B")

        with pytest.raises(encryption.DecryptionError):
            encryption.decrypt(corrupted)

    def test_wrong_key_fails_closed(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_valid_key(monkeypatch, raw=b"A" * 32)
        monkeypatch.setattr(encryption, "_USE_REAL_AES", False)
        ciphertext = encryption.encrypt("locked")

        _set_valid_key(monkeypatch, raw=b"B" * 32)
        with pytest.raises(encryption.DecryptionError):
            encryption.decrypt(ciphertext)


class TestFallbackAndExceptionPath:
    def test_unknown_algorithm_token_uses_legacy_dispatch_and_fails_closed(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_valid_key(monkeypatch)
        monkeypatch.setattr(encryption, "_USE_REAL_AES", False)

        with pytest.raises(encryption.DecryptionError):
            encryption.decrypt("ENC:unknown-format")

    def test_exception_from_legacy_backend_is_wrapped(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_valid_key(monkeypatch)
        monkeypatch.setattr(encryption, "_USE_REAL_AES", False)

        def _raise_value_error(token: str, key: bytes) -> str:  # noqa: ARG001
            raise ValueError("boom")

        monkeypatch.setattr(encryption, "_decrypt_hmac_ctr", _raise_value_error)

        with pytest.raises(encryption.DecryptionError, match="malformed ciphertext"):
            encryption.decrypt("ENC:anything")
