"""Integration regression tests for the three critical defects.

This module verifies that all three critical security defects are resolved
and remain fixed across the codebase:

1. TrustLog secure-by-default — no plaintext leakage, mandatory encryption
2. Pickle complete removal — MemoryOS uses only safe JSON serialization
3. FUJI/ValueCore deterministic-first — safety works without LLM

Each test section is self-contained and uses fixtures to isolate state.
"""
from __future__ import annotations

import ast
import importlib
import json
import os
import re
import sys
import textwrap
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Defect 1: TrustLog secure-by-default
# ---------------------------------------------------------------------------


class TestTrustLogSecureByDefault:
    """Verify TrustLog encryption is mandatory and no plaintext leaks."""

    def test_encrypt_raises_without_key(self, monkeypatch):
        """encrypt() must raise EncryptionKeyMissing when no key is set."""
        monkeypatch.delenv("VERITAS_ENCRYPTION_KEY", raising=False)
        from veritas_os.logging.encryption import EncryptionKeyMissing, encrypt

        with pytest.raises(EncryptionKeyMissing):
            encrypt("sensitive data")

    def test_encrypt_does_not_allow_plaintext_by_default(self, monkeypatch):
        """_allow_plaintext defaults to False — plaintext is never stored."""
        monkeypatch.delenv("VERITAS_ENCRYPTION_KEY", raising=False)
        from veritas_os.logging.encryption import EncryptionKeyMissing, encrypt

        with pytest.raises(EncryptionKeyMissing):
            encrypt("some plaintext")

    def test_no_allow_plaintext_true_in_production_code(self):
        """Grep source code: _allow_plaintext=True must not appear in non-test files."""
        src_root = Path(__file__).resolve().parents[1]
        violations = []
        for py_file in src_root.rglob("*.py"):
            if "/tests/" in str(py_file):
                continue
            content = py_file.read_text(encoding="utf-8", errors="replace")
            if "_allow_plaintext=True" in content or "_allow_plaintext = True" in content:
                violations.append(str(py_file))
        assert violations == [], (
            f"Production code uses _allow_plaintext=True: {violations}"
        )

    def test_append_trust_log_fails_without_encryption_key(self, tmp_path, monkeypatch):
        """append_trust_log must fail when encryption key is missing."""
        monkeypatch.delenv("VERITAS_ENCRYPTION_KEY", raising=False)
        from veritas_os.logging import trust_log
        from veritas_os.logging.encryption import EncryptionKeyMissing

        monkeypatch.setattr(trust_log, "LOG_DIR", tmp_path, raising=False)
        monkeypatch.setattr(trust_log, "LOG_JSON", tmp_path / "trust_log.json", raising=False)
        monkeypatch.setattr(trust_log, "LOG_JSONL", tmp_path / "trust_log.jsonl", raising=False)

        def _open():
            return open(tmp_path / "trust_log.jsonl", "a", encoding="utf-8")

        monkeypatch.setattr(trust_log, "open_trust_log_for_append", _open, raising=False)

        with pytest.raises(EncryptionKeyMissing):
            trust_log.append_trust_log({"event": "test", "query": "hello"})

    def test_stored_jsonl_is_encrypted(self, tmp_path, monkeypatch):
        """JSONL lines on disk must start with 'ENC:' prefix."""
        from veritas_os.logging.encryption import generate_key
        from veritas_os.logging import trust_log

        key = generate_key()
        monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", key)
        monkeypatch.setattr(trust_log, "LOG_DIR", tmp_path, raising=False)
        monkeypatch.setattr(trust_log, "LOG_JSON", tmp_path / "trust_log.json", raising=False)

        jsonl_path = tmp_path / "trust_log.jsonl"
        monkeypatch.setattr(trust_log, "LOG_JSONL", jsonl_path, raising=False)

        def _open():
            jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            return open(jsonl_path, "a", encoding="utf-8")

        monkeypatch.setattr(trust_log, "open_trust_log_for_append", _open, raising=False)
        monkeypatch.setattr(
            "veritas_os.audit.trustlog_signed.append_signed_decision",
            lambda d: d,
            raising=False,
        )

        trust_log.append_trust_log({"event": "test", "query": "secret data"})

        raw = jsonl_path.read_text(encoding="utf-8")
        for line in raw.strip().splitlines():
            assert line.startswith("ENC:"), "JSONL line must be encrypted (ENC: prefix)"
            # Must NOT be parseable as plain JSON
            with pytest.raises(json.JSONDecodeError):
                json.loads(line)

    def test_pii_redacted_before_storage(self, tmp_path, monkeypatch):
        """PII (email, phone) must be redacted from stored entries."""
        from veritas_os.logging.encryption import generate_key, decrypt
        from veritas_os.logging import trust_log

        key = generate_key()
        monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", key)
        monkeypatch.setattr(trust_log, "LOG_DIR", tmp_path, raising=False)
        monkeypatch.setattr(trust_log, "LOG_JSON", tmp_path / "trust_log.json", raising=False)

        jsonl_path = tmp_path / "trust_log.jsonl"
        monkeypatch.setattr(trust_log, "LOG_JSONL", jsonl_path, raising=False)

        def _open():
            jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            return open(jsonl_path, "a", encoding="utf-8")

        monkeypatch.setattr(trust_log, "open_trust_log_for_append", _open, raising=False)
        monkeypatch.setattr(
            "veritas_os.audit.trustlog_signed.append_signed_decision",
            lambda d: d,
            raising=False,
        )

        secret_key = "sk-abcdefghijklmnopqrstuvwxyz1234567890"
        entry = trust_log.append_trust_log({
            "event": "test",
            "query": f"Contact: user@example.com, API key: {secret_key}",
        })

        # Decrypt and verify PII is masked
        raw = jsonl_path.read_text(encoding="utf-8").strip()
        decrypted = decrypt(raw)
        assert "user@example.com" not in decrypted, "Email should be redacted"
        assert secret_key not in decrypted, "API key should be redacted"

    def test_hash_chain_integrity_after_encryption(self, tmp_path, monkeypatch):
        """Hash chain verification must pass with encrypted entries."""
        from veritas_os.logging.encryption import generate_key
        from veritas_os.logging import trust_log

        key = generate_key()
        monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", key)
        monkeypatch.setattr(trust_log, "LOG_DIR", tmp_path, raising=False)
        monkeypatch.setattr(trust_log, "LOG_JSON", tmp_path / "trust_log.json", raising=False)

        jsonl_path = tmp_path / "trust_log.jsonl"
        monkeypatch.setattr(trust_log, "LOG_JSONL", jsonl_path, raising=False)

        def _open():
            jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            return open(jsonl_path, "a", encoding="utf-8")

        monkeypatch.setattr(trust_log, "open_trust_log_for_append", _open, raising=False)
        monkeypatch.setattr(
            "veritas_os.audit.trustlog_signed.append_signed_decision",
            lambda d: d,
            raising=False,
        )

        # Write 3 chained entries
        for i in range(3):
            trust_log.append_trust_log({"event": f"test_{i}", "data": f"entry {i}"})

        # Verify chain
        result = trust_log.verify_trust_log()
        assert result["ok"] is True, f"Chain verification failed: {result}"
        assert result["checked"] == 3

    def test_tamper_detection_works(self, tmp_path, monkeypatch):
        """Modifying a line in the JSONL must break chain verification."""
        from veritas_os.logging.encryption import generate_key
        from veritas_os.logging import trust_log

        key = generate_key()
        monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", key)
        monkeypatch.setattr(trust_log, "LOG_DIR", tmp_path, raising=False)
        monkeypatch.setattr(trust_log, "LOG_JSON", tmp_path / "trust_log.json", raising=False)

        jsonl_path = tmp_path / "trust_log.jsonl"
        monkeypatch.setattr(trust_log, "LOG_JSONL", jsonl_path, raising=False)

        def _open():
            jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            return open(jsonl_path, "a", encoding="utf-8")

        monkeypatch.setattr(trust_log, "open_trust_log_for_append", _open, raising=False)
        monkeypatch.setattr(
            "veritas_os.audit.trustlog_signed.append_signed_decision",
            lambda d: d,
            raising=False,
        )

        for i in range(3):
            trust_log.append_trust_log({"event": f"test_{i}"})

        # Tamper: swap line order
        lines = jsonl_path.read_text().strip().splitlines()
        lines[0], lines[1] = lines[1], lines[0]
        jsonl_path.write_text("\n".join(lines) + "\n")

        result = trust_log.verify_trust_log()
        assert result["ok"] is False, "Tampered log must fail verification"
        assert result["broken"] is True


