"""Secure TrustLog tests — verify secure-by-default guarantees.

Tests cover:
    1. PII in input is redacted before persistence
    2. Stored file is NOT plaintext JSON
    3. Encrypted entries still pass chain verification
    4. Tampering is detected
    5. Without decryption key, content is unreadable
    6. Secrets (API keys, bearer tokens) are redacted
    7. Encryption is mandatory (no key → error)
"""
from __future__ import annotations

import base64
import json
import os
import secrets

import pytest

from veritas_os.logging import trust_log
from veritas_os.logging.encryption import (
    EncryptionKeyMissing,
    decrypt,
    encrypt,
    generate_key,
)
from veritas_os.logging.redact import redact_entry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def encryption_key(monkeypatch):
    """Set a valid encryption key for the test session."""
    key = generate_key()
    monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", key)
    return key


@pytest.fixture
def temp_log_env(tmp_path, monkeypatch, encryption_key):
    """Redirect TrustLog paths to tmp_path with encryption enabled."""
    monkeypatch.setattr(trust_log, "LOG_DIR", tmp_path, raising=False)

    json_path = tmp_path / "trust_log.json"
    jsonl_path = tmp_path / "trust_log.jsonl"
    monkeypatch.setattr(trust_log, "LOG_JSON", json_path, raising=False)
    monkeypatch.setattr(trust_log, "LOG_JSONL", jsonl_path, raising=False)

    def _open_trust_log_for_append():
        trust_log.LOG_JSONL.parent.mkdir(parents=True, exist_ok=True)
        return open(trust_log.LOG_JSONL, "a", encoding="utf-8")

    monkeypatch.setattr(
        trust_log,
        "open_trust_log_for_append",
        _open_trust_log_for_append,
        raising=False,
    )

    return {
        "log_dir": tmp_path,
        "json": json_path,
        "jsonl": jsonl_path,
    }


# ---------------------------------------------------------------------------
# 1. PII redaction before persistence
# ---------------------------------------------------------------------------


class TestPIIRedaction:
    """PII-containing input must be redacted before storage."""

    def test_email_is_redacted(self, temp_log_env):
        entry = trust_log.append_trust_log({
            "request_id": "pii-email",
            "query": "Contact me at user@example.com please",
        })
        assert "user@example.com" not in json.dumps(entry)

    def test_phone_is_redacted(self, temp_log_env):
        entry = trust_log.append_trust_log({
            "request_id": "pii-phone",
            "query": "Call 090-1234-5678 for details",
        })
        assert "090-1234-5678" not in json.dumps(entry)

    def test_address_is_redacted(self, temp_log_env):
        entry = trust_log.append_trust_log({
            "request_id": "pii-addr",
            "query": "Ship to 東京都新宿区西新宿2丁目",
        })
        assert "東京都新宿区" not in json.dumps(entry)

    def test_redact_entry_standalone(self):
        """redact_entry works independently of TrustLog pipeline."""
        raw = {
            "request_id": "r1",
            "query": "Email: admin@corp.io, key: sk-1234567890abcdef1234567890",
        }
        safe = redact_entry(raw)
        assert safe["request_id"] == "r1"  # structural field preserved
        assert "admin@corp.io" not in safe["query"]
        assert "sk-1234567890abcdef1234567890" not in safe["query"]


# ---------------------------------------------------------------------------
# 2. Stored file is NOT plaintext JSON
# ---------------------------------------------------------------------------


class TestNoPlaintextStorage:
    """The JSONL file must contain encrypted data, not raw JSON."""

    def test_jsonl_is_not_readable_json(self, temp_log_env):
        trust_log.append_trust_log({
            "request_id": "enc-test",
            "query": "secret payload",
        })

        raw_content = temp_log_env["jsonl"].read_text(encoding="utf-8")
        lines = [l for l in raw_content.strip().split("\n") if l.strip()]

        for line in lines:
            assert line.startswith("ENC:"), (
                "Stored line must be encrypted (ENC: prefix)"
            )
            # Must NOT be parseable as plain JSON
            try:
                parsed = json.loads(line)
                # If we get here, it means the line is valid JSON — fail
                pytest.fail("Stored line is plaintext JSON — encryption not applied")
            except json.JSONDecodeError:
                pass  # Expected: encrypted lines are not valid JSON

    def test_query_text_not_in_raw_file(self, temp_log_env):
        secret_marker = "SUPER_SECRET_DATA_12345"
        trust_log.append_trust_log({
            "request_id": "raw-leak",
            "query": secret_marker,
        })

        raw = temp_log_env["jsonl"].read_bytes()
        assert secret_marker.encode() not in raw


# ---------------------------------------------------------------------------
# 3. Chain verification works on encrypted log
# ---------------------------------------------------------------------------


class TestChainVerificationWithEncryption:
    """Hash chain must remain verifiable after encrypt/decrypt round-trip."""

    def test_chain_integrity_multiple_entries(self, temp_log_env):
        for i in range(5):
            trust_log.append_trust_log({
                "request_id": f"chain-{i}",
                "step": i,
            })

        result = trust_log.verify_trust_log()
        assert result["ok"] is True
        assert result["checked"] == 5
        assert result["broken"] is False

    def test_iter_trust_log_returns_decrypted(self, temp_log_env):
        trust_log.append_trust_log({"request_id": "iter-1", "data": "hello"})
        trust_log.append_trust_log({"request_id": "iter-2", "data": "world"})

        entries = list(trust_log.iter_trust_log(reverse=False))
        assert len(entries) == 2
        assert entries[0]["request_id"] == "iter-1"
        assert entries[1]["request_id"] == "iter-2"


# ---------------------------------------------------------------------------
# 4. Tampering detection
# ---------------------------------------------------------------------------


