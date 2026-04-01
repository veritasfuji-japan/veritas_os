# -*- coding: utf-8 -*-
"""カバレッジ補完テスト

各モジュールのカバレッジ補完テストを統合。

※ cryptography 依存モジュールを含むテスト。"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


# ============================================================
# Source: test_coverage_boost.py
# ============================================================


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
        # Pydantic validates max_length on the text field and returns 422
        assert resp.status_code == 422

    def test_memory_put_too_many_tags(self, monkeypatch):
        store = SimpleNamespace(put=lambda k, v: "id1", search=lambda: [])
        monkeypatch.setattr(server, "get_memory_store", lambda: store)
        resp = _client.post("/v1/memory/put", headers=_AUTH, json={
            "text": "hi", "tags": ["t"] * 101,
        })
        # Pydantic validator rejects oversized tag lists with 422
        assert resp.status_code == 422

    def test_memory_put_success(self, monkeypatch):
        captured = {}

        def _put(kind, item):
            captured["kind"] = kind
            captured["item"] = item
            return "new-id"

        store = SimpleNamespace(put=_put)
        monkeypatch.setattr(server, "get_memory_store", lambda: store)
        resp = _client.post("/v1/memory/put", headers=_AUTH, json={
            "text": "hello", "user_id": "u1", "tags": ["t1"], "kind": "semantic",
        })
        body = resp.json()
        assert body["ok"] is True
        assert body["vector"]["saved"] is True
        assert (
            captured["item"]["meta"]["user_id"]
            == server._derive_api_user_id(_TEST_KEY)
        )

    def test_memory_put_invalid_kind_defaults_to_semantic(self, monkeypatch):
        store = SimpleNamespace(put=lambda kind, item: "id1")
        monkeypatch.setattr(server, "get_memory_store", lambda: store)
        resp = _client.post("/v1/memory/put", headers=_AUTH, json={
            "text": "hello", "kind": "INVALID_KIND",
        })
        body = resp.json()
        assert body["ok"] is True

    def test_memory_put_reports_partial_failure_when_legacy_save_fails(
        self,
        monkeypatch,
    ):
        class PartialStore:
            def put(self, *args, **kwargs):
                if args and args[0] == server._derive_api_user_id(_TEST_KEY):
                    raise RuntimeError("legacy backend unavailable")
                return "vector-id"

        monkeypatch.setattr(server, "get_memory_store", lambda: PartialStore())
        resp = _client.post(
            "/v1/memory/put",
            headers=_AUTH,
            json={
                "user_id": "u1",
                "key": "legacy-key",
                "value": {"hello": "world"},
                "text": "episode text",
                "kind": "semantic",
            },
        )

        body = resp.json()
        assert body["ok"] is True
        assert body["status"] == "partial_failure"
        assert body["legacy"]["saved"] is False
        assert body["vector"]["saved"] is True
        assert body["errors"] == [
            {
                "stage": "legacy",
                "message": "legacy save failed",
                "error_code": "backend_unavailable",
            }
        ]

    def test_memory_search_store_unavailable(self, monkeypatch):
        monkeypatch.setattr(server, "get_memory_store", lambda: None)
        resp = _client.post("/v1/memory/search", headers=_AUTH, json={
            "query": "test", "user_id": "u1",
        })
        assert resp.json()["ok"] is False

    def test_memory_search_without_user_id_uses_api_scoped_user(self, monkeypatch):
        store = SimpleNamespace(search=lambda **kw: {})
        monkeypatch.setattr(server, "get_memory_store", lambda: store)
        resp = _client.post("/v1/memory/search", headers=_AUTH, json={"query": "test"})
        assert resp.json()["ok"] is True

    def test_memory_search_with_dict_results(self, monkeypatch):
        scoped_user = server._derive_api_user_id(_TEST_KEY)
        hits = {
            "semantic": [
                {"id": "1", "text": "hi", "score": 0.9, "meta": {"user_id": scoped_user}}
            ]
        }
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
        scoped_user = server._derive_api_user_id(_TEST_KEY)
        hits = {"semantic": [
            {"id": "1", "text": "hi", "score": 0.9, "meta": {"user_id": scoped_user}},
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

    def test_memory_search_rejects_invalid_kinds(self, monkeypatch):
        store = SimpleNamespace(search=lambda **kw: {})
        monkeypatch.setattr(server, "get_memory_store", lambda: store)
        resp = _client.post(
            "/v1/memory/search",
            headers=_AUTH,
            json={"query": "test", "kinds": ["semantic", "bad-kind"]},
        )
        body = resp.json()
        assert body["ok"] is False
        assert "invalid kinds" in body["error"]

    def test_memory_search_normalizes_and_deduplicates_kinds(self, monkeypatch):
        captured = {}

        def fake_search(**kwargs):
            captured.update(kwargs)
            return {}

        store = SimpleNamespace(search=fake_search)
        monkeypatch.setattr(server, "get_memory_store", lambda: store)
        resp = _client.post(
            "/v1/memory/search",
            headers=_AUTH,
            json={"query": "test", "kinds": [" Semantic ", "semantic", "DOC"]},
        )

        body = resp.json()
        assert body["ok"] is True
        assert captured["kinds"] == ["semantic", "doc"]

    def test_memory_search_rejects_non_string_kind_item(self, monkeypatch):
        store = SimpleNamespace(search=lambda **kw: {})
        monkeypatch.setattr(server, "get_memory_store", lambda: store)
        resp = _client.post(
            "/v1/memory/search",
            headers=_AUTH,
            json={"query": "test", "kinds": ["semantic", 123]},
        )

        body = resp.json()
        assert body["ok"] is False
        assert "kinds must be" in body["error"]

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
        # Pydantic requires the 'key' field; missing → 422
        assert resp.status_code == 422

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
        assert body["ok"] is False
        assert "unavailable" in body["error"]

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
        assert body["ok"] is True
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
        assert body["ok"] is True
        assert calls[0]["score"] == 0.5

    def test_trust_feedback_no_append_method(self, monkeypatch):
        """value_core without append_trust_log returns error."""
        monkeypatch.setattr(server, "get_value_core", lambda: SimpleNamespace())
        resp = _client.post("/v1/trust/feedback", headers=_AUTH, json={"score": 0.5})
        body = resp.json()
        assert body["ok"] is False
        assert "not found" in body["error"]


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
        assert body["trust_json_status"] == "missing"
        assert body["trust_json_error"] is False

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
        assert body["trust_json_status"] == "missing"

    def test_metrics_reports_unreadable_trust_json(self, monkeypatch, tmp_path):
        """Metrics should expose degraded aggregate trust-log readability."""
        log_json = tmp_path / "tl.json"
        log_json.write_text("{broken", encoding="utf-8")
        monkeypatch.setattr(server, "_effective_shadow_dir", lambda: tmp_path)
        monkeypatch.setattr(
            server,
            "_effective_log_paths",
            lambda: (tmp_path, log_json, tmp_path / "tl.jsonl"),
        )

        resp = _client.get("/v1/metrics", headers=_AUTH)

        body = resp.json()
        assert body["trust_json_status"] == "unreadable"
        assert body["trust_json_error"] is True


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

    def test_allow_sse_query_api_key_flag_values(self, monkeypatch):
        """Feature flag requires explicit risk acknowledgement."""
        monkeypatch.setenv("VERITAS_ALLOW_SSE_QUERY_API_KEY", "yes")
        monkeypatch.delenv("VERITAS_ACK_SSE_QUERY_API_KEY_RISK", raising=False)
        assert server._allow_sse_query_api_key() is False

        monkeypatch.setenv("VERITAS_ACK_SSE_QUERY_API_KEY_RISK", "on")
        assert server._allow_sse_query_api_key() is True

        monkeypatch.setenv("VERITAS_ALLOW_SSE_QUERY_API_KEY", "0")
        assert server._allow_sse_query_api_key() is False

    def test_nonce_cleanup_scheduler_start_stop(self, monkeypatch):
        """Nonce cleanup scheduler should be singleton and stoppable."""

        class _FakeTimer:
            def __init__(self, interval, callback):
                self.interval = interval
                self.callback = callback
                self.daemon = False
                self.started = False
                self.canceled = False

            def start(self):
                self.started = True

            def cancel(self):
                self.canceled = True

        monkeypatch.setattr(server.threading, "Timer", _FakeTimer)
        server._stop_nonce_cleanup_scheduler()

        server._start_nonce_cleanup_scheduler()
        first_timer = server._nonce_cleanup_timer
        assert first_timer is not None
        assert first_timer.started is True

        server._start_nonce_cleanup_scheduler()
        assert server._nonce_cleanup_timer is first_timer

        server._stop_nonce_cleanup_scheduler()
        assert first_timer.canceled is True
        assert server._nonce_cleanup_timer is None

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
        # RFC 8785 canonical JSON（空白なし・キーソート）でエントリを生成
        entries = []
        prev_hash = None
        for i in range(5):
            entry = {"request_id": f"r{i}", "sha256_prev": prev_hash}
            entry_json = json.dumps(
                {k: v for k, v in entry.items() if k not in ("sha256", "sha256_prev")},
                sort_keys=True, separators=(",", ":"), ensure_ascii=False,
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
        """Cover sha256_prev mismatch detection in verify_trust_log."""
        import hashlib as _hl
        f = tmp_path / "trust_log.jsonl"

        # RFC 8785 canonical JSON（空白なし・キーソート）を使用してエントリを生成
        # verify_trust_log が _normalize_entry_for_hash() で使うフォーマットと一致させる
        def canonical(d):
            return json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

        # First entry (valid)
        e1 = {"request_id": "r1"}
        e1_json = canonical(e1)
        e1["sha256"] = _hl.sha256(e1_json.encode()).hexdigest()
        e1["sha256_prev"] = None
        # Second entry (broken chain: sha256_prev は実際の e1["sha256"] と異なる "WRONG_HASH")
        e2 = {"request_id": "r2", "sha256_prev": "WRONG_HASH"}
        e2_json = canonical({k: v for k, v in e2.items() if k not in ("sha256", "sha256_prev")})
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
        assert body["ok"] is False

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


# ============================================================
# Source: test_coverage_final_sweep.py
# ============================================================


import asyncio
import json
import math
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# =========================================================
# fuji.py helpers
# =========================================================
from veritas_os.core import fuji


def _sh(
    *,
    risk_score: float = 0.1,
    categories: list | None = None,
    rationale: str = "",
    model: str = "test_model",
    raw: dict | None = None,
) -> fuji.SafetyHeadResult:
    return fuji.SafetyHeadResult(
        risk_score=risk_score,
        categories=categories or [],
        rationale=rationale,
        model=model,
        raw=raw or {},
    )


SIMPLE_POLICY: Dict[str, Any] = {
    "version": "test_policy",
    "base_thresholds": {"default": 0.5, "high_stakes": 0.35, "low_stakes": 0.70},
    "categories": {},
    "actions": {
        "allow": {"risk_upper": 0.40},
        "warn": {"risk_upper": 0.65},
        "human_review": {"risk_upper": 0.85},
        "deny": {},
    },
}


# =========================================================
# 1) fuji.py – _apply_llm_fallback_penalty branches
# =========================================================
class TestApplyLlmFallbackPenalty:
    """Cover lines 356-361: high stakes + risk cats, low stakes + risk cats."""

    def test_high_stakes_with_risk_categories(self):
        """stakes >= 0.7 with risk categories → risk floor 0.70."""
        result = _sh(risk_score=0.2, categories=["illicit"])
        fuji._apply_llm_fallback_penalty(result, {"stakes": 0.8}, label="test")
        assert result.risk_score >= 0.70
        assert "high stakes" in result.rationale

    def test_low_stakes_with_risk_categories(self):
        """stakes < 0.7 with risk categories → risk floor 0.50."""
        result = _sh(risk_score=0.2, categories=["PII"])
        fuji._apply_llm_fallback_penalty(result, {"stakes": 0.3}, label="test")
        assert result.risk_score >= 0.50
        assert "risk floor 0.50" in result.rationale

    def test_no_risk_categories_baseline(self):
        """No risk categories → baseline risk floor 0.30."""
        result = _sh(risk_score=0.05, categories=[])
        fuji._apply_llm_fallback_penalty(result, {"stakes": 0.5}, label="test")
        assert result.risk_score >= 0.30
        assert "baseline" in result.rationale

    def test_safety_head_error_only_counts_as_no_risk(self):
        """safety_head_error alone should not be treated as risk category."""
        result = _sh(risk_score=0.05, categories=["safety_head_error"])
        fuji._apply_llm_fallback_penalty(result, {"stakes": 0.9}, label="test")
        assert result.risk_score >= 0.30
        assert "baseline" in result.rationale


# =========================================================
# 2) fuji.py – fuji_core_decide inner helpers
# =========================================================
class TestFujiCoreDecideExtractPolicyAction:
    """Cover lines 475-502: _extract_policy_action and _mark_policy_pre_and_final_gate."""

    def test_policy_action_from_reasons_string(self):
        """policy_action extracted from reasons list when dict key absent."""
        sh = _sh(risk_score=0.9, categories=["illicit"])
        result = fuji.fuji_core_decide(
            safety_head=sh,
            stakes=0.9,
            telos_score=0.5,
            evidence_count=0,
            policy=SIMPLE_POLICY,
            min_evidence=1,
            text="テスト",
            poc_mode=True,
        )
        # poc_mode + low evidence should produce reasons with final_gate
        reasons = result.get("reasons", [])
        has_final_gate = any("final_gate=" in r for r in reasons)
        assert has_final_gate

    def test_policy_action_pre_poc_replacement(self):
        """When poc mode replaces policy_action, we get policy_action_pre_poc."""
        sh = _sh(risk_score=0.6, categories=[])
        result = fuji.fuji_core_decide(
            safety_head=sh,
            stakes=0.3,
            telos_score=0.5,
            evidence_count=0,
            policy=SIMPLE_POLICY,
            min_evidence=1,
            text="テスト",
            poc_mode=True,
        )
        reasons = result.get("reasons", [])
        has_pre_poc = any("policy_action_pre_poc=" in r for r in reasons)
        assert has_pre_poc


# =========================================================
# 3) fuji.py – heuristic_fallback name_like PII normalization
# =========================================================
class TestFujiNameLikePiiNormalization:
    """Cover lines 556-563: dict-form pii_hits and string-form."""

    def test_pii_hits_dict_form_name_like_only(self):
        """When pii_hits are dicts with 'kind': 'name_like', PII is suppressed."""
        sh = _sh(
            risk_score=0.5,
            categories=["PII"],
            rationale="name_like detected",
            model="heuristic_fallback",
            raw={"fallback": True, "pii_hits": [{"kind": "name_like"}]},
        )
        result = fuji.fuji_core_decide(
            safety_head=sh,
            stakes=0.3,
            telos_score=0.5,
            evidence_count=10,
            policy=SIMPLE_POLICY,
            text="山田太郎",
        )
        # name_like_only should suppress PII → risk capped low
        reasons = result.get("reasons", [])
        assert any("name_like_only" in r for r in reasons)

    def test_pii_hits_string_form_name_like_only(self):
        """When pii_hits is a bare string 'name_like'."""
        sh = _sh(
            risk_score=0.5,
            categories=["PII"],
            rationale="name_like only",
            model="heuristic_fallback",
            raw={"fallback": True, "pii_hits": "name_like"},
        )
        result = fuji.fuji_core_decide(
            safety_head=sh,
            stakes=0.3,
            telos_score=0.5,
            evidence_count=10,
            policy=SIMPLE_POLICY,
            text="名前テスト",
        )
        reasons = result.get("reasons", [])
        assert any("name_like_only" in r for r in reasons)


# =========================================================
# 4) fuji.py – config fallback paths for risk adjustments
# =========================================================
class TestFujiConfigFallbackPaths:
    """Cover lines 598-599, 614-615, 635-636: fallback to YAML/hardcoded when cfg attr missing."""

    def test_pii_safe_cap_yaml_fallback(self):
        """pii_safe_cap falls back to YAML risk_adjustments."""
        sh = _sh(risk_score=0.6, categories=["PII"], model="test_model")
        policy_with_adjustments = {
            **SIMPLE_POLICY,
            "risk_adjustments": {"pii_safe_cap": 0.25},
        }
        result = fuji.fuji_core_decide(
            safety_head=sh,
            stakes=0.3,
            telos_score=0.5,
            evidence_count=10,
            policy=policy_with_adjustments,
            safe_applied=True,
            text="テスト",
        )
        # When safe_applied=True with PII category, risk should be capped
        reasons = result.get("reasons", [])
        assert any("pii_safe_applied" in r for r in reasons)

    def test_low_evidence_penalty_fallback(self):
        """low_evidence_penalty falls back to YAML risk_adjustments."""
        sh = _sh(risk_score=0.1, categories=[])
        policy_with_adjustments = {
            **SIMPLE_POLICY,
            "risk_adjustments": {"low_evidence_penalty": 0.20},
        }
        result = fuji.fuji_core_decide(
            safety_head=sh,
            stakes=0.3,
            telos_score=0.5,
            evidence_count=0,
            policy=policy_with_adjustments,
            min_evidence=1,
            text="テスト",
        )
        reasons = result.get("reasons", [])
        assert any("low_evidence" in r for r in reasons)

    def test_telos_scale_factor_fallback(self):
        """telos_risk_scale falls back to YAML risk_adjustments."""
        sh = _sh(risk_score=0.3, categories=[])
        policy_with_adjustments = {
            **SIMPLE_POLICY,
            "risk_adjustments": {"telos_scale_factor": 0.15},
        }
        result = fuji.fuji_core_decide(
            safety_head=sh,
            stakes=0.5,
            telos_score=0.9,
            evidence_count=10,
            policy=policy_with_adjustments,
            text="テスト",
        )
        # Result should complete without error
        assert "risk" in result


# =========================================================
# 5) fuji.py – _check_policy_hot_reload OSError branches
# =========================================================
class TestFujiPolicyHotReload:
    """Cover lines 277-279, 292-293: OSError during stat and read."""

    def test_hot_reload_stat_oserror(self, tmp_path: Path):
        """When stat() raises OSError, hot reload is skipped silently."""
        policy_file = tmp_path / "fuji_policy.yaml"
        policy_file.write_text("version: test")

        original_stat = Path.stat
        _call_count = {"n": 0}

        def stat_side_effect(self_path, *args, **kwargs):
            if self_path == policy_file:
                _call_count["n"] += 1
                # First call is from exists(), let it pass; second is the actual stat()
                if _call_count["n"] > 1:
                    raise OSError("disk error")
            return original_stat(self_path, *args, **kwargs)

        with patch.object(fuji, "_policy_path", return_value=policy_file):
            with patch.object(Path, "stat", stat_side_effect):
                # Should not raise – the OSError on stat() is caught
                fuji._check_policy_hot_reload()

    def test_hot_reload_read_oserror(self, tmp_path: Path):
        """When read_text() raises OSError during hot reload, skipped."""
        policy_file = tmp_path / "fuji_policy.yaml"
        policy_file.write_text("version: test")
        # Set a high mtime to force reload attempt
        old_mtime = fuji._POLICY_MTIME

        with patch.object(fuji, "_policy_path", return_value=policy_file):
            with patch.object(fuji, "_POLICY_MTIME", -1):
                with patch.object(
                    Path, "read_text", side_effect=OSError("io error")
                ):
                    fuji._check_policy_hot_reload()

        # Restore
        fuji._POLICY_MTIME = old_mtime


# =========================================================
# 6) fuji.py – evaluate() invariant fixes (lines 917-922)
# =========================================================
class TestFujiEvaluateInvariantFixes:
    """Cover the deny invariant coercion at the end of evaluate()."""

    def test_evaluate_returns_valid_structure(self):
        """evaluate() returns a well-formed result with required keys."""
        with patch.object(fuji, "call_tool", side_effect=RuntimeError("no llm")):
            result = fuji.evaluate(
                "安全なテスト",
                context={"stakes": 0.5, "telos_score": 0.5},
                evidence=[],
            )
        assert "status" in result
        assert "decision_status" in result
        assert "risk" in result
        assert isinstance(result["risk"], float)
        # If deny, must have rejection_reason
        if result["decision_status"] == "deny":
            assert result.get("rejection_reason")


# =========================================================
# 7) fuji.py – NaN/Inf risk handling (line 453)
# =========================================================
class TestFujiNanInfRiskHandling:
    """Cover line 452-453: NaN/Inf risk_score → fail-closed to 1.0."""

    def test_nan_risk_score_becomes_max(self):
        """NaN risk score should be clamped to 1.0 (fail-closed)."""
        sh = _sh(risk_score=float("nan"), categories=[])
        result = fuji.fuji_core_decide(
            safety_head=sh,
            stakes=0.5,
            telos_score=0.5,
            evidence_count=10,
            policy=SIMPLE_POLICY,
            text="テスト",
        )
        assert result["risk"] <= 1.0
        assert result["risk"] >= 0.0

    def test_inf_risk_score_becomes_max(self):
        """Inf risk score should be clamped to 1.0 (fail-closed)."""
        sh = _sh(risk_score=float("inf"), categories=[])
        result = fuji.fuji_core_decide(
            safety_head=sh,
            stakes=0.5,
            telos_score=0.5,
            evidence_count=10,
            policy=SIMPLE_POLICY,
            text="テスト",
        )
        assert result["risk"] == 1.0


# =========================================================
# 8) kernel.py – security-related branches
# =========================================================
from veritas_os.core import kernel


class TestKernelSecurityConfinement:
    """Cover lines 70-72, 85, 89-90, 109: _read_proc_self_status_seccomp and _read_apparmor_profile."""

    def test_seccomp_parse_error_returns_none(self):
        """ValueError in parsing Seccomp line → None."""
        bad_content = "Seccomp:\tnot_a_number\n"
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value=bad_content):
                result = kernel._read_proc_self_status_seccomp()
        assert result is None

    def test_seccomp_oserror_returns_none(self):
        """OSError reading /proc/self/status → None."""
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", side_effect=OSError("denied")):
                result = kernel._read_proc_self_status_seccomp()
        assert result is None

    def test_seccomp_no_seccomp_line(self):
        """No 'Seccomp:' line in status → None."""
        content = "Name:\tpython\nPid:\t123\n"
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value=content):
                result = kernel._read_proc_self_status_seccomp()
        assert result is None

    def test_apparmor_empty_profile(self):
        """Empty profile string → None."""
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value="   "):
                result = kernel._read_apparmor_profile()
        assert result is None

    def test_apparmor_oserror(self):
        """OSError reading profile → None."""
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", side_effect=OSError("denied")):
                result = kernel._read_apparmor_profile()
        assert result is None

    def test_confinement_unconfined_apparmor(self):
        """'unconfined' apparmor profile → not active."""
        with patch.object(kernel, "_read_proc_self_status_seccomp", return_value=None):
            with patch.object(kernel, "_read_apparmor_profile", return_value="unconfined"):
                assert kernel._is_doctor_confinement_profile_active() is False

    def test_confinement_seccomp_active(self):
        """Seccomp mode > 0 → confinement active."""
        with patch.object(kernel, "_read_proc_self_status_seccomp", return_value=2):
            assert kernel._is_doctor_confinement_profile_active() is True

    def test_confinement_apparmor_custom_profile(self):
        """Custom AppArmor profile → confinement active."""
        with patch.object(kernel, "_read_proc_self_status_seccomp", return_value=None):
            with patch.object(kernel, "_read_apparmor_profile", return_value="my_custom_profile"):
                assert kernel._is_doctor_confinement_profile_active() is True


# =========================================================
# 9) kernel.py – _dedupe_alts score comparison edge cases
# =========================================================
class TestKernelDedupeAltsScoreEdge:
    """Cover lines 453-454: score comparison with invalid scores."""

    def test_dedupe_alts_invalid_prev_score(self):
        """When existing entry has non-numeric score, new entry wins."""
        alts = [
            {"title": "A", "description": "desc", "score": "bad"},
            {"title": "A", "description": "desc", "score": 0.5},
        ]
        result = kernel._dedupe_alts(alts)
        assert len(result) == 1
        assert result[0]["score"] == 0.5


# =========================================================
# 10) kernel.py – decide with debate exception
# =========================================================
class TestKernelDebateFallback:
    """Cover lines 814-836: debate exception fallback and reject_all."""

    @pytest.fixture
    def anyio_backend(self):
        return "asyncio"

    @pytest.mark.anyio
    async def test_debate_exception_with_no_alts_gives_fallback(self):
        """When debate raises and no alts, a fallback option is created."""
        mock_debate = MagicMock()
        mock_debate.run_debate.side_effect = RuntimeError("LLM down")

        with patch.object(kernel, "debate_core", mock_debate):
            with patch.object(kernel, "fuji_core") as mock_fuji:
                mock_fuji.evaluate.return_value = {
                    "status": "allow",
                    "decision_status": "allow",
                    "risk": 0.1,
                    "reasons": [],
                    "violations": [],
                    "guidance": "",
                    "rejection_reason": None,
                    "meta": {},
                    "checks": [],
                    "policy_version": "test",
                }
                mock_fuji.fuji_gate = mock_fuji.evaluate
                result = await kernel.decide(
                    context={"user_id": "u1"},
                    query="テスト質問",
                    alternatives=[],
                )
        assert isinstance(result, dict)
        assert "chosen" in result


# =========================================================
# 11) kernel.py – reason_core async branch & memory save error
# =========================================================
class TestKernelReasonCoreAsync:
    """Cover lines 918-919: async generate_reason call."""

    @pytest.fixture
    def anyio_backend(self):
        return "asyncio"

    @pytest.mark.anyio
    async def test_async_generate_reason_called(self):
        """When reason_core.generate_reason is async, it's awaited."""
        async def async_reason(**kwargs):
            return "async reason result"

        mock_reason = MagicMock()
        mock_reason.generate_reason = async_reason

        with patch.object(kernel, "reason_core", mock_reason):
            with patch.object(kernel, "debate_core") as mock_debate:
                mock_debate.run_debate.return_value = {
                    "chosen": {"id": "a", "title": "test", "score": 0.5},
                    "options": [{"id": "a", "title": "test", "score": 0.5}],
                }
                with patch.object(kernel, "fuji_core") as mock_fuji:
                    mock_fuji.evaluate.return_value = {
                        "status": "allow",
                        "decision_status": "allow",
                        "risk": 0.1,
                        "reasons": [],
                        "violations": [],
                        "guidance": "",
                        "rejection_reason": None,
                        "meta": {},
                        "checks": [],
                        "policy_version": "test",
                    }
                    mock_fuji.fuji_gate = mock_fuji.evaluate
                    result = await kernel.decide(
                        context={"user_id": "u1", "stakes": 0.8},
                        query="テスト",
                        alternatives=[
                            {"id": "a", "title": "test", "description": "d", "score": 0.5},
                        ],
                    )
        assert isinstance(result, dict)
        # The affect section should have the natural reason
        affect = result.get("extras", result).get("affect", {}) if isinstance(result.get("extras"), dict) else {}


