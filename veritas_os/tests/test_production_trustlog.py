"""Production-like TrustLog write / read / verify validation.

These tests exercise the TrustLog subsystem through the same code-paths
that a production deployment uses: append → iterate → verify chain,
including encryption, hash-chaining, and signed-decision flows.

Markers:
    production — production-like validation (excluded from default CI)
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def trustlog_env(tmp_path, monkeypatch):
    """Redirect TrustLog paths to a temp directory with a fresh key."""
    from veritas_os.logging import trust_log
    from veritas_os.logging.encryption import generate_key

    key = generate_key()
    monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", key)

    monkeypatch.setattr(trust_log, "LOG_DIR", tmp_path, raising=False)
    json_path = tmp_path / "trust_log.json"
    jsonl_path = tmp_path / "trust_log.jsonl"
    monkeypatch.setattr(trust_log, "LOG_JSON", json_path, raising=False)
    monkeypatch.setattr(trust_log, "LOG_JSONL", jsonl_path, raising=False)

    def _open_for_append():
        trust_log.LOG_JSONL.parent.mkdir(parents=True, exist_ok=True)
        return open(trust_log.LOG_JSONL, "a", encoding="utf-8")

    monkeypatch.setattr(
        trust_log, "open_trust_log_for_append", _open_for_append
    )

    return {
        "log_dir": tmp_path,
        "json": json_path,
        "jsonl": jsonl_path,
        "key": key,
    }


@pytest.fixture()
def signed_trustlog_env(tmp_path, monkeypatch):
    """Redirect signed TrustLog paths to a temp directory."""
    from veritas_os.audit import trustlog_signed as ts

    jsonl = tmp_path / "signed_trustlog.jsonl"
    worm = tmp_path / "worm"
    worm.mkdir()
    pub_key = tmp_path / "ed25519_pub.pem"

    monkeypatch.setattr(ts, "SIGNED_TRUSTLOG_JSONL", jsonl, raising=False)
    monkeypatch.setattr(ts, "WORM_MIRROR_DIR", worm, raising=False)
    monkeypatch.setattr(ts, "PUBLIC_KEY_PATH", pub_key, raising=False)
    # Reset chain state for isolation
    monkeypatch.setattr(ts, "_previous_hash", None, raising=False)

    return {
        "jsonl": jsonl,
        "worm_dir": worm,
        "pub_key": pub_key,
    }


# ---------------------------------------------------------------------------
# Production-like TrustLog tests
# ---------------------------------------------------------------------------


@pytest.mark.production
class TestTrustLogWriteReadVerify:
    """Full write → read → verify lifecycle."""

    def test_single_append_and_read(self, trustlog_env):
        from veritas_os.logging.trust_log import (
            append_trust_log,
            iter_trust_log,
        )

        entry = {"action": "approve", "risk": 0.2, "user": "prod-test"}
        result = append_trust_log(entry)

        # append_trust_log returns the enriched entry
        assert "sha256" in result

        # Read back
        entries = list(iter_trust_log())
        assert len(entries) >= 1
        last = entries[-1]
        assert last.get("action") == "approve"

    def test_chain_integrity_after_multiple_writes(self, trustlog_env):
        from veritas_os.logging.trust_log import (
            append_trust_log,
            verify_trust_log,
        )

        for i in range(10):
            append_trust_log({"seq": i, "action": "step", "risk": i * 0.1})

        result = verify_trust_log()
        assert result["ok"] is True
        assert result["checked"] == 10
        assert result["broken"] is False

    def test_hash_chain_detects_tampering(self, trustlog_env):
        from veritas_os.logging.trust_log import (
            append_trust_log,
            verify_trust_log,
        )

        for i in range(5):
            append_trust_log({"seq": i, "action": "write"})

        # Tamper with the JSONL — corrupt second line
        lines = trustlog_env["jsonl"].read_text().splitlines()
        if len(lines) >= 2:
            # Replace the second line with garbage
            lines[1] = '{"tampered": true}'
            trustlog_env["jsonl"].write_text("\n".join(lines) + "\n")

            result = verify_trust_log()
            # Chain should detect the corruption
            assert result["broken"] is True or result["checked"] < 5

    def test_encrypted_entries_round_trip(self, trustlog_env):
        """Ensure encrypted entries can be decrypted on read."""
        from veritas_os.logging.trust_log import (
            append_trust_log,
            iter_trust_log,
        )

        secret_entry = {
            "action": "sensitive_decision",
            "details": "confidential-payload-12345",
        }
        append_trust_log(secret_entry)

        entries = list(iter_trust_log())
        assert len(entries) >= 1
        found = any(
            e.get("action") == "sensitive_decision" for e in entries
        )
        assert found, "Encrypted entry should be decryptable on read"

    def test_stats_increment(self, trustlog_env):
        from veritas_os.logging.trust_log import (
            append_trust_log,
            get_trust_log_stats,
        )

        stats_before = get_trust_log_stats()
        append_trust_log({"action": "stats-test"})
        stats_after = get_trust_log_stats()

        assert (
            stats_after["append_success"]
            >= stats_before["append_success"] + 1
        )

    def test_concurrent_appends_safe(self, trustlog_env):
        """Verify thread-safe appends under concurrent load."""
        import threading

        from veritas_os.logging.trust_log import (
            append_trust_log,
            verify_trust_log,
        )

        errors = []
        n_threads = 5
        n_writes = 4

        def worker(tid):
            try:
                for i in range(n_writes):
                    append_trust_log(
                        {"thread": tid, "seq": i, "action": "concurrent"}
                    )
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=worker, args=(t,))
            for t in range(n_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Concurrent append errors: {errors}"

        result = verify_trust_log()
        assert result["ok"] is True
        assert result["checked"] == n_threads * n_writes


@pytest.mark.production
class TestSignedTrustLog:
    """Signed TrustLog append → chain verify → export."""

    def test_append_and_verify(self, signed_trustlog_env):
        from veritas_os.audit.trustlog_signed import (
            append_signed_decision,
            verify_trustlog_chain,
        )

        payload = {
            "action": "approve",
            "risk_score": 0.15,
            "reason": "low-risk automated approval",
        }
        result = append_signed_decision(payload)
        assert "decision_id" in result
        assert "signature" in result

        chain = verify_trustlog_chain(signed_trustlog_env["jsonl"])
        assert chain["ok"] is True
        assert chain["entries_checked"] >= 1

    def test_multi_entry_chain(self, signed_trustlog_env):
        from veritas_os.audit.trustlog_signed import (
            append_signed_decision,
            verify_trustlog_chain,
        )

        for i in range(5):
            append_signed_decision(
                {"action": f"step-{i}", "risk_score": i * 0.1}
            )

        chain = verify_trustlog_chain(signed_trustlog_env["jsonl"])
        assert chain["ok"] is True
        assert chain["entries_checked"] == 5

    def test_export_contains_all_entries(self, signed_trustlog_env):
        from veritas_os.audit.trustlog_signed import (
            append_signed_decision,
            export_signed_trustlog,
        )

        for i in range(3):
            append_signed_decision({"action": f"export-{i}"})

        export = export_signed_trustlog(signed_trustlog_env["jsonl"])
        assert export["count"] == 3
        assert len(export["entries"]) == 3

    def test_tamper_detection(self, signed_trustlog_env):
        from veritas_os.audit.trustlog_signed import (
            append_signed_decision,
            verify_trustlog_chain,
        )

        for i in range(3):
            append_signed_decision({"action": f"tamper-{i}"})

        # Tamper: flip a byte in the middle entry
        lines = signed_trustlog_env["jsonl"].read_text().splitlines()
        if len(lines) >= 2:
            obj = json.loads(lines[1])
            obj["decision_payload"]["action"] = "TAMPERED"
            lines[1] = json.dumps(obj)
            signed_trustlog_env["jsonl"].write_text(
                "\n".join(lines) + "\n"
            )

            chain = verify_trustlog_chain(signed_trustlog_env["jsonl"])
            # Should detect signature mismatch or chain break
            assert not chain["ok"] or len(chain.get("issues", [])) > 0