class TestTamperingDetection:
    """Modifications to stored data must be detectable."""

    def test_modified_ciphertext_detected(self, temp_log_env):
        trust_log.append_trust_log({"request_id": "tamper-1"})
        trust_log.append_trust_log({"request_id": "tamper-2"})

        # Tamper with file: swap order of lines
        raw = temp_log_env["jsonl"].read_text(encoding="utf-8")
        lines = raw.strip().split("\n")
        assert len(lines) == 2

        # Write lines in reversed order
        temp_log_env["jsonl"].write_text(
            lines[1] + "\n" + lines[0] + "\n",
            encoding="utf-8",
        )

        result = trust_log.verify_trust_log()
        assert result["ok"] is False
        assert result["broken"] is True

    def test_corrupted_ciphertext_detected(self, temp_log_env):
        trust_log.append_trust_log({"request_id": "corrupt-1"})

        raw = temp_log_env["jsonl"].read_text(encoding="utf-8")
        # Flip some bytes in the encrypted content
        corrupted = raw[:20] + "XXXX" + raw[24:]
        temp_log_env["jsonl"].write_text(corrupted, encoding="utf-8")

        result = trust_log.verify_trust_log()
        assert result["ok"] is False


# ---------------------------------------------------------------------------
# 5. Without key, content is unreadable
# ---------------------------------------------------------------------------


class TestNoKeyNoAccess:
    """Without the decryption key, log content must be inaccessible."""

    def test_iter_returns_nothing_without_key(self, temp_log_env, monkeypatch):
        trust_log.append_trust_log({"request_id": "nokey-1"})

        # Remove key
        monkeypatch.delenv("VERITAS_ENCRYPTION_KEY")

        entries = list(trust_log.iter_trust_log())
        assert entries == []

    def test_verify_fails_without_key(self, temp_log_env, monkeypatch):
        trust_log.append_trust_log({"request_id": "nokey-v"})

        monkeypatch.delenv("VERITAS_ENCRYPTION_KEY")

        result = trust_log.verify_trust_log()
        assert result["ok"] is False

    def test_decrypt_raises_without_key(self, monkeypatch):
        monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", generate_key())
        ct = encrypt("hello world")
        assert ct.startswith("ENC:")

        monkeypatch.delenv("VERITAS_ENCRYPTION_KEY")
        with pytest.raises(EncryptionKeyMissing):
            decrypt(ct)


# ---------------------------------------------------------------------------
# 6. Secret / API key / bearer token redaction
# ---------------------------------------------------------------------------


class TestSecretRedaction:
    """API keys, bearer tokens, and secret-like strings must be redacted."""

    def test_api_key_redacted(self, temp_log_env):
        entry = trust_log.append_trust_log({
            "request_id": "sec-api",
            "query": "Use key sk-abcdefghijklmnopqrstuvwxyz1234",
        })
        dumped = json.dumps(entry)
        assert "sk-abcdefghijklmnopqrstuvwxyz1234" not in dumped

    def test_bearer_token_redacted(self, temp_log_env):
        entry = trust_log.append_trust_log({
            "request_id": "sec-bearer",
            "headers": "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.signature",
        })
        dumped = json.dumps(entry)
        assert "eyJhbGciOiJIUzI1NiJ9" not in dumped

    def test_secret_kv_redacted(self):
        raw = {
            "request_id": "sec-kv",
            "config": "api_secret=SuperSecret123456789!@#",
        }
        safe = redact_entry(raw)
        assert "SuperSecret123456789" not in safe["config"]


# ---------------------------------------------------------------------------
# 7. Mandatory encryption (no key = write failure)
# ---------------------------------------------------------------------------


class TestMandatoryEncryption:
    """append_trust_log must refuse to write without an encryption key."""

    def test_append_raises_without_key(self, tmp_path, monkeypatch):
        # Ensure NO encryption key is set
        monkeypatch.delenv("VERITAS_ENCRYPTION_KEY", raising=False)

        monkeypatch.setattr(trust_log, "LOG_DIR", tmp_path, raising=False)
        monkeypatch.setattr(trust_log, "LOG_JSON", tmp_path / "t.json", raising=False)
        monkeypatch.setattr(trust_log, "LOG_JSONL", tmp_path / "t.jsonl", raising=False)

        def _open():
            return open(tmp_path / "t.jsonl", "a", encoding="utf-8")

        monkeypatch.setattr(trust_log, "open_trust_log_for_append", _open, raising=False)

        with pytest.raises(EncryptionKeyMissing):
            trust_log.append_trust_log({"request_id": "must-fail"})

        # Verify nothing was written
        jsonl = tmp_path / "t.jsonl"
        if jsonl.exists():
            assert jsonl.read_text().strip() == ""


# ---------------------------------------------------------------------------
# 8. Encryption round-trip correctness
# ---------------------------------------------------------------------------


class TestEncryptionRoundTrip:
    """encrypt → decrypt must be lossless."""

    def test_basic_round_trip(self, encryption_key):
        original = '{"request_id":"rt","sha256":"abc"}'
        ct = encrypt(original)
        assert ct.startswith("ENC:")
        assert ct != original
        pt = decrypt(ct)
        assert pt == original

    def test_unicode_round_trip(self, encryption_key):
        original = '{"query":"日本語テスト 🚀"}'
        ct = encrypt(original)
        pt = decrypt(ct)
        assert pt == original

    def test_large_payload(self, encryption_key):
        original = json.dumps({"data": "x" * 100_000})
        ct = encrypt(original)
        pt = decrypt(ct)
        assert pt == original

    def test_non_encrypted_passthrough(self):
        """decrypt on non-ENC: string returns it unchanged."""
        plain = '{"hello": "world"}'
        assert decrypt(plain) == plain
