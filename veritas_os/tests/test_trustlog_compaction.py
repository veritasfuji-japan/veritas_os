"""Tests for TrustLog compaction (lightweight audit summary).

Validates that:
1. Multiple /v1/decide-style appends don't corrupt trailing entries.
2. trustlog.jsonl lines don't contain bulky world_state / projects data.
3. Hash-chain and signature verification remain intact after compaction.
4. Full payloads are preserved in decide_*.json (not lost).
5. Oversized entry defence works correctly.
6. Single-entry max size is bounded.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

from veritas_os.audit import trustlog_signed
from veritas_os.audit.trustlog_signed import (
    MAX_ENTRY_LINE_BYTES,
    _OVERSIZED_MARKER,
    _enforce_entry_size,
    append_signed_decision,
    build_trustlog_summary,
    verify_trustlog_chain,
    verify_signature,
    export_signed_trustlog,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def signed_env(tmp_path, monkeypatch):
    """Redirect signed TrustLog to a temp directory with fresh keys."""
    log_path = tmp_path / "trustlog.jsonl"
    private_key = tmp_path / "keys" / "priv.key"
    public_key = tmp_path / "keys" / "pub.key"

    monkeypatch.setattr(trustlog_signed, "SIGNED_TRUSTLOG_JSONL", log_path)
    monkeypatch.setattr(trustlog_signed, "PRIVATE_KEY_PATH", private_key)
    monkeypatch.setattr(trustlog_signed, "PUBLIC_KEY_PATH", public_key)

    return {"jsonl": log_path, "private_key": private_key, "public_key": public_key}


def _make_bulky_payload(*, request_id: str = "req-bulky") -> Dict[str, Any]:
    """Create a realistic full decision payload with large nested data."""
    return {
        "request_id": request_id,
        "created_at": "2026-01-01T00:00:00Z",
        "context": {
            "user_id": "user-42",
            "world_state": {f"entity_{i}": {"data": "x" * 500} for i in range(50)},
            "projects": [{"name": f"proj-{i}", "history": list(range(200))} for i in range(10)],
            "memory": {"long_history": ["event"] * 1000},
        },
        "query": "Should I proceed?",
        "chosen": {
            "title": "Approve",
            "answer": "Yes, proceed.",
            "full_rationale": "x" * 5000,
            "evidence_chain": [{"doc": "y" * 2000}] * 5,
        },
        "telos_score": 0.92,
        "fuji": {
            "status": "approved",
            "risk": 0.1,
            "full_policy_trace": "z" * 3000,
        },
        "gate_status": "pass",
        "gate_risk": 0.1,
        "gate_total": 0.95,
        "plan_steps": 3,
        "fast_mode": False,
        "mem_hits": 5,
        "web_hits": 2,
        "critique_ok": True,
        "critique_mode": "auto",
        "critique_reason": None,
        "decision_status": "approved",
        "rejection_reason": None,
        "sha256": "a" * 64,
        "sha256_prev": None,
    }


# ---------------------------------------------------------------------------
# build_trustlog_summary tests
# ---------------------------------------------------------------------------

class TestBuildTrustlogSummary:

    def test_excludes_world_state(self):
        full = _make_bulky_payload()
        summary = build_trustlog_summary(full)
        assert "context" not in summary
        assert "world_state" not in json.dumps(summary)

    def test_excludes_projects(self):
        full = _make_bulky_payload()
        summary = build_trustlog_summary(full)
        serialized = json.dumps(summary)
        assert "projects" not in serialized
        assert "history" not in serialized

    def test_excludes_large_evidence_and_rationale(self):
        full = _make_bulky_payload()
        summary = build_trustlog_summary(full)
        serialized = json.dumps(summary)
        assert "full_rationale" not in serialized
        assert "evidence_chain" not in serialized
        assert "full_policy_trace" not in serialized

    def test_preserves_audit_essential_fields(self):
        full = _make_bulky_payload()
        summary = build_trustlog_summary(full)
        assert summary["request_id"] == "req-bulky"
        assert summary["telos_score"] == 0.92
        assert summary["gate_status"] == "pass"
        assert summary["gate_risk"] == 0.1
        assert summary["fast_mode"] is False
        assert summary["critique_ok"] is True
        assert summary["decision_status"] == "approved"

    def test_extracts_nested_scalars(self):
        full = _make_bulky_payload()
        summary = build_trustlog_summary(full)
        assert summary.get("fuji_status") == "approved"
        assert summary.get("fuji_risk") == 0.1
        assert summary.get("chosen_title") == "Approve"

    def test_summary_is_much_smaller_than_full(self):
        full = _make_bulky_payload()
        summary = build_trustlog_summary(full)
        full_size = len(json.dumps(full).encode("utf-8"))
        summary_size = len(json.dumps(summary).encode("utf-8"))
        # Summary should be at least 10x smaller than the bulky payload
        assert summary_size < full_size / 10, (
            f"Summary ({summary_size}B) is not significantly smaller "
            f"than full ({full_size}B)"
        )

    def test_summary_line_under_max_bytes(self):
        full = _make_bulky_payload()
        summary = build_trustlog_summary(full)
        line = json.dumps(summary, ensure_ascii=False).encode("utf-8")
        assert len(line) < MAX_ENTRY_LINE_BYTES

    def test_empty_payload_produces_empty_summary(self):
        summary = build_trustlog_summary({})
        assert isinstance(summary, dict)
        # Should be a valid, small dict
        assert len(json.dumps(summary)) < 100


# ---------------------------------------------------------------------------
# _enforce_entry_size tests
# ---------------------------------------------------------------------------

class TestEnforceEntrySize:

    def test_small_entry_passes_through(self):
        entry = {"decision_payload": {"request_id": "r1"}, "payload_hash": "abc"}
        result = _enforce_entry_size(entry)
        assert result is entry  # same object, not replaced

    def test_oversized_entry_replaced_with_stub(self):
        huge_payload = {"request_id": "r-huge", "blob": "x" * (MAX_ENTRY_LINE_BYTES + 1000)}
        entry = {"decision_payload": huge_payload, "payload_hash": "hash123"}
        result = _enforce_entry_size(entry)
        assert result["decision_payload"].get(_OVERSIZED_MARKER) is True
        assert result["decision_payload"]["request_id"] == "r-huge"
        assert result["decision_payload"]["original_payload_hash"] == "hash123"

    def test_oversized_stub_is_within_limit(self):
        huge_payload = {"request_id": "r-huge", "blob": "x" * (MAX_ENTRY_LINE_BYTES * 2)}
        entry = {"decision_payload": huge_payload, "payload_hash": "hash456"}
        result = _enforce_entry_size(entry)
        line = json.dumps(result, ensure_ascii=False).encode("utf-8")
        assert len(line) < MAX_ENTRY_LINE_BYTES


# ---------------------------------------------------------------------------
# append_signed_decision integration (with compaction)
# ---------------------------------------------------------------------------

class TestAppendSignedDecisionCompaction:

    def test_single_append_with_bulky_payload(self, signed_env):
        full = _make_bulky_payload(request_id="r-compact-1")
        entry = append_signed_decision(full)

        # Entry should have compact decision_payload
        dp = entry["decision_payload"]
        assert "context" not in dp
        serialized = json.dumps(dp)
        assert "world_state" not in serialized
        assert "projects" not in serialized

        # Should have full_payload_hash for cross-reference
        assert "full_payload_hash" in entry
        assert len(entry["full_payload_hash"]) == 64

        # Signature should verify
        assert verify_signature(entry) is True

    def test_multiple_appends_no_corruption(self, signed_env):
        """Multiple appends should not produce corrupt trailing entries."""
        for i in range(5):
            full = _make_bulky_payload(request_id=f"r-multi-{i}")
            append_signed_decision(full)

        # Verify chain integrity
        result = verify_trustlog_chain(path=signed_env["jsonl"])
        assert result["ok"] is True
        assert result["entries_checked"] == 5

        # Verify each line is valid JSON
        lines = signed_env["jsonl"].read_text(encoding="utf-8").splitlines()
        assert len(lines) == 5
        for idx, line in enumerate(lines):
            parsed = json.loads(line)
            assert "decision_payload" in parsed, f"Line {idx} missing decision_payload"
            assert "world_state" not in json.dumps(parsed), f"Line {idx} contains world_state"

    def test_no_trailing_corruption_after_repeated_appends(self, signed_env):
        """Regression: 2+ appends must not produce corrupt trailing entry."""
        for i in range(10):
            append_signed_decision({"request_id": f"r-trail-{i}", "action": "approve"})

        # Read all lines — every one should parse cleanly
        lines = signed_env["jsonl"].read_text(encoding="utf-8").splitlines()
        for idx, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            try:
                json.loads(line)
            except json.JSONDecodeError:
                pytest.fail(f"Corrupt trailing entry at line {idx}")

        result = verify_trustlog_chain(path=signed_env["jsonl"])
        assert result["ok"] is True

    def test_line_size_bounded(self, signed_env):
        """Each JSONL line should stay within MAX_ENTRY_LINE_BYTES."""
        for i in range(3):
            full = _make_bulky_payload(request_id=f"r-size-{i}")
            append_signed_decision(full)

        lines = signed_env["jsonl"].read_text(encoding="utf-8").splitlines()
        for idx, line in enumerate(lines):
            size = len(line.encode("utf-8"))
            assert size <= MAX_ENTRY_LINE_BYTES, (
                f"Line {idx} is {size} bytes, exceeds {MAX_ENTRY_LINE_BYTES}"
            )

    def test_hash_chain_integrity_with_compaction(self, signed_env):
        """Hash chain verification must pass after compaction."""
        payloads = [
            _make_bulky_payload(request_id=f"r-chain-{i}")
            for i in range(5)
        ]
        for p in payloads:
            append_signed_decision(p)

        result = verify_trustlog_chain(path=signed_env["jsonl"])
        assert result["ok"] is True
        assert result["entries_checked"] == 5
        assert not result["issues"]

    def test_signature_validation_after_compaction(self, signed_env):
        """Signatures must verify against the compact payload hash."""
        full = _make_bulky_payload(request_id="r-sig")
        entry = append_signed_decision(full)

        assert verify_signature(entry) is True

        # Verify via chain as well
        result = verify_trustlog_chain(path=signed_env["jsonl"])
        assert result["ok"] is True

    def test_full_payload_hash_differs_from_summary_hash(self, signed_env):
        """full_payload_hash and payload_hash should differ (different data)."""
        full = _make_bulky_payload(request_id="r-diff")
        entry = append_signed_decision(full)

        assert entry["full_payload_hash"] != entry["payload_hash"]
        assert len(entry["full_payload_hash"]) == 64
        assert len(entry["payload_hash"]) == 64

    def test_export_after_compaction(self, signed_env):
        """Exported entries should contain compact payloads."""
        for i in range(3):
            append_signed_decision(_make_bulky_payload(request_id=f"r-export-{i}"))

        export = export_signed_trustlog(path=signed_env["jsonl"])
        assert export["count"] == 3
        for entry in export["entries"]:
            dp = entry["decision_payload"]
            serialized = json.dumps(dp)
            assert "world_state" not in serialized
            assert "projects" not in serialized

    def test_concurrent_signed_appends_no_corruption(self, signed_env):
        """10 threads × 3 appends must not corrupt the signed TrustLog chain."""
        import threading

        errors: list = []
        n_threads = 10
        n_writes = 3

        def worker(tid: int) -> None:
            try:
                for seq in range(n_writes):
                    append_signed_decision(
                        {"request_id": f"r-conc-{tid}-{seq}", "thread": tid}
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
            t.join(timeout=30)

        assert not errors, f"Concurrent signed append errors: {errors}"

        result = verify_trustlog_chain(path=signed_env["jsonl"])
        assert result["ok"] is True
        assert result["entries_checked"] == n_threads * n_writes

        # Every line must be valid JSON
        lines = signed_env["jsonl"].read_text(encoding="utf-8").splitlines()
        assert len(lines) == n_threads * n_writes
        for idx, line in enumerate(lines):
            try:
                json.loads(line)
            except json.JSONDecodeError:
                pytest.fail(f"Corrupt entry at line {idx} after concurrent writes")

    def test_15_sequential_appends_chain_intact(self, signed_env):
        """15 sequential appends must keep the hash chain and signatures intact."""
        for i in range(15):
            full = _make_bulky_payload(request_id=f"r-seq15-{i}")
            entry = append_signed_decision(full)
            assert verify_signature(entry) is True

        result = verify_trustlog_chain(path=signed_env["jsonl"])
        assert result["ok"] is True
        assert result["entries_checked"] == 15
        assert not result["issues"]

        # Verify no world_state / projects leak in any line
        raw = signed_env["jsonl"].read_text(encoding="utf-8")
        assert "world_state" not in raw
        assert '"projects"' not in raw

    def test_detect_tampering_still_works(self, signed_env):
        """Tampering detection must still work with compact payloads."""
        from veritas_os.audit.trustlog_signed import detect_tampering

        for i in range(3):
            append_signed_decision({"request_id": f"r-tamper-{i}", "action": "ok"})

        # Tamper with second entry
        lines = signed_env["jsonl"].read_text(encoding="utf-8").splitlines()
        obj = json.loads(lines[1])
        obj["decision_payload"]["request_id"] = "TAMPERED"
        lines[1] = json.dumps(obj, ensure_ascii=False)
        signed_env["jsonl"].write_text("\n".join(lines) + "\n", encoding="utf-8")

        result = detect_tampering(path=signed_env["jsonl"])
        assert result["tampered"] is True


# ---------------------------------------------------------------------------
# persist_audit_log compaction tests
# ---------------------------------------------------------------------------

class TestPersistAuditLogCompaction:

    def test_audit_entry_excludes_context(self):
        """The audit entry passed to append_trust_log should not contain ctx.context."""
        from veritas_os.core.pipeline_persist import persist_audit_log
        from veritas_os.core.pipeline_types import PipelineContext

        captured_entries = []

        def fake_append(entry):
            captured_entries.append(entry)
            return entry

        def fake_shadow(*args, **kwargs):
            pass

        ctx = PipelineContext()
        ctx.request_id = "req-ctx-test"
        ctx.query = "test query"
        ctx.context = {
            "user_id": "u1",
            "world_state": {"huge": "data" * 1000},
            "projects": [{"name": "p1", "history": list(range(500))}],
        }
        ctx.chosen = {"title": "OK", "answer": "yes", "giant_blob": "z" * 5000}
        ctx.telos = 0.8
        ctx.fuji_dict = {"status": "pass", "risk": 0.1}
        ctx.values_payload = {"total": 0.9}
        ctx.plan = {"steps": [1, 2]}
        ctx.fast_mode = False
        ctx.response_extras = {"metrics": {"mem_hits": 1, "web_hits": 2}}
        ctx.critique = {"ok": True, "mode": "auto", "reason": None}
        ctx.body = {"query": "test query"}

        persist_audit_log(ctx, append_trust_log_fn=fake_append, write_shadow_decide_fn=fake_shadow)

        assert len(captured_entries) == 1
        entry = captured_entries[0]

        # Must NOT contain the full context dict
        assert "context" not in entry
        # Must have context_user_id instead
        assert entry.get("context_user_id") == "u1"
        # world_state and projects must not appear
        serialized = json.dumps(entry)
        assert "world_state" not in serialized
        assert "projects" not in serialized
        # chosen should be compacted (no giant_blob)
        assert "giant_blob" not in json.dumps(entry.get("chosen", {}))
        # But title should be preserved
        assert entry["chosen"].get("title") == "OK"


# ---------------------------------------------------------------------------
# Oversized entry verification roundtrip
# ---------------------------------------------------------------------------

class TestOversizedEntryVerification:
    """Verify that oversized entries pass chain verification after stub replacement."""

    def test_oversized_entry_passes_chain_verification(self, signed_env):
        """An oversized entry must not cause false-positive chain breakage."""
        # First, append a normal entry
        append_signed_decision({"request_id": "r-normal-1", "action": "ok"})

        # Then append an oversized payload that triggers stub replacement.
        # Use an allowlisted field so the *summary* itself exceeds the limit.
        huge_payload = _make_bulky_payload(request_id="r-oversized")
        huge_payload["rejection_reason"] = "x" * (MAX_ENTRY_LINE_BYTES + 5000)
        append_signed_decision(huge_payload)

        # Append another normal entry after the oversized one
        append_signed_decision({"request_id": "r-normal-2", "action": "ok"})

        # The chain must still verify cleanly
        result = verify_trustlog_chain(path=signed_env["jsonl"])
        assert result["ok"] is True, (
            f"Chain verification failed after oversized entry: {result['issues']}"
        )
        assert result["entries_checked"] == 3

    def test_oversized_stub_has_marker(self, signed_env):
        """Oversized entries must contain the __trustlog_oversized__ marker."""
        # Use an allowlisted field with a huge value so the summary itself is oversized
        huge_payload = {
            "request_id": "r-huge-mark",
            "rejection_reason": "y" * (MAX_ENTRY_LINE_BYTES + 5000),
        }
        entry = append_signed_decision(huge_payload)

        dp = entry["decision_payload"]
        assert dp.get(_OVERSIZED_MARKER) is True
        assert dp.get("original_payload_hash") is not None

    def test_oversized_entry_signature_verifies(self, signed_env):
        """Signature must verify against the recalculated stub payload_hash."""
        huge_payload = {
            "request_id": "r-huge-sig",
            "rejection_reason": "z" * (MAX_ENTRY_LINE_BYTES + 5000),
        }
        entry = append_signed_decision(huge_payload)

        assert verify_signature(entry) is True


# ---------------------------------------------------------------------------
# Concurrent full-pipeline append_trust_log test
# ---------------------------------------------------------------------------

class TestConcurrentAppendTrustLog:
    """Verify that 10+ concurrent append_trust_log calls don't corrupt the chain."""

    def test_concurrent_full_pipeline_appends(self, tmp_path, monkeypatch):
        """10 threads × 3 appends through the full append_trust_log pipeline."""
        import threading
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
        # Redirect signed TrustLog to avoid interference
        monkeypatch.setattr(trustlog_signed, "SIGNED_TRUSTLOG_JSONL", tmp_path / "trustlog.jsonl")
        monkeypatch.setattr(trustlog_signed, "PRIVATE_KEY_PATH", tmp_path / "keys" / "priv.key")
        monkeypatch.setattr(trustlog_signed, "PUBLIC_KEY_PATH", tmp_path / "keys" / "pub.key")

        errors: list = []
        n_threads = 10
        n_writes = 3

        def worker(tid: int) -> None:
            try:
                for seq in range(n_writes):
                    trust_log.append_trust_log({
                        "request_id": f"conc-{tid}-{seq}",
                        "event": "test",
                        "data": f"thread {tid} seq {seq}",
                    })
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=worker, args=(t,))
            for t in range(n_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)

        assert not errors, f"Concurrent append_trust_log errors: {errors}"

        # Verify the encrypted hash chain is intact
        result = trust_log.verify_trust_log()
        assert result["ok"] is True, f"Chain broken after concurrent writes: {result}"
        assert result["checked"] == n_threads * n_writes