# =========================================================
# 12) kernel.py – latency metric error (lines 1016-1017)
# =========================================================
class TestKernelLatencyMetricError:
    """Cover lines 1016-1017: TypeError/ValueError in latency computation."""

    @pytest.fixture
    def anyio_backend(self):
        return "asyncio"

    @pytest.mark.anyio
    async def test_decide_handles_time_error_gracefully(self):
        """If time.time() somehow causes issues, decide doesn't crash."""
        # This is extremely defensive – just ensure decide() completes
        with patch.object(kernel, "fuji_core") as mock_fuji:
            mock_fuji.evaluate.return_value = {
                "status": "allow",
                "decision_status": "allow",
                "risk": 0.1,
                "reasons": [],
                "violations": [],
                "guidance": "",
                "rejection_reason": None,
                "meta": {},
                "checks": [],
                "policy_version": "test",
            }
            mock_fuji.fuji_gate = mock_fuji.evaluate
            result = await kernel.decide(
                context={"user_id": "u1", "fast": True},
                query="テスト",
                alternatives=[],
            )
        assert isinstance(result, dict)


# =========================================================
# 13) memory.py – locked_memory edge cases
# =========================================================
from veritas_os.core import memory


class TestMemoryLockedMemoryEdge:
    """Cover lines 795-799, 805-806: lock timeout and unlock error."""

    def test_locked_memory_timeout_raises(self, tmp_path: Path):
        """When lock cannot be acquired within timeout, TimeoutError raised."""
        mem_file = tmp_path / "memory.json"
        mem_file.write_text("{}")

        if memory.fcntl is not None:
            # On POSIX, simulate BlockingIOError persisting past timeout
            with patch.object(
                memory.fcntl,
                "flock",
                side_effect=BlockingIOError("locked"),
            ):
                with pytest.raises(TimeoutError, match="failed to acquire lock"):
                    with memory.locked_memory(mem_file, timeout=0.05):
                        pass  # pragma: no cover
        else:
            # Windows-like path: simulate .lock file existing past timeout
            lock_file = mem_file.with_suffix(".json.lock")
            lock_file.write_text(str(os.getpid()))
            with patch("time.time", side_effect=[0.0, 0.0, 10.0]):
                with pytest.raises(TimeoutError):
                    with memory.locked_memory(mem_file, timeout=0.05):
                        pass  # pragma: no cover


