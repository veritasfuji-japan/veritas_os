"""Hardening tests for MemoryStore branch coverage.

Targets uncovered branches in memory_store.py, memory_storage.py,
memory_lifecycle.py, and memory_compliance.py to ensure fail-safe
behavior under edge conditions: corrupt data, broken storage,
boundary user_id values, legal hold string variants, and race-prone
paths.
"""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import pytest

from veritas_os.core.memory_store import (
    ALLOWED_RETENTION_CLASSES,
    DEFAULT_RETENTION_CLASS,
    MemoryStore,
)


@pytest.fixture
def store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(tmp_path / "memory.json")


# ---------------------------------------------------------------------------
# MemoryStore.__init__ — cache TTL env var fallback
# ---------------------------------------------------------------------------


class TestCacheTTLEnvVar:
    def test_invalid_cache_ttl_falls_back_to_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Invalid VERITAS_MEMORY_CACHE_TTL triggers fallback to 5.0."""
        monkeypatch.setenv("VERITAS_MEMORY_CACHE_TTL", "not_a_number")
        s = MemoryStore(tmp_path / "memory.json")
        assert s._cache_ttl == 5.0

    def test_valid_cache_ttl_is_applied(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("VERITAS_MEMORY_CACHE_TTL", "10.0")
        s = MemoryStore(tmp_path / "memory.json")
        assert s._cache_ttl == 10.0


# ---------------------------------------------------------------------------
# _load_all — cache hit paths
# ---------------------------------------------------------------------------


class TestLoadAllCacheBehavior:
    def test_cache_hit_returns_cached_data(self, store: MemoryStore) -> None:
        """After put(), a subsequent _load_all should use cache if mtime matches."""
        store.put("u1", "k1", "v1")
        data1 = store._load_all(copy=True)
        data2 = store._load_all(copy=True)
        assert data1 == data2

    def test_cache_hit_copy_false_returns_same_reference(
        self, store: MemoryStore
    ) -> None:
        """copy=False on cache hit should return the same list object."""
        store.put("u1", "k1", "v1")
        # Prime the cache
        store._load_all(copy=False)
        ref1 = store._load_all(copy=False)
        ref2 = store._load_all(copy=False)
        assert ref1 is ref2

    def test_cache_stat_file_not_found(
        self, tmp_path: Path
    ) -> None:
        """If file is deleted between init and _load_all, mtime defaults to 0."""
        path = tmp_path / "memory.json"
        store = MemoryStore(path)
        path.unlink()
        data = store._load_all(copy=True, use_cache=True)
        assert data == []

    def test_load_all_copy_false_after_file_read(
        self, store: MemoryStore
    ) -> None:
        """copy=False after fresh read returns list without copying."""
        store.put("u1", "k1", "v1")
        store._cache_data = None  # Invalidate cache
        data = store._load_all(copy=False, use_cache=False)
        assert len(data) == 1
        assert data[0]["value"] == "v1"


# ---------------------------------------------------------------------------
# _load_all — error handling
# ---------------------------------------------------------------------------


class TestLoadAllErrorHandling:
    def test_os_error_on_file_read(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OSError during JSON load should return empty list."""
        path = tmp_path / "memory.json"
        path.write_text("[]", encoding="utf-8")
        store = MemoryStore(path)

        @contextmanager
        def boom_lock(_path, timeout=5.0):
            raise OSError("disk failure")

        monkeypatch.setattr("veritas_os.core.memory_store.locked_memory", boom_lock)
        data = store._load_all(copy=True, use_cache=False)
        assert data == []

    def test_timeout_error_on_file_read(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """TimeoutError during file lock should return empty list."""
        path = tmp_path / "memory.json"
        path.write_text("[]", encoding="utf-8")
        store = MemoryStore(path)

        @contextmanager
        def timeout_lock(_path, timeout=5.0):
            raise TimeoutError("lock timeout")

        monkeypatch.setattr("veritas_os.core.memory_store.locked_memory", timeout_lock)
        data = store._load_all(copy=True, use_cache=False)
        assert data == []


# ---------------------------------------------------------------------------
# _parse_expires_at — edge cases
# ---------------------------------------------------------------------------


class TestParseExpiresAtEdgeCases:
    def test_unsupported_type_returns_none(self) -> None:
        """Non-string/numeric types should return None (fail-closed)."""
        assert MemoryStore._parse_expires_at([1, 2]) is None
        assert MemoryStore._parse_expires_at({"key": "val"}) is None
        assert MemoryStore._parse_expires_at(object()) is None

    def test_whitespace_only_string_returns_none(self) -> None:
        assert MemoryStore._parse_expires_at("   ") is None

    def test_float_timestamp(self) -> None:
        result = MemoryStore._parse_expires_at(1700000000.5)
        assert result is not None and "2023" in result


# ---------------------------------------------------------------------------
# _is_record_expired — branch coverage
# ---------------------------------------------------------------------------


class TestIsRecordExpiredBranches:
    def test_non_dict_meta_returns_false(self) -> None:
        """If meta is not a dict, record is considered not expired."""
        record = {"value": {"meta": "not-a-dict"}}
        assert MemoryStore._is_record_expired(record) is False

    def test_string_legal_hold_true_prevents_expiry(self) -> None:
        """String 'true' legal_hold must prevent expiry (same as bool True)."""
        past = time.time() - 86400
        record = {"value": {"meta": {"expires_at": past, "legal_hold": "true"}}}
        assert MemoryStore._is_record_expired(record) is False

    def test_string_legal_hold_yes_prevents_expiry(self) -> None:
        past = time.time() - 86400
        record = {"value": {"meta": {"expires_at": past, "legal_hold": "yes"}}}
        assert MemoryStore._is_record_expired(record) is False

    def test_string_legal_hold_one_prevents_expiry(self) -> None:
        past = time.time() - 86400
        record = {"value": {"meta": {"expires_at": past, "legal_hold": "1"}}}
        assert MemoryStore._is_record_expired(record) is False

    def test_string_legal_hold_false_allows_expiry(self) -> None:
        """String 'false' must NOT prevent expiry."""
        past = time.time() - 86400
        record = {"value": {"meta": {"expires_at": past, "legal_hold": "false"}}}
        assert MemoryStore._is_record_expired(record) is True

    def test_now_ts_parameter_used(self) -> None:
        """Explicit now_ts should override time.time()."""
        record = {"value": {"meta": {"expires_at": "2024-01-01T00:00:00+00:00"}}}
        # now_ts before expiry
        assert MemoryStore._is_record_expired(record, now_ts=0.0) is False
        # now_ts after expiry
        future_ts = datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp()
        assert MemoryStore._is_record_expired(record, now_ts=future_ts) is True

    def test_value_is_none_returns_false(self) -> None:
        record = {"value": None}
        assert MemoryStore._is_record_expired(record) is False

    def test_empty_record_returns_false(self) -> None:
        assert MemoryStore._is_record_expired({}) is False


# ---------------------------------------------------------------------------
# _is_record_legal_hold / _should_cascade_delete_semantic delegates
# ---------------------------------------------------------------------------


class TestStaticDelegates:
    def test_is_record_legal_hold_true(self) -> None:
        record = {"value": {"meta": {"legal_hold": True}}}
        assert MemoryStore._is_record_legal_hold(record) is True

    def test_is_record_legal_hold_false(self) -> None:
        record = {"value": {"meta": {"legal_hold": False}}}
        assert MemoryStore._is_record_legal_hold(record) is False

    def test_is_record_legal_hold_string_true(self) -> None:
        record = {"value": {"meta": {"legal_hold": "true"}}}
        assert MemoryStore._is_record_legal_hold(record) is True

    def test_is_record_legal_hold_string_false(self) -> None:
        record = {"value": {"meta": {"legal_hold": "false"}}}
        assert MemoryStore._is_record_legal_hold(record) is False

    def test_should_cascade_delete_semantic_positive(self) -> None:
        record = {
            "value": {
                "kind": "semantic",
                "meta": {
                    "user_id": "u1",
                    "source_episode_keys": ["ep-1"],
                    "legal_hold": False,
                },
            }
        }
        assert (
            MemoryStore._should_cascade_delete_semantic(record, "u1", {"ep-1"})
            is True
        )

    def test_should_cascade_delete_semantic_negative(self) -> None:
        record = {
            "value": {
                "kind": "semantic",
                "meta": {
                    "user_id": "u1",
                    "source_episode_keys": ["ep-1"],
                    "legal_hold": False,
                },
            }
        }
        assert (
            MemoryStore._should_cascade_delete_semantic(record, "u1", {"ep-99"})
            is False
        )


# ---------------------------------------------------------------------------
# search() — branch coverage
# ---------------------------------------------------------------------------


class TestSearchBranches:
    def test_search_skips_non_dict_values(self, store: MemoryStore) -> None:
        """Records with non-dict values should be silently skipped."""
        store.put("u1", "k1", "plain string value")
        result = store.search("plain")
        assert result == {}

    def test_search_skips_records_without_text(self, store: MemoryStore) -> None:
        """Records with empty text/query should be skipped."""
        store.put("u1", "k1", {"kind": "episodic", "tags": ["t1"]})
        result = store.search("anything")
        assert result == {}

    def test_search_user_id_filtering(self, store: MemoryStore) -> None:
        """user_id filter excludes records from other users."""
        store.put("u1", "k1", {"text": "shared term", "kind": "episodic"})
        store.put("u2", "k2", {"text": "shared term", "kind": "episodic"})
        result = store.search("shared", user_id="u1")
        assert "episodic" in result
        ids = [h["meta"]["user_id"] for h in result["episodic"]]
        assert all(uid == "u1" for uid in ids)

    def test_search_kind_filtering(self, store: MemoryStore) -> None:
        """kinds filter only returns matching kinds."""
        store.put("u1", "k1", {"text": "term", "kind": "episodic"})
        store.put("u1", "k2", {"text": "term", "kind": "semantic"})
        result = store.search("term", kinds=["semantic"])
        assert "episodic" in result
        assert all(
            h["meta"]["kind"] == "semantic" for h in result["episodic"]
        )

    def test_search_respects_k_limit(self, store: MemoryStore) -> None:
        """k parameter limits the number of results."""
        for i in range(5):
            store.put("u1", f"k{i}", {"text": "common term", "kind": "episodic"})
        result = store.search("common", k=2)
        assert len(result.get("episodic", [])) <= 2

    def test_search_whitespace_query(self, store: MemoryStore) -> None:
        """Whitespace-only query should return empty dict."""
        store.put("u1", "k1", {"text": "hello", "kind": "episodic"})
        assert store.search("   ") == {}

    def test_search_none_query(self, store: MemoryStore) -> None:
        """None query should be handled safely."""
        assert store.search(None) == {}

    def test_search_result_structure(self, store: MemoryStore) -> None:
        """Verify search hit structure has expected keys."""
        store.put("u1", "k1", {"text": "target text", "kind": "episodic", "tags": ["t1"]})
        result = store.search("target")
        assert "episodic" in result
        hit = result["episodic"][0]
        assert set(hit.keys()) == {"id", "text", "score", "tags", "ts", "meta"}
        assert set(hit["meta"].keys()) == {"user_id", "created_at", "kind"}

    def test_search_sorted_by_score_descending(self, store: MemoryStore) -> None:
        """Results should be sorted by score, highest first."""
        store.put("u1", "k1", {"text": "partial match", "kind": "episodic"})
        store.put("u1", "k2", {"text": "exact partial match terms", "kind": "episodic"})
        result = store.search("partial match")
        hits = result.get("episodic", [])
        if len(hits) >= 2:
            assert hits[0]["score"] >= hits[1]["score"]


# ---------------------------------------------------------------------------
# _simple_score — edge cases
# ---------------------------------------------------------------------------


class TestSimpleScoreEdgeCases:
    def test_empty_text_returns_zero(self, store: MemoryStore) -> None:
        assert store._simple_score("hello", "") == 0.0

    def test_both_empty(self, store: MemoryStore) -> None:
        assert store._simple_score("", "") == 0.0

    def test_token_overlap_without_substring(self, store: MemoryStore) -> None:
        """Tokens match but full substring does not."""
        score = store._simple_score("alpha beta", "gamma alpha delta")
        assert 0.0 < score < 1.0

    def test_reverse_substring(self, store: MemoryStore) -> None:
        """When text is contained in query (reverse substring)."""
        score = store._simple_score("hello world foo", "hello")
        assert score >= 0.5

    def test_case_insensitive(self, store: MemoryStore) -> None:
        score = store._simple_score("HELLO", "hello world")
        assert score >= 0.5


# ---------------------------------------------------------------------------
# recent() — edge cases
# ---------------------------------------------------------------------------


class TestRecentEdgeCases:
    def test_recent_with_non_dict_value_and_contains(
        self, store: MemoryStore
    ) -> None:
        """Non-dict values should be stringified for contains matching."""
        store.put("u1", "k1", "simple string with keyword")
        results = store.recent("u1", contains="keyword")
        assert len(results) == 1

    def test_recent_no_match_contains(self, store: MemoryStore) -> None:
        store.put("u1", "k1", {"text": "no match here"})
        results = store.recent("u1", contains="zzz")
        assert len(results) == 0

    def test_recent_empty_user(self, store: MemoryStore) -> None:
        results = store.recent("nonexistent_user")
        assert results == []


# ---------------------------------------------------------------------------
# put_episode — branch coverage
# ---------------------------------------------------------------------------


class TestPutEpisodeBranches:
    def test_kwargs_passthrough(self, store: MemoryStore) -> None:
        """Extra kwargs should be added to the episode record."""
        key = store.put_episode(
            "text", tags=["t"], meta={"user_id": "u1"}, custom_field="custom_val"
        )
        record = store.get("u1", key)
        assert record["custom_field"] == "custom_val"

    def test_kwargs_do_not_overwrite_existing_keys(
        self, store: MemoryStore
    ) -> None:
        """kwargs should not overwrite text/tags/meta."""
        key = store.put_episode(
            "original", tags=["orig"], meta={"user_id": "u1"}, extra="extra_val"
        )
        record = store.get("u1", key)
        assert record["text"] == "original"
        assert record["extra"] == "extra_val"

    def test_put_episode_stores_to_kvs(self, store: MemoryStore) -> None:
        """put_episode should persist the episode via KVS put."""
        key = store.put_episode("saved text", tags=["t1"])
        # Default user_id when none in meta is "episodic"
        record = store.get("episodic", key)
        assert record is not None
        assert record["text"] == "saved text"
        assert record["tags"] == ["t1"]

    def test_put_episode_with_user_meta(self, store: MemoryStore) -> None:
        """put_episode should use meta.user_id if provided."""
        key = store.put_episode("test", meta={"user_id": "alice"})
        record = store.get("alice", key)
        assert record is not None

    def test_vector_sync_success_via_original(
        self, tmp_path: Path
    ) -> None:
        """Test vector sync using the original put_episode (not compat).

        This tests the _get_mem_vec_fn parameter which only exists on the
        original MemoryStore.put_episode, not the compat replacement.
        """
        # Use the original method directly to bypass any compat replacement
        from veritas_os.core.memory_store import MemoryStore as MS

        store = MS(tmp_path / "memory.json")
        vec = mock.Mock()
        vec.add.return_value = "vec-id"

        # Call the original class method descriptor directly
        original_put_episode = MS.__dict__.get("put_episode")
        if original_put_episode is None:
            pytest.skip("put_episode not in class __dict__ (replaced by compat)")

        import inspect
        sig = inspect.signature(original_put_episode)
        if "_get_mem_vec_fn" not in sig.parameters:
            pytest.skip("put_episode has been replaced by compat layer")

        key = original_put_episode(
            store, "sync test", tags=["t"], _get_mem_vec_fn=lambda: vec
        )
        assert key.startswith("episode_")
        vec.add.assert_called_once()

    def test_vector_sync_fn_returns_none(self, store: MemoryStore) -> None:
        """put_episode when _get_mem_vec_fn returns None."""
        import inspect

        sig = inspect.signature(type(store).put_episode)
        if "_get_mem_vec_fn" not in sig.parameters:
            pytest.skip("put_episode has been replaced by compat layer")

        key = store.put_episode(
            "no vec", tags=["t"], _get_mem_vec_fn=lambda: None
        )
        assert key.startswith("episode_")

    def test_vector_sync_error_logged(
        self, store: MemoryStore, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Vector add error should be logged, not raised."""
        import inspect

        sig = inspect.signature(type(store).put_episode)
        if "_get_mem_vec_fn" not in sig.parameters:
            pytest.skip("put_episode has been replaced by compat layer")

        vec = mock.Mock()
        vec.add.side_effect = RuntimeError("vector down")

        with caplog.at_level("WARNING"):
            key = store.put_episode(
                "fail vec", tags=["t"], _get_mem_vec_fn=lambda: vec
            )

        assert key.startswith("episode_")
        assert "MEM_VEC.add error" in caplog.text

    def test_default_user_id_is_episodic(self, store: MemoryStore) -> None:
        """Without meta.user_id, default user_id should be 'episodic'."""
        key = store.put_episode("no user", tags=[])
        record = store.get("episodic", key)
        assert record is not None
        assert record["text"] == "no user"


# ---------------------------------------------------------------------------
# erase_user — integration
# ---------------------------------------------------------------------------


class TestEraseUserIntegration:
    def test_erase_with_legal_hold_protection(self, store: MemoryStore) -> None:
        """Records with legal hold survive erasure."""
        past = time.time() - 86400
        store.put("u1", "normal", {"text": "delete me"})
        store.put(
            "u1",
            "held",
            {"text": "protected", "meta": {"legal_hold": True, "expires_at": past}},
        )
        report = store.erase_user("u1", "gdpr", "admin")
        assert report["deleted_count"] >= 1
        assert report["protected_by_legal_hold"] >= 1
        # Legal hold record should survive
        held = store.get("u1", "held")
        assert held is not None

    def test_erase_with_string_legal_hold(self, store: MemoryStore) -> None:
        """String 'true' legal_hold should protect from erasure."""
        store.put(
            "u1",
            "held_str",
            {"text": "protected", "meta": {"legal_hold": "true"}},
        )
        report = store.erase_user("u1", "gdpr", "admin")
        assert report["protected_by_legal_hold"] >= 1
        assert store.get("u1", "held_str") is not None

    def test_erase_creates_audit_trail(self, store: MemoryStore) -> None:
        """Erase should create an audit record."""
        store.put("u1", "k1", "v1")
        store.erase_user("u1", "gdpr", "admin")
        all_records = store.list_all()
        audit = [r for r in all_records if r.get("user_id") == "__audit__"]
        assert len(audit) >= 1

    def test_erase_cascade_deletes_semantic_lineage(
        self, store: MemoryStore
    ) -> None:
        """Semantic records sourced from erased episodes should be cascade-deleted."""
        store.put("u1", "ep1", {"text": "episode", "kind": "episodic"})
        store.put(
            "u1",
            "sem1",
            {
                "text": "semantic summary",
                "kind": "semantic",
                "meta": {
                    "user_id": "u1",
                    "source_episode_keys": ["ep1"],
                    "legal_hold": False,
                },
            },
        )
        report = store.erase_user("u1", "gdpr", "admin")
        assert report["cascade_deleted_count"] >= 1
        assert store.get("u1", "sem1") is None

    def test_erase_report_ok_false_on_save_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If saving fails after erase, report['ok'] should be False."""
        store = MemoryStore(tmp_path / "memory.json")
        store.put("u1", "k1", "v1")

        # Make _save_all always fail from now on
        monkeypatch.setattr(store, "_save_all", lambda data: False)
        report = store.erase_user("u1", "gdpr", "admin")
        assert report["ok"] is False

    def test_erase_other_user_unaffected(self, store: MemoryStore) -> None:
        """Erasing u1 should not affect u2's records."""
        store.put("u1", "k1", "v1")
        store.put("u2", "k2", "v2")
        store.erase_user("u1", "gdpr", "admin")
        assert store.get("u2", "k2") == "v2"


# ---------------------------------------------------------------------------
# _save_all — error branches
# ---------------------------------------------------------------------------


class TestSaveAllErrorBranches:
    def test_os_error_returns_false(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = MemoryStore(tmp_path / "memory.json")

        @contextmanager
        def fake_lock(_path, timeout=5.0):
            yield

        monkeypatch.setattr("veritas_os.core.memory_store.locked_memory", fake_lock)
        monkeypatch.setattr(
            "veritas_os.core.atomic_io.atomic_write_json",
            mock.Mock(side_effect=OSError("write failed")),
        )
        assert store._save_all([]) is False

    def test_type_error_returns_false(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = MemoryStore(tmp_path / "memory.json")

        @contextmanager
        def fake_lock(_path, timeout=5.0):
            yield

        monkeypatch.setattr("veritas_os.core.memory_store.locked_memory", fake_lock)
        monkeypatch.setattr(
            "veritas_os.core.atomic_io.atomic_write_json",
            mock.Mock(side_effect=TypeError("bad data")),
        )
        assert store._save_all([]) is False

    def test_value_error_returns_false(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = MemoryStore(tmp_path / "memory.json")

        @contextmanager
        def fake_lock(_path, timeout=5.0):
            yield

        monkeypatch.setattr("veritas_os.core.memory_store.locked_memory", fake_lock)
        monkeypatch.setattr(
            "veritas_os.core.atomic_io.atomic_write_json",
            mock.Mock(side_effect=ValueError("encoding")),
        )
        assert store._save_all([]) is False

    def test_timeout_error_returns_false(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = MemoryStore(tmp_path / "memory.json")

        @contextmanager
        def fake_lock(_path, timeout=5.0):
            raise TimeoutError("lock failed")

        monkeypatch.setattr("veritas_os.core.memory_store.locked_memory", fake_lock)
        assert store._save_all([]) is False


# ---------------------------------------------------------------------------
# memory_lifecycle.py — parse_legal_hold
# ---------------------------------------------------------------------------


class TestParseLegalHold:
    def test_bool_true(self) -> None:
        from veritas_os.core.memory_lifecycle import parse_legal_hold

        assert parse_legal_hold(True) is True

    def test_bool_false(self) -> None:
        from veritas_os.core.memory_lifecycle import parse_legal_hold

        assert parse_legal_hold(False) is False

    def test_string_true_variants(self) -> None:
        from veritas_os.core.memory_lifecycle import parse_legal_hold

        assert parse_legal_hold("true") is True
        assert parse_legal_hold("True") is True
        assert parse_legal_hold("TRUE") is True
        assert parse_legal_hold("1") is True
        assert parse_legal_hold("yes") is True
        assert parse_legal_hold("YES") is True

    def test_string_false_variants(self) -> None:
        from veritas_os.core.memory_lifecycle import parse_legal_hold

        assert parse_legal_hold("false") is False
        assert parse_legal_hold("False") is False
        assert parse_legal_hold("0") is False
        assert parse_legal_hold("no") is False
        assert parse_legal_hold("") is False

    def test_int_values(self) -> None:
        from veritas_os.core.memory_lifecycle import parse_legal_hold

        assert parse_legal_hold(1) is True
        assert parse_legal_hold(0) is False

    def test_none(self) -> None:
        from veritas_os.core.memory_lifecycle import parse_legal_hold

        assert parse_legal_hold(None) is False


# ---------------------------------------------------------------------------
# memory_lifecycle.py — additional branch coverage
# ---------------------------------------------------------------------------


class TestLifecycleAdditionalBranches:
    def test_normalize_lifecycle_non_dict_returns_unchanged(self) -> None:
        from veritas_os.core.memory_lifecycle import normalize_lifecycle, parse_expires_at

        assert normalize_lifecycle(42, "standard", {"standard"}, parse_expires_at) == 42
        assert (
            normalize_lifecycle("str", "standard", {"standard"}, parse_expires_at)
            == "str"
        )

    def test_normalize_lifecycle_string_legal_hold(self) -> None:
        """String legal_hold 'false' should be normalized to bool False."""
        from veritas_os.core.memory_lifecycle import normalize_lifecycle, parse_expires_at

        result = normalize_lifecycle(
            {"text": "x", "meta": {"legal_hold": "false"}},
            "standard",
            ALLOWED_RETENTION_CLASSES,
            parse_expires_at,
        )
        assert result["meta"]["legal_hold"] is False

    def test_normalize_lifecycle_string_legal_hold_yes(self) -> None:
        from veritas_os.core.memory_lifecycle import normalize_lifecycle, parse_expires_at

        result = normalize_lifecycle(
            {"text": "x", "meta": {"legal_hold": "yes"}},
            "standard",
            ALLOWED_RETENTION_CLASSES,
            parse_expires_at,
        )
        assert result["meta"]["legal_hold"] is True

    def test_is_record_expired_string_legal_hold_protects(self) -> None:
        """String 'true' legal hold should protect in lifecycle module too."""
        from veritas_os.core.memory_lifecycle import is_record_expired, parse_expires_at

        record = {
            "value": {
                "meta": {
                    "expires_at": "2020-01-01T00:00:00+00:00",
                    "legal_hold": "true",
                }
            }
        }
        assert (
            is_record_expired(record, parse_expires_at, now_ts=2_000_000_000.0)
            is False
        )

    def test_is_record_expired_string_legal_hold_false_allows(self) -> None:
        """String 'false' legal hold must NOT protect."""
        from veritas_os.core.memory_lifecycle import is_record_expired, parse_expires_at

        record = {
            "value": {
                "meta": {
                    "expires_at": "2020-01-01T00:00:00+00:00",
                    "legal_hold": "false",
                }
            }
        }
        assert (
            is_record_expired(record, parse_expires_at, now_ts=2_000_000_000.0)
            is True
        )

    def test_is_record_legal_hold_non_dict_value(self) -> None:
        from veritas_os.core.memory_lifecycle import is_record_legal_hold

        assert is_record_legal_hold({"value": "not-a-dict"}) is False

    def test_is_record_legal_hold_non_dict_meta(self) -> None:
        from veritas_os.core.memory_lifecycle import is_record_legal_hold

        assert is_record_legal_hold({"value": {"meta": "not-a-dict"}}) is False

    def test_is_record_legal_hold_string_true(self) -> None:
        from veritas_os.core.memory_lifecycle import is_record_legal_hold

        assert is_record_legal_hold({"value": {"meta": {"legal_hold": "true"}}}) is True

    def test_is_record_legal_hold_string_false(self) -> None:
        from veritas_os.core.memory_lifecycle import is_record_legal_hold

        assert (
            is_record_legal_hold({"value": {"meta": {"legal_hold": "false"}}}) is False
        )

    def test_should_cascade_delete_non_dict_value(self) -> None:
        from veritas_os.core.memory_lifecycle import should_cascade_delete_semantic

        assert (
            should_cascade_delete_semantic(
                {"value": "string"}, "u1", {"ep-1"}
            )
            is False
        )

    def test_should_cascade_delete_non_dict_meta(self) -> None:
        from veritas_os.core.memory_lifecycle import should_cascade_delete_semantic

        record = {"value": {"kind": "semantic", "meta": "not-a-dict"}}
        assert (
            should_cascade_delete_semantic(record, "u1", {"ep-1"}) is False
        )

    def test_should_cascade_delete_string_legal_hold_protects(self) -> None:
        """String 'true' legal_hold should protect semantic records."""
        from veritas_os.core.memory_lifecycle import should_cascade_delete_semantic

        record = {
            "value": {
                "kind": "semantic",
                "meta": {
                    "user_id": "u1",
                    "source_episode_keys": ["ep-1"],
                    "legal_hold": "true",
                },
            }
        }
        assert (
            should_cascade_delete_semantic(record, "u1", {"ep-1"}) is False
        )


# ---------------------------------------------------------------------------
# memory_compliance.py — string legal_hold consistency
# ---------------------------------------------------------------------------


class TestComplianceStringLegalHold:
    def test_is_record_legal_hold_string_true(self) -> None:
        from veritas_os.core.memory_compliance import is_record_legal_hold

        assert is_record_legal_hold({"value": {"meta": {"legal_hold": "true"}}}) is True

    def test_is_record_legal_hold_string_false(self) -> None:
        from veritas_os.core.memory_compliance import is_record_legal_hold

        assert (
            is_record_legal_hold({"value": {"meta": {"legal_hold": "false"}}}) is False
        )

    def test_should_cascade_delete_string_legal_hold(self) -> None:
        from veritas_os.core.memory_compliance import should_cascade_delete_semantic

        record = {
            "value": {
                "kind": "semantic",
                "meta": {
                    "user_id": "u1",
                    "source_episode_keys": ["ep-1"],
                    "legal_hold": "true",
                },
            }
        }
        assert (
            should_cascade_delete_semantic(record, "u1", {"ep-1"}) is False
        )

    def test_erase_user_data_respects_string_legal_hold(self) -> None:
        """String 'true' legal_hold should protect records during erasure."""
        from veritas_os.core.memory_compliance import erase_user_data

        data = [
            {
                "user_id": "u1",
                "key": "k1",
                "value": {"text": "protected", "meta": {"legal_hold": "true"}},
            },
            {
                "user_id": "u1",
                "key": "k2",
                "value": {"text": "delete me"},
            },
        ]
        kept, report = erase_user_data(data, "u1", "test", "admin")
        assert report["protected_by_legal_hold"] == 1
        assert report["deleted_count"] == 1
        user_records = [r for r in kept if r.get("user_id") == "u1"]
        assert len(user_records) == 1

    def test_erase_user_data_string_false_not_protected(self) -> None:
        """String 'false' legal_hold should NOT protect records."""
        from veritas_os.core.memory_compliance import erase_user_data

        data = [
            {
                "user_id": "u1",
                "key": "k1",
                "value": {"text": "exposed", "meta": {"legal_hold": "false"}},
            },
        ]
        kept, report = erase_user_data(data, "u1", "test", "admin")
        assert report["protected_by_legal_hold"] == 0
        assert report["deleted_count"] == 1


# ---------------------------------------------------------------------------
# POSIX flock timeout (memory_storage.py)
# ---------------------------------------------------------------------------


class TestLockedMemoryPosixTimeout:
    @pytest.mark.skipif(
        os.name == "nt",
        reason="POSIX flock branch only",
    )
    def test_posix_flock_timeout_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """POSIX flock should raise TimeoutError when lock not acquired."""
        import veritas_os.core.memory_storage as memory_storage

        if memory_storage.fcntl is None:
            pytest.skip("fcntl not available")

        target = tmp_path / "memory.json"

        def always_block(fd, operation):
            if operation != memory_storage.fcntl.LOCK_UN:
                raise BlockingIOError("always busy")

        monkeypatch.setattr(memory_storage.fcntl, "flock", always_block)
        monkeypatch.setattr(memory_storage.time, "sleep", lambda _: None)

        times = iter([0.0, 0.3, 0.7])
        monkeypatch.setattr(memory_storage.time, "time", lambda: next(times))

        with pytest.raises(TimeoutError, match="failed to acquire lock"):
            with memory_storage.locked_memory(target, timeout=0.5):
                pass


# ---------------------------------------------------------------------------
# End-to-end: persist / load round-trip
# ---------------------------------------------------------------------------


class TestPersistLoadRoundTrip:
    def test_data_survives_new_store_instance(self, tmp_path: Path) -> None:
        """Data written by one MemoryStore instance should be loadable by another."""
        path = tmp_path / "memory.json"
        store1 = MemoryStore(path)
        store1.put("u1", "k1", {"text": "persistent", "kind": "episodic"})

        store2 = MemoryStore(path)
        val = store2.get("u1", "k1")
        assert val is not None
        assert val["text"] == "persistent"

    def test_corrupt_json_recovery(self, tmp_path: Path) -> None:
        """Store should recover gracefully from corrupt JSON on disk."""
        path = tmp_path / "memory.json"
        store = MemoryStore(path)
        store.put("u1", "k1", "v1")

        # Corrupt the file
        path.write_text("<<<CORRUPT>>>", encoding="utf-8")

        data = store._load_all(copy=True, use_cache=False)
        assert data == []

        # Store should still be usable after corruption
        assert store.put("u1", "k2", "v2") is True
        assert store.get("u1", "k2") == "v2"

    def test_unicode_values_round_trip(self, tmp_path: Path) -> None:
        """Unicode text should survive persist/load cycle."""
        path = tmp_path / "memory.json"
        store = MemoryStore(path)
        store.put("u1", "k1", {"text": "日本語テスト 🎌", "kind": "episodic"})

        store2 = MemoryStore(path)
        val = store2.get("u1", "k1")
        assert val["text"] == "日本語テスト 🎌"


# ---------------------------------------------------------------------------
# User-ID boundary tests
# ---------------------------------------------------------------------------


class TestUserIdBoundary:
    def test_empty_string_user_id(self, store: MemoryStore) -> None:
        """Empty-string user_id should be a valid, distinct namespace."""
        store.put("", "k1", "empty-user")
        store.put("u1", "k1", "normal-user")
        assert store.get("", "k1") == "empty-user"
        assert store.get("u1", "k1") == "normal-user"

    def test_special_char_user_id(self, store: MemoryStore) -> None:
        """Special characters in user_id should work."""
        uid = "user@domain.com/path#fragment"
        store.put(uid, "k1", "special")
        assert store.get(uid, "k1") == "special"

    def test_user_isolation_in_search(self, store: MemoryStore) -> None:
        """Search with user_id should be isolated per user."""
        store.put("u1", "k1", {"text": "shared concept", "kind": "episodic"})
        store.put("u2", "k2", {"text": "shared concept", "kind": "episodic"})
        r1 = store.search("shared", user_id="u1")
        r2 = store.search("shared", user_id="u2")
        if r1.get("episodic"):
            assert all(h["meta"]["user_id"] == "u1" for h in r1["episodic"])
        if r2.get("episodic"):
            assert all(h["meta"]["user_id"] == "u2" for h in r2["episodic"])
