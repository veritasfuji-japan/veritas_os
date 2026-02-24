# veritas_os/tests/test_memory_coverage.py
"""
Coverage-boost tests for veritas_os/core/memory.py.
Focus on utility functions, class methods, and edge cases
that can be tested in isolation.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from veritas_os.core import memory


# =========================================================
# 1. Pickle / security helpers
# =========================================================


class TestAllowLegacyPickleMigration:
    def test_default_false(self, monkeypatch):
        monkeypatch.delenv("VERITAS_MEMORY_ALLOW_PICKLE_MIGRATION", raising=False)
        assert memory._allow_legacy_pickle_migration() is False

    @pytest.mark.parametrize("val", ["1", "true", "yes", "y", "on", "TRUE", " Yes "])
    def test_truthy_values(self, monkeypatch, val):
        monkeypatch.setenv("VERITAS_MEMORY_ALLOW_PICKLE_MIGRATION", val)
        assert memory._allow_legacy_pickle_migration() is True

    def test_falsy_value(self, monkeypatch):
        monkeypatch.setenv("VERITAS_MEMORY_ALLOW_PICKLE_MIGRATION", "no")
        assert memory._allow_legacy_pickle_migration() is False

    def test_sunset_passed_forces_false(self, monkeypatch):
        monkeypatch.setenv("VERITAS_MEMORY_ALLOW_PICKLE_MIGRATION", "1")
        monkeypatch.setenv("VERITAS_MEMORY_PICKLE_MIGRATION_SUNSET", "2000-01-01")
        assert memory._allow_legacy_pickle_migration() is False


class TestLegacyPickleMigrationSunset:
    def test_past_sunset(self, monkeypatch):
        monkeypatch.setenv("VERITAS_MEMORY_PICKLE_MIGRATION_SUNSET", "2000-01-01")
        assert memory._legacy_pickle_migration_sunset_passed() is True

    def test_future_sunset(self, monkeypatch):
        monkeypatch.setenv("VERITAS_MEMORY_PICKLE_MIGRATION_SUNSET", "2999-12-31")
        assert memory._legacy_pickle_migration_sunset_passed() is False

    def test_invalid_sunset_fails_closed(self, monkeypatch):
        monkeypatch.setenv("VERITAS_MEMORY_PICKLE_MIGRATION_SUNSET", "invalid-date")
        assert memory._legacy_pickle_migration_sunset_passed() is True


class TestShouldDeletePickleAfterMigration:
    def test_default_delete(self, monkeypatch):
        monkeypatch.delenv("VERITAS_MEMORY_KEEP_PICKLE_BACKUP", raising=False)
        assert memory._should_delete_pickle_after_migration() is True

    def test_keep_backup(self, monkeypatch):
        monkeypatch.setenv("VERITAS_MEMORY_KEEP_PICKLE_BACKUP", "1")
        assert memory._should_delete_pickle_after_migration() is False


class TestIsPickleFileStale:
    def test_fresh_file(self, tmp_path):
        p = tmp_path / "fresh.pkl"
        p.write_bytes(b"data")
        assert memory._is_pickle_file_stale(p, max_age_days=90) is False

    def test_stale_returns_true_on_missing(self, tmp_path):
        p = tmp_path / "nonexistent.pkl"
        assert memory._is_pickle_file_stale(p) is True




class TestLegacyPickleSizeLimit:
    def test_max_pickle_size_default(self, monkeypatch):
        monkeypatch.delenv("VERITAS_MEMORY_MAX_PICKLE_SIZE_BYTES", raising=False)
        assert memory._max_legacy_pickle_size_bytes() == 10 * 1024 * 1024

    def test_max_pickle_size_invalid_env_uses_default(self, monkeypatch):
        monkeypatch.setenv("VERITAS_MEMORY_MAX_PICKLE_SIZE_BYTES", "invalid")
        assert memory._max_legacy_pickle_size_bytes() == 10 * 1024 * 1024

    def test_max_pickle_size_non_positive_uses_default(self, monkeypatch):
        monkeypatch.setenv("VERITAS_MEMORY_MAX_PICKLE_SIZE_BYTES", "0")
        assert memory._max_legacy_pickle_size_bytes() == 10 * 1024 * 1024

    def test_safe_read_legacy_pickle_bytes_within_limit(self, tmp_path, monkeypatch):
        p = tmp_path / "legacy.pkl"
        payload = b"abcde"
        p.write_bytes(payload)
        monkeypatch.setenv("VERITAS_MEMORY_MAX_PICKLE_SIZE_BYTES", "5")

        assert memory._safe_read_legacy_pickle_bytes(p) == payload

    def test_safe_read_legacy_pickle_bytes_oversized_raises(self, tmp_path, monkeypatch):
        p = tmp_path / "legacy.pkl"
        p.write_bytes(b"012345")
        monkeypatch.setenv("VERITAS_MEMORY_MAX_PICKLE_SIZE_BYTES", "5")

        with pytest.raises(ValueError, match="too large"):
            memory._safe_read_legacy_pickle_bytes(p)


class TestValidatePickleDataStructure:
    def test_valid_structure_no_embeddings(self):
        data = {"documents": [{"id": "1"}], "embeddings": None}
        assert memory._validate_pickle_data_structure(data) is True

    def test_not_dict(self):
        assert memory._validate_pickle_data_structure([1, 2]) is False

    def test_documents_not_list(self):
        assert memory._validate_pickle_data_structure({"documents": "oops"}) is False

    def test_document_element_not_dict(self):
        data = {"documents": ["bad"]}
        assert memory._validate_pickle_data_structure(data) is False

    def test_empty_documents(self):
        data = {"documents": []}
        assert memory._validate_pickle_data_structure(data) is True

    def test_none_documents(self):
        data = {"documents": None}
        assert memory._validate_pickle_data_structure(data) is True


class TestRestrictedUnpicklerFindClass:
    def test_blocked_reconstruct(self):
        import pickle
        with pytest.raises(pickle.UnpicklingError, match="blocked"):
            memory.RestrictedUnpickler._find_class("numpy.core.multiarray", "_reconstruct")

    def test_blocked_scalar(self):
        import pickle
        with pytest.raises(pickle.UnpicklingError, match="blocked"):
            memory.RestrictedUnpickler._find_class("numpy", "scalar")

    def test_allowed_builtin_dict(self):
        result = memory.RestrictedUnpickler._find_class("builtins", "dict")
        assert result is dict

    def test_disallowed_module(self):
        import pickle
        with pytest.raises(pickle.UnpicklingError, match="not allowed"):
            memory.RestrictedUnpickler._find_class("os", "system")


# =========================================================
# 2. _hits_to_evidence
# =========================================================


class TestHitsToEvidence:
    def test_basic_conversion(self):
        hits = [
            {"id": "ep_1", "text": "hello world", "score": 0.9, "tags": ["t"], "meta": {}},
        ]
        result = memory._hits_to_evidence(hits, source_prefix="mem")
        assert len(result) == 1
        assert result[0]["source"] == "mem:ep_1"
        assert result[0]["text"] == "hello world"
        assert result[0]["score"] == 0.9

    def test_skips_non_dict(self):
        hits = ["not_a_dict", {"id": "1", "text": "ok"}]
        result = memory._hits_to_evidence(hits)
        assert len(result) == 1

    def test_skips_empty_text(self):
        hits = [{"id": "x", "text": ""}]
        result = memory._hits_to_evidence(hits)
        assert len(result) == 0

    def test_missing_id_uses_unknown(self):
        hits = [{"text": "data"}]
        result = memory._hits_to_evidence(hits)
        assert result[0]["source"] == "memory:unknown"


# =========================================================
# 3. get_evidence_for_decision / get_evidence_for_query
# =========================================================


class TestGetEvidenceForDecision:
    def test_empty_query_returns_empty(self, monkeypatch):
        result = memory.get_evidence_for_decision({})
        assert result == []

    def test_extracts_query_from_chosen(self, monkeypatch):
        monkeypatch.setattr(memory, "search", lambda **kw: [])
        decision = {"chosen": {"title": "test title"}}
        result = memory.get_evidence_for_decision(decision)
        assert result == []

    def test_calls_search_with_user_id(self, monkeypatch):
        captured = {}

        def mock_search(**kwargs):
            captured.update(kwargs)
            return [{"id": "1", "text": "hit", "score": 0.5}]

        monkeypatch.setattr(memory, "search", mock_search)
        decision = {"query": "test", "context": {"user_id": "u1"}}
        result = memory.get_evidence_for_decision(decision, top_k=3)
        assert captured["user_id"] == "u1"
        assert captured["k"] == 3
        assert len(result) == 1


class TestGetEvidenceForQuery:
    def test_empty_query(self):
        assert memory.get_evidence_for_query("") == []

    def test_returns_evidence(self, monkeypatch):
        monkeypatch.setattr(
            memory, "search",
            lambda **kw: [{"id": "1", "text": "match", "score": 0.8}],
        )
        result = memory.get_evidence_for_query("test query")
        assert len(result) == 1
        assert result[0]["source"].startswith("memory:")

    def test_non_list_search_result(self, monkeypatch):
        monkeypatch.setattr(memory, "search", lambda **kw: None)
        assert memory.get_evidence_for_query("test") == []


# =========================================================
# 4. _LazyMemoryStore
# =========================================================


class TestLazyMemoryStore:
    def test_lazy_load_on_first_access(self, tmp_path):
        path = tmp_path / "mem.json"
        calls = {"count": 0}

        def loader():
            calls["count"] += 1
            return memory.MemoryStore(path)

        lazy = memory._LazyMemoryStore(loader)
        assert calls["count"] == 0
        # Trigger load via attribute access
        _ = lazy.path
        assert calls["count"] == 1
        # Second access should not call loader again
        _ = lazy.path
        assert calls["count"] == 1

    def test_error_raised_on_failed_load(self):
        def bad_loader():
            raise ValueError("boom")

        lazy = memory._LazyMemoryStore(bad_loader)
        with pytest.raises(ValueError, match="boom"):
            _ = lazy.path

    def test_subsequent_access_raises_after_failure(self):
        def bad_loader():
            raise ValueError("once")

        lazy = memory._LazyMemoryStore(bad_loader)
        with pytest.raises(ValueError):
            _ = lazy.path
        with pytest.raises(RuntimeError, match="MemoryStore load failed"):
            _ = lazy.path


# =========================================================
# 5. MemoryStore: summarize_for_planner
# =========================================================


class TestSummarizeForPlanner:
    def test_no_results(self, tmp_path):
        store = memory.MemoryStore(tmp_path / "mem.json")
        result = store.summarize_for_planner("u1", "test")
        assert "見つかりませんでした" in result

    def test_with_results(self, tmp_path):
        store = memory.MemoryStore(tmp_path / "mem.json")
        store.put("u1", "k1", {"text": "important note", "kind": "episodic"})
        result = store.summarize_for_planner("u1", "important")
        assert "MemoryOS 要約" in result
        assert "important note" in result

    def test_truncates_long_text(self, tmp_path):
        store = memory.MemoryStore(tmp_path / "mem.json")
        long_text = "x" * 200
        store.put("u1", "k1", {"text": long_text, "kind": "episodic"})
        result = store.summarize_for_planner("u1", long_text[:10])
        assert "..." in result


# =========================================================
# 6. MemoryStore: _simple_score
# =========================================================


class TestSimpleScore:
    def test_empty_query_returns_zero(self, tmp_path):
        store = memory.MemoryStore(tmp_path / "mem.json")
        assert store._simple_score("", "text") == 0.0

    def test_empty_text_returns_zero(self, tmp_path):
        store = memory.MemoryStore(tmp_path / "mem.json")
        assert store._simple_score("query", "") == 0.0

    def test_substring_match(self, tmp_path):
        store = memory.MemoryStore(tmp_path / "mem.json")
        score = store._simple_score("hello", "say hello world")
        assert score >= 0.5

    def test_token_match(self, tmp_path):
        store = memory.MemoryStore(tmp_path / "mem.json")
        score = store._simple_score("hello world", "hello there world")
        assert score > 0.0


# =========================================================
# 7. _dedup_hits
# =========================================================


class TestDedupHits:
    def test_dedup_same_text_same_user(self):
        hits = [
            {"text": "a", "meta": {"user_id": "u1"}, "score": 1.0},
            {"text": "a", "meta": {"user_id": "u1"}, "score": 0.5},
        ]
        result = memory._dedup_hits(hits, k=10)
        assert len(result) == 1

    def test_keeps_different_texts(self):
        hits = [
            {"text": "a", "meta": {"user_id": "u1"}},
            {"text": "b", "meta": {"user_id": "u1"}},
        ]
        result = memory._dedup_hits(hits, k=10)
        assert len(result) == 2

    def test_respects_k_limit(self):
        hits = [
            {"text": f"t{i}", "meta": {"user_id": "u1"}} for i in range(10)
        ]
        result = memory._dedup_hits(hits, k=3)
        assert len(result) == 3

    def test_skips_non_dict(self):
        hits = ["not_dict", {"text": "ok", "meta": {}}]
        result = memory._dedup_hits(hits, k=10)
        assert len(result) == 1


# =========================================================
# 8. MemoryStore: put, get, search, recent
# =========================================================


class TestMemoryStorePutGet:
    def test_put_update_existing(self, tmp_path):
        store = memory.MemoryStore(tmp_path / "mem.json")
        store.put("u1", "k1", {"text": "v1"})
        store.put("u1", "k1", {"text": "v2"})
        val = store.get("u1", "k1")
        assert val["text"] == "v2"

    def test_get_nonexistent(self, tmp_path):
        store = memory.MemoryStore(tmp_path / "mem.json")
        assert store.get("u1", "missing") is None

    def test_search_empty_query(self, tmp_path):
        store = memory.MemoryStore(tmp_path / "mem.json")
        assert store.search("") == {}

    def test_search_with_kinds_filter(self, tmp_path):
        store = memory.MemoryStore(tmp_path / "mem.json")
        store.put("u1", "k1", {"text": "hello world", "kind": "episodic"})
        store.put("u1", "k2", {"text": "hello world", "kind": "semantic"})
        result = store.search("hello", kinds=["semantic"], user_id="u1")
        if result:
            for hit_list in result.values():
                for hit in hit_list:
                    assert hit["meta"]["kind"] == "semantic"


class TestMemoryStoreNormalize:
    def test_normalize_list(self, tmp_path):
        store = memory.MemoryStore(tmp_path / "mem.json")
        data = [{"user_id": "u1", "key": "k", "value": {}, "ts": 1}]
        assert store._normalize(data) == data

    def test_normalize_old_dict_format(self, tmp_path):
        store = memory.MemoryStore(tmp_path / "mem.json")
        old_data = {"users": {"u1": {"k1": "v1", "k2": "v2"}}}
        result = store._normalize(old_data)
        assert len(result) == 2
        assert all(r["user_id"] == "u1" for r in result)

    def test_normalize_garbage(self, tmp_path):
        store = memory.MemoryStore(tmp_path / "mem.json")
        assert store._normalize("garbage") == []


# =========================================================
# 9. rebuild_vector_index
# =========================================================


class TestRebuildVectorIndex:
    def test_no_mem_vec(self, monkeypatch):
        monkeypatch.setattr(memory, "MEM_VEC", None)
        # Should not raise
        memory.rebuild_vector_index()

    def test_no_rebuild_method(self, monkeypatch):
        mock_vec = MagicMock(spec=[])  # no rebuild_index
        monkeypatch.setattr(memory, "MEM_VEC", mock_vec)
        memory.rebuild_vector_index()

    def test_rebuild_calls_correctly(self, monkeypatch, tmp_path):
        store = memory.MemoryStore(tmp_path / "mem.json")
        store.put("u1", "k1", {"text": "hello", "kind": "episodic"})

        mock_vec = MagicMock()
        mock_vec.rebuild_index = MagicMock()
        monkeypatch.setattr(memory, "MEM_VEC", mock_vec)
        monkeypatch.setattr(memory, "MEM", store)

        memory.rebuild_vector_index()
        mock_vec.rebuild_index.assert_called_once()
        docs = mock_vec.rebuild_index.call_args[0][0]
        assert len(docs) == 1
        assert docs[0]["text"] == "hello"


# =========================================================
# 10. distill_memory_for_user (mocked LLM)
# =========================================================


class TestDistillMemoryForUser:
    def test_no_episodic_records(self, monkeypatch, tmp_path):
        store = memory.MemoryStore(tmp_path / "mem.json")
        monkeypatch.setattr(memory, "MEM", store)
        result = memory.distill_memory_for_user("u1")
        assert result is None

    def test_successful_distill(self, monkeypatch, tmp_path):
        store = memory.MemoryStore(tmp_path / "mem.json")
        store.put("u1", "ep1", {
            "text": "Working on VERITAS project today",
            "kind": "episodic",
            "tags": ["veritas"],
        })
        monkeypatch.setattr(memory, "MEM", store)

        # Mock LLM
        mock_llm = MagicMock()
        mock_llm.chat_completion = MagicMock(return_value="Summary: VERITAS project")
        monkeypatch.setattr(memory, "llm_client", mock_llm)

        # Mock put to capture call
        put_called = {"called": False}
        original_put = memory.put

        def mock_put(*args, **kwargs):
            put_called["called"] = True
            return True

        monkeypatch.setattr(memory, "put", mock_put)

        result = memory.distill_memory_for_user("u1")
        assert result is not None
        assert result["kind"] == "semantic"
        assert "Summary" in result["text"]


# =========================================================
# 11. _build_distill_prompt
# =========================================================


class TestBuildDistillPrompt:
    def test_basic_prompt_structure(self):
        episodes = [
            {"text": "did something", "tags": ["work"], "ts": time.time()},
            {"text": "another thing", "tags": [], "ts": None},
        ]
        prompt = memory._build_distill_prompt("testuser", episodes)
        assert "testuser" in prompt
        assert "did something" in prompt
        assert "another thing" in prompt
        assert "Memory Distill" in prompt

    def test_long_text_truncated(self):
        episodes = [
            {"text": "x" * 500, "tags": [], "ts": time.time()},
        ]
        prompt = memory._build_distill_prompt("u1", episodes)
        assert "..." in prompt


# =========================================================
# 12. predict_decision_status / predict_gate_label
# =========================================================


class TestPredictDecisionStatus:
    def test_no_model_returns_unknown(self, monkeypatch):
        monkeypatch.setattr(memory, "MODEL", None)
        assert memory.predict_decision_status("test query") == "unknown"

    def test_model_predict_error(self, monkeypatch):
        mock_model = MagicMock()
        mock_model.predict = MagicMock(side_effect=RuntimeError("boom"))
        monkeypatch.setattr(memory, "MODEL", mock_model)
        assert memory.predict_decision_status("test") == "unknown"


class TestPredictGateLabel:
    def test_no_clf_no_model(self, monkeypatch):
        monkeypatch.setattr(memory, "MEM_CLF", None)
        monkeypatch.setattr(memory, "MODEL", None)
        result = memory.predict_gate_label("text")
        assert result == {"allow": 0.5}

    def test_with_clf(self, monkeypatch):
        mock_clf = MagicMock()
        mock_clf.predict_proba = MagicMock(return_value=[[0.8, 0.2]])
        mock_clf.classes_ = ["allow", "deny"]
        monkeypatch.setattr(memory, "MEM_CLF", mock_clf)
        result = memory.predict_gate_label("text")
        assert result["allow"] == 0.8

    def test_clf_error_falls_through(self, monkeypatch):
        mock_clf = MagicMock()
        mock_clf.predict_proba = MagicMock(side_effect=RuntimeError("err"))
        monkeypatch.setattr(memory, "MEM_CLF", mock_clf)
        monkeypatch.setattr(memory, "MODEL", None)
        result = memory.predict_gate_label("text")
        assert result == {"allow": 0.5}