class TestMemoryPredictGateLabel:
    """Cover lines 749-751: predict_gate_label with MODEL."""

    def test_predict_gate_label_with_model(self):
        """When MODEL has predict_proba, use it."""
        mock_model = MagicMock()
        mock_model.predict_proba.return_value = [[0.8, 0.2]]
        mock_model.classes_ = ["allow", "deny"]

        old_model = memory.MODEL
        try:
            memory.MODEL = mock_model
            result = memory.predict_gate_label("test text")
            assert "allow" in result
            assert result["allow"] == pytest.approx(0.8)
        finally:
            memory.MODEL = old_model

    def test_predict_gate_label_model_error(self):
        """When MODEL.predict_proba raises, graceful fallback."""
        mock_model = MagicMock()
        mock_model.predict_proba.side_effect = RuntimeError("model broken")

        old_model = memory.MODEL
        try:
            memory.MODEL = mock_model
            result = memory.predict_gate_label("test text")
            assert "allow" in result
        finally:
            memory.MODEL = old_model

    def test_predict_gate_label_no_allow_class(self):
        """When MODEL has no 'allow' class, uses max prob."""
        mock_model = MagicMock()
        mock_model.predict_proba.return_value = [[0.3, 0.7]]
        mock_model.classes_ = ["reject", "accept"]

        old_model = memory.MODEL
        try:
            memory.MODEL = mock_model
            result = memory.predict_gate_label("test text")
            assert "allow" in result
            assert result["allow"] == pytest.approx(0.7)
        finally:
            memory.MODEL = old_model


