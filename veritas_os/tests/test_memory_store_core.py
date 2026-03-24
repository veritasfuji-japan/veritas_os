# tests for veritas_os/core/memory_store.py — direct module tests
"""Tests for MemoryStore KVS core."""
from __future__ import annotations

import json
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import pytest

from veritas_os.core.memory_store import (
    MemoryStore,
    DEFAULT_RETENTION_CLASS,
    ALLOWED_RETENTION_CLASSES,
)
from veritas_os.core.memory_store_helpers import (
    erase_user_records,
    is_record_expired_compat,
    normalize_document_lifecycle,
    put_episode_record,
    recent_records_compat,
    search_records_compat,
    summarize_records_for_planner,
)


@pytest.fixture
def store(tmp_path):
    path = tmp_path / "memory.json"
    return MemoryStore(path)


class TestMemoryStoreInit:
    def test_creates_empty_file(self, tmp_path):
        path = tmp_path / "sub" / "memory.json"
        store = MemoryStore(path)
        assert path.exists()

    def test_load_classmethod(self, tmp_path):
        path = tmp_path / "memory.json"
        store = MemoryStore.load(path)
        assert isinstance(store, MemoryStore)


class TestNormalize:
    def test_list_passthrough(self, store):
        data = [{"key": "k1"}]
        assert store._normalize(data) == data

    def test_old_dict_format_migration(self, store):
        old = {"users": {"u1": {"k1": "v1", "k2": "v2"}}}
        result = store._normalize(old)
        assert len(result) == 2
        assert all(r["user_id"] == "u1" for r in result)

    def test_invalid_returns_empty(self, store):
        assert store._normalize("bad") == []
        assert store._normalize(42) == []


class TestPutGet:
    def test_put_and_get(self, store):
        assert store.put("u1", "key1", "value1") is True
        assert store.get("u1", "key1") == "value1"

    def test_get_missing(self, store):
        assert store.get("u1", "nonexistent") is None

    def test_put_update(self, store):
        store.put("u1", "k", "v1")
        store.put("u1", "k", "v2")
        assert store.get("u1", "k") == "v2"


class TestListAll:
    def test_list_all(self, store):
        store.put("u1", "k1", "v1")
        store.put("u2", "k2", "v2")
        all_records = store.list_all()
        assert len(all_records) == 2

    def test_list_all_by_user(self, store):
        store.put("u1", "k1", "v1")
        store.put("u2", "k2", "v2")
        assert len(store.list_all(user_id="u1")) == 1


class TestParseExpiresAt:
    def test_none(self):
        assert MemoryStore._parse_expires_at(None) is None

    def test_empty_string(self):
        assert MemoryStore._parse_expires_at("") is None

    def test_unix_timestamp(self):
        result = MemoryStore._parse_expires_at(1700000000)
        assert result is not None
        assert "2023" in result

    def test_iso_string(self):
        result = MemoryStore._parse_expires_at("2025-01-01T00:00:00Z")
        assert result is not None

    def test_iso_without_tz(self):
        result = MemoryStore._parse_expires_at("2025-01-01T00:00:00")
        assert result is not None

    def test_invalid_string(self):
        assert MemoryStore._parse_expires_at("not-a-date") is None


class TestNormalizeLifecycle:
    def test_non_dict_passthrough(self):
        assert MemoryStore._normalize_lifecycle("string") == "string"
        assert MemoryStore._normalize_lifecycle(42) == 42

    def test_plain_dict_passthrough(self):
        d = {"foo": "bar"}
        assert MemoryStore._normalize_lifecycle(d) == d

    def test_document_gets_lifecycle(self):
        d = {"text": "hello", "meta": {}}
        result = MemoryStore._normalize_lifecycle(d)
        assert result["meta"]["retention_class"] == DEFAULT_RETENTION_CLASS
        assert result["meta"]["legal_hold"] is False

    def test_retention_class_normalized(self):
        d = {"text": "x", "meta": {"retention_class": "  LONG  "}}
        result = MemoryStore._normalize_lifecycle(d)
        assert result["meta"]["retention_class"] == "long"

    def test_invalid_retention_class_defaults(self):
        d = {"text": "x", "meta": {"retention_class": "invalid"}}
        result = MemoryStore._normalize_lifecycle(d)
        assert result["meta"]["retention_class"] == DEFAULT_RETENTION_CLASS

    def test_legal_hold_string_false(self):
        d = {"text": "x", "meta": {"legal_hold": "false"}}
        result = MemoryStore._normalize_lifecycle(d)
        assert result["meta"]["legal_hold"] is False

    def test_legal_hold_string_true(self):
        d = {"text": "x", "meta": {"legal_hold": "true"}}
        result = MemoryStore._normalize_lifecycle(d)
        assert result["meta"]["legal_hold"] is True

    def test_legal_hold_string_one(self):
        d = {"text": "x", "meta": {"legal_hold": "1"}}
        result = MemoryStore._normalize_lifecycle(d)
        assert result["meta"]["legal_hold"] is True

    def test_legal_hold_string_zero(self):
        d = {"text": "x", "meta": {"legal_hold": "0"}}
        result = MemoryStore._normalize_lifecycle(d)
        assert result["meta"]["legal_hold"] is False


