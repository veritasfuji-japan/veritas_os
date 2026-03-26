"""Adversarial tests for TrustLog encryption / signing / WORM / transparency.

Target: audit-grade failure resilience with fail-closed guarantees.
Covers: missing key, wrong key, corrupted ciphertext, truncated line,
        signature invalid, previous_hash mismatch, WORM mirror write failure,
        transparency anchor failure.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from veritas_os.audit import trustlog_signed
from veritas_os.audit.trustlog_signed import (
    SignedTrustLogWriteError,
    _entry_chain_hash,
    _read_all_entries,
    _read_last_entry,
    append_signed_decision,
    verify_signature,
    verify_trustlog_chain,
)
from veritas_os.logging import encryption, trust_log
from veritas_os.logging.encryption import (
    DecryptionError,
    EncryptionKeyMissing,
    decrypt,
    encrypt,
    generate_key,
    is_encryption_enabled,
)
from veritas_os.security.signing import (
    sign_payload_hash,
    store_keypair,
    verify_payload_signature,
)
from veritas_os.security.hash import sha256_of_canonical_json


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


def _stub_signing(monkeypatch):
    """Stub out signing infrastructure for unit isolation."""
    monkeypatch.setattr(trustlog_signed, "_ensure_signing_keys", lambda: None)
    monkeypatch.setattr(
        trustlog_signed, "sha256_of_canonical_json", lambda _p: "h" * 64,
    )
    monkeypatch.setattr(
        trustlog_signed, "sign_payload_hash", lambda *a, **kw: "sig",
    )
    monkeypatch.setattr(
        trustlog_signed, "public_key_fingerprint", lambda _p: "fp",
    )


# ===========================================================================
# 1. Encryption — missing key
# ===========================================================================

class TestEncryptionMissingKey:
    """Encryption must fail-closed when key is absent."""

    def test_encrypt_raises_without_key(self, monkeypatch):
        monkeypatch.delenv("VERITAS_ENCRYPTION_KEY", raising=False)
        with pytest.raises(EncryptionKeyMissing):
            encrypt("secret data")

    def test_decrypt_raises_without_key_for_encrypted_input(self, monkeypatch):
        monkeypatch.delenv("VERITAS_ENCRYPTION_KEY", raising=False)
        with pytest.raises(EncryptionKeyMissing):
            decrypt("ENC:hmac-ctr:dGVzdA==")

    def test_decrypt_raises_without_key_for_aesgcm_input(self, monkeypatch):
        monkeypatch.delenv("VERITAS_ENCRYPTION_KEY", raising=False)
        with pytest.raises(EncryptionKeyMissing):
            decrypt("ENC:aesgcm:dGVzdA==")

    def test_is_encryption_disabled_when_key_unset(self, monkeypatch):
        monkeypatch.delenv("VERITAS_ENCRYPTION_KEY", raising=False)
        assert is_encryption_enabled() is False

    def test_encrypt_type_error_for_non_string(self, monkeypatch):
        _set_valid_key(monkeypatch)
        with pytest.raises(TypeError):
            encrypt(12345)  # type: ignore[arg-type]


# ===========================================================================
# 2. Encryption — wrong key
# ===========================================================================

class TestEncryptionWrongKey:
    """Decryption with wrong key must fail-closed (not return garbage)."""

    def test_wrong_key_hmac_ctr_raises(self, monkeypatch):
        _set_valid_key(monkeypatch, raw=b"A" * 32)
        monkeypatch.setattr(encryption, "_USE_REAL_AES", False)
        ct = encrypt("locked-data")

        _set_valid_key(monkeypatch, raw=b"B" * 32)
        with pytest.raises(DecryptionError):
            decrypt(ct)

    def test_wrong_key_invalid_base64(self, monkeypatch):
        monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", "%%%not-base64%%%")
        assert is_encryption_enabled() is False

    def test_wrong_key_too_short(self, monkeypatch):
        monkeypatch.setenv(
            "VERITAS_ENCRYPTION_KEY",
            base64.urlsafe_b64encode(b"short").decode("ascii"),
        )
        assert is_encryption_enabled() is False
        with pytest.raises(EncryptionKeyMissing):
            encrypt("data")

    def test_wrong_key_too_long(self, monkeypatch):
        monkeypatch.setenv(
            "VERITAS_ENCRYPTION_KEY",
            base64.urlsafe_b64encode(b"X" * 64).decode("ascii"),
        )
        assert is_encryption_enabled() is False
        with pytest.raises(EncryptionKeyMissing):
            encrypt("data")


# ===========================================================================
# 3. Encryption — corrupted ciphertext
# ===========================================================================

class TestCorruptedCiphertext:
    """Tampered ciphertext must be detected and rejected."""

    def test_flipped_bit_in_payload(self, monkeypatch):
        _set_valid_key(monkeypatch, raw=b"C" * 32)
        monkeypatch.setattr(encryption, "_USE_REAL_AES", False)
        ct = encrypt("tamper-target")

        # Flip a character in the base64 payload
        prefix, payload = ct.rsplit(":", 1)
        corrupted_payload = payload[:-2] + ("Z" if payload[-2] != "Z" else "Q") + payload[-1]
        corrupted = f"{prefix}:{corrupted_payload}"

        with pytest.raises(DecryptionError):
            decrypt(corrupted)

    def test_completely_random_payload(self, monkeypatch):
        _set_valid_key(monkeypatch, raw=b"D" * 32)
        random_b64 = base64.urlsafe_b64encode(os.urandom(128)).decode("ascii")
        with pytest.raises(DecryptionError):
            decrypt(f"ENC:hmac-ctr:{random_b64}")

    def test_empty_payload_after_prefix(self, monkeypatch):
        _set_valid_key(monkeypatch, raw=b"E" * 32)
        with pytest.raises(DecryptionError):
            decrypt("ENC:hmac-ctr:")

    def test_truncated_payload_too_short(self, monkeypatch):
        _set_valid_key(monkeypatch, raw=b"F" * 32)
        # Just a few bytes, less than HMAC_SIZE + IV_SIZE + 1
        short_b64 = base64.urlsafe_b64encode(b"x" * 10).decode("ascii")
        with pytest.raises(DecryptionError):
            decrypt(f"ENC:hmac-ctr:{short_b64}")

    def test_mixed_old_new_format_rejected(self, monkeypatch):
        _set_valid_key(monkeypatch, raw=b"F" * 32)
        with pytest.raises(DecryptionError, match="invalid base64 payload"):
            decrypt("ENC:hmac-ctr:legacy:payload")

    def test_legacy_payload_requires_explicit_opt_in(self, monkeypatch):
        _set_valid_key(monkeypatch, raw=b"Q" * 32)
        monkeypatch.setattr(encryption, "_USE_REAL_AES", False)
        modern = encrypt("legacy-migration")
        legacy = modern.replace("ENC:hmac-ctr:", "ENC:")

        with pytest.raises(DecryptionError, match="legacy encrypted envelope not accepted"):
            decrypt(legacy)

        monkeypatch.setenv("VERITAS_ENCRYPTION_LEGACY_DECRYPT", "true")
        assert decrypt(legacy) == "legacy-migration"


# ===========================================================================
# 4. Truncated line handling
# ===========================================================================

class TestTruncatedLine:
    """Truncated/corrupt JSONL lines must not break the pipeline."""

    def test_decode_line_returns_none_for_truncated_json(self):
        result = trust_log._decode_line('{"request_id": "r1", "sha256":')
        assert result is None

    def test_decode_line_returns_none_for_empty(self):
        assert trust_log._decode_line("") is None
        assert trust_log._decode_line("   \n") is None

    def test_decode_line_returns_none_for_corrupted_encryption(self, monkeypatch):
        _set_valid_key(monkeypatch, raw=b"G" * 32)
        result = trust_log._decode_line("ENC:hmac-ctr:GARBAGE_NOT_BASE64")
        assert result is None

    def test_verify_trust_log_detects_truncated_entry(self, monkeypatch, tmp_path):
        _set_valid_key(monkeypatch, raw=b"H" * 32)
        monkeypatch.setattr(encryption, "_USE_REAL_AES", False)
        log_file = tmp_path / "trust_log.jsonl"

        # Write a truncated encrypted line — verify_trust_log should detect it
        log_file.write_text("ENC:hmac-ctr:TRUNC\n", encoding="utf-8")

        monkeypatch.setattr(trust_log, "LOG_JSONL", log_file)
        result = trust_log.verify_trust_log()
        # Truncated encrypted lines fail decryption → reported as decode error
        assert result["broken"] is True
        assert result["broken_reason"] in ("json_decode_error",)

    def test_extract_last_sha256_skips_truncated_lines(self, monkeypatch):
        _set_valid_key(monkeypatch, raw=b"I" * 32)
        monkeypatch.setattr(encryption, "_USE_REAL_AES", False)

        good_entry = json.dumps({"sha256": "a" * 64})
        enc_good = encrypt(good_entry)

        lines = ["TRUNCATED_GARBAGE", enc_good, "ANOTHER_BAD_LINE"]
        result = trust_log._extract_last_sha256_from_lines(lines)
        assert result == "a" * 64


# ===========================================================================
# 5. Signature invalid
# ===========================================================================

class TestSignatureInvalid:
    """Invalid/tampered signatures must be detected."""

    def test_verify_signature_rejects_tampered_signature(self, tmp_path):
        priv_path = tmp_path / "priv.key"
        pub_path = tmp_path / "pub.key"
        store_keypair(priv_path, pub_path)

        payload_hash = sha256_of_canonical_json({"decision": "allow"})
        sig = sign_payload_hash(payload_hash, priv_path)

        # Tamper with signature
        sig_bytes = base64.urlsafe_b64decode(sig)
        tampered = bytes([b ^ 0xFF for b in sig_bytes[:4]]) + sig_bytes[4:]
        tampered_sig = base64.urlsafe_b64encode(tampered).decode("ascii")

        assert verify_payload_signature(payload_hash, tampered_sig, pub_path) is False

    def test_verify_signature_rejects_wrong_payload(self, tmp_path):
        priv_path = tmp_path / "priv.key"
        pub_path = tmp_path / "pub.key"
        store_keypair(priv_path, pub_path)

        payload_hash = sha256_of_canonical_json({"decision": "allow"})
        sig = sign_payload_hash(payload_hash, priv_path)

        wrong_hash = sha256_of_canonical_json({"decision": "deny"})
        assert verify_payload_signature(wrong_hash, sig, pub_path) is False

    def test_verify_trustlog_chain_detects_forged_signature(self, tmp_path, monkeypatch):
        # Create real keys
        priv_path = tmp_path / "keys" / "priv.key"
        pub_path = tmp_path / "keys" / "pub.key"
        store_keypair(priv_path, pub_path)
        monkeypatch.setattr(trustlog_signed, "PUBLIC_KEY_PATH", pub_path)

        # Build a valid entry then tamper its signature
        payload = {"decision": "allow", "request_id": "sig-test"}
        payload_hash = sha256_of_canonical_json(payload)
        sig = sign_payload_hash(payload_hash, priv_path)

        # Create a completely wrong signature (valid base64 of random bytes)
        wrong_sig = base64.urlsafe_b64encode(os.urandom(64)).decode("ascii")

        entry = {
            "decision_id": "test-id",
            "timestamp": "2026-01-01T00:00:00Z",
            "previous_hash": None,
            "decision_payload": payload,
            "payload_hash": payload_hash,
            "signature": wrong_sig,
            "signature_key_fingerprint": "fp",
        }

        trustlog_path = tmp_path / "trustlog.jsonl"
        trustlog_path.write_text(json.dumps(entry) + "\n", encoding="utf-8")

        result = verify_trustlog_chain(trustlog_path)
        assert result["ok"] is False
        assert any(i["reason"] == "signature_invalid" for i in result["issues"])

    def test_verify_signature_returns_false_for_missing_fields(self, tmp_path):
        pub_path = tmp_path / "pub.key"
        # Missing key file
        assert verify_signature({"payload_hash": "h" * 64, "signature": "sig"}) is False
        # Missing required fields
        assert verify_signature({"payload_hash": "h" * 64}) is False
        assert verify_signature({}) is False


# ===========================================================================
# 6. previous_hash mismatch
# ===========================================================================

class TestPreviousHashMismatch:
    """Chain hash breaks must be detected."""

    def test_verify_trustlog_chain_detects_previous_hash_mismatch(self, tmp_path, monkeypatch):
        priv_path = tmp_path / "keys" / "priv.key"
        pub_path = tmp_path / "keys" / "pub.key"
        store_keypair(priv_path, pub_path)
        monkeypatch.setattr(trustlog_signed, "PUBLIC_KEY_PATH", pub_path)

        # Build entry 1
        payload1 = {"decision": "allow", "request_id": "chain-1"}
        payload_hash1 = sha256_of_canonical_json(payload1)
        sig1 = sign_payload_hash(payload_hash1, priv_path)
        entry1 = {
            "decision_id": "id-1",
            "timestamp": "2026-01-01T00:00:00Z",
            "previous_hash": None,
            "decision_payload": payload1,
            "payload_hash": payload_hash1,
            "signature": sig1,
            "signature_key_fingerprint": "fp",
        }

        # Build entry 2 with WRONG previous_hash
        payload2 = {"decision": "deny", "request_id": "chain-2"}
        payload_hash2 = sha256_of_canonical_json(payload2)
        sig2 = sign_payload_hash(payload_hash2, priv_path)
        entry2 = {
            "decision_id": "id-2",
            "timestamp": "2026-01-01T00:01:00Z",
            "previous_hash": "WRONG_HASH_VALUE",  # Should be hash of entry1
            "decision_payload": payload2,
            "payload_hash": payload_hash2,
            "signature": sig2,
            "signature_key_fingerprint": "fp",
        }

        trustlog_path = tmp_path / "trustlog.jsonl"
        lines = json.dumps(entry1) + "\n" + json.dumps(entry2) + "\n"
        trustlog_path.write_text(lines, encoding="utf-8")

        result = verify_trustlog_chain(trustlog_path)
        assert result["ok"] is False
        assert any(i["reason"] == "previous_hash_mismatch" for i in result["issues"])

    def test_verify_trust_log_detects_sha256_prev_mismatch(self, monkeypatch, tmp_path):
        """Main trust_log.verify_trust_log catches sha256_prev chain breaks."""
        _set_valid_key(monkeypatch, raw=b"J" * 32)
        monkeypatch.setattr(encryption, "_USE_REAL_AES", False)

        log_file = tmp_path / "trust_log.jsonl"
        monkeypatch.setattr(trust_log, "LOG_JSONL", log_file)

        # Write two entries where second has wrong sha256_prev
        entry1 = {"request_id": "r1", "sha256_prev": None, "data": "first"}
        entry1_json = trust_log._normalize_entry_for_hash(entry1)
        entry1["sha256"] = trust_log._sha256(entry1_json)
        line1 = encrypt(json.dumps(entry1))

        entry2 = {"request_id": "r2", "sha256_prev": "WRONG", "data": "second"}
        entry2_json = trust_log._normalize_entry_for_hash(entry2)
        entry2["sha256"] = trust_log._sha256("WRONG" + entry2_json)
        line2 = encrypt(json.dumps(entry2))

        log_file.write_text(line1 + "\n" + line2 + "\n", encoding="utf-8")

        result = trust_log.verify_trust_log()
        assert result["ok"] is False
        assert result["broken_reason"] == "sha256_prev_mismatch"


# ===========================================================================
# 7. WORM mirror write failure
# ===========================================================================

class TestWORMMirrorFailure:
    """WORM mirror failures must be handled according to configuration."""

    def test_worm_soft_fail_returns_error_dict(self, monkeypatch, tmp_path):
        """Default soft-fail mode: WORM error returned but not raised."""
        trustlog_path = tmp_path / "trustlog.jsonl"
        monkeypatch.setattr(trustlog_signed, "SIGNED_TRUSTLOG_JSONL", trustlog_path)
        _stub_signing(monkeypatch)

        # Configure WORM path to a read-only location
        worm_path = tmp_path / "readonly" / "worm.jsonl"
        monkeypatch.setenv("VERITAS_TRUSTLOG_WORM_MIRROR_PATH", str(worm_path))
        monkeypatch.delenv("VERITAS_TRUSTLOG_WORM_HARD_FAIL", raising=False)

        # Make WORM write fail
        original_append = trustlog_signed._append_line

        def _fail_worm(path, line):
            if str(path) == str(worm_path):
                raise OSError("WORM storage read-only")
            original_append(path, line)

        monkeypatch.setattr(trustlog_signed, "_append_line", _fail_worm)

        entry = append_signed_decision({"request_id": "worm-soft"})
        assert entry["worm_mirror"]["configured"] is True
        assert entry["worm_mirror"]["ok"] is False
        assert "error" in entry["worm_mirror"]

    def test_worm_hard_fail_raises(self, monkeypatch, tmp_path):
        """Hard-fail mode: WORM error causes SignedTrustLogWriteError."""
        trustlog_path = tmp_path / "trustlog.jsonl"
        monkeypatch.setattr(trustlog_signed, "SIGNED_TRUSTLOG_JSONL", trustlog_path)
        _stub_signing(monkeypatch)

        worm_path = tmp_path / "worm.jsonl"
        monkeypatch.setenv("VERITAS_TRUSTLOG_WORM_MIRROR_PATH", str(worm_path))
        monkeypatch.setenv("VERITAS_TRUSTLOG_WORM_HARD_FAIL", "1")

        original_append = trustlog_signed._append_line

        def _fail_worm(path, line):
            if str(path) == str(worm_path):
                raise OSError("WORM disk full")
            original_append(path, line)

        monkeypatch.setattr(trustlog_signed, "_append_line", _fail_worm)

        with pytest.raises(SignedTrustLogWriteError):
            append_signed_decision({"request_id": "worm-hard"})

    def test_worm_not_configured_returns_unconfigured(self, monkeypatch, tmp_path):
        """When WORM is not configured, entry shows unconfigured status."""
        trustlog_path = tmp_path / "trustlog.jsonl"
        monkeypatch.setattr(trustlog_signed, "SIGNED_TRUSTLOG_JSONL", trustlog_path)
        _stub_signing(monkeypatch)
        monkeypatch.delenv("VERITAS_TRUSTLOG_WORM_MIRROR_PATH", raising=False)

        entry = append_signed_decision({"request_id": "worm-none"})
        assert entry["worm_mirror"]["configured"] is False

    def test_worm_failure_is_logged(self, monkeypatch, tmp_path, caplog):
        """WORM write failure emits a warning log."""
        import logging

        trustlog_path = tmp_path / "trustlog.jsonl"
        monkeypatch.setattr(trustlog_signed, "SIGNED_TRUSTLOG_JSONL", trustlog_path)
        _stub_signing(monkeypatch)

        worm_path = tmp_path / "worm.jsonl"
        monkeypatch.setenv("VERITAS_TRUSTLOG_WORM_MIRROR_PATH", str(worm_path))
        monkeypatch.delenv("VERITAS_TRUSTLOG_WORM_HARD_FAIL", raising=False)

        original_append = trustlog_signed._append_line

        def _fail_worm(path, line):
            if str(path) == str(worm_path):
                raise OSError("permission denied")
            original_append(path, line)

        monkeypatch.setattr(trustlog_signed, "_append_line", _fail_worm)

        with caplog.at_level(logging.WARNING):
            append_signed_decision({"request_id": "worm-log"})

        assert any("WORM mirror write failed" in r.message for r in caplog.records)


# ===========================================================================
# 8. Transparency anchor failure
# ===========================================================================

class TestTransparencyAnchorFailure:
    """Transparency anchor failures must be handled according to configuration."""

    def test_transparency_soft_fail_returns_error_dict(self, monkeypatch, tmp_path):
        trustlog_path = tmp_path / "trustlog.jsonl"
        monkeypatch.setattr(trustlog_signed, "SIGNED_TRUSTLOG_JSONL", trustlog_path)
        _stub_signing(monkeypatch)

        anchor_path = tmp_path / "anchor.jsonl"
        monkeypatch.setenv("VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH", str(anchor_path))
        monkeypatch.delenv("VERITAS_TRUSTLOG_TRANSPARENCY_REQUIRED", raising=False)

        original_append = trustlog_signed._append_line

        def _fail_anchor(path, line):
            if str(path) == str(anchor_path):
                raise OSError("anchor fs read-only")
            original_append(path, line)

        monkeypatch.setattr(trustlog_signed, "_append_line", _fail_anchor)

        entry = append_signed_decision({"request_id": "anchor-soft"})
        assert entry["transparency_anchor"]["configured"] is True
        assert entry["transparency_anchor"]["ok"] is False

    def test_transparency_hard_fail_raises(self, monkeypatch, tmp_path):
        trustlog_path = tmp_path / "trustlog.jsonl"
        monkeypatch.setattr(trustlog_signed, "SIGNED_TRUSTLOG_JSONL", trustlog_path)
        _stub_signing(monkeypatch)

        anchor_path = tmp_path / "anchor.jsonl"
        monkeypatch.setenv("VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH", str(anchor_path))
        monkeypatch.setenv("VERITAS_TRUSTLOG_TRANSPARENCY_REQUIRED", "1")

        original_append = trustlog_signed._append_line

        def _fail_anchor(path, line):
            if str(path) == str(anchor_path):
                raise OSError("anchor write error")
            original_append(path, line)

        monkeypatch.setattr(trustlog_signed, "_append_line", _fail_anchor)

        with pytest.raises(SignedTrustLogWriteError):
            append_signed_decision({"request_id": "anchor-hard"})

    def test_transparency_failure_is_logged(self, monkeypatch, tmp_path, caplog):
        """Transparency anchor write failure emits a warning log."""
        import logging

        trustlog_path = tmp_path / "trustlog.jsonl"
        monkeypatch.setattr(trustlog_signed, "SIGNED_TRUSTLOG_JSONL", trustlog_path)
        _stub_signing(monkeypatch)

        anchor_path = tmp_path / "anchor.jsonl"
        monkeypatch.setenv("VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH", str(anchor_path))
        monkeypatch.delenv("VERITAS_TRUSTLOG_TRANSPARENCY_REQUIRED", raising=False)

        original_append = trustlog_signed._append_line

        def _fail_anchor(path, line):
            if str(path) == str(anchor_path):
                raise OSError("disk error")
            original_append(path, line)

        monkeypatch.setattr(trustlog_signed, "_append_line", _fail_anchor)

        with caplog.at_level(logging.WARNING):
            append_signed_decision({"request_id": "anchor-log"})

        assert any("Transparency anchor write failed" in r.message for r in caplog.records)


# ===========================================================================
# 9. No-downgrade / fail-closed guarantees
# ===========================================================================

class TestFailClosedGuarantees:
    """Verify that no silent security downgrade can occur."""

    def test_append_trust_log_raises_when_encryption_key_missing(self, monkeypatch, tmp_path):
        """append_trust_log must raise when encryption is required but key is absent."""
        monkeypatch.delenv("VERITAS_ENCRYPTION_KEY", raising=False)
        monkeypatch.setattr(trust_log, "LOG_DIR", tmp_path)
        monkeypatch.setattr(trust_log, "LOG_JSON", tmp_path / "trust_log.json")
        monkeypatch.setattr(trust_log, "LOG_JSONL", tmp_path / "trust_log.jsonl")
        monkeypatch.setattr(trust_log, "_get_last_hash_unlocked", lambda: None)
        monkeypatch.setattr(
            trust_log, "open_trust_log_for_append",
            lambda: (tmp_path / "trust_log.jsonl").open("a", encoding="utf-8"),
        )

        with pytest.raises(EncryptionKeyMissing):
            trust_log.append_trust_log({"request_id": "no-key"})

    def test_encryption_enforcement_rejects_plaintext_when_enabled(self, monkeypatch, tmp_path):
        """Even if _encrypt_line somehow returns plaintext, enforcement catches it."""
        _set_valid_key(monkeypatch, raw=b"L" * 32)
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
            trust_log.append_trust_log({"request_id": "plaintext-block"})

    def test_decrypt_plaintext_passthrough_only_without_enc_prefix(self, monkeypatch):
        """Only non-ENC: prefixed strings pass through decrypt unchanged."""
        _set_valid_key(monkeypatch)
        assert decrypt("plain text") == "plain text"
        assert decrypt("not encrypted") == "not encrypted"
        # ENC: prefix MUST attempt decryption (fail-closed)
        with pytest.raises(DecryptionError):
            decrypt("ENC:bad-algorithm:payload")

    def test_no_secret_leakage_in_exception_messages(self, monkeypatch):
        """Exception messages must not contain key material or plaintext."""
        monkeypatch.delenv("VERITAS_ENCRYPTION_KEY", raising=False)
        try:
            encrypt("TOP_SECRET_DATA")
        except EncryptionKeyMissing as exc:
            msg = str(exc)
            assert "TOP_SECRET_DATA" not in msg
            assert "VERITAS_ENCRYPTION_KEY" in msg  # OK to mention env var name

    def test_signed_trustlog_payload_hash_mismatch_detected(self, tmp_path, monkeypatch):
        """Entries with tampered payload_hash field are detected."""
        priv_path = tmp_path / "keys" / "priv.key"
        pub_path = tmp_path / "keys" / "pub.key"
        store_keypair(priv_path, pub_path)
        monkeypatch.setattr(trustlog_signed, "PUBLIC_KEY_PATH", pub_path)

        payload = {"decision": "allow"}
        real_hash = sha256_of_canonical_json(payload)
        sig = sign_payload_hash(real_hash, priv_path)

        entry = {
            "decision_id": "id-tamper",
            "timestamp": "2026-01-01T00:00:00Z",
            "previous_hash": None,
            "decision_payload": payload,
            "payload_hash": "TAMPERED_HASH",  # Wrong!
            "signature": sig,
            "signature_key_fingerprint": "fp",
        }

        trustlog_path = tmp_path / "trustlog.jsonl"
        trustlog_path.write_text(json.dumps(entry) + "\n", encoding="utf-8")

        result = verify_trustlog_chain(trustlog_path)
        assert result["ok"] is False
        assert any(i["reason"] == "payload_hash_mismatch" for i in result["issues"])


# ===========================================================================
# 10. Corrupt signed TrustLog entry handling
# ===========================================================================

class TestCorruptSignedEntries:
    """Corrupt entries in the signed TrustLog must be handled gracefully."""

    def test_read_last_entry_skips_corrupt_trailing_line(self, tmp_path):
        valid = json.dumps({"decision_id": "good", "payload_hash": "h" * 64})
        corrupt = "NOT_VALID_JSON{{{{"
        log_path = tmp_path / "trustlog.jsonl"
        log_path.write_text(valid + "\n" + corrupt + "\n", encoding="utf-8")

        result = _read_last_entry(log_path)
        assert result is not None
        assert result["decision_id"] == "good"

    def test_read_all_entries_skips_corrupt_lines(self, tmp_path):
        valid = json.dumps({"decision_id": "ok"})
        log_path = tmp_path / "trustlog.jsonl"
        log_path.write_text(
            valid + "\n" + "CORRUPT\n" + valid + "\n", encoding="utf-8"
        )

        entries = _read_all_entries(log_path)
        assert len(entries) == 2
        assert all(e["decision_id"] == "ok" for e in entries)

    def test_read_last_entry_returns_none_for_all_corrupt(self, tmp_path):
        log_path = tmp_path / "trustlog.jsonl"
        log_path.write_text("BAD1\nBAD2\nBAD3\n", encoding="utf-8")

        result = _read_last_entry(log_path)
        assert result is None

    def test_read_last_entry_returns_none_for_empty_file(self, tmp_path):
        log_path = tmp_path / "trustlog.jsonl"
        log_path.write_text("", encoding="utf-8")

        result = _read_last_entry(log_path)
        assert result is None

    def test_read_last_entry_returns_none_for_missing_file(self, tmp_path):
        result = _read_last_entry(tmp_path / "nonexistent.jsonl")
        assert result is None