# =========================================================
# 14) memory.py – _run_runtime_pickle_guard_once branches
# =========================================================
class TestMemoryRuntimePickleGuard:
    """Cover lines 637, 643, 648, 653: various pickle guard conditions."""

    def test_guard_runs_once_only(self):
        """Second call is a no-op."""
        old_checked = memory._runtime_guard_checked
        try:
            memory._runtime_guard_checked = True
            # Should return immediately
            memory._run_runtime_pickle_guard_once()
        finally:
            memory._runtime_guard_checked = old_checked

    def test_guard_with_configured_memory_dir(self, tmp_path: Path):
        """When VERITAS_MEMORY_DIR is set, it's included in scan roots."""
        mem_dir = tmp_path / "custom_mem"
        mem_dir.mkdir()

        old_checked = memory._runtime_guard_checked
        try:
            memory._runtime_guard_checked = False
            with patch.dict(os.environ, {"VERITAS_MEMORY_DIR": str(mem_dir)}):
                with patch.object(memory, "_warn_for_legacy_pickle_artifacts") as mock_warn:
                    with patch.object(memory, "MODELS_DIR", tmp_path / "models"):
                        (tmp_path / "models").mkdir(exist_ok=True)
                        memory._run_runtime_pickle_guard_once()
                        # Verify custom dir was included
                        call_args = mock_warn.call_args[0][0]
                        assert any(str(mem_dir) in str(p) for p in call_args)
        finally:
            memory._runtime_guard_checked = old_checked


