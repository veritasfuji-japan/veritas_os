# veritas_os/tests/test_coverage_boost.py
"""Targeted coverage-boosting tests for under-covered modules."""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import patch, MagicMock

import pytest

# ================================================================
# 1. reason.py — target: lines 85,87,106-108,174-175,203,244-245,
#    248,258,266,269,273-274,278,280,301-302
# ================================================================
import veritas_os.core.reason as reason


class TestReasonBoostClipping:
    """Cover boost calculation paths in reflect()."""

    def test_boost_positive_max(self, tmp_path, monkeypatch):
        """Extreme positive inputs → boost maximised."""
        monkeypatch.setattr(reason, "META_LOG", tmp_path / "meta.jsonl")
        decision = {
            "query": "test",
            "chosen": {"title": "情報収集プランA"},
            "gate": {"risk": 0.0, "decision_status": "allow"},
            "values": {"total": 1.0, "ema": 0.9},
        }
        out = reason.reflect(decision)
        assert out["next_value_boost"] > 0

    def test_boost_negative_max(self, tmp_path, monkeypatch):
        """Extreme negative inputs → boost is negative."""
        monkeypatch.setattr(reason, "META_LOG", tmp_path / "meta.jsonl")
        decision = {
            "query": "test",
            "chosen": {"title": "通常"},
            "gate": {"risk": 1.0, "decision_status": "rejected"},
            "values": {"total": 0.0, "ema": 0.1},
        }
        out = reason.reflect(decision)
        assert out["next_value_boost"] <= 0

    def test_reflect_meta_log_write_error(self, tmp_path, monkeypatch):
        """When META_LOG write fails, reflect still returns result."""
        # Point to a read-only directory
        ro_dir = tmp_path / "readonly"
        ro_dir.mkdir()
        meta = ro_dir / "sub" / "deep" / "meta.jsonl"
        monkeypatch.setattr(reason, "META_LOG", meta)
        # Make the parent unwritable
        monkeypatch.setattr(reason, "_ensure_log_dir", lambda: (_ for _ in ()).throw(OSError("no perms")))

        decision = {"query": "test", "chosen": {}, "gate": {}, "values": {}}
        out = reason.reflect(decision)
        assert "next_value_boost" in out


