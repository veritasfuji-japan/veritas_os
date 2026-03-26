"""Adversarial tests for encryption.py — cryptographic boundary hardening.

These tests verify fail-closed behaviour, error hygiene, and absence of
silent security downgrades at the encryption boundary.

Target coverage gaps (from COVERAGE_REPORT.md):
    - invalid key encoding → raises EncryptionKeyMissing (not silent None)
    - wrong key length → raises EncryptionKeyMissing (not silent None)
    - encrypt() output ALWAYS starts with ``ENC:`` (anti-plaintext-downgrade)
    - decrypt() error messages never contain key material or raw payloads
    - truncated ciphertext at various lengths
    - HMAC tag tampering detected
    - unsupported algorithm marker rejected
    - empty / missing envelope rejected
    - legacy format rejected without explicit opt-in
    - TrustLog write side rejects plaintext when encryption is enabled
"""

from __future__ import annotations

import base64
import json
import os

import pytest

from veritas_os.logging import encryption
from veritas_os.logging.encryption import (
    DecryptionError,
    EncryptionKeyMissing,
    decrypt,
    encrypt,
    generate_key,
    is_encryption_enabled,
    _HMAC_SIZE,
    _IV_SIZE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _set_valid_key(monkeypatch: pytest.MonkeyPatch, raw: bytes | None = None) -> bytes:
    key = raw or (b"K" * 32)
    monkeypatch.setenv(
        "VERITAS_ENCRYPTION_KEY",
        base64.urlsafe_b64encode(key).decode("ascii"),
    )
    return key


# ===========================================================================
# 1. Key validation — misconfigured keys must fail-closed
# ===========================================================================


class TestKeyValidation:
    """Misconfigured keys must raise EncryptionKeyMissing, never silently disable."""

    def test_invalid_base64_key_raises_on_encrypt(self, monkeypatch):
        monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", "%%%invalid%%")
        with pytest.raises(EncryptionKeyMissing, match="invalid base64"):
            encrypt("test")

    def test_invalid_base64_key_raises_on_decrypt(self, monkeypatch):
        monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", "%%%invalid%%")
        with pytest.raises(EncryptionKeyMissing, match="invalid base64"):
            decrypt("ENC:hmac-ctr:dGVzdA==")

    def test_too_short_key_raises_on_encrypt(self, monkeypatch):
        monkeypatch.setenv(
            "VERITAS_ENCRYPTION_KEY",
            base64.urlsafe_b64encode(b"short").decode("ascii"),
        )
        with pytest.raises(EncryptionKeyMissing, match="exactly 32 bytes"):
            encrypt("test")

    def test_too_long_key_raises_on_encrypt(self, monkeypatch):
        monkeypatch.setenv(
            "VERITAS_ENCRYPTION_KEY",
            base64.urlsafe_b64encode(b"X" * 64).decode("ascii"),
        )
        with pytest.raises(EncryptionKeyMissing, match="exactly 32 bytes"):
            encrypt("test")

    def test_is_encryption_enabled_false_for_invalid_key(self, monkeypatch):
        """is_encryption_enabled() returns False for invalid keys (not True)."""
        monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", "%%%invalid%%")
        assert is_encryption_enabled() is False

    def test_is_encryption_enabled_false_for_wrong_length(self, monkeypatch):
        monkeypatch.setenv(
            "VERITAS_ENCRYPTION_KEY",
            base64.urlsafe_b64encode(b"short").decode("ascii"),
        )
        assert is_encryption_enabled() is False

    def test_is_encryption_enabled_true_for_valid_key(self, monkeypatch):
        _set_valid_key(monkeypatch)
        assert is_encryption_enabled() is True

    def test_empty_string_key_treated_as_missing(self, monkeypatch):
        """Empty string should be treated as missing (not invalid)."""
        monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", "")
        assert is_encryption_enabled() is False
        with pytest.raises(EncryptionKeyMissing, match="not set"):
            encrypt("test")


# ===========================================================================
# 2. Anti-plaintext-downgrade: encrypt() ALWAYS returns ENC: prefix
# ===========================================================================


class TestAntiPlaintextDowngrade:
    """encrypt() must never return a plaintext string."""

    def test_encrypt_always_returns_enc_prefix(self, monkeypatch):
        _set_valid_key(monkeypatch)
        monkeypatch.setattr(encryption, "_USE_REAL_AES", False)
        for text in ["", "a", "hello world", "日本語", "x" * 100_000]:
            ct = encrypt(text)
            assert ct.startswith("ENC:"), f"encrypt({text!r:.20}) did not produce ENC: prefix"

    def test_encrypt_empty_string_roundtrip(self, monkeypatch):
        _set_valid_key(monkeypatch)
        monkeypatch.setattr(encryption, "_USE_REAL_AES", False)
        ct = encrypt("")
        assert ct.startswith("ENC:")
        assert decrypt(ct) == ""

    def test_encrypt_output_contains_algorithm_marker(self, monkeypatch):
        _set_valid_key(monkeypatch)
        monkeypatch.setattr(encryption, "_USE_REAL_AES", False)
        ct = encrypt("test")
        assert ct.startswith("ENC:hmac-ctr:")

    def test_encrypt_never_returns_raw_plaintext(self, monkeypatch):
        """Even for edge-case inputs, encrypt() must not return the input unchanged."""
        _set_valid_key(monkeypatch)
        monkeypatch.setattr(encryption, "_USE_REAL_AES", False)
        for text in ["ENC:", "ENC:hmac-ctr:", "null", "{}", "[]"]:
            ct = encrypt(text)
            assert ct != text


# ===========================================================================
# 3. Error hygiene — no key/payload leakage in exceptions
# ===========================================================================


class TestErrorHygiene:
    """Exception messages must not contain key material, raw payloads, or secrets."""

    def test_encrypt_missing_key_error_no_plaintext_leak(self, monkeypatch):
        monkeypatch.delenv("VERITAS_ENCRYPTION_KEY", raising=False)
        try:
            encrypt("SENSITIVE_PAYLOAD_12345")
        except EncryptionKeyMissing as exc:
            msg = str(exc)
            assert "SENSITIVE_PAYLOAD_12345" not in msg

    def test_encrypt_invalid_key_error_no_key_leak(self, monkeypatch):
        monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", "my-secret-key-value")
        try:
            encrypt("test")
        except EncryptionKeyMissing as exc:
            msg = str(exc)
            assert "my-secret-key-value" not in msg

    def test_decrypt_error_no_ciphertext_leak(self, monkeypatch):
        _set_valid_key(monkeypatch)
        payload = base64.urlsafe_b64encode(b"x" * 10).decode("ascii")
        try:
            decrypt(f"ENC:hmac-ctr:{payload}")
        except DecryptionError as exc:
            msg = str(exc)
            assert payload not in msg

    def test_decrypt_wrong_key_error_no_plaintext_leak(self, monkeypatch):
        _set_valid_key(monkeypatch, raw=b"A" * 32)
        monkeypatch.setattr(encryption, "_USE_REAL_AES", False)
        ct = encrypt("CONFIDENTIAL")
        _set_valid_key(monkeypatch, raw=b"B" * 32)
        try:
            decrypt(ct)
        except DecryptionError as exc:
            msg = str(exc)
            assert "CONFIDENTIAL" not in msg


# ===========================================================================
# 4. Envelope parsing — malformed envelopes must be rejected
# ===========================================================================


class TestEnvelopeParsing:
    """Malformed ENC: envelopes must be rejected with DecryptionError."""

    def test_enc_prefix_only(self, monkeypatch):
        _set_valid_key(monkeypatch)
        with pytest.raises(DecryptionError, match="missing encrypted envelope"):
            decrypt("ENC:")

    def test_unsupported_algorithm_marker(self, monkeypatch):
        _set_valid_key(monkeypatch)
        with pytest.raises(DecryptionError, match="unsupported encryption algorithm"):
            decrypt("ENC:chacha20:dGVzdA==")

    def test_missing_payload_after_algorithm(self, monkeypatch):
        _set_valid_key(monkeypatch)
        with pytest.raises(DecryptionError, match="missing encrypted payload"):
            decrypt("ENC:hmac-ctr:")

    def test_missing_payload_after_aesgcm(self, monkeypatch):
        _set_valid_key(monkeypatch)
        with pytest.raises(DecryptionError, match="missing encrypted payload"):
            decrypt("ENC:aesgcm:")

    def test_legacy_format_rejected_by_default(self, monkeypatch):
        _set_valid_key(monkeypatch)
        monkeypatch.delenv("VERITAS_ENCRYPTION_LEGACY_DECRYPT", raising=False)
        with pytest.raises(DecryptionError, match="legacy encrypted envelope"):
            decrypt("ENC:Zm9v")

    def test_legacy_format_accepted_with_opt_in(self, monkeypatch):
        _set_valid_key(monkeypatch, raw=b"L" * 32)
        monkeypatch.setattr(encryption, "_USE_REAL_AES", False)
        ct = encrypt("legacy-test")
        legacy = ct.replace("ENC:hmac-ctr:", "ENC:")
        monkeypatch.setenv("VERITAS_ENCRYPTION_LEGACY_DECRYPT", "1")
        assert decrypt(legacy) == "legacy-test"

    def test_legacy_opt_in_values(self, monkeypatch):
        """Only explicit opt-in values enable legacy decrypt."""
        _set_valid_key(monkeypatch)
        for value in ["0", "false", "no", "off", ""]:
            monkeypatch.setenv("VERITAS_ENCRYPTION_LEGACY_DECRYPT", value)
            with pytest.raises(DecryptionError, match="legacy"):
                decrypt("ENC:Zm9v")


# ===========================================================================
# 5. Truncated / corrupted ciphertext
# ===========================================================================


class TestTruncatedAndCorruptedCiphertext:
    """Truncated or corrupted ciphertext must be rejected, not silently accepted."""

    def test_ciphertext_below_minimum_size(self, monkeypatch):
        """Ciphertext shorter than HMAC + IV must be rejected."""
        _set_valid_key(monkeypatch)
        for size in [0, 1, 10, _HMAC_SIZE, _HMAC_SIZE + _IV_SIZE - 1]:
            short = base64.urlsafe_b64encode(os.urandom(max(1, size))).decode("ascii")
            with pytest.raises(DecryptionError):
                decrypt(f"ENC:hmac-ctr:{short}")

    def test_valid_size_but_wrong_hmac(self, monkeypatch):
        """Ciphertext with correct size but wrong HMAC must be rejected."""
        _set_valid_key(monkeypatch)
        fake = os.urandom(_HMAC_SIZE + _IV_SIZE + 16)
        payload = base64.urlsafe_b64encode(fake).decode("ascii")
        with pytest.raises(DecryptionError, match="HMAC verification failed"):
            decrypt(f"ENC:hmac-ctr:{payload}")

    def test_hmac_tag_bit_flip(self, monkeypatch):
        """Single bit flip in HMAC tag must be detected."""
        _set_valid_key(monkeypatch, raw=b"T" * 32)
        monkeypatch.setattr(encryption, "_USE_REAL_AES", False)
        ct = encrypt("integrity-test")
        prefix, b64 = ct.rsplit(":", 1)
        raw = base64.urlsafe_b64decode(b64)
        # Flip one bit in the HMAC tag (first 32 bytes)
        tampered = bytes([raw[0] ^ 0x01]) + raw[1:]
        tampered_b64 = base64.urlsafe_b64encode(tampered).decode("ascii")
        with pytest.raises(DecryptionError):
            decrypt(f"{prefix}:{tampered_b64}")

    def test_iv_bit_flip(self, monkeypatch):
        """Single bit flip in IV must be detected (HMAC covers IV)."""
        _set_valid_key(monkeypatch, raw=b"U" * 32)
        monkeypatch.setattr(encryption, "_USE_REAL_AES", False)
        ct = encrypt("iv-test")
        prefix, b64 = ct.rsplit(":", 1)
        raw = base64.urlsafe_b64decode(b64)
        # Flip one bit in the IV (bytes 32..47)
        iv_offset = _HMAC_SIZE
        tampered = raw[:iv_offset] + bytes([raw[iv_offset] ^ 0x01]) + raw[iv_offset + 1:]
        tampered_b64 = base64.urlsafe_b64encode(tampered).decode("ascii")
        with pytest.raises(DecryptionError):
            decrypt(f"{prefix}:{tampered_b64}")

    def test_ciphertext_body_bit_flip(self, monkeypatch):
        """Single bit flip in ciphertext body must be detected (HMAC covers body)."""
        _set_valid_key(monkeypatch, raw=b"V" * 32)
        monkeypatch.setattr(encryption, "_USE_REAL_AES", False)
        ct = encrypt("body-test")
        prefix, b64 = ct.rsplit(":", 1)
        raw = base64.urlsafe_b64decode(b64)
        # Flip one bit in the ciphertext body (after HMAC+IV)
        body_offset = _HMAC_SIZE + _IV_SIZE
        tampered = raw[:body_offset] + bytes([raw[body_offset] ^ 0x01]) + raw[body_offset + 1:]
        tampered_b64 = base64.urlsafe_b64encode(tampered).decode("ascii")
        with pytest.raises(DecryptionError):
            decrypt(f"{prefix}:{tampered_b64}")

    def test_truncated_after_encoding(self, monkeypatch):
        """Ciphertext truncated after base64 encoding must be rejected."""
        _set_valid_key(monkeypatch, raw=b"W" * 32)
        monkeypatch.setattr(encryption, "_USE_REAL_AES", False)
        ct = encrypt("truncation-target")
        # Truncate the base64 portion to various lengths
        prefix, b64 = ct.rsplit(":", 1)
        for length in [1, 10, len(b64) // 2]:
            truncated = f"{prefix}:{b64[:length]}"
            with pytest.raises(DecryptionError):
                decrypt(truncated)

    def test_completely_random_payload(self, monkeypatch):
        _set_valid_key(monkeypatch)
        random_b64 = base64.urlsafe_b64encode(os.urandom(200)).decode("ascii")
        with pytest.raises(DecryptionError):
            decrypt(f"ENC:hmac-ctr:{random_b64}")

    def test_malformed_base64_payload(self, monkeypatch):
        _set_valid_key(monkeypatch)
        with pytest.raises(DecryptionError, match="invalid base64"):
            decrypt("ENC:hmac-ctr:not!valid!base64")

    def test_non_ascii_in_payload(self, monkeypatch):
        _set_valid_key(monkeypatch)
        with pytest.raises(DecryptionError):
            decrypt("ENC:hmac-ctr:日本語ペイロード")


# ===========================================================================
# 6. Wrong key decryption
# ===========================================================================


class TestWrongKeyDecryption:
    """Decryption with wrong key must fail-closed, never return garbage."""

    def test_wrong_key_hmac_ctr(self, monkeypatch):
        _set_valid_key(monkeypatch, raw=b"A" * 32)
        monkeypatch.setattr(encryption, "_USE_REAL_AES", False)
        ct = encrypt("secret-data")
        _set_valid_key(monkeypatch, raw=b"B" * 32)
        with pytest.raises(DecryptionError):
            decrypt(ct)

    def test_wrong_key_similar_keys(self, monkeypatch):
        """Keys differing by a single byte must still fail."""
        key1 = b"A" * 31 + b"X"
        key2 = b"A" * 31 + b"Y"
        _set_valid_key(monkeypatch, raw=key1)
        monkeypatch.setattr(encryption, "_USE_REAL_AES", False)
        ct = encrypt("one-byte-diff")
        _set_valid_key(monkeypatch, raw=key2)
        with pytest.raises(DecryptionError):
            decrypt(ct)


# ===========================================================================
# 7. Unicode and encoding edge cases
# ===========================================================================


class TestUnicodeEdgeCases:
    """Unicode edge cases must be handled correctly in encrypt/decrypt."""

    def test_empty_string_roundtrip(self, monkeypatch):
        _set_valid_key(monkeypatch)
        monkeypatch.setattr(encryption, "_USE_REAL_AES", False)
        assert decrypt(encrypt("")) == ""

    def test_null_byte_string(self, monkeypatch):
        _set_valid_key(monkeypatch)
        monkeypatch.setattr(encryption, "_USE_REAL_AES", False)
        text = "before\x00after"
        assert decrypt(encrypt(text)) == text

    def test_emoji_roundtrip(self, monkeypatch):
        _set_valid_key(monkeypatch)
        monkeypatch.setattr(encryption, "_USE_REAL_AES", False)
        text = "🔐🛡️🔑"
        assert decrypt(encrypt(text)) == text

    def test_multibyte_japanese(self, monkeypatch):
        _set_valid_key(monkeypatch)
        monkeypatch.setattr(encryption, "_USE_REAL_AES", False)
        text = "暗号化のテスト"
        assert decrypt(encrypt(text)) == text

    def test_large_unicode_payload(self, monkeypatch):
        _set_valid_key(monkeypatch)
        monkeypatch.setattr(encryption, "_USE_REAL_AES", False)
        text = "あ" * 50_000
        assert decrypt(encrypt(text)) == text


# ===========================================================================
# 8. Type safety
# ===========================================================================


class TestTypeSafety:
    """encrypt() must reject non-string inputs cleanly."""

    def test_encrypt_rejects_bytes(self, monkeypatch):
        _set_valid_key(monkeypatch)
        with pytest.raises(TypeError, match="str"):
            encrypt(b"bytes-input")  # type: ignore[arg-type]

    def test_encrypt_rejects_int(self, monkeypatch):
        _set_valid_key(monkeypatch)
        with pytest.raises(TypeError, match="str"):
            encrypt(12345)  # type: ignore[arg-type]

    def test_encrypt_rejects_none(self, monkeypatch):
        _set_valid_key(monkeypatch)
        with pytest.raises(TypeError, match="str"):
            encrypt(None)  # type: ignore[arg-type]

    def test_encrypt_rejects_dict(self, monkeypatch):
        _set_valid_key(monkeypatch)
        with pytest.raises(TypeError, match="str"):
            encrypt({"key": "value"})  # type: ignore[arg-type]


# ===========================================================================
# 9. TrustLog integration — fail-closed enforcement
# ===========================================================================


class TestTrustLogIntegration:
    """TrustLog must never silently write plaintext."""

    def test_append_trust_log_blocks_plaintext_write(self, monkeypatch, tmp_path):
        """If _encrypt_line somehow returns plaintext, the write is blocked."""
        from veritas_os.logging import trust_log

        _set_valid_key(monkeypatch, raw=b"M" * 32)
        monkeypatch.setattr(trust_log, "LOG_DIR", tmp_path)
        monkeypatch.setattr(trust_log, "LOG_JSON", tmp_path / "trust_log.json")
        monkeypatch.setattr(trust_log, "LOG_JSONL", tmp_path / "trust_log.jsonl")
        monkeypatch.setattr(trust_log, "_get_last_hash_unlocked", lambda: None)
        monkeypatch.setattr(
            trust_log, "open_trust_log_for_append",
            lambda: (tmp_path / "trust_log.jsonl").open("a", encoding="utf-8"),
        )

        # Simulate broken encrypt that returns plaintext
        monkeypatch.setattr(trust_log, "_encrypt_line", lambda x: x)

        with pytest.raises(EncryptionKeyMissing, match="Plaintext write blocked"):
            trust_log.append_trust_log({"request_id": "anti-downgrade"})

        # Verify nothing was written
        jsonl = tmp_path / "trust_log.jsonl"
        if jsonl.exists():
            assert jsonl.read_text().strip() == ""

    def test_append_trust_log_raises_without_key(self, monkeypatch, tmp_path):
        from veritas_os.logging import trust_log

        monkeypatch.delenv("VERITAS_ENCRYPTION_KEY", raising=False)
        monkeypatch.setattr(trust_log, "LOG_DIR", tmp_path)
        monkeypatch.setattr(trust_log, "LOG_JSON", tmp_path / "trust_log.json")
        monkeypatch.setattr(trust_log, "LOG_JSONL", tmp_path / "trust_log.jsonl")
        monkeypatch.setattr(
            trust_log, "open_trust_log_for_append",
            lambda: (tmp_path / "trust_log.jsonl").open("a", encoding="utf-8"),
        )

        with pytest.raises(EncryptionKeyMissing):
            trust_log.append_trust_log({"request_id": "no-key"})

    def test_append_trust_log_raises_with_invalid_key(self, monkeypatch, tmp_path):
        """Invalid key must raise, not silently disable encryption."""
        from veritas_os.logging import trust_log

        monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", "%%%invalid%%")
        monkeypatch.setattr(trust_log, "LOG_DIR", tmp_path)
        monkeypatch.setattr(trust_log, "LOG_JSON", tmp_path / "trust_log.json")
        monkeypatch.setattr(trust_log, "LOG_JSONL", tmp_path / "trust_log.jsonl")
        monkeypatch.setattr(
            trust_log, "open_trust_log_for_append",
            lambda: (tmp_path / "trust_log.jsonl").open("a", encoding="utf-8"),
        )

        with pytest.raises(EncryptionKeyMissing, match="invalid base64"):
            trust_log.append_trust_log({"request_id": "bad-key"})


# ===========================================================================
# 10. generate_key() output is valid
# ===========================================================================


class TestGenerateKey:
    """generate_key() must produce keys that are usable."""

    def test_generated_key_enables_encryption(self, monkeypatch):
        key = generate_key()
        monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", key)
        assert is_encryption_enabled() is True

    def test_generated_key_roundtrip(self, monkeypatch):
        key = generate_key()
        monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", key)
        monkeypatch.setattr(encryption, "_USE_REAL_AES", False)
        ct = encrypt("generated-key-test")
        assert decrypt(ct) == "generated-key-test"

    def test_generated_keys_are_unique(self):
        keys = {generate_key() for _ in range(10)}
        assert len(keys) == 10


# ===========================================================================
# 11. get_encryption_status() consistency
# ===========================================================================


class TestEncryptionStatus:
    """get_encryption_status() must report accurately."""

    def test_status_with_valid_key(self, monkeypatch):
        _set_valid_key(monkeypatch)
        status = encryption.get_encryption_status()
        assert status["encryption_enabled"] is True
        assert status["key_configured"] is True

    def test_status_without_key(self, monkeypatch):
        monkeypatch.delenv("VERITAS_ENCRYPTION_KEY", raising=False)
        status = encryption.get_encryption_status()
        assert status["encryption_enabled"] is False
        assert status["key_configured"] is False

    def test_status_with_invalid_key(self, monkeypatch):
        """Invalid key should report as not enabled (not crash)."""
        monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", "%%%invalid%%")
        status = encryption.get_encryption_status()
        assert status["encryption_enabled"] is False