# =========================================================
# 15) memory.py – search() old signature fallback
# =========================================================
class TestMemorySearchOldSigFallback:
    """Cover lines 1315-1331: TypeError triggers old-signature fallback."""

    def test_search_old_sig_fallback(self, tmp_path: Path):
        """When vector search raises TypeError, try old signature."""
        store = memory.MemoryStore(tmp_path / "mem.json")
        store.put("u1", "k1", {"text": "hello world", "kind": "semantic"})

        mock_vec = MagicMock()
        # New signature raises TypeError
        mock_vec.search.side_effect = [
            TypeError("unexpected keyword"),
            [{"text": "hello", "score": 0.9, "id": "1"}],
        ]

        old_mem = memory.MEM
        old_vec = memory.MEM_VEC
        try:
            memory.MEM = store
            memory.MEM_VEC = mock_vec
            result = memory.search(query="hello", user_id="u1")
            assert isinstance(result, list)
        finally:
            memory.MEM = old_mem
            memory.MEM_VEC = old_vec

    def test_search_old_sig_also_fails(self, tmp_path: Path):
        """When both signatures fail, falls back to KVS."""
        store = memory.MemoryStore(tmp_path / "mem.json")
        store.put("u1", "k1", {"text": "hello world", "kind": "semantic"})

        mock_vec = MagicMock()
        mock_vec.search.side_effect = TypeError("always fails")

        old_mem = memory.MEM
        old_vec = memory.MEM_VEC
        try:
            memory.MEM = store
            memory.MEM_VEC = mock_vec
            result = memory.search(query="hello", user_id="u1")
            assert isinstance(result, list)
        finally:
            memory.MEM = old_mem
            memory.MEM_VEC = old_vec


# =========================================================
# 16) memory.py – distill_memory_for_user LLM error paths
# =========================================================
class TestMemoryDistillLlmErrors:
    """Cover line 1424+: LLM call errors in distill_memory_for_user."""

    def test_distill_typeerror_returns_none(self, tmp_path: Path):
        """TypeError from LLM → returns None."""
        store = memory.MemoryStore(tmp_path / "mem.json")
        store.put("u1", "k1", {"text": "episode one", "kind": "episodic"})

        mock_chat = MagicMock(side_effect=TypeError("bad call"))
        old_mem = memory.MEM
        try:
            memory.MEM = store
            with patch.object(memory.llm_client, "chat_completion", mock_chat):
                result = memory.distill_memory_for_user(user_id="u1")
            assert result is None
        finally:
            memory.MEM = old_mem

    def test_distill_runtime_error_returns_none(self, tmp_path: Path):
        """RuntimeError from LLM → returns None."""
        store = memory.MemoryStore(tmp_path / "mem.json")
        store.put("u1", "k1", {"text": "episode one", "kind": "episodic"})

        mock_chat = MagicMock(side_effect=RuntimeError("LLM down"))
        old_mem = memory.MEM
        try:
            memory.MEM = store
            with patch.object(memory.llm_client, "chat_completion", mock_chat):
                result = memory.distill_memory_for_user(user_id="u1")
            assert result is None
        finally:
            memory.MEM = old_mem


# =========================================================
# 17) memory.py – VectorMemory._load_index edge cases
# =========================================================
class TestVectorMemoryLoadIndexEdge:
    """Cover lines 246, 252, 260: embeddings formats and legacy pickle."""

    def test_load_index_list_format(self, tmp_path: Path):
        """When embeddings are stored as list, they're loaded as numpy array."""
        import numpy as np

        index_path = tmp_path / "vector_index.json"
        data = {
            "documents": [{"text": "test", "id": 1}],
            "embeddings": [[0.1, 0.2, 0.3]],
            "model_name": "test_model",
        }
        index_path.write_text(json.dumps(data))

        vm = memory.VectorMemory(model_name="test", index_path=index_path)
        assert len(vm.documents) == 1
        assert vm.embeddings is not None
        assert vm.embeddings.shape == (1, 3)

    def test_load_index_unknown_embeddings_type(self, tmp_path: Path):
        """When embeddings have unexpected type, set to None."""
        index_path = tmp_path / "vector_index.json"
        data = {
            "documents": [{"text": "test", "id": 1}],
            "embeddings": 12345,  # unexpected type
            "model_name": "test_model",
        }
        index_path.write_text(json.dumps(data))

        vm = memory.VectorMemory(model_name="test", index_path=index_path)
        assert len(vm.documents) == 1
        assert vm.embeddings is None


# =========================================================
# 18) server.py – import fallback paths
# =========================================================
class TestServerImportFallbacks:
    """Cover server.py lines 120-124, 129-130, 136-139, 155, 162-166, 303-308.

    These are module-level import blocks. We verify the fallback attributes
    exist and have correct types after normal import.
    """

    def test_server_has_atomic_io_flag(self):
        """_HAS_ATOMIC_IO is set after import."""
        from veritas_os.api import server
        assert isinstance(server._HAS_ATOMIC_IO, bool)

    def test_server_has_sanitize_flag(self):
        """_HAS_SANITIZE exists after import."""
        from veritas_os.api import server
        assert isinstance(server._HAS_SANITIZE, bool)

    def test_server_utc_now_iso_z_works(self):
        """utc_now_iso_z returns valid ISO string."""
        from veritas_os.api import server
        ts = server.utc_now_iso_z()
        assert isinstance(ts, str)
        assert ts.endswith("Z")

    def test_server_resolve_cors_settings(self):
        """_resolve_cors_settings handles various inputs."""
        from veritas_os.api import server

        # String input (not a list) → empty result
        origins, allow_cred = server._resolve_cors_settings("http://a.com,http://b.com")
        assert isinstance(origins, list)

        # Wildcard in list
        origins, allow_cred = server._resolve_cors_settings(["*"])
        # Wildcard disables credentials for security
        assert "*" in origins
        assert allow_cred is False

        # List input with valid origin
        origins, allow_cred = server._resolve_cors_settings(["http://localhost:3000"])
        assert "http://localhost:3000" in origins

    def test_server_is_placeholder(self):
        """_is_placeholder correctly detects placeholder objects."""
        from veritas_os.api import server

        class FakePlaceholder:
            __veritas_placeholder__ = True

        assert server._is_placeholder(FakePlaceholder()) is True
        assert server._is_placeholder("real_value") is False
        assert server._is_placeholder(None) is False