class TestGenerateReasonStrResponse:
    """Cover str LLM response path."""

    def test_llm_returns_plain_string(self, monkeypatch):
        """When llm_client.chat returns a str instead of dict."""
        monkeypatch.setattr(
            reason.llm_client, "chat",
            lambda **kw: "plain text reason",
        )
        res = reason.generate_reason(query="test")
        assert res["text"] == "plain text reason"
        assert res["source"] == "openai_llm"

    def test_llm_returns_error(self, monkeypatch):
        """When llm_client.chat raises, return empty text."""
        monkeypatch.setattr(
            reason.llm_client, "chat",
            lambda **kw: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        res = reason.generate_reason(query="test")
        assert res["text"] == ""
        assert res["source"] == "error"


class TestGenerateReflectionTemplateEdge:
    """Cover edge cases in generate_reflection_template."""

    def test_empty_query_returns_empty(self):
        """Empty query returns {}."""
        tmpl = asyncio.run(
            reason.generate_reflection_template(
                query="", chosen={"title": "X"},
                gate={}, values={},
            )
        )
        assert tmpl == {}

    def test_empty_chosen_returns_empty(self):
        """Empty chosen returns {}."""
        tmpl = asyncio.run(
            reason.generate_reflection_template(
                query="test", chosen={},
                gate={}, values={},
            )
        )
        assert tmpl == {}

    def test_llm_returns_string_directly(self, monkeypatch, tmp_path):
        """When LLM returns a plain string (not dict)."""
        monkeypatch.setattr(reason, "META_LOG", tmp_path / "meta.jsonl")
        valid_json = json.dumps({
            "pattern": "p", "guidance": "g", "tags": ["a"], "priority": 0.5,
        })
        monkeypatch.setattr(
            reason.llm_client, "chat",
            lambda **kw: valid_json,
        )
        tmpl = asyncio.run(
            reason.generate_reflection_template(
                query="test", chosen={"title": "X"},
                gate={}, values={},
            )
        )
        assert tmpl["pattern"] == "p"

    def test_llm_returns_empty_text(self, monkeypatch):
        """When LLM returns dict with empty text."""
        monkeypatch.setattr(
            reason.llm_client, "chat",
            lambda **kw: {"text": "", "source": "stub"},
        )
        tmpl = asyncio.run(
            reason.generate_reflection_template(
                query="test", chosen={"title": "X"},
                gate={}, values={},
            )
        )
        assert tmpl == {}

    def test_llm_returns_non_dict_json(self, monkeypatch):
        """When LLM returns JSON that is a list, not dict."""
        monkeypatch.setattr(
            reason.llm_client, "chat",
            lambda **kw: {"text": "[1,2,3]", "source": "stub"},
        )
        tmpl = asyncio.run(
            reason.generate_reflection_template(
                query="test", chosen={"title": "X"},
                gate={}, values={},
            )
        )
        assert tmpl == {}

    def test_missing_guidance_returns_empty(self, monkeypatch):
        """When pattern exists but guidance is empty."""
        data = json.dumps({"pattern": "p", "guidance": "", "tags": [], "priority": 0.5})
        monkeypatch.setattr(
            reason.llm_client, "chat",
            lambda **kw: {"text": data, "source": "stub"},
        )
        tmpl = asyncio.run(
            reason.generate_reflection_template(
                query="test", chosen={"title": "X"},
                gate={}, values={},
            )
        )
        assert tmpl == {}

    def test_non_list_tags_fallback(self, monkeypatch, tmp_path):
        """When tags is not a list, fallback to ["reflection"]."""
        monkeypatch.setattr(reason, "META_LOG", tmp_path / "meta.jsonl")
        data = json.dumps({"pattern": "p", "guidance": "g", "tags": "string", "priority": 0.5})
        monkeypatch.setattr(
            reason.llm_client, "chat",
            lambda **kw: {"text": data, "source": "stub"},
        )
        tmpl = asyncio.run(
            reason.generate_reflection_template(
                query="test", chosen={"title": "X"},
                gate={}, values={},
            )
        )
        assert tmpl["tags"] == ["reflection"]

    def test_non_numeric_priority_defaults(self, monkeypatch, tmp_path):
        """When priority can't be float-parsed, default to 0.5."""
        monkeypatch.setattr(reason, "META_LOG", tmp_path / "meta.jsonl")
        data = json.dumps({"pattern": "p", "guidance": "g", "tags": ["a"], "priority": "invalid"})
        monkeypatch.setattr(
            reason.llm_client, "chat",
            lambda **kw: {"text": data, "source": "stub"},
        )
        tmpl = asyncio.run(
            reason.generate_reflection_template(
                query="test", chosen={"title": "X"},
                gate={}, values={},
            )
        )
        assert tmpl["priority"] == 0.5

    def test_priority_clipped_below_zero(self, monkeypatch, tmp_path):
        """Negative priority clipped to 0.0."""
        monkeypatch.setattr(reason, "META_LOG", tmp_path / "meta.jsonl")
        data = json.dumps({"pattern": "p", "guidance": "g", "tags": ["a"], "priority": -5.0})
        monkeypatch.setattr(
            reason.llm_client, "chat",
            lambda **kw: {"text": data, "source": "stub"},
        )
        tmpl = asyncio.run(
            reason.generate_reflection_template(
                query="test", chosen={"title": "X"},
                gate={}, values={},
            )
        )
        assert tmpl["priority"] == 0.0

    def test_priority_clipped_above_one(self, monkeypatch, tmp_path):
        """Priority > 1.0 clipped to 1.0."""
        monkeypatch.setattr(reason, "META_LOG", tmp_path / "meta.jsonl")
        data = json.dumps({"pattern": "p", "guidance": "g", "tags": ["a"], "priority": 99.0})
        monkeypatch.setattr(
            reason.llm_client, "chat",
            lambda **kw: {"text": data, "source": "stub"},
        )
        tmpl = asyncio.run(
            reason.generate_reflection_template(
                query="test", chosen={"title": "X"},
                gate={}, values={},
            )
        )
        assert tmpl["priority"] == 1.0

    def test_meta_log_write_error_still_returns(self, monkeypatch, tmp_path):
        """When meta_log write fails, still return template."""
        data = json.dumps({"pattern": "p", "guidance": "g", "tags": ["a"], "priority": 0.5})
        monkeypatch.setattr(
            reason.llm_client, "chat",
            lambda **kw: {"text": data, "source": "stub"},
        )
        monkeypatch.setattr(reason, "META_LOG", tmp_path / "no_parent" / "deep" / "meta.jsonl")
        monkeypatch.setattr(reason, "_ensure_log_dir", lambda: (_ for _ in ()).throw(OSError("fail")))
        tmpl = asyncio.run(
            reason.generate_reflection_template(
                query="test", chosen={"title": "X"},
                gate={}, values={},
            )
        )
        assert tmpl["pattern"] == "p"


# ================================================================
# 2. reflection.py — target: lines 33, 38-39, 44-45, 62-64, 98-99
# ================================================================
from veritas_os.core import reflection


class TestReflectionEdge:
    def test_get_decision_id_none(self):
        """None decision returns empty string."""
        assert reflection._get_decision_id(None) == ""

    def test_get_decision_id_str_raises(self):
        """When str(getattr(decision, 'id')) raises, fallback to str(decision)."""
        class BadStr:
            def __str__(self):
                raise RuntimeError("bad str")
        class HasBadId:
            id = BadStr()
        result = reflection._get_decision_id(HasBadId())
        # Falls through to str(decision)
        assert isinstance(result, str)

    def test_get_decision_id_dict_value_raises(self):
        """When str(decision['id']) raises, fallback to str(decision)."""
        class BadStr:
            def __str__(self):
                raise RuntimeError("bad str")
        d = {"id": BadStr()}
        result = reflection._get_decision_id(d)
        assert isinstance(result, str)

    def test_compute_score_trust_log_evaluate_raises(self, monkeypatch):
        """When trust_log.evaluate raises, fall through to outcome score."""
        class FailTL:
            def evaluate(self, *a, **kw):
                raise RuntimeError("eval fail")
        monkeypatch.setattr(reflection, "trust_log", FailTL(), raising=False)
        monkeypatch.setattr(reflection, "value_core", None, raising=False)
        mem: list = []
        score = reflection.evaluate_decision({"id": "x"}, {"score": 0.3}, mem)
        assert score == 0.3

    def test_adjust_weights_raises_ignored(self, monkeypatch):
        """When value_core.adjust_weights raises, it's silently ignored."""
        class FailVC:
            @staticmethod
            def adjust_weights(name, delta):
                raise RuntimeError("adjust fail")
        class OkTL:
            def evaluate(self, d, o):
                return 0.2
        monkeypatch.setattr(reflection, "trust_log", OkTL(), raising=False)
        monkeypatch.setattr(reflection, "value_core", FailVC, raising=False)
        mem: list = []
        score = reflection.evaluate_decision("d", {}, mem)
        assert score == 0.2
        assert mem[0]["score"] == 0.2


# ================================================================
# 3. logging/paths.py — target: lines 31, 38, 45, 61, 76-80, 96-97
# ================================================================
from veritas_os.logging import paths as log_paths


class TestLogPathsValidation:
    def test_validate_path_traversal_dotdot(self):
        """Path with '..' components raises RuntimeError."""
        p = Path("/tmp/logs/../etc/passwd")
        with pytest.raises(RuntimeError, match="traversal"):
            log_paths._validate_resolved_path(p)

    def test_validate_sensitive_directory_etc(self):
        """Path inside /etc raises RuntimeError."""
        p = Path("/etc/veritas_logs")
        with pytest.raises(RuntimeError, match="sensitive"):
            log_paths._validate_resolved_path(p)

    def test_validate_sensitive_directory_proc(self):
        """Path inside /proc raises RuntimeError."""
        p = Path("/proc/veritas_logs")
        with pytest.raises(RuntimeError, match="sensitive"):
            log_paths._validate_resolved_path(p)

    def test_validate_ok_path(self, tmp_path):
        """Valid path passes validation."""
        result = log_paths._validate_resolved_path(tmp_path / "logs")
        assert isinstance(result, Path)


class TestLogPathsResolveLogRoot:
    def test_encrypted_root_used(self, tmp_path, monkeypatch):
        """VERITAS_ENCRYPTED_LOG_ROOT takes precedence."""
        log_dir = tmp_path / "encrypted"
        log_dir.mkdir()
        monkeypatch.setenv("VERITAS_ENCRYPTED_LOG_ROOT", str(log_dir))
        monkeypatch.delenv("VERITAS_DATA_DIR", raising=False)
        monkeypatch.delenv("VERITAS_LOG_ROOT", raising=False)
        monkeypatch.delenv("VERITAS_REQUIRE_ENCRYPTED_LOG_DIR", raising=False)
        result = log_paths._resolve_log_root()
        assert result == log_dir

    def test_require_encrypted_without_encrypted_root(self, monkeypatch, tmp_path):
        """VERITAS_REQUIRE_ENCRYPTED_LOG_DIR=1 without ENCRYPTED_LOG_ROOT raises."""
        monkeypatch.delenv("VERITAS_ENCRYPTED_LOG_ROOT", raising=False)
        monkeypatch.setenv("VERITAS_REQUIRE_ENCRYPTED_LOG_DIR", "1")
        monkeypatch.setenv("VERITAS_DATA_DIR", str(tmp_path / "data"))
        with pytest.raises(RuntimeError, match="VERITAS_ENCRYPTED_LOG_ROOT"):
            log_paths._resolve_log_root()

    def test_data_dir_used(self, tmp_path, monkeypatch):
        """VERITAS_DATA_DIR takes precedence over LOG_ROOT."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        monkeypatch.delenv("VERITAS_ENCRYPTED_LOG_ROOT", raising=False)
        monkeypatch.setenv("VERITAS_DATA_DIR", str(data_dir))
        monkeypatch.delenv("VERITAS_REQUIRE_ENCRYPTED_LOG_DIR", raising=False)
        result = log_paths._resolve_log_root()
        assert result == data_dir


class TestEnsureSecurePermissions:
    def test_permissions_oserror_ignored(self, tmp_path, monkeypatch):
        """OSError in chmod is logged but not raised."""
        d = tmp_path / "logs"
        d.mkdir()
        # Monkeypatch os.chmod to raise
        monkeypatch.setattr(os, "chmod", lambda p, m: (_ for _ in ()).throw(OSError("denied")))
        # Should not raise
        log_paths._ensure_secure_permissions(d)


# ================================================================
# 4. logging/rotate.py — target: lines 36, 42, 54, 80, 83, 103-104, 131, 135
# ================================================================
from veritas_os.logging import rotate


class TestRotateEdge:
    def test_read_last_nonempty_line_missing_file(self, tmp_path):
        """Non-existent file returns None."""
        result = rotate._read_last_nonempty_line(tmp_path / "nope.jsonl")
        assert result is None

    def test_read_last_nonempty_line_empty_file(self, tmp_path):
        """Empty file returns None."""
        f = tmp_path / "empty.jsonl"
        f.write_bytes(b"")
        result = rotate._read_last_nonempty_line(f)
        assert result is None

    def test_read_last_nonempty_line_valid(self, tmp_path):
        """Valid file returns last non-empty line."""
        f = tmp_path / "test.jsonl"
        f.write_text('{"a":1}\n{"b":2}\n\n')
        result = rotate._read_last_nonempty_line(f)
        assert result == '{"b":2}'

    def test_save_last_hash_marker_no_file(self, tmp_path):
        """When trust_log doesn't exist, marker is not created."""
        rotate.save_last_hash_marker(tmp_path / "nope.jsonl")
        marker = tmp_path / rotate._LAST_HASH_MARKER
        assert not marker.exists()

    def test_save_last_hash_marker_no_hash(self, tmp_path):
        """When last entry has no sha256 key, marker is not written."""
        f = tmp_path / "trust_log.jsonl"
        f.write_text('{"action":"test"}\n')
        rotate.save_last_hash_marker(f)
        marker = tmp_path / rotate._LAST_HASH_MARKER
        assert not marker.exists()

    def test_save_last_hash_marker_with_hash(self, tmp_path):
        """When last entry has sha256, marker is written."""
        f = tmp_path / "trust_log.jsonl"
        f.write_text('{"sha256":"abc123"}\n')
        rotate.save_last_hash_marker(f)
        marker = tmp_path / rotate._LAST_HASH_MARKER
        assert marker.read_text() == "abc123"

    def test_load_last_hash_marker_exists(self, tmp_path):
        """Load existing marker value."""
        marker = tmp_path / rotate._LAST_HASH_MARKER
        marker.write_text("myhash")
        result = rotate.load_last_hash_marker(tmp_path / "trust_log.jsonl")
        assert result == "myhash"

    def test_load_last_hash_marker_empty(self, tmp_path):
        """Empty marker returns None."""
        marker = tmp_path / rotate._LAST_HASH_MARKER
        marker.write_text("")
        result = rotate.load_last_hash_marker(tmp_path / "trust_log.jsonl")
        assert result is None

    def test_load_last_hash_marker_missing(self, tmp_path):
        """Missing marker returns None."""
        result = rotate.load_last_hash_marker(tmp_path / "trust_log.jsonl")
        assert result is None

    def test_count_lines_missing_file(self, tmp_path):
        assert rotate.count_lines(tmp_path / "nope") == 0

    def test_count_lines_str_path(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("a\nb\nc\n")
        assert rotate.count_lines(str(f)) == 3

    def test_rotate_symlink_detected(self, tmp_path, monkeypatch):
        """Symlink on log path raises RuntimeError."""
        real = tmp_path / "real.jsonl"
        real.write_text("\n" * 6000)
        link = tmp_path / "trust_log.jsonl"
        link.symlink_to(real)
        monkeypatch.setattr(rotate, "_get_trust_log_path", lambda: link)
        with pytest.raises(RuntimeError, match="symlink"):
            rotate.rotate_if_needed()


# ================================================================
# 5. core/atomic_io.py — target lines 90-93 (dir fsync OSError),
#    99-100, 103-104 (cleanup on failure), 152->154 (newline)
# ================================================================
from veritas_os.core import atomic_io


class TestAtomicIoEdge:
    def test_atomic_write_text_basic(self, tmp_path):
        """Basic atomic write works."""
        p = tmp_path / "test.txt"
        atomic_io.atomic_write_text(p, "hello\nworld")
        assert p.read_text() == "hello\nworld"

    def test_atomic_write_json_adds_newline(self, tmp_path):
        """atomic_write_json adds trailing newline."""
        p = tmp_path / "test.json"
        atomic_io.atomic_write_json(p, {"a": 1}, indent=None)
        content = p.read_text()
        assert content.endswith("\n")

    def test_atomic_append_line_adds_newline(self, tmp_path):
        """atomic_append_line adds newline if missing."""
        p = tmp_path / "test.log"
        atomic_io.atomic_append_line(p, "line without newline")
        assert p.read_text() == "line without newline\n"

    def test_atomic_append_line_preserves_newline(self, tmp_path):
        """atomic_append_line doesn't double newline."""
        p = tmp_path / "test.log"
        atomic_io.atomic_append_line(p, "already has\n")
        assert p.read_text() == "already has\n"


# ================================================================
# 6. server.py endpoint coverage — memory, trust, metrics, etc.
# ================================================================
_TEST_KEY = "cov-boost-key"
os.environ["VERITAS_API_KEY"] = _TEST_KEY

import veritas_os.api.server as server
from fastapi.testclient import TestClient

_client = TestClient(server.app)
_AUTH = {"X-API-Key": _TEST_KEY}


@pytest.fixture(autouse=True)
def _reset_server_state(monkeypatch):
    monkeypatch.setenv("VERITAS_API_KEY", _TEST_KEY)
    server._rate_bucket.clear()
    yield
    server._rate_bucket.clear()


class TestServerMemoryEndpoints:
    """Cover memory_put, memory_search, memory_get paths."""

    def test_memory_put_store_unavailable(self, monkeypatch):
        monkeypatch.setattr(server, "get_memory_store", lambda: None)
        resp = _client.post("/v1/memory/put", headers=_AUTH, json={"text": "hello"})
        assert resp.json()["ok"] is False
        assert "unavailable" in resp.json()["error"]

    def test_memory_put_text_too_large(self, monkeypatch):
        store = SimpleNamespace(put=lambda k, v: "id1", search=lambda: [])
        monkeypatch.setattr(server, "get_memory_store", lambda: store)
        resp = _client.post("/v1/memory/put", headers=_AUTH, json={"text": "x" * 100_001})
        assert resp.json()["ok"] is False
        assert "too large" in resp.json()["error"]

    def test_memory_put_too_many_tags(self, monkeypatch):
        store = SimpleNamespace(put=lambda k, v: "id1", search=lambda: [])
        monkeypatch.setattr(server, "get_memory_store", lambda: store)
        resp = _client.post("/v1/memory/put", headers=_AUTH, json={
            "text": "hi", "tags": ["t"] * 101,
        })
        assert resp.json()["ok"] is False
        assert "tags" in resp.json()["error"]

    def test_memory_put_success(self, monkeypatch):
        store = SimpleNamespace(put=lambda kind, item: "new-id")
        monkeypatch.setattr(server, "get_memory_store", lambda: store)
        resp = _client.post("/v1/memory/put", headers=_AUTH, json={
            "text": "hello", "user_id": "u1", "tags": ["t1"], "kind": "semantic",
        })
        body = resp.json()
        assert body["ok"] is True
        assert body["vector"]["saved"] is True

    def test_memory_put_invalid_kind_defaults_to_semantic(self, monkeypatch):
        store = SimpleNamespace(put=lambda kind, item: "id1")
        monkeypatch.setattr(server, "get_memory_store", lambda: store)
        resp = _client.post("/v1/memory/put", headers=_AUTH, json={
            "text": "hello", "kind": "INVALID_KIND",
        })
        body = resp.json()
        assert body["ok"] is True

    def test_memory_search_store_unavailable(self, monkeypatch):
        monkeypatch.setattr(server, "get_memory_store", lambda: None)
        resp = _client.post("/v1/memory/search", headers=_AUTH, json={
            "query": "test", "user_id": "u1",
        })
        assert resp.json()["ok"] is False

    def test_memory_search_missing_user_id(self, monkeypatch):
        store = SimpleNamespace(search=lambda **kw: {})
        monkeypatch.setattr(server, "get_memory_store", lambda: store)
        resp = _client.post("/v1/memory/search", headers=_AUTH, json={"query": "test"})
        assert resp.json()["ok"] is False
        assert "user_id" in resp.json()["error"]

    def test_memory_search_with_dict_results(self, monkeypatch):
        hits = {"semantic": [{"id": "1", "text": "hi", "score": 0.9, "meta": {"user_id": "u1"}}]}
        store = SimpleNamespace(search=lambda **kw: hits)
        monkeypatch.setattr(server, "get_memory_store", lambda: store)
        resp = _client.post("/v1/memory/search", headers=_AUTH, json={
            "query": "test", "user_id": "u1",
        })
        body = resp.json()
        assert body["ok"] is True
        assert body["count"] == 1

    def test_memory_search_filters_by_user_id(self, monkeypatch):
        """Hits from other users should be filtered out."""
        hits = {"semantic": [
            {"id": "1", "text": "hi", "score": 0.9, "meta": {"user_id": "u1"}},
            {"id": "2", "text": "hi", "score": 0.8, "meta": {"user_id": "other"}},
        ]}
        store = SimpleNamespace(search=lambda **kw: hits)
        monkeypatch.setattr(server, "get_memory_store", lambda: store)
        resp = _client.post("/v1/memory/search", headers=_AUTH, json={
            "query": "test", "user_id": "u1",
        })
        assert resp.json()["count"] == 1

    def test_memory_search_bad_k_value(self, monkeypatch):
        store = SimpleNamespace(search=lambda **kw: {})
        monkeypatch.setattr(server, "get_memory_store", lambda: store)
        resp = _client.post("/v1/memory/search", headers=_AUTH, json={
            "query": "test", "user_id": "u1", "k": "bad",
        })
        body = resp.json()
        assert body["ok"] is True

    def test_memory_search_bad_min_sim_value(self, monkeypatch):
        store = SimpleNamespace(search=lambda **kw: {})
        monkeypatch.setattr(server, "get_memory_store", lambda: store)
        resp = _client.post("/v1/memory/search", headers=_AUTH, json={
            "query": "test", "user_id": "u1", "min_sim": "bad",
        })
        body = resp.json()
        assert body["ok"] is True

    def test_memory_get_store_unavailable(self, monkeypatch):
        monkeypatch.setattr(server, "get_memory_store", lambda: None)
        resp = _client.post("/v1/memory/get", headers=_AUTH, json={
            "user_id": "u1", "key": "k1",
        })
        assert resp.json()["ok"] is False

    def test_memory_get_missing_fields(self, monkeypatch):
        store = SimpleNamespace(get=lambda uid, key: None)
        monkeypatch.setattr(server, "get_memory_store", lambda: store)
        resp = _client.post("/v1/memory/get", headers=_AUTH, json={})
        assert resp.json()["ok"] is False
        assert "required" in resp.json()["error"]

    def test_memory_get_success(self, monkeypatch):
        store = SimpleNamespace(get=lambda uid, **kw: {"data": 1})
        monkeypatch.setattr(server, "get_memory_store", lambda: store)
        resp = _client.post("/v1/memory/get", headers=_AUTH, json={
            "user_id": "u1", "key": "k1",
        })
        body = resp.json()
        assert body["ok"] is True


class TestServerTrustFeedback:
    """Cover trust_feedback endpoint paths."""

    def test_trust_feedback_vc_unavailable(self, monkeypatch):
        monkeypatch.setattr(server, "get_value_core", lambda: None)
        resp = _client.post("/v1/trust/feedback", headers=_AUTH, json={"score": 0.5})
        body = resp.json()
        assert body["status"] == "error"
        assert "unavailable" in body["detail"]

    def test_trust_feedback_success(self, monkeypatch):
        calls = []
        class FakeVC:
            @staticmethod
            def append_trust_log(**kw):
                calls.append(kw)
        monkeypatch.setattr(server, "get_value_core", lambda: FakeVC)
        resp = _client.post("/v1/trust/feedback", headers=_AUTH, json={
            "user_id": "u1", "score": 0.8, "note": "good",
        })
        body = resp.json()
        assert body["status"] == "ok"
        assert body["user_id"] == "u1"
        assert len(calls) == 1

    def test_trust_feedback_bad_score(self, monkeypatch):
        """Non-numeric score defaults to 0.5."""
        calls = []
        class FakeVC:
            @staticmethod
            def append_trust_log(**kw):
                calls.append(kw)
        monkeypatch.setattr(server, "get_value_core", lambda: FakeVC)
        resp = _client.post("/v1/trust/feedback", headers=_AUTH, json={
            "score": "not-a-number",
        })
        body = resp.json()
        assert body["status"] == "ok"
        assert calls[0]["score"] == 0.5

    def test_trust_feedback_no_append_method(self, monkeypatch):
        """value_core without append_trust_log returns error."""
        monkeypatch.setattr(server, "get_value_core", lambda: SimpleNamespace())
        resp = _client.post("/v1/trust/feedback", headers=_AUTH, json={"score": 0.5})
        body = resp.json()
        assert body["status"] == "error"
        assert "not found" in body["detail"]


class TestServerMetrics:
    """Cover /v1/metrics endpoint."""

    def test_metrics_basic(self, monkeypatch, tmp_path):
        monkeypatch.setattr(server, "_effective_shadow_dir", lambda: tmp_path)
        monkeypatch.setattr(server, "_effective_log_paths",
            lambda: (tmp_path, tmp_path / "tl.json", tmp_path / "tl.jsonl"))
        resp = _client.get("/v1/metrics", headers=_AUTH)
        body = resp.json()
        assert "decide_files" in body
        assert body["decide_files"] == 0

    def test_metrics_with_files(self, monkeypatch, tmp_path):
        shadow = tmp_path / "shadow"
        shadow.mkdir()
        decide_f = shadow / "decide_001.json"
        decide_f.write_text(json.dumps({"created_at": "2025-01-01"}))
        jsonl = tmp_path / "tl.jsonl"
        jsonl.write_text("line1\nline2\n")
        monkeypatch.setattr(server, "_effective_shadow_dir", lambda: shadow)
        monkeypatch.setattr(server, "_effective_log_paths",
            lambda: (tmp_path, tmp_path / "tl.json", jsonl))
        resp = _client.get("/v1/metrics", headers=_AUTH)
        body = resp.json()
        assert body["decide_files"] == 1
        assert body["trust_jsonl_lines"] == 2


class TestServerTrustLogs:
    """Cover /v1/trust/logs and /v1/trust/{request_id}."""

    def test_trust_logs_endpoint(self, monkeypatch):
        monkeypatch.setattr(server, "get_trust_log_page", lambda **kw: {"items": [], "cursor": None})
        resp = _client.get("/v1/trust/logs", headers=_AUTH)
        assert resp.status_code == 200

    def test_trust_log_by_request(self, monkeypatch):
        monkeypatch.setattr(server, "get_trust_logs_by_request", lambda **kw: {"items": []})
        resp = _client.get("/v1/trust/test-req-123", headers=_AUTH)
        assert resp.status_code == 200


class TestServerStorePutGetSearch:
    """Cover _store_put, _store_get, _store_search fallback paths."""

    def test_store_put_no_put_method(self):
        with pytest.raises(RuntimeError, match="store.put not found"):
            server._store_put(SimpleNamespace(), "u", "k", {})

    def test_store_get_no_get_method(self):
        with pytest.raises(RuntimeError, match="store.get not found"):
            server._store_get(SimpleNamespace(), "u", "k")

    def test_store_search_no_search_method(self):
        with pytest.raises(RuntimeError, match="store.search not found"):
            server._store_search(SimpleNamespace(), query="q", k=5, kinds=None, min_sim=0.25, user_id="u")

    def test_store_put_fallback_signatures(self):
        """_store_put tries multiple signatures."""
        calls = []
        def two_arg_put(key, val):
            calls.append(("two", key, val))
        store = SimpleNamespace(put=two_arg_put)
        server._store_put(store, "uid", "mykey", {"v": 1})
        assert len(calls) == 1

    def test_store_get_fallback_signatures(self):
        """_store_get tries multiple signatures."""
        def one_arg_get(key):
            return {"data": key}
        store = SimpleNamespace(get=one_arg_get)
        result = server._store_get(store, "uid", "mykey")
        assert result["data"] == "mykey"

    def test_store_search_fallback_signatures(self):
        """_store_search tries multiple signatures."""
        def simple_search(query):
            return [{"id": "1", "score": 0.9}]
        store = SimpleNamespace(search=simple_search)
        result = server._store_search(store, query="q", k=5, kinds=None, min_sim=0.25, user_id="u")
        assert len(result) == 1


class TestServerMiscCoverage:
    """Cover misc uncovered paths in server.py."""

    def test_status_endpoint_debug_mode(self, monkeypatch):
        monkeypatch.setenv("VERITAS_DEBUG_MODE", "1")
        resp = _client.get("/status")
        body = resp.json()
        assert "version" in body

    def test_load_logs_json_missing_file(self, monkeypatch, tmp_path):
        missing = tmp_path / "no_file.json"
        result = server._load_logs_json(missing)
        assert result == []

    def test_load_logs_json_dict_format(self, monkeypatch, tmp_path):
        f = tmp_path / "log.json"
        f.write_text(json.dumps({"items": [{"a": 1}]}))
        result = server._load_logs_json(f)
        assert result == [{"a": 1}]

    def test_load_logs_json_list_format(self, monkeypatch, tmp_path):
        f = tmp_path / "log.json"
        f.write_text(json.dumps([{"a": 1}]))
        result = server._load_logs_json(f)
        assert result == [{"a": 1}]

    def test_load_logs_json_invalid(self, monkeypatch, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("not json")
        result = server._load_logs_json(f)
        assert result == []

    def test_save_json(self, tmp_path):
        p = tmp_path / "out.json"
        server._save_json(p, [{"x": 1}])
        data = json.loads(p.read_text())
        assert data["items"] == [{"x": 1}]

    def test_append_trust_log_basic(self, tmp_path, monkeypatch):
        monkeypatch.setattr(server, "_effective_log_paths",
            lambda: (tmp_path, tmp_path / "tl.json", tmp_path / "tl.jsonl"))
        server.append_trust_log({"action": "test", "score": 0.5})
        jsonl = tmp_path / "tl.jsonl"
        assert jsonl.exists()

    def test_coerce_alt_list_with_items(self):
        result = server._coerce_alt_list([
            {"title": "A", "score": "0.9"},
            "plain",
        ])
        assert len(result) == 2
        assert result[0]["score"] == 0.9
        assert result[1]["title"] == "plain"

    def test_coerce_decide_payload_missing_chosen(self):
        result = server._coerce_decide_payload({"ok": True})
        assert result["chosen"] == {}
        assert isinstance(result["alternatives"], list)

    def test_coerce_decide_payload_non_dict_chosen(self):
        result = server._coerce_decide_payload({"chosen": "text"})
        assert result["chosen"]["title"] == "text"

    def test_format_sse_message(self):
        event = {"id": "e1", "type": "test", "data": "d"}
        msg = server._format_sse_message(event)
        assert "id: e1" in msg
        assert "event: test" in msg

    def test_publish_event_no_crash(self):
        """_publish_event should never raise."""
        server._publish_event("test_event", {"ok": True})

    def test_get_api_secret_placeholder(self, monkeypatch):
        """Placeholder secret returns empty bytes."""
        monkeypatch.setattr(server, "API_SECRET", b"")
        monkeypatch.setenv("VERITAS_API_SECRET", "YOUR_VERITAS_API_SECRET_HERE")
        result = server._get_api_secret()
        assert result == b""

    def test_get_api_secret_short(self, monkeypatch):
        """Short secret still works but logs warning."""
        monkeypatch.setattr(server, "API_SECRET", b"")
        monkeypatch.setenv("VERITAS_API_SECRET", "short")
        result = server._get_api_secret()
        assert result == b"short"

    def test_require_api_key_header_or_query_no_key(self, monkeypatch):
        """SSE auth endpoint rejects missing key."""
        from fastapi import HTTPException
        monkeypatch.setenv("VERITAS_API_KEY", _TEST_KEY)
        with pytest.raises(HTTPException) as exc:
            server.require_api_key_header_or_query(x_api_key=None, api_key=None)
        assert exc.value.status_code == 401

    def test_require_api_key_header_or_query_valid(self, monkeypatch):
        """SSE auth endpoint accepts valid key."""
        monkeypatch.setenv("VERITAS_API_KEY", _TEST_KEY)
        result = server.require_api_key_header_or_query(x_api_key=_TEST_KEY, api_key=None)
        assert result is True

    def test_verify_signature_bad_utf8(self, monkeypatch):
        """Non-UTF-8 body raises 400."""
        monkeypatch.setattr(server, "API_SECRET", b"secret-for-test-1234567890abcdef")
        import asyncio

        class _Req:
            async def body(self):
                return b"\xff\xfe"

        ts = str(int(time.time()))
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            asyncio.run(server.verify_signature(
                _Req(), x_api_key="k", x_timestamp=ts, x_nonce="n", x_signature="sig",
            ))
        assert exc.value.status_code == 400


# ================================================================
# 7. trust_log.py — target: lines 65, 108, 150, 153-154, 162-164,
#    355, 368, 372, 383, 386-387, 389-390, 420, 425, 443-447,
#    474, 491-492, 496, 546, 550, 554-555, 572, 612-614
# ================================================================
from veritas_os.logging import trust_log as tl_mod


class TestTrustLogHelpers:
    def test_sha256_bytes_input(self):
        """Cover line 65: _sha256 with bytes data."""
        result = tl_mod._sha256(b"hello")
        assert isinstance(result, str) and len(result) == 64

    def test_sha256_str_input(self):
        result = tl_mod._sha256("hello")
        assert isinstance(result, str) and len(result) == 64

    def test_extract_last_sha256_empty_lines(self):
        """Cover line 108: empty line skip."""
        result = tl_mod._extract_last_sha256_from_lines(["", "", ""])
        assert result is None

    def test_extract_last_sha256_with_valid(self):
        lines = ['{"action":"test"}', '{"sha256":"abc123"}', ""]
        result = tl_mod._extract_last_sha256_from_lines(lines)
        assert result == "abc123"

    def test_extract_last_sha256_bad_json(self):
        lines = ["bad json", '{"sha256":"ok"}']
        result = tl_mod._extract_last_sha256_from_lines(lines)
        assert result == "ok"


class TestTrustLogGetLastHash:
    def test_get_last_hash_missing_file(self, monkeypatch, tmp_path):
        """Cover line 150: file does not exist."""
        monkeypatch.setattr(tl_mod, "LOG_JSONL", tmp_path / "nope.jsonl")
        result = tl_mod.get_last_hash()
        assert result is None

    def test_get_last_hash_empty_file(self, monkeypatch, tmp_path):
        """Cover: empty file returns marker or None."""
        f = tmp_path / "trust_log.jsonl"
        f.write_text("")
        monkeypatch.setattr(tl_mod, "LOG_JSONL", f)
        result = tl_mod.get_last_hash()
        assert result is None

    def test_get_last_hash_with_data(self, monkeypatch, tmp_path):
        f = tmp_path / "trust_log.jsonl"
        f.write_text('{"sha256":"hash123","action":"test"}\n')
        monkeypatch.setattr(tl_mod, "LOG_JSONL", f)
        result = tl_mod.get_last_hash()
        assert result == "hash123"


class TestTrustLogIterAndLoad:
    def test_iter_trust_log_missing_file(self, monkeypatch, tmp_path):
        """Cover line 355: LOG_JSONL doesn't exist."""
        monkeypatch.setattr(tl_mod, "LOG_JSONL", tmp_path / "nope.jsonl")
        result = list(tl_mod.iter_trust_log(reverse=False))
        assert result == []

    def test_iter_trust_log_reverse_with_data(self, monkeypatch, tmp_path):
        """Cover lines 368, 372: reverse iteration with empty/bad lines."""
        f = tmp_path / "trust_log.jsonl"
        f.write_text('{"a":1}\nbad json\n\n{"b":2}\n')
        monkeypatch.setattr(tl_mod, "LOG_JSONL", f)
        result = list(tl_mod.iter_trust_log(reverse=True))
        assert len(result) == 2
        assert result[0] == {"b": 2}

    def test_iter_trust_log_forward_with_data(self, monkeypatch, tmp_path):
        """Cover lines 383, 386-387: forward iteration."""
        f = tmp_path / "trust_log.jsonl"
        f.write_text('\n{"a":1}\nbad\n{"b":2}\n')
        monkeypatch.setattr(tl_mod, "LOG_JSONL", f)
        result = list(tl_mod.iter_trust_log(reverse=False))
        assert len(result) == 2

    def test_load_trust_log_with_limit(self, monkeypatch, tmp_path):
        f = tmp_path / "trust_log.jsonl"
        f.write_text('{"a":1}\n{"b":2}\n{"c":3}\n')
        monkeypatch.setattr(tl_mod, "LOG_JSONL", f)
        result = tl_mod.load_trust_log(limit=2)
        assert len(result) == 2

    def test_get_trust_log_entry_empty_id(self, monkeypatch, tmp_path):
        """Cover line 420: empty request_id returns None."""
        monkeypatch.setattr(tl_mod, "LOG_JSONL", tmp_path / "nope.jsonl")
        result = tl_mod.get_trust_log_entry("")
        assert result is None

    def test_get_trust_log_entry_not_found(self, monkeypatch, tmp_path):
        """Cover line 425: request_id not in any entry."""
        f = tmp_path / "trust_log.jsonl"
        f.write_text('{"request_id":"other","a":1}\n')
        monkeypatch.setattr(tl_mod, "LOG_JSONL", f)
        result = tl_mod.get_trust_log_entry("missing")
        assert result is None


class TestTrustLogPagination:
    def test_coerce_pagination_with_cursor(self):
        """Cover lines 443-447: cursor parsing."""
        offset, limit = tl_mod._coerce_pagination("5", 10)
        assert offset == 5
        assert limit == 10

    def test_coerce_pagination_bad_cursor(self):
        """Bad cursor defaults to 0."""
        offset, limit = tl_mod._coerce_pagination("bad", 10)
        assert offset == 0

    def test_coerce_pagination_none_cursor(self):
        offset, limit = tl_mod._coerce_pagination(None, 10)
        assert offset == 0


class TestTrustLogsByRequest:
    def test_empty_request_id(self, monkeypatch, tmp_path):
        """Cover line 474: empty request_id."""
        monkeypatch.setattr(tl_mod, "LOG_JSONL", tmp_path / "nope.jsonl")
        result = tl_mod.get_trust_logs_by_request("")
        assert result["count"] == 0
        assert result["chain_ok"] is False

    def test_not_found_request_id(self, monkeypatch, tmp_path):
        """Cover line 496: no matching entries."""
        f = tmp_path / "trust_log.jsonl"
        f.write_text('{"request_id":"other"}\n')
        monkeypatch.setattr(tl_mod, "LOG_JSONL", f)
        result = tl_mod.get_trust_logs_by_request("missing")
        assert result["verification_result"] == "not_found"

    def test_chain_broken(self, monkeypatch, tmp_path):
        """Cover lines 491-492: chain mismatch."""
        f = tmp_path / "trust_log.jsonl"
        entries = [
            {"request_id": "r1", "sha256": "aaa", "sha256_prev": None},
            {"request_id": "r1", "sha256": "bbb", "sha256_prev": "WRONG"},
        ]
        f.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
        monkeypatch.setattr(tl_mod, "LOG_JSONL", f)
        result = tl_mod.get_trust_logs_by_request("r1")
        assert result["chain_ok"] is False


class TestVerifyTrustLog:
    def test_verify_missing_file(self, monkeypatch, tmp_path):
        monkeypatch.setattr(tl_mod, "LOG_JSONL", tmp_path / "nope.jsonl")
        result = tl_mod.verify_trust_log()
        assert result["ok"] is True
        assert result["checked"] == 0

    def test_verify_empty_lines_skipped(self, monkeypatch, tmp_path):
        """Cover line 550: empty lines in JSONL are skipped."""
        f = tmp_path / "trust_log.jsonl"
        f.write_text("\n\n")
        monkeypatch.setattr(tl_mod, "LOG_JSONL", f)
        result = tl_mod.verify_trust_log()
        assert result["ok"] is True
        assert result["checked"] == 0

    def test_verify_bad_json(self, monkeypatch, tmp_path):
        """Cover lines 554-555: bad JSON returns broken."""
        f = tmp_path / "trust_log.jsonl"
        f.write_text("not-json\n")
        monkeypatch.setattr(tl_mod, "LOG_JSONL", f)
        result = tl_mod.verify_trust_log()
        assert result["ok"] is False
        assert result["broken_reason"] == "json_decode_error"

    def test_verify_max_entries(self, monkeypatch, tmp_path):
        """Cover line 546: max_entries limits verification."""
        f = tmp_path / "trust_log.jsonl"
        # Create valid chain entries
        entries = []
        prev_hash = None
        for i in range(5):
            entry = {"request_id": f"r{i}", "sha256_prev": prev_hash}
            entry_json = json.dumps(
                {k: v for k, v in entry.items() if k not in ("sha256", "sha256_prev")},
                sort_keys=True, ensure_ascii=False,
            )
            combined = (prev_hash or "") + entry_json
            import hashlib
            sha = hashlib.sha256(combined.encode("utf-8")).hexdigest()
            entry["sha256"] = sha
            entries.append(entry)
            prev_hash = sha
        f.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
        monkeypatch.setattr(tl_mod, "LOG_JSONL", f)
        result = tl_mod.verify_trust_log(max_entries=2)
        assert result["ok"] is True
        assert result["checked"] == 2


# ================================================================
# 8. server.py write_shadow_decide coverage
# ================================================================

class TestServerWriteShadowDecide:
    def test_write_shadow_decide_basic(self, monkeypatch, tmp_path):
        shadow = tmp_path / "shadow"
        shadow.mkdir()
        monkeypatch.setattr(server, "_effective_shadow_dir", lambda: shadow)
        server.write_shadow_decide(
            request_id="req1",
            body={"query": "test"},
            chosen={"title": "A"},
            telos_score=0.8,
            fuji={"status": "allow"},
        )
        files = list(shadow.glob("decide_*.json"))
        assert len(files) == 1

    def test_write_shadow_decide_mkdir_fails(self, monkeypatch, tmp_path):
        """Cover lines 1207-1209: mkdir failure returns silently."""
        # Point to a path that can't be created
        monkeypatch.setattr(server, "_effective_shadow_dir", lambda: Path("/proc/veritas_shadow"))
        # Should not raise
        server.write_shadow_decide(
            request_id="req1",
            body={},
            chosen={},
            telos_score=0.0,
            fuji=None,
        )


# ================================================================
# 9. Additional server.py lazy_state coverage
# ================================================================

class TestServerLazyImport:
    def test_get_decision_pipeline_import_fail(self, monkeypatch):
        """Cover get_decision_pipeline error path."""
        server._pipeline_state = server._LazyState()
        monkeypatch.setattr(
            "importlib.import_module",
            lambda name: (_ for _ in ()).throw(ImportError("no pipeline")),
        )
        result = server.get_decision_pipeline()
        # Restore
        server._pipeline_state = server._LazyState()
        assert result is None

    def test_get_decision_pipeline_cached_error(self, monkeypatch):
        """When pipeline import already failed, return None without retry."""
        server._pipeline_state = server._LazyState(attempted=True, err="previous failure")
        result = server.get_decision_pipeline()
        server._pipeline_state = server._LazyState()
        assert result is None


# ================================================================
# 10. Push over 85% — additional trust_log, server, memory coverage
# ================================================================


class TestTrustLogVerifyChain:
    def test_verify_sha256_prev_mismatch(self, monkeypatch, tmp_path):
        """Cover line 572: sha256_prev mismatch detected."""
        import hashlib as _hl
        f = tmp_path / "trust_log.jsonl"
        # First entry (valid)
        e1 = {"request_id": "r1"}
        e1_json = json.dumps(e1, sort_keys=True, ensure_ascii=False)
        e1["sha256"] = _hl.sha256(e1_json.encode()).hexdigest()
        e1["sha256_prev"] = None
        # Second entry (broken chain)
        e2 = {"request_id": "r2", "sha256_prev": "WRONG_HASH"}
        e2_json = json.dumps(
            {k: v for k, v in e2.items() if k not in ("sha256", "sha256_prev")},
            sort_keys=True, ensure_ascii=False,
        )
        e2["sha256"] = _hl.sha256(("WRONG_HASH" + e2_json).encode()).hexdigest()
        f.write_text(json.dumps(e1) + "\n" + json.dumps(e2) + "\n")
        monkeypatch.setattr(tl_mod, "LOG_JSONL", f)
        result = tl_mod.verify_trust_log()
        assert result["ok"] is False
        assert result["broken_reason"] == "sha256_prev_mismatch"


class TestServerExtraCoverage:
    def test_status_debug_shows_errors(self, monkeypatch):
        monkeypatch.setenv("VERITAS_DEBUG_MODE", "1")
        old_err = server._cfg_state.err
        server._cfg_state.err = "some error"
        resp = _client.get("/status")
        server._cfg_state.err = old_err
        body = resp.json()
        assert "cfg_error" in body

    def test_metrics_debug_mode(self, monkeypatch, tmp_path):
        monkeypatch.setenv("VERITAS_DEBUG_MODE", "1")
        monkeypatch.setattr(server, "_effective_shadow_dir", lambda: tmp_path)
        monkeypatch.setattr(server, "_effective_log_paths",
            lambda: (tmp_path, tmp_path / "tl.json", tmp_path / "tl.jsonl"))
        resp = _client.get("/v1/metrics", headers=_AUTH)
        assert resp.status_code == 200

    def test_memory_search_exception_handled(self, monkeypatch):
        def bad_search(**kw):
            raise RuntimeError("search fail")
        store = SimpleNamespace(search=bad_search)
        monkeypatch.setattr(server, "get_memory_store", lambda: store)
        resp = _client.post("/v1/memory/search", headers=_AUTH, json={
            "query": "test", "user_id": "u1",
        })
        assert resp.json()["ok"] is False

    def test_memory_get_exception_handled(self, monkeypatch):
        def bad_get(*a, **kw):
            raise RuntimeError("get fail")
        store = SimpleNamespace(get=bad_get)
        monkeypatch.setattr(server, "get_memory_store", lambda: store)
        resp = _client.post("/v1/memory/get", headers=_AUTH, json={
            "user_id": "u1", "key": "k1",
        })
        assert resp.json()["ok"] is False

    def test_memory_search_non_dict_raw_hits(self, monkeypatch):
        store = SimpleNamespace(search=lambda **kw: iter([]))
        monkeypatch.setattr(server, "get_memory_store", lambda: store)
        resp = _client.post("/v1/memory/search", headers=_AUTH, json={
            "query": "test", "user_id": "u1",
        })
        assert resp.json()["ok"] is True

    def test_trust_feedback_exception(self, monkeypatch):
        class BadVC:
            @staticmethod
            def append_trust_log(**kw):
                raise RuntimeError("log fail")
        monkeypatch.setattr(server, "get_value_core", lambda: BadVC)
        resp = _client.post("/v1/trust/feedback", headers=_AUTH, json={"score": 0.5})
        body = resp.json()
        assert body["status"] == "error"

    def test_redact_sanitize_fails_fallback(self, monkeypatch):
        def bad_mask(t):
            raise RuntimeError("sanitize broken")
        monkeypatch.setattr(server, "_HAS_SANITIZE", True)
        monkeypatch.setattr(server, "_sanitize_mask_pii", bad_mask)
        result = server.redact("contact user@example.com today")
        assert "user@example.com" not in result

    def test_append_trust_log_mkdir_fail(self, monkeypatch):
        """Cover lines 1165-1167: mkdir failure."""
        monkeypatch.setattr(server, "_effective_log_paths",
            lambda: (Path("/proc/no_write"), Path("/proc/no_write/tl.json"), Path("/proc/no_write/tl.jsonl")))
        # Should not raise
        server.append_trust_log({"action": "test"})

    def test_memory_put_with_value_and_text(self, monkeypatch):
        """Cover legacy + vector put paths."""
        calls = []
        def fake_put(kind, item):
            calls.append((kind, item))
            return "new-id"
        store = SimpleNamespace(put=fake_put)
        monkeypatch.setattr(server, "get_memory_store", lambda: store)
        resp = _client.post("/v1/memory/put", headers=_AUTH, json={
            "value": {"k": "v"}, "text": "hello world", "user_id": "u1",
            "tags": ["t1"], "kind": "episodic",
        })
        body = resp.json()
        assert body["ok"] is True
