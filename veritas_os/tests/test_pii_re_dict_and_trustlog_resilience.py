# veritas_os/tests/test_pii_re_dict_and_trustlog_resilience.py
"""
Tests for two key improvements:
1. _PII_RE dict-based PII pattern management (replaces globals() in fuji.py)
2. _read_all_entries resilience to corrupted JSONL lines (trustlog_signed.py)
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict

import pytest

from veritas_os.core import fuji
from veritas_os.audit import trustlog_signed


# =========================================================
# 1. _PII_RE dict tests
# =========================================================


class TestPIIREDict:
    """Verify that _PII_RE dict replaces globals()-based pattern management."""

    def test_pii_re_is_dict(self):
        """_PII_RE should be a dict, not separate module variables."""
        assert isinstance(fuji._PII_RE, dict)

    def test_pii_re_has_all_keys(self):
        """_PII_RE should contain all four PII pattern keys."""
        expected_keys = {"phone", "email", "address_jp", "person_name_jp"}
        assert set(fuji._PII_RE.keys()) == expected_keys

    def test_pii_re_values_are_compiled_patterns(self):
        """Each value in _PII_RE should be a compiled regex."""
        for key, pattern in fuji._PII_RE.items():
            assert isinstance(pattern, re.Pattern), (
                f"_PII_RE[{key!r}] should be a compiled regex"
            )

    def test_phone_pattern_matches(self):
        """Phone pattern should match Japanese phone numbers."""
        assert fuji._PII_RE["phone"].search("090-1234-5678")
        assert fuji._PII_RE["phone"].search("03-1234-5678")

    def test_email_pattern_matches(self):
        """Email pattern should match email addresses."""
        assert fuji._PII_RE["email"].search("user@example.com")

    def test_address_jp_pattern_matches(self):
        """Address pattern should match Japanese addresses."""
        assert fuji._PII_RE["address_jp"].search("東京都港区1-2-3")

    def test_person_name_jp_pattern_matches(self):
        """Name pattern should match Japanese honorific names."""
        assert fuji._PII_RE["person_name_jp"].search("田中太郎さん")

    def test_no_globals_used_for_pii_patterns(self):
        """Verify the old _RE_* module variables no longer exist."""
        assert not hasattr(fuji, "_RE_PHONE")
        assert not hasattr(fuji, "_RE_EMAIL")
        assert not hasattr(fuji, "_RE_ADDRJP")
        assert not hasattr(fuji, "_RE_NAMEJP")


class TestBuildRuntimePatternsDict:
    """Verify _build_runtime_patterns_from_policy updates _PII_RE dict."""

    def test_policy_overrides_phone_pattern(self):
        """PII patterns from policy should override defaults via _PII_RE dict."""
        original = fuji._PII_RE["phone"]
        custom_phone = r"CUSTOM_PHONE_\d+"
        policy: Dict[str, Any] = {
            "pii": {"patterns": {"phone": custom_phone}},
        }
        try:
            fuji._build_runtime_patterns_from_policy(policy)
            assert fuji._PII_RE["phone"].pattern == custom_phone
            assert fuji._PII_RE["phone"].search("CUSTOM_PHONE_123")
        finally:
            fuji._PII_RE["phone"] = original

    def test_invalid_regex_keeps_existing(self):
        """Invalid regex in policy should keep existing pattern unchanged."""
        original = fuji._PII_RE["email"]
        policy: Dict[str, Any] = {
            "pii": {"patterns": {"email": "[invalid(regex"}},
        }
        fuji._build_runtime_patterns_from_policy(policy)
        assert fuji._PII_RE["email"] is original

    def test_empty_patterns_no_change(self):
        """Empty patterns section should leave _PII_RE unchanged."""
        originals = {k: v for k, v in fuji._PII_RE.items()}
        policy: Dict[str, Any] = {"pii": {"patterns": {}}}
        fuji._build_runtime_patterns_from_policy(policy)
        for key in originals:
            assert fuji._PII_RE[key] is originals[key]


class TestRedactUsesDict:
    """Verify that PII redaction and safety head use _PII_RE dict."""

    def test_redact_uses_pii_re_phone(self):
        """_redact_text_for_trust_log should use _PII_RE for phone redaction."""
        policy: Dict[str, Any] = {
            "audit": {"redact_before_log": True},
            "pii": {"enabled": True, "masked_markers": ["●"]},
        }
        text = "Call 090-1234-5678 now"
        result = fuji._redact_text_for_trust_log(text, policy)
        assert "090-1234-5678" not in result
        assert "●" in result

    def test_redact_uses_pii_re_email(self):
        """_redact_text_for_trust_log should use _PII_RE for email redaction."""
        policy: Dict[str, Any] = {
            "audit": {"redact_before_log": True},
            "pii": {"enabled": True, "masked_markers": ["*"]},
        }
        text = "Email user@example.com"
        result = fuji._redact_text_for_trust_log(text, policy)
        assert "user@example.com" not in result

    def test_fallback_safety_head_detects_pii(self):
        """_fallback_safety_head should use _PII_RE for PII detection."""
        result = fuji._fallback_safety_head("連絡先は090-1234-5678です")
        assert "PII" in result.categories
        assert "phone" in result.rationale


# =========================================================
# 2. _read_all_entries resilience tests
# =========================================================


class TestReadAllEntriesResilience:
    """Verify _read_all_entries handles corrupt JSONL lines gracefully."""

    def test_skips_corrupt_lines(self, tmp_path: Path):
        """Corrupt lines should be skipped, not crash the reader."""
        log_file = tmp_path / "trustlog.jsonl"
        entries = [
            json.dumps({"id": 1, "data": "valid1"}),
            "THIS IS NOT VALID JSON {{{",
            json.dumps({"id": 2, "data": "valid2"}),
        ]
        log_file.write_text("\n".join(entries) + "\n", encoding="utf-8")

        result = trustlog_signed._read_all_entries(log_file)
        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[1]["id"] == 2

    def test_logs_warning_for_corrupt_lines(self, tmp_path: Path, caplog):
        """Corrupt lines should produce a warning log message."""
        log_file = tmp_path / "trustlog.jsonl"
        log_file.write_text(
            '{"valid": true}\nNOT_JSON\n{"also_valid": true}\n',
            encoding="utf-8",
        )

        with caplog.at_level(logging.WARNING, logger="veritas_os.audit.trustlog_signed"):
            result = trustlog_signed._read_all_entries(log_file)

        assert len(result) == 2
        assert any(
            "corrupt" in msg.lower() or "skipping" in msg.lower()
            for msg in caplog.messages
        )

    def test_all_corrupt_returns_empty(self, tmp_path: Path):
        """If all lines are corrupt, should return empty list."""
        log_file = tmp_path / "trustlog.jsonl"
        log_file.write_text("BAD1\nBAD2\nBAD3\n", encoding="utf-8")

        result = trustlog_signed._read_all_entries(log_file)
        assert result == []

    def test_empty_file_returns_empty(self, tmp_path: Path):
        """Empty file should return empty list."""
        log_file = tmp_path / "trustlog.jsonl"
        log_file.write_text("", encoding="utf-8")

        result = trustlog_signed._read_all_entries(log_file)
        assert result == []

    def test_nonexistent_file_returns_empty(self, tmp_path: Path):
        """Non-existent file should return empty list."""
        result = trustlog_signed._read_all_entries(tmp_path / "does_not_exist.jsonl")
        assert result == []

    def test_valid_entries_preserved(self, tmp_path: Path):
        """All valid entries should be preserved in order."""
        log_file = tmp_path / "trustlog.jsonl"
        entries = [{"i": i} for i in range(5)]
        log_file.write_text(
            "\n".join(json.dumps(e) for e in entries) + "\n",
            encoding="utf-8",
        )

        result = trustlog_signed._read_all_entries(log_file)
        assert len(result) == 5
        for i, entry in enumerate(result):
            assert entry["i"] == i

    def test_corrupt_between_valid_preserves_chain(self, tmp_path: Path):
        """Corrupt lines between valid entries shouldn't prevent chaining."""
        log_file = tmp_path / "trustlog.jsonl"
        valid1 = json.dumps({"decision_id": "d1", "previous_hash": None})
        valid2 = json.dumps({"decision_id": "d2", "previous_hash": "hash1"})
        log_file.write_text(
            f"{valid1}\nCORRUPT_LINE\n{valid2}\n",
            encoding="utf-8",
        )

        result = trustlog_signed._read_all_entries(log_file)
        assert len(result) == 2
        assert result[-1]["decision_id"] == "d2"


# =========================================================
# 3. Hot-reload pattern rebuild test
# =========================================================


class TestHotReloadPatternsRebuild:
    """Verify that _check_policy_hot_reload rebuilds runtime patterns."""

    def test_hot_reload_calls_build_patterns(self, monkeypatch, tmp_path: Path):
        """Hot-reload should call _build_runtime_patterns_from_policy."""
        policy_file = tmp_path / "test_policy.yaml"
        policy_file.write_text(
            "version: test\npii:\n  patterns:\n    phone: 'HOT_RELOAD_\\d+'\n",
            encoding="utf-8",
        )

        build_called = []

        original_build = fuji._build_runtime_patterns_from_policy

        def tracking_build(policy):
            build_called.append(True)
            return original_build(policy)

        monkeypatch.setattr(fuji, "_build_runtime_patterns_from_policy", tracking_build)
        monkeypatch.setattr(fuji, "_policy_path", lambda: policy_file)
        monkeypatch.setattr(fuji, "_POLICY_MTIME", 0.0)

        fuji._check_policy_hot_reload()

        assert len(build_called) > 0, (
            "_build_runtime_patterns_from_policy should be called during hot-reload"
        )