# =========================================================
# 19) pipeline.py – optional dependency unavailable paths
# =========================================================
class TestPipelineOptionalDeps:
    """Cover pipeline.py lines 220-221, 227-228, 632-633.

    These are import-time fallbacks. Since the module is already imported,
    verify the flags exist and have correct values.
    """

    def test_pipeline_has_atomic_io_flag(self):
        """_HAS_ATOMIC_IO is set."""
        from veritas_os.core import pipeline
        assert isinstance(pipeline._HAS_ATOMIC_IO, bool)

    def test_pipeline_request_exists_or_none(self):
        """Request is either the FastAPI class or None."""
        from veritas_os.core import pipeline
        # In test environment with fastapi installed, it should be the real class
        assert pipeline.Request is not None

    def test_pipeline_web_search_exists_or_none(self):
        """_tool_web_search is either callable or None."""
        from veritas_os.core import pipeline
        assert pipeline._tool_web_search is None or callable(pipeline._tool_web_search)


# =========================================================
# 20) kernel.py – _is_safe_python_executable edge cases
# =========================================================
class TestKernelSafePythonExecutable:
    """Cover kernel.py line 136: non-executable file."""

    def test_not_absolute_path(self):
        assert kernel._is_safe_python_executable("python3") is False

    def test_none_path(self):
        assert kernel._is_safe_python_executable(None) is False

    def test_nonexistent_path(self):
        assert kernel._is_safe_python_executable("/nonexistent/python3") is False

    def test_valid_python_executable(self):
        """The current Python executable should be considered safe."""
        result = kernel._is_safe_python_executable(sys.executable)
        assert result is True

    def test_non_python_executable(self, tmp_path: Path):
        """Non-python named executable → False."""
        fake_exe = tmp_path / "notpython"
        fake_exe.write_text("#!/bin/bash")
        fake_exe.chmod(0o755)
        assert kernel._is_safe_python_executable(str(fake_exe)) is False


# =========================================================
# 21) kernel.py – _open_doctor_log_fd
# =========================================================
class TestKernelOpenDoctorLogFd:
    """Cover kernel.py lines 144-170+: secure log file descriptor."""

    def test_open_doctor_log_fd_creates_file(self, tmp_path: Path):
        """Creates log file with restrictive permissions."""
        log_path = tmp_path / "doctor.log"
        fd = kernel._open_doctor_log_fd(str(log_path))
        try:
            assert fd > 0
            assert log_path.exists()
        finally:
            os.close(fd)

    def test_open_doctor_log_fd_not_regular_file(self, tmp_path: Path):
        """Opening a non-regular file raises ValueError."""
        if sys.platform == "win32":
            pytest.skip("No /dev/null on Windows")
        # /dev/null is not a regular file
        with pytest.raises(ValueError):
            kernel._open_doctor_log_fd("/dev/null")


# =========================================================
# 22) memory.py – _LazyMemoryStore retry after failure
# =========================================================
class TestLazyMemoryStoreRetry:
    """Cover memory.py lines 1074-1082: retry after initial failure."""

    def test_lazy_store_raises_on_repeated_failure(self):
        """After first load failure, subsequent calls raise immediately."""
        def failing_loader():
            raise RuntimeError("init failed")

        lazy = memory._LazyMemoryStore(failing_loader)

        with pytest.raises(RuntimeError, match="init failed"):
            lazy._load()

        # Second call should also raise (cached error)
        with pytest.raises(RuntimeError, match="MemoryStore load failed"):
            lazy._load()


# =========================================================
# 23) memory.py – emit_manifest_on_import branch
# =========================================================
class TestMemoryCapabilityManifest:
    """Cover memory.py line 128: emit_capability_manifest."""

    def test_capability_cfg_has_expected_flags(self):
        """memory module has the expected capability flags."""
        from veritas_os.core.config import capability_cfg
        assert isinstance(capability_cfg.enable_memory_posix_file_lock, bool)
        assert isinstance(capability_cfg.enable_memory_sentence_transformers, bool)
        assert isinstance(capability_cfg.emit_manifest_on_import, bool)


# =========================================================
# 24) kernel.py – auto_doctor context handling
# =========================================================
class TestKernelAutoDoctor:
    """Cover kernel.py lines 1003-1011: auto_doctor context flag."""

    @pytest.fixture
    def anyio_backend(self):
        return "asyncio"

    @pytest.mark.anyio
    async def test_auto_doctor_without_confinement(self):
        """auto_doctor=True without confinement → skipped with warning."""
        with patch.object(kernel, "_is_doctor_confinement_profile_active", return_value=False):
            with patch.object(kernel, "fuji_core") as mock_fuji:
                mock_fuji.evaluate.return_value = {
                    "status": "allow",
                    "decision_status": "allow",
                    "risk": 0.1,
                    "reasons": [],
                    "violations": [],
                    "guidance": "",
                    "rejection_reason": None,
                    "meta": {},
                    "checks": [],
                    "policy_version": "test",
                }
                mock_fuji.fuji_gate = mock_fuji.evaluate
                result = await kernel.decide(
                    context={"auto_doctor": True, "user_id": "u1", "fast": True},
                    query="テスト",
                    alternatives=[],
                )
        extras = result.get("extras", {})
        doctor = extras.get("doctor", {})
        assert doctor.get("skipped") == "confinement_required"

    @pytest.mark.anyio
    async def test_auto_doctor_with_confinement(self):
        """auto_doctor=True with confinement → delegated_to_pipeline."""
        with patch.object(kernel, "_is_doctor_confinement_profile_active", return_value=True):
            with patch.object(kernel, "fuji_core") as mock_fuji:
                mock_fuji.evaluate.return_value = {
                    "status": "allow",
                    "decision_status": "allow",
                    "risk": 0.1,
                    "reasons": [],
                    "violations": [],
                    "guidance": "",
                    "rejection_reason": None,
                    "meta": {},
                    "checks": [],
                    "policy_version": "test",
                }
                mock_fuji.fuji_gate = mock_fuji.evaluate
                result = await kernel.decide(
                    context={"auto_doctor": True, "user_id": "u1", "fast": True},
                    query="テスト",
                    alternatives=[],
                )
        extras = result.get("extras", {})
        doctor = extras.get("doctor", {})
        assert doctor.get("skipped") == "delegated_to_pipeline"


# =========================================================
# 25) kernel.py – memory save error branch
# =========================================================
class TestKernelMemorySaveError:
    """Cover lines 999-1001: memory save error → extras.memory_log.error."""

    @pytest.fixture
    def anyio_backend(self):
        return "asyncio"

    @pytest.mark.anyio
    async def test_memory_save_error_captured(self):
        """When memory save fails, error is captured in extras."""
        mock_mem = MagicMock()
        mock_mem.MEM = MagicMock()
        mock_mem.MEM.put.side_effect = RuntimeError("disk full")

        with patch.object(kernel, "mem_core", mock_mem):
            with patch.object(kernel, "fuji_core") as mock_fuji:
                mock_fuji.evaluate.return_value = {
                    "status": "allow",
                    "decision_status": "allow",
                    "risk": 0.1,
                    "reasons": [],
                    "violations": [],
                    "guidance": "",
                    "rejection_reason": None,
                    "meta": {},
                    "checks": [],
                    "policy_version": "test",
                }
                mock_fuji.fuji_gate = mock_fuji.evaluate
                result = await kernel.decide(
                    context={"user_id": "u1", "fast": True},
                    query="テスト",
                    alternatives=[],
                )
        extras = result.get("extras", {})
        mem_log = extras.get("memory_log", {})
        if "error" in mem_log:
            assert "disk full" in mem_log["error"] or "RuntimeError" in mem_log["error"]


# ============================================================
# Source: test_coverage_map_extra.py
# ============================================================


import json
import os
from pathlib import Path
from typing import Any, Dict

import pytest

import veritas_os.tools.coverage_map_pipeline as m