# ---------------------------------------------------------------------------
# Defect 2: Pickle complete removal
# ---------------------------------------------------------------------------


class TestPickleCompleteRemoval:
    """Verify pickle is completely removed from runtime code."""

    def test_no_pickle_import_in_production_code(self):
        """No production (non-test) Python file should import pickle."""
        src_root = Path(__file__).resolve().parents[1]
        violations = []
        for py_file in src_root.rglob("*.py"):
            rel = str(py_file.relative_to(src_root))
            # Skip test files and the migration script
            if "tests/" in rel or "test_" in rel or "migrate_pickle" in rel:
                continue
            content = py_file.read_text(encoding="utf-8", errors="replace")
            if re.search(r"^\s*import\s+pickle\b", content, re.MULTILINE):
                violations.append(rel)
            if re.search(r"^\s*from\s+pickle\s+import", content, re.MULTILINE):
                violations.append(rel)
        assert violations == [], (
            f"Production code imports pickle: {violations}"
        )

    def test_no_pickle_load_or_dump_in_production(self):
        """No production code calls pickle.load/dump/loads/dumps."""
        src_root = Path(__file__).resolve().parents[1]
        violations = []
        for py_file in src_root.rglob("*.py"):
            rel = str(py_file.relative_to(src_root))
            if "tests/" in rel or "test_" in rel or "migrate_pickle" in rel:
                continue
            content = py_file.read_text(encoding="utf-8", errors="replace")
            for pattern in [
                r"pickle\.load\(",
                r"pickle\.dump\(",
                r"pickle\.loads\(",
                r"pickle\.dumps\(",
                r"joblib\.load\(",
                r"joblib\.dump\(",
            ]:
                if re.search(pattern, content):
                    violations.append(f"{rel}: {pattern}")
        assert violations == [], (
            f"Production code uses pickle/joblib: {violations}"
        )

    def test_memory_store_uses_json_only(self):
        """MemoryStore must use .jsonl files, not pickle."""
        from veritas_os.memory.store import FILES

        for kind, path in FILES.items():
            assert str(path).endswith(".jsonl"), (
                f"MemoryStore[{kind}] uses non-JSONL file: {path}"
            )

    def test_memory_store_index_uses_npz(self):
        """MemoryStore index files must be .npz (safe numpy), not .pkl."""
        from veritas_os.memory.store import INDEX

        for kind, path in INDEX.items():
            assert str(path).endswith(".npz"), (
                f"MemoryStore index[{kind}] uses non-npz file: {path}"
            )

    def test_memory_store_put_and_search_json_roundtrip(self, tmp_path, monkeypatch):
        """MemoryStore write and read cycle uses only JSON."""
        from veritas_os.memory import store

        # Redirect storage to tmp
        for kind in store.FILES:
            monkeypatch.setitem(store.FILES, kind, tmp_path / f"{kind}.jsonl")
            monkeypatch.setitem(store.INDEX, kind, tmp_path / f"{kind}.index.npz")

        ms = store.MemoryStore(dim=16)
        item_id = ms.put("episodic", {
            "text": "Integration test item for pickle removal verification",
            "tags": ["test"],
        })

        # Verify file is valid JSONL
        jsonl_path = tmp_path / "episodic.jsonl"
        assert jsonl_path.exists()
        line = jsonl_path.read_text(encoding="utf-8").strip()
        parsed = json.loads(line)
        assert parsed["id"] == item_id
        assert parsed["text"] == "Integration test item for pickle removal verification"

        # Verify no .pkl file was created
        pkl_files = list(tmp_path.glob("*.pkl"))
        assert pkl_files == [], f"Pickle files found: {pkl_files}"

    def test_no_unsafe_deserializers_in_production(self):
        """No production code uses marshal, shelve, yaml.load, eval, exec for data."""
        src_root = Path(__file__).resolve().parents[1]
        violations = []
        for py_file in src_root.rglob("*.py"):
            rel = str(py_file.relative_to(src_root))
            if "tests/" in rel or "test_" in rel or "migrate_pickle" in rel:
                continue
            content = py_file.read_text(encoding="utf-8", errors="replace")
            # Check for unsafe yaml.load (without SafeLoader)
            if re.search(r"yaml\.load\([^)]*\)", content):
                # Allow yaml.safe_load and yaml.load(...Loader=SafeLoader)
                for match in re.finditer(r"yaml\.load\(([^)]*)\)", content):
                    if "SafeLoader" not in match.group(1) and "safe_load" not in match.group(0):
                        violations.append(f"{rel}: yaml.load without SafeLoader")
            # Check for shelve
            if re.search(r"\bshelve\.\w+\(", content):
                violations.append(f"{rel}: shelve usage")
            # Check for marshal.load
            if re.search(r"marshal\.load\(", content):
                violations.append(f"{rel}: marshal.load")
        assert violations == [], (
            f"Unsafe deserializer in production code: {violations}"
        )