class TestIsRecordExpired:
    def test_not_expired(self):
        future = time.time() + 86400
        record = {"value": {"meta": {"expires_at": future}}}
        assert MemoryStore._is_record_expired(record) is False

    def test_expired(self):
        past = time.time() - 86400
        record = {"value": {"meta": {"expires_at": past}}}
        assert MemoryStore._is_record_expired(record) is True

    def test_legal_hold_prevents_expiry(self):
        past = time.time() - 86400
        record = {"value": {"meta": {"expires_at": past, "legal_hold": True}}}
        assert MemoryStore._is_record_expired(record) is False

    def test_no_expiry(self):
        record = {"value": {"meta": {}}}
        assert MemoryStore._is_record_expired(record) is False

    def test_non_dict_value(self):
        assert MemoryStore._is_record_expired({"value": "string"}) is False


class TestMemoryStoreCompatHelpers:
    def test_normalize_document_lifecycle_keeps_contract(self):
        payload = {
            "text": "hello",
            "meta": {"retention_class": "LONG", "legal_hold": "yes"},
        }

        result = normalize_document_lifecycle(
            payload,
            default_retention_class=DEFAULT_RETENTION_CLASS,
            allowed_retention_classes={"short", "medium", "long"},
            parse_expires_at=MemoryStore._parse_expires_at,
        )

        assert result["meta"]["retention_class"] == "long"
        assert result["meta"]["legal_hold"] is True

    def test_is_record_expired_compat_handles_expired_record(self):
        past = time.time() - 86400
        record = {"value": {"meta": {"expires_at": past}}}

        assert is_record_expired_compat(
            record,
            parse_expires_at=MemoryStore._parse_expires_at,
        ) is True

    def test_erase_user_records_prefers_patched_helper(self, store):
        store.put("u1", "k1", {"text": "secret"})

        helper_module = mock.Mock()
        helper_module.erase_user_data = mock.Mock(
            return_value=(
                [],
                {"deleted_count": 1, "reason": "gdpr", "actor": "tester"},
            )
        )

        report = erase_user_records(
            store=store,
            helper_module=helper_module,
            original_helper=object(),
            fallback_helper=mock.Mock(),
            user_id="u1",
            reason="gdpr",
            actor="tester",
        )

        assert report["ok"] is True
        helper_module.erase_user_data.assert_called_once()

    def test_recent_records_compat_prefers_patched_helper(self, store):
        store.put("u1", "k1", {"text": "alpha"})
        helper_module = mock.Mock()
        helper_module.filter_recent_records = mock.Mock(
            return_value=[{"key": "patched"}]
        )

        result = recent_records_compat(
            store=store,
            helper_module=helper_module,
            original_helper=object(),
            fallback_helper=mock.Mock(),
            user_id="u1",
            limit=5,
        )

        assert result == [{"key": "patched"}]
        helper_module.filter_recent_records.assert_called_once()

    def test_search_records_compat_prefers_patched_helper(self, store):
        store.put("u1", "k1", {"text": "hello world", "kind": "episodic"})
        helper_module = mock.Mock()
        helper_module.build_kvs_search_hits = mock.Mock(
            return_value=[{"id": "patched", "text": "hello world", "score": 1.0}]
        )

        result = search_records_compat(
            store=store,
            helper_module=helper_module,
            original_helper=object(),
            fallback_helper=mock.Mock(),
            query="hello",
            user_id="u1",
        )

        assert result == {
            "episodic": [{"id": "patched", "text": "hello world", "score": 1.0}]
        }
        helper_module.build_kvs_search_hits.assert_called_once()

    def test_put_episode_record_logs_vector_failure_without_breaking(self, store):
        mem_vec = mock.Mock()
        mem_vec.add.side_effect = RuntimeError("vector down")
        logger = mock.Mock()

        key = put_episode_record(
            store=store,
            text="episodic note",
            tags=["ops"],
            meta={"user_id": "u1"},
            mem_vec=mem_vec,
            logger=logger,
        )

        assert key.startswith("episode_")
        assert store.get("u1", key)["text"] == "episodic note"
        logger.warning.assert_called_once()

    def test_summarize_records_for_planner_uses_search_contract(self, store):
        store.put("u1", "k1", {"text": "planner context", "kind": "episodic"})

        result = summarize_records_for_planner(
            store=store,
            user_id="u1",
            query="planner",
            limit=3,
            build_summary=lambda items: f"items={len(items)}",
        )

        assert result == "items=1"


class TestSearch:
    def test_basic_search(self, store):
        store.put("u1", "k1", {"text": "hello world", "kind": "episodic"})
        result = store.search("hello")
        assert "episodic" in result
        assert len(result["episodic"]) > 0

    def test_empty_query(self, store):
        assert store.search("") == {}

    def test_no_matches(self, store):
        store.put("u1", "k1", {"text": "hello", "kind": "episodic"})
        result = store.search("zzzznotfound", min_sim=0.5)
        assert result == {} or len(result.get("episodic", [])) == 0

