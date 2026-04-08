"""Production-like encryption key fail-closed validation.

These tests verify the secure-by-default design of VERITAS encryption:
when the encryption key is missing or misconfigured, TrustLog writes
must fail explicitly (fail-closed) rather than silently writing plaintext.

Markers:
    production — production-like validation (excluded from default CI)
"""

from __future__ import annotations

import base64
import os

import pytest


# ---------------------------------------------------------------------------
# Production-like encryption tests
# ---------------------------------------------------------------------------


@pytest.mark.production
class TestEncryptionKeyGeneration:
    """Verify key generation produces valid keys."""

    def test_generate_key_returns_base64(self):
        from veritas_os.logging.encryption import generate_key

        key = generate_key()
        assert isinstance(key, str)
        assert len(key) > 0
        # Should be valid base64
        raw = base64.urlsafe_b64decode(key)
        assert len(raw) == 32  # 256-bit key

    def test_generate_key_unique(self):
        from veritas_os.logging.encryption import generate_key

        keys = {generate_key() for _ in range(10)}
        assert len(keys) == 10, "Generated keys should be unique"


@pytest.mark.production
class TestFailClosedEncryption:
    """Verify fail-closed behaviour when key is absent or invalid."""

    def test_missing_key_raises(self, monkeypatch):
        """TrustLog append must fail when encryption key is absent."""
        monkeypatch.delenv("VERITAS_ENCRYPTION_KEY", raising=False)

        from veritas_os.logging.encryption import _get_key_bytes

        # _get_key_bytes returns None when key is not set (fail-closed
        # is enforced by the caller — encrypt() raises EncryptionKeyMissing)
        result = _get_key_bytes()
        assert result is None, "Missing key should return None"

    def test_missing_key_encrypt_raises(self, monkeypatch):
        """encrypt() must raise when key is absent."""
        monkeypatch.delenv("VERITAS_ENCRYPTION_KEY", raising=False)

        from veritas_os.logging.encryption import (
            EncryptionKeyMissing,
            encrypt,
        )

        with pytest.raises(EncryptionKeyMissing):
            encrypt("some data")

    def test_invalid_base64_key_raises(self, monkeypatch):
        """Invalid base64 key must raise, not silently degrade."""
        monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", "not-valid-base64!!!")

        import veritas_os.logging.encryption as enc

        monkeypatch.setattr(enc, "_KEY_CACHE", None, raising=False)

        from veritas_os.logging.encryption import (
            EncryptionKeyMissing,
            _get_key_bytes,
        )

        with pytest.raises(EncryptionKeyMissing):
            _get_key_bytes()

    def test_wrong_length_key_raises(self, monkeypatch):
        """Key with wrong byte length must raise."""
        # Generate a 16-byte key (too short for 256-bit)
        short_key = base64.urlsafe_b64encode(os.urandom(16)).decode()
        monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", short_key)

        import veritas_os.logging.encryption as enc

        monkeypatch.setattr(enc, "_KEY_CACHE", None, raising=False)

        from veritas_os.logging.encryption import (
            EncryptionKeyMissing,
            _get_key_bytes,
        )

        with pytest.raises(EncryptionKeyMissing):
            _get_key_bytes()


@pytest.mark.production
class TestEncryptDecryptRoundTrip:
    """Verify encrypt → decrypt round-trip with valid key."""

    def test_round_trip(self, monkeypatch):
        from veritas_os.logging.encryption import (
            decrypt,
            encrypt,
            generate_key,
        )

        key = generate_key()
        monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", key)

        import veritas_os.logging.encryption as enc

        monkeypatch.setattr(enc, "_KEY_CACHE", None, raising=False)

        plaintext = "sensitive decision data for audit"
        ciphertext = encrypt(plaintext)
        assert ciphertext != plaintext
        recovered = decrypt(ciphertext)
        assert recovered == plaintext

    def test_different_keys_cannot_decrypt(self, monkeypatch):
        from veritas_os.logging.encryption import (
            encrypt,
            generate_key,
        )

        key1 = generate_key()
        monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", key1)

        import veritas_os.logging.encryption as enc

        monkeypatch.setattr(enc, "_KEY_CACHE", None, raising=False)

        ciphertext = encrypt("secret")

        # Switch to a different key
        key2 = generate_key()
        monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", key2)
        monkeypatch.setattr(enc, "_KEY_CACHE", None, raising=False)

        from veritas_os.logging.encryption import decrypt

        # Decryption with wrong key must fail or produce different output
        try:
            result = decrypt(ciphertext)
            # If it doesn't raise, result MUST differ from original plaintext
            assert result != "secret", "Decryption with wrong key must not produce original plaintext"
        except (ValueError, RuntimeError):
            pass  # Expected — wrong key should fail

    def test_encrypt_empty_string(self, monkeypatch):
        from veritas_os.logging.encryption import (
            decrypt,
            encrypt,
            generate_key,
        )

        key = generate_key()
        monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", key)

        import veritas_os.logging.encryption as enc

        monkeypatch.setattr(enc, "_KEY_CACHE", None, raising=False)

        ciphertext = encrypt("")
        assert decrypt(ciphertext) == ""


@pytest.mark.production
class TestEncryptionEnabled:
    """Verify is_encryption_enabled() reports correct state."""

    def test_enabled_with_valid_key(self, monkeypatch):
        from veritas_os.logging.encryption import (
            generate_key,
            is_encryption_enabled,
        )

        monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", generate_key())

        import veritas_os.logging.encryption as enc

        monkeypatch.setattr(enc, "_KEY_CACHE", None, raising=False)

        assert is_encryption_enabled() is True

    def test_disabled_without_key(self, monkeypatch):
        monkeypatch.delenv("VERITAS_ENCRYPTION_KEY", raising=False)

        import veritas_os.logging.encryption as enc

        monkeypatch.setattr(enc, "_KEY_CACHE", None, raising=False)

        from veritas_os.logging.encryption import is_encryption_enabled

        assert is_encryption_enabled() is False