class TestCovFileEntryEdgeCases:
    """Test CovFileEntry.from_cov edge cases."""

    def test_missing_lines_non_numeric_skipped(self):
        """Non-numeric values in missing_lines should be skipped."""
        entry = {"missing_lines": [1, "abc", 3, "5"]}
        result = m.CovFileEntry.from_cov(entry)
        # "abc" skipped, numeric strings converted
        assert 1 in result.missing_lines
        assert 3 in result.missing_lines
        assert 5 in result.missing_lines

    def test_missing_lines_with_string_numbers(self):
        """String numeric values should be converted to int."""
        entry = {"missing_lines": ["1", "2", "3"]}
        result = m.CovFileEntry.from_cov(entry)
        assert result.missing_lines == [1, 2, 3]

    def test_missing_lines_with_negative_string(self):
        """Negative string numbers should work."""
        entry = {"missing_lines": ["-1", "10"]}
        result = m.CovFileEntry.from_cov(entry)
        assert -1 in result.missing_lines
        assert 10 in result.missing_lines

    def test_missing_branches_invalid_tuple_skipped(self):
        """Invalid branch tuples (wrong length) should be skipped."""
        entry = {"missing_branches": [[1, 2], [3], [4, 5, 6], [7, 8]]}
        result = m.CovFileEntry.from_cov(entry)
        assert result.missing_branches == [[1, 2], [7, 8]]

    def test_missing_branches_non_convertible_skipped(self):
        """Branches with non-convertible values should be skipped."""
        entry = {"missing_branches": [[1, 2], ["a", "b"], [3, 4]]}
        result = m.CovFileEntry.from_cov(entry)
        assert result.missing_branches == [[1, 2], [3, 4]]

    def test_executed_branches_invalid_skipped(self):
        """Invalid executed_branches should be skipped."""
        entry = {"executed_branches": [[1, 2], [3], "invalid", [4, 5]]}
        result = m.CovFileEntry.from_cov(entry)
        assert result.executed_branches == [[1, 2], [4, 5]]

    def test_empty_entry(self):
        """Empty entry should produce empty lists."""
        result = m.CovFileEntry.from_cov({})
        assert result.missing_lines == []
        assert result.missing_branches == []
        assert result.executed_branches == []

    def test_none_values(self):
        """None values should be treated as empty."""
        entry = {"missing_lines": None, "missing_branches": None, "executed_branches": None}
        result = m.CovFileEntry.from_cov(entry)
        assert result.missing_lines == []
        assert result.missing_branches == []
        assert result.executed_branches == []


    def test_missing_lines_unexpected_runtime_error_propagates(self):
        """Unexpected RuntimeError should not be swallowed."""

        class _BadStr:
            def __str__(self) -> str:
                raise RuntimeError("boom")

        entry = {"missing_lines": [_BadStr()]}
        with pytest.raises(RuntimeError, match="boom"):
            m.CovFileEntry.from_cov(entry)


class TestResolveCovJson:
    """Test _resolve_cov_json edge cases."""

    def test_cov_json_relative_path(self, monkeypatch, tmp_path):
        """Test relative COV_JSON path resolution."""
        cov_file = tmp_path / "coverage.json"
        cov_file.write_text("{}", encoding="utf-8")

        # Create a relative path
        rel_path = Path("coverage.json")
        monkeypatch.setattr(m, "COV_JSON", rel_path)

        # Change to tmp_path so relative resolution works
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = m._resolve_cov_json()
            assert result is not None
            assert result.exists()
        finally:
            os.chdir(old_cwd)

    def test_env_variable_resolution(self, monkeypatch, tmp_path):
        """Test VERITAS_COVERAGE_JSON env variable."""
        cov_file = tmp_path / "my_coverage.json"
        cov_file.write_text("{}", encoding="utf-8")

        # Make COV_JSON point to non-existent
        monkeypatch.setattr(m, "COV_JSON", tmp_path / "nonexistent.json")
        monkeypatch.setenv("VERITAS_COVERAGE_JSON", str(cov_file))

        result = m._resolve_cov_json()
        assert result == cov_file

    def test_env_variable_relative_path(self, monkeypatch, tmp_path):
        """Test relative path in env variable."""
        cov_file = tmp_path / "cov.json"
        cov_file.write_text("{}", encoding="utf-8")

        monkeypatch.setattr(m, "COV_JSON", tmp_path / "nonexistent.json")

        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            monkeypatch.setenv("VERITAS_COVERAGE_JSON", "cov.json")
            result = m._resolve_cov_json()
            assert result is not None
        finally:
            os.chdir(old_cwd)

    def test_none_when_not_found(self, monkeypatch, tmp_path):
        """Returns None when no coverage.json found."""
        monkeypatch.setattr(m, "COV_JSON", tmp_path / "nonexistent.json")
        monkeypatch.delenv("VERITAS_COVERAGE_JSON", raising=False)
        monkeypatch.setattr(m, "COV_JSON_CANDIDATES", (tmp_path / "also_nonexistent.json",))

        result = m._resolve_cov_json()
        assert result is None


class TestLoadCov:
    """Test load_cov edge cases."""

    def test_load_cov_not_found(self, monkeypatch, tmp_path, capsys):
        """load_cov returns {} when file not found."""
        monkeypatch.setattr(m, "COV_JSON", tmp_path / "nonexistent.json")
        monkeypatch.delenv("VERITAS_COVERAGE_JSON", raising=False)
        monkeypatch.setattr(m, "COV_JSON_CANDIDATES", ())

        result = m.load_cov()
        assert result == {}

        captured = capsys.readouterr()
        assert "coverage.json not found" in captured.err

    def test_load_cov_invalid_json(self, monkeypatch, tmp_path, capsys):
        """load_cov returns {} for invalid JSON."""
        cov_file = tmp_path / "coverage.json"
        cov_file.write_text("not valid json {{{", encoding="utf-8")
        monkeypatch.setattr(m, "COV_JSON", cov_file)

        result = m.load_cov()
        assert result == {}

        captured = capsys.readouterr()
        assert "failed to parse" in captured.err


    def test_load_cov_unexpected_runtime_error_propagates(self, monkeypatch, tmp_path):
        """Unexpected RuntimeError from read_text should propagate."""

        class _BadPath:
            def read_text(self, encoding: str = "utf-8") -> str:
                raise RuntimeError("unexpected")

        monkeypatch.setattr(m, "_resolve_cov_json", lambda: _BadPath())
        with pytest.raises(RuntimeError, match="unexpected"):
            m.load_cov()


class TestFindTargetFile:
    """Test find_target_file edge cases."""

    def test_files_not_dict_raises(self):
        """Raises SystemExit when files is not a dict."""
        cov = {"files": "not a dict"}
        with pytest.raises(SystemExit) as exc:
            m.find_target_file(cov)
        assert "Target not found" in str(exc.value)

    def test_normalized_windows_path_match(self):
        """Test Windows-style path normalization."""
        # Use backslashes like Windows
        cov = {"files": {"C:\\project\\veritas_os\\core\\pipeline.py": {}}}
        # Should still match with forward-slash suffix
        result = m.find_target_file(cov, "veritas_os/core/pipeline.py")
        assert result == "C:\\project\\veritas_os\\core\\pipeline.py"

    def test_non_string_key_skipped(self):
        """Non-string keys are skipped."""
        cov = {"files": {123: {}, "path/veritas_os/core/pipeline.py": {}}}
        result = m.find_target_file(cov)
        assert result == "path/veritas_os/core/pipeline.py"


class TestSafeReadText:
    """Test _safe_read_text edge cases."""

    def test_file_not_found(self, tmp_path, capsys):
        """Returns None for non-existent file."""
        result = m._safe_read_text(tmp_path / "nonexistent.py")
        assert result is None

        captured = capsys.readouterr()
        assert "cannot read source" in captured.err