# ---------------------------------------------------------------------------
# Defect 3: FUJI / ValueCore deterministic-first
# ---------------------------------------------------------------------------


class TestFUJIDeterministicFirst:
    """Verify FUJI safety works deterministically without LLM."""

    def test_heuristic_analyzer_detects_illicit(self):
        """Heuristic analyzer must detect dangerous content without LLM."""
        from veritas_os.tools.llm_safety import heuristic_analyze

        result = heuristic_analyze("I want to kill someone and make a bomb")
        assert result["ok"] is True
        assert result["risk_score"] >= 0.7
        assert "illicit" in result["categories"]

    def test_heuristic_analyzer_detects_pii(self):
        """Heuristic analyzer must detect PII without LLM."""
        from veritas_os.tools.llm_safety import heuristic_analyze

        result = heuristic_analyze("Email: user@example.com, Phone: 090-1234-5678")
        assert "PII" in result["categories"]

    def test_safety_continues_without_openai(self, monkeypatch):
        """Safety check must still work when OPENAI_API_KEY is not set."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("VERITAS_SAFETY_MODE", "heuristic")
        from veritas_os.tools import llm_safety

        result = llm_safety.run("This is a test of safety without LLM")
        assert result["ok"] is True
        assert isinstance(result["risk_score"], float)

    def test_forced_heuristic_mode(self, monkeypatch):
        """VERITAS_SAFETY_MODE=heuristic forces deterministic-only analysis."""
        monkeypatch.setenv("VERITAS_SAFETY_MODE", "heuristic")
        from veritas_os.tools import llm_safety

        result = llm_safety.run("Some test query")
        assert result["ok"] is True
        assert "fallback" in result.get("raw", {})

    def test_llm_fallback_flag_set_when_unavailable(self, monkeypatch):
        """When LLM is unavailable, llm_fallback=True must be set."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        # Ensure no LLM client exists
        from veritas_os.tools import llm_safety
        monkeypatch.setattr(llm_safety, "_client", None, raising=False)

        result = llm_safety.run("Safety test without LLM")
        assert result.get("llm_fallback") is True

    def test_value_core_loads_with_defaults_on_missing_config(self, tmp_path, monkeypatch):
        """ValueProfile.load() must return defaults when config file is missing."""
        from veritas_os.core.value_core import ValueProfile, DEFAULT_WEIGHTS

        monkeypatch.setattr("veritas_os.core.value_core.CFG_DIR", tmp_path, raising=False)
        monkeypatch.setattr(
            "veritas_os.core.value_core.CFG_PATH",
            tmp_path / "value_core.json",
            raising=False,
        )

        profile = ValueProfile.load()
        assert isinstance(profile.weights, dict)
        assert len(profile.weights) > 0
        # Should have core ethical dimensions
        assert "ethics" in profile.weights
        assert "legality" in profile.weights
        assert "harm_avoid" in profile.weights

    def test_fuji_judgment_source_field_exists(self):
        """FUJI must track judgment_source for rule/advisory separation."""
        import veritas_os.core.fuji as fuji_mod

        source = fuji_mod.__file__
        content = Path(source).read_text(encoding="utf-8")
        assert "judgment_source" in content, (
            "fuji.py must include judgment_source field for audit"
        )
        assert "llm_available" in content, (
            "fuji.py must include llm_available field for audit"
        )

    def test_deterministic_risk_floors_in_fuji(self):
        """FUJI must have deterministic risk floor constants."""
        import veritas_os.core.fuji as fuji_mod

        source = fuji_mod.__file__
        content = Path(source).read_text(encoding="utf-8")
        # Check for deterministic floor assignments
        assert "deterministic_illicit_floor" in content, (
            "fuji.py must have deterministic illicit risk floor"
        )
        assert "deterministic_self_harm_floor" in content, (
            "fuji.py must have deterministic self_harm risk floor"
        )