class TestSimpleScore:
    def test_exact_substring(self, store):
        score = store._simple_score("hello", "hello world")
        assert score >= 0.5

    def test_no_match(self, store):
        score = store._simple_score("abc", "xyz")
        assert score < 0.5

    def test_empty(self, store):
        assert store._simple_score("", "hello") == 0.0

class TestRecent:
    def test_recent(self, store):
        store.put("u1", "k1", {"text": "first"})
        store.put("u1", "k2", {"text": "second"})
        results = store.recent("u1", limit=1)
        assert len(results) <= 1

    def test_recent_with_contains(self, store):
        store.put("u1", "k1", {"text": "apple pie"})
        store.put("u1", "k2", {"text": "banana split"})
        results = store.recent("u1", contains="apple")
        assert len(results) == 1

class TestEraseUser:
    def test_erase(self, store):
        store.put("u1", "k1", "v1")
        store.put("u2", "k2", "v2")
        report = store.erase_user("u1", "gdpr", "admin")
        assert report["deleted_count"] >= 1
        assert store.get("u1", "k1") is None

class TestPutEpisode:
    def test_basic_episode(self, store):
        key = store.put_episode("test episode text", tags=["test"])
        assert key.startswith("episode_")

class TestSummarizeForPlanner:
    def test_no_matches(self, store):
        result = store.summarize_for_planner("u1", "nonexistent")
        assert "見つかりませんでした" in result

    def test_with_matches(self, store):
        store.put("u1", "k1", {"text": "VERITAS project update", "kind": "episodic"})
        result = store.summarize_for_planner("u1", "VERITAS")
        assert "VERITAS" in result

class TestAppendHistory:
    def test_append(self, store):
        assert store.append_history("u1", {"event": "test"}) is True

class TestAddUsage:
    def test_add(self, store):
        assert store.add_usage("u1", cited_ids=["id1"]) is True


class TestMemoryStoreIOAndIsolation:
    def test_load_all_returns_empty_when_file_missing(self, tmp_path):
        path = tmp_path / "missing.json"
        store = MemoryStore(path)
        path.unlink()

        assert store._load_all(copy=True, use_cache=False) == []

    def test_load_all_returns_empty_for_corrupt_json(self, tmp_path):
        path = tmp_path / "memory.json"
        path.write_text("{bad json", encoding="utf-8")
        store = MemoryStore(path)

        assert store._load_all(copy=True, use_cache=False) == []

    def test_save_all_returns_false_on_atomic_write_error(self, tmp_path, monkeypatch):
        store = MemoryStore(tmp_path / "memory.json")

        @contextmanager
        def fake_lock(_path):
            yield

        def bad_atomic_write_json(*_args, **_kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr("veritas_os.core.memory_store.locked_memory", fake_lock)
        monkeypatch.setattr(
            "veritas_os.core.atomic_io.atomic_write_json",
            bad_atomic_write_json,
        )

        assert store._save_all([]) is False

    def test_put_get_list_with_user_isolation(self, store):
        assert store.put("u1", "k1", "v1") is True
        assert store.put("u2", "k1", "v2") is True

        assert store.get("u1", "k1") == "v1"
        assert store.get("u2", "k1") == "v2"

        u1_records = store.list_all("u1")
        u2_records = store.list_all("u2")
        assert len(u1_records) == 1
        assert len(u2_records) == 1
        assert u1_records[0]["value"] == "v1"
        assert u2_records[0]["value"] == "v2"

    def test_expired_record_filtered_but_legal_hold_survives(self, store):
        now = datetime.now(timezone.utc).timestamp()
        expired = now - 60
        store.put(
            "u1",
            "expired",
            {"text": "stale", "meta": {"expires_at": expired, "legal_hold": False}},
        )
        store.put(
            "u1",
            "held",
            {"text": "protected", "meta": {"expires_at": expired, "legal_hold": True}},
        )

        assert store.get("u1", "expired") is None
        held = store.get("u1", "held")
        assert held is not None
        assert held["text"] == "protected"
        assert [r["key"] for r in store.list_all("u1")] == ["held"]

    def test_search_filters_by_user_kind_and_min_similarity(self, store):
        store.put("u1", "k1", {"text": "alpha plan", "kind": "episodic"})
        store.put("u2", "k2", {"text": "alpha plan", "kind": "semantic"})

        result = store.search(
            "alpha",
            user_id="u1",
            kinds=["episodic"],
            min_sim=0.5,
        )

        assert "episodic" in result
        assert len(result["episodic"]) == 1
        assert result["episodic"][0]["id"] == "k1"

    def test_search_returns_empty_when_filtered_out(self, store):
        store.put("u1", "k1", {"text": "tiny signal", "kind": "episodic"})

        assert store.search("completely different", min_sim=0.9) == {}