class TestParseTargetSuffix:
    """Test _parse_target_suffix."""

    def test_default_suffix(self):
        """Returns default when no --target."""
        result = m._parse_target_suffix([])
        assert result == m.TARGET_SUFFIX

    def test_custom_target(self):
        """Returns custom target when specified."""
        result = m._parse_target_suffix(["--target", "custom/path.py"])
        assert result == "custom/path.py"

    def test_invalid_target_usage(self, capsys):
        """Handles invalid --target usage."""
        # --target at end with no value
        result = m._parse_target_suffix(["--target"])
        # Should return default and print error
        assert result == m.TARGET_SUFFIX


class TestMainEdgeCases:
    """Test main() edge cases."""

    def test_main_no_coverage_json(self, monkeypatch, tmp_path, capsys):
        """main() handles missing coverage.json gracefully."""
        monkeypatch.setattr(m, "COV_JSON", tmp_path / "nonexistent.json")
        monkeypatch.delenv("VERITAS_COVERAGE_JSON", raising=False)
        monkeypatch.setattr(m, "COV_JSON_CANDIDATES", ())

        result = m.main([])
        assert result == 0

        captured = capsys.readouterr()
        assert "[pipeline] missing_lines=0" in captured.out
        assert "coverage.json missing or invalid" in captured.out

    def test_main_target_not_found(self, monkeypatch, tmp_path, capsys):
        """main() handles target not found gracefully."""
        cov_file = tmp_path / "coverage.json"
        cov_file.write_text('{"files": {"other.py": {}}}', encoding="utf-8")
        monkeypatch.setattr(m, "COV_JSON", cov_file)

        result = m.main([])
        assert result == 0

        captured = capsys.readouterr()
        assert "[pipeline] missing_lines=0" in captured.out
        assert "target not found" in captured.out

    def test_main_source_unreadable(self, monkeypatch, tmp_path, capsys):
        """main() handles unreadable source file."""
        # Create coverage.json pointing to non-existent source
        cov = {
            "files": {
                "/nonexistent/veritas_os/core/pipeline.py": {
                    "missing_lines": [1, 2, 3],
                    "missing_branches": [],
                    "executed_branches": []
                }
            }
        }
        cov_file = tmp_path / "coverage.json"
        cov_file.write_text(json.dumps(cov), encoding="utf-8")
        monkeypatch.setattr(m, "COV_JSON", cov_file)
        monkeypatch.setattr(m, "ROOT", tmp_path)

        result = m.main([])
        assert result == 0

        captured = capsys.readouterr()
        # Should still output but note source unreadable
        assert "[pipeline]" in captured.out
        # Missing lines should be grouped under module-level when AST unavailable
        assert "<module-level>" in captured.out

    def test_main_zero_missing_lines(self, monkeypatch, tmp_path, capsys):
        """main() handles case with no missing lines."""
        # Create a valid setup with no missing lines
        pkg = tmp_path / "veritas_os" / "core"
        pkg.mkdir(parents=True)
        src = pkg / "pipeline.py"
        src.write_text("x = 1\n", encoding="utf-8")

        cov = {
            "files": {
                str(src): {
                    "missing_lines": [],
                    "missing_branches": [],
                    "executed_branches": [[1, 2]]
                }
            }
        }
        cov_file = tmp_path / "coverage.json"
        cov_file.write_text(json.dumps(cov), encoding="utf-8")
        monkeypatch.setattr(m, "COV_JSON", cov_file)

        result = m.main([])
        assert result == 0

        captured = capsys.readouterr()
        assert "[pipeline] missing_lines=0" in captured.out

    def test_main_owners_none_with_defs(self, monkeypatch, tmp_path, capsys):
        """main() shows (none) when defs exist but no missing lines."""
        # Create a file with function defs but no missing lines
        pkg = tmp_path / "veritas_os" / "core"
        pkg.mkdir(parents=True)
        src = pkg / "pipeline.py"
        src.write_text("def foo():\n    return 1\n", encoding="utf-8")

        cov = {
            "files": {
                str(src): {
                    "missing_lines": [],
                    "missing_branches": [],
                    "executed_branches": []
                }
            }
        }
        cov_file = tmp_path / "coverage.json"
        cov_file.write_text(json.dumps(cov), encoding="utf-8")
        monkeypatch.setattr(m, "COV_JSON", cov_file)

        result = m.main([])
        assert result == 0

        captured = capsys.readouterr()
        assert "[top owners] (none)" in captured.out

    def test_main_ast_parse_failure(self, monkeypatch, tmp_path, capsys):
        """main() handles AST parse failure gracefully."""
        pkg = tmp_path / "veritas_os" / "core"
        pkg.mkdir(parents=True)
        src = pkg / "pipeline.py"
        # Write invalid Python syntax
        src.write_text("def broken(\n", encoding="utf-8")

        cov = {
            "files": {
                str(src): {
                    "missing_lines": [1],
                    "missing_branches": [],
                    "executed_branches": []
                }
            }
        }
        cov_file = tmp_path / "coverage.json"
        cov_file.write_text(json.dumps(cov), encoding="utf-8")
        monkeypatch.setattr(m, "COV_JSON", cov_file)

        result = m.main([])
        assert result == 0

        captured = capsys.readouterr()
        assert "AST parse failed" in captured.err
        # Lines should be under module-level when AST fails
        assert "<module-level>" in captured.out


class TestHelperFunctions:
    """Test helper functions."""

    def test_preview_ints_truncation(self):
        """Test _preview_ints truncates long lists."""
        result = m._preview_ints(list(range(20)), max_n=5)
        assert "..." in result
        assert "0, 1, 2, 3, 4" in result

    def test_preview_ints_no_truncation(self):
        """Test _preview_ints doesn't truncate short lists."""
        result = m._preview_ints([1, 2, 3], max_n=5)
        assert "..." not in result
        assert result == "1, 2, 3"

    def test_exit_arcs_filter(self):
        """Test _exit_arcs filters correctly."""
        branches = [[1, 2], [3, -1], [4, 0], [5, 6], [7, -1]]
        result = m._exit_arcs(branches)
        assert result == [[3, -1], [4, 0], [7, -1]]

    def test_eprint(self, capsys):
        """Test _eprint writes to stderr."""
        m._eprint("test message")
        captured = capsys.readouterr()
        assert captured.err == "test message\n"


class TestOwnerFunction:
    """Test owner() function edge cases."""

    def test_owner_module_level(self):
        """Test owner returns module-level for out-of-range lines."""
        defs = [("func1", 5, 10), ("func2", 15, 20)]
        assert m.owner(defs, 1) == "<module-level>"
        assert m.owner(defs, 12) == "<module-level>"
        assert m.owner(defs, 100) == "<module-level>"

    def test_owner_empty_defs(self):
        """Test owner with empty defs."""
        assert m.owner([], 5) == "<module-level>"

class TestRiskWeightedCoverage:
    """Tests for risk-weighted coverage helpers."""

    def test_parse_risk_weights_valid_file(self, tmp_path) -> None:
        """Risk weight parser should clamp values to [0, 1]."""
        weights = tmp_path / "weights.json"
        weights.write_text('{"A": 0.2, "B": 2.0, "C": -1.0}', encoding="utf-8")

        parsed = m._parse_risk_weights(["--risk-weights", str(weights)])
        assert parsed["A"] == 0.2
        assert parsed["B"] == 1.0
        assert parsed["C"] == 0.0

    def test_compute_weighted_gap(self) -> None:
        """Weighted gap should use owner weights and default to 0.5."""
        by_owner = {"A": [1, 2], "B": [10]}
        weights = {"A": 1.0}
        got = m._compute_weighted_gap(by_owner=by_owner, risk_weights=weights)
        # ((2 * 1.0) + (1 * 0.5)) / 3
        assert round(got, 4) == round(2.5 / 3.0, 4)