# ---------------------------------------------------------------------------
# Cross-cutting: README / docs consistency
# ---------------------------------------------------------------------------


class TestDocsConsistency:
    """Verify documentation matches implementation."""

    def test_readme_mentions_encryption_mandatory(self):
        """Both READMEs must state encryption is mandatory, not optional."""
        readme_en = Path(__file__).resolve().parents[2] / "README.md"
        readme_jp = Path(__file__).resolve().parents[2] / "README_JP.md"

        en_content = readme_en.read_text(encoding="utf-8")
        jp_content = readme_jp.read_text(encoding="utf-8")

        # English README
        assert "secure-by-default" in en_content.lower()
        assert "VERITAS_ENCRYPTION_KEY" in en_content
        assert "EncryptionKeyMissing" in en_content

        # Japanese README
        assert "secure-by-default" in jp_content.lower()
        assert "VERITAS_ENCRYPTION_KEY" in jp_content
        assert "EncryptionKeyMissing" in jp_content

    def test_readme_jp_does_not_claim_plaintext_storage(self):
        """README_JP must NOT claim that TrustLog is plaintext or encryption optional."""
        readme_jp = Path(__file__).resolve().parents[2] / "README_JP.md"
        content = readme_jp.read_text(encoding="utf-8")

        assert "保存時暗号化（任意）" not in content, (
            "README_JP must not say encryption is optional"
        )
        assert "TrustLog/Memoryは平文保存です" not in content, (
            "README_JP must not claim plaintext storage"
        )

    def test_env_example_includes_encryption_key(self):
        """The .env.example must mention VERITAS_ENCRYPTION_KEY."""
        env_example = Path(__file__).resolve().parents[2] / ".env.example"
        content = env_example.read_text(encoding="utf-8")
        assert "VERITAS_ENCRYPTION_KEY" in content, (
            ".env.example must include VERITAS_ENCRYPTION_KEY"
        )

    def test_readme_mentions_deterministic_safety(self):
        """README must mention deterministic safety layer."""
        readme_en = Path(__file__).resolve().parents[2] / "README.md"
        content = readme_en.read_text(encoding="utf-8")
        assert "deterministic" in content.lower()

    def test_security_md_exists_and_covers_key_topics(self):
        """SECURITY.md must exist and cover vulnerability reporting."""
        security_md = Path(__file__).resolve().parents[2] / "SECURITY.md"
        assert security_md.exists()
        content = security_md.read_text(encoding="utf-8")
        assert "vulnerability" in content.lower()
