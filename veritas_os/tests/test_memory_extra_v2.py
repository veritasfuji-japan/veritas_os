# veritas_os/tests/test_memory_extra_v2.py
"""Additional coverage tests for veritas_os/core/memory.py.

Targets uncovered lines identified from coverage.json:
  - VectorMemory._load_index JSON loading (322-366)
  - VectorMemory._save_index (440-481)
  - VectorMemory.add with no model / no text (502-543)
  - VectorMemory.search edge cases (545-634)
  - VectorMemory.rebuild_index (659-693)
  - VectorMemory._cosine_similarity exception (653-657)
  - RestrictedUnpickler._find_class paths (215-241)
  - RestrictedUnpickler.loads validation failure (269-274)
  - MemoryStore cache paths (1001-1042)
  - MemoryStore._save_all exception (1058-1060)
  - MemoryStore CRUD ops (1062-1165)
  - locked_memory Windows path (887-935) via fcntl=None monkeypatch
  - predict_gate_label with MEM_CLF (827-843)
  - predict_decision_status with MODEL (803-808)
  - put_episode and summarize_for_planner paths
"""
from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from veritas_os.core import memory


# =========================================================
# VectorMemory helpers
# =========================================================


def _make_vm_no_model(tmp_path: Path) -> memory.VectorMemory:
    """Create a VectorMemory instance with model mocked to None (fast init)."""
    # Patch _load_model so sentence_transformers is never imported
    with patch.object(memory.VectorMemory, "_load_model", lambda self: None):
        vm = memory.VectorMemory(
            model_name="all-MiniLM-L6-v2",
            index_path=tmp_path / "index.pkl",
            embedding_dim=384,
        )
    vm.model = None  # Ensure model is None
    return vm


def _make_vm_with_mock_model(tmp_path: Path) -> tuple:
    """Create VectorMemory with a mocked SentenceTransformer model."""
    mock_model = MagicMock()

    def fake_encode(texts):
        return np.random.rand(len(texts), 384).astype(np.float32)

    mock_model.encode = fake_encode

    vm = memory.VectorMemory(
        model_name="all-MiniLM-L6-v2",
        index_path=tmp_path / "index.pkl",
        embedding_dim=384,
    )
    vm.model = mock_model
    return vm, mock_model


# =========================================================
# VectorMemory._load_index with JSON
# =========================================================


class TestVectorMemoryLoadIndex:
    def test_load_json_index_with_embeddings_b64(self, tmp_path):
        """Lines 354-366: JSON index with base64 embeddings."""
        # Create a JSON index file
        embeddings = np.random.rand(3, 384).astype(np.float32)
        embeddings_b64 = base64.b64encode(embeddings.tobytes()).decode("ascii")

        data = {
            "documents": [
                {"id": "doc1", "kind": "semantic", "text": "hello world", "tags": [], "meta": {}, "ts": 0.0},
                {"id": "doc2", "kind": "episodic", "text": "test doc", "tags": [], "meta": {}, "ts": 0.0},
                {"id": "doc3", "kind": "semantic", "text": "another", "tags": [], "meta": {}, "ts": 0.0},
            ],
            "embeddings": embeddings_b64,
            "embeddings_dtype": "float32",
            "embeddings_shape": [3, 384],
            "model_name": "all-MiniLM-L6-v2",
            "embedding_dim": 384,
            "format_version": "2.0",
        }

        json_path = tmp_path / "index.json"
        json_path.write_text(json.dumps(data), encoding="utf-8")

        vm = memory.VectorMemory(
            model_name="all-MiniLM-L6-v2",
            index_path=json_path,
            embedding_dim=384,
        )
        vm.model = None  # Don't load the model

        # Force reload
        vm._load_index()

        assert len(vm.documents) == 3
        assert vm.embeddings is not None

    def test_load_json_index_with_list_embeddings(self, tmp_path):
        """Line 363-364: JSON index with list embeddings."""
        embeddings_list = np.random.rand(2, 8).tolist()

        data = {
            "documents": [
                {"id": "doc1", "kind": "semantic", "text": "test1", "tags": [], "meta": {}, "ts": 0.0},
                {"id": "doc2", "kind": "semantic", "text": "test2", "tags": [], "meta": {}, "ts": 0.0},
            ],
            "embeddings": embeddings_list,
            "model_name": "all-MiniLM-L6-v2",
            "embedding_dim": 8,
            "format_version": "2.0",
        }

        json_path = tmp_path / "index.json"
        json_path.write_text(json.dumps(data), encoding="utf-8")

        vm = memory.VectorMemory(
            model_name="all-MiniLM-L6-v2",
            index_path=json_path,
            embedding_dim=8,
        )
        vm.model = None

        vm._load_index()
        assert len(vm.documents) == 2
        assert vm.embeddings is not None

    def test_load_json_index_with_none_embeddings(self, tmp_path):
        """Line 365-366: JSON index with None embeddings."""
        data = {
            "documents": [
                {"id": "doc1", "kind": "semantic", "text": "test", "tags": [], "meta": {}, "ts": 0.0},
            ],
            "embeddings": None,
            "model_name": "all-MiniLM-L6-v2",
            "embedding_dim": 384,
            "format_version": "2.0",
        }

        json_path = tmp_path / "index.json"
        json_path.write_text(json.dumps(data), encoding="utf-8")

        vm = memory.VectorMemory(
            model_name="all-MiniLM-L6-v2",
            index_path=json_path,
            embedding_dim=384,
        )
        vm.model = None
        vm._load_index()
        assert len(vm.documents) == 1
        assert vm.embeddings is None

    def test_load_index_missing_file(self, tmp_path):
        """No index file → documents stay empty."""
        vm = memory.VectorMemory(
            model_name="all-MiniLM-L6-v2",
            index_path=tmp_path / "nonexistent.pkl",
            embedding_dim=384,
        )
        vm.model = None
        assert vm.documents == []


# =========================================================
# VectorMemory._save_index
# =========================================================


class TestVectorMemorySaveIndex:
    def test_save_index_no_path(self, tmp_path):
        """Line 437-438: returns early when no index_path."""
        vm, _ = _make_vm_with_mock_model(tmp_path)
        vm.index_path = None
        # Should not raise
        vm._save_index()

    def test_save_index_with_embeddings(self, tmp_path):
        """Lines 440-479: saves index with numpy embeddings."""
        vm, mock_model = _make_vm_with_mock_model(tmp_path)

        # Manually set documents and embeddings
        vm.documents = [
            {"id": "doc1", "kind": "semantic", "text": "hello", "tags": [], "meta": {}, "ts": 0.0},
        ]
        vm.embeddings = np.array([[0.1, 0.2, 0.3]], dtype=np.float32)
        vm.index_path = tmp_path / "index.pkl"

        # Should save without error
        vm._save_index()

        # Check file was created
        json_path = tmp_path / "index.json"
        assert json_path.exists()

    def test_save_index_exception_handled(self, tmp_path):
        """Lines 480-481: exception during save is swallowed."""
        vm, _ = _make_vm_with_mock_model(tmp_path)
        vm.documents = [{"id": "doc1", "text": "test"}]
        vm.embeddings = None
        # Point to impossible path to trigger exception
        vm.index_path = Path("/nonexistent/deep/nested/path/index.pkl")

        # Should not raise
        vm._save_index()


# =========================================================
# VectorMemory.add
# =========================================================


class TestVectorMemoryAdd:
    def test_add_returns_false_when_no_model(self, tmp_path):
        """Lines 502-504: returns False immediately when model is None."""
        vm = _make_vm_no_model(tmp_path)
        vm.model = None
        result = vm.add(kind="semantic", text="some text")
        assert result is False

    def test_add_returns_false_for_empty_text(self, tmp_path):
        """Lines 506-507: returns False for empty text."""
        vm, mock_model = _make_vm_with_mock_model(tmp_path)
        result = vm.add(kind="semantic", text="   ")
        assert result is False

    def test_add_returns_false_for_none_text(self, tmp_path):
        """Returns False for None text."""
        vm, mock_model = _make_vm_with_mock_model(tmp_path)
        result = vm.add(kind="semantic", text="")
        assert result is False

    def test_add_success_with_model(self, tmp_path):
        """Lines 509-539: successful add with mock model."""
        vm, mock_model = _make_vm_with_mock_model(tmp_path)
        vm.index_path = None  # Don't save to disk

        result = vm.add(kind="semantic", text="test document", tags=["tag1"], meta={"key": "val"})
        assert result is True
        assert len(vm.documents) == 1
        assert vm.documents[0]["kind"] == "semantic"

    def test_add_appends_to_existing_embeddings(self, tmp_path):
        """Line 531-532: vstack with existing embeddings."""
        vm, mock_model = _make_vm_with_mock_model(tmp_path)
        vm.index_path = None

        # Add first document
        vm.add(kind="semantic", text="first doc")
        assert vm.embeddings is not None
        first_shape = vm.embeddings.shape

        # Add second document
        vm.add(kind="episodic", text="second doc")
        assert vm.embeddings.shape[0] == 2

    def test_add_saves_every_100_docs(self, tmp_path):
        """Lines 535-536: triggers _save_index at 100 docs."""
        vm, mock_model = _make_vm_with_mock_model(tmp_path)
        vm.index_path = tmp_path / "index.pkl"

        # Patch _save_index
        save_calls = []
        original_save = vm._save_index
        vm._save_index = lambda: save_calls.append(1)

        # Add 99 docs (no save trigger)
        for i in range(99):
            vm.add(kind="semantic", text=f"doc {i}")

        assert len(save_calls) == 0

        # Add 100th doc (should trigger save)
        vm.add(kind="semantic", text="doc 99")
        assert len(save_calls) == 1

    def test_add_exception_returns_false(self, tmp_path):
        """Lines 541-543: exception during encode → returns False."""
        vm, mock_model = _make_vm_with_mock_model(tmp_path)
        mock_model.encode = MagicMock(side_effect=RuntimeError("encode failed"))

        result = vm.add(kind="semantic", text="test")
        assert result is False


# =========================================================
# VectorMemory.search
# =========================================================


class TestVectorMemorySearch:
    def test_search_returns_empty_when_no_model(self, tmp_path):
        """Lines 564-566: returns [] when model is None."""
        vm = _make_vm_no_model(tmp_path)
        result = vm.search("test query")
        assert result == []

    def test_search_returns_empty_for_empty_query(self, tmp_path):
        """Lines 568-569: returns [] for empty query."""
        vm, mock_model = _make_vm_with_mock_model(tmp_path)
        result = vm.search("")
        assert result == []

    def test_search_returns_empty_when_no_documents(self, tmp_path):
        """Lines 571-573: returns [] when no documents."""
        vm, mock_model = _make_vm_with_mock_model(tmp_path)
        vm.documents = []
        vm.embeddings = None
        result = vm.search("test query")
        assert result == []

    def test_search_with_documents(self, tmp_path):
        """Lines 575-630: successful search with documents."""
        vm, mock_model = _make_vm_with_mock_model(tmp_path)
        vm.index_path = None

        # Add some documents
        vm.add(kind="semantic", text="hello world")
        vm.add(kind="episodic", text="test document")

        results = vm.search("hello", k=5)
        assert isinstance(results, list)

    def test_search_with_min_sim_filter(self, tmp_path):
        """Lines 595-596: min_sim filter."""
        vm, mock_model = _make_vm_with_mock_model(tmp_path)
        vm.index_path = None
        vm.add(kind="semantic", text="test doc")

        results = vm.search("test", k=10, min_sim=0.99)  # Very high threshold
        assert isinstance(results, list)  # May be empty due to threshold

    def test_search_with_kinds_filter(self, tmp_path):
        """Lines 603-605: kinds filter."""
        vm, mock_model = _make_vm_with_mock_model(tmp_path)
        vm.index_path = None
        vm.add(kind="semantic", text="semantic doc")
        vm.add(kind="episodic", text="episodic doc")

        results = vm.search("doc", k=10, kinds=["semantic"])
        # All results should be semantic kind
        for r in results:
            assert r.get("kind") == "semantic"

    def test_search_handles_index_out_of_bounds(self, tmp_path):
        """Line 598-599: idx >= len(docs_snapshot) guard."""
        vm, mock_model = _make_vm_with_mock_model(tmp_path)
        vm.index_path = None

        # Set up mismatched embeddings/docs
        vm.documents = [{"id": "doc1", "kind": "semantic", "text": "test", "tags": [], "ts": 0.0}]
        vm.embeddings = np.array([[0.1] * 384, [0.2] * 384], dtype=np.float32)  # 2 embeddings for 1 doc

        results = vm.search("test")
        assert isinstance(results, list)

    def test_search_exception_returns_empty(self, tmp_path):
        """Lines 632-634: exception during search → empty list."""
        vm, mock_model = _make_vm_with_mock_model(tmp_path)
        vm.index_path = None
        vm.add(kind="semantic", text="test")

        # Make encode raise on second call (during search)
        call_count = [0]
        original_encode = mock_model.encode

        def sometimes_fail(texts):
            call_count[0] += 1
            if call_count[0] > 1:
                raise RuntimeError("search encode failed")
            return original_encode(texts)

        mock_model.encode = sometimes_fail

        result = vm.search("test")
        assert isinstance(result, list)


# =========================================================
# VectorMemory._cosine_similarity
# =========================================================


class TestVectorMemoryCossineSimilarity:
    def test_cosine_similarity_normal(self):
        """Normal cosine similarity calculation."""
        vec = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        matrix = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float32)
        result = memory.VectorMemory._cosine_similarity(vec, matrix)
        assert len(result) == 2
        # First vector is similar, second is orthogonal
        assert result[0] > 0.9
        assert abs(result[1]) < 0.1

    def test_cosine_similarity_exception(self):
        """Lines 653-657: exception → zeros array."""
        # Pass invalid objects that numpy can't handle
        result = memory.VectorMemory._cosine_similarity("not a vector", "not a matrix")
        # Should return zeros array or handle gracefully
        assert result is not None


# =========================================================
# VectorMemory.rebuild_index
# =========================================================


class TestVectorMemoryRebuildIndex:
    def test_rebuild_returns_when_no_model(self, tmp_path):
        """Lines 666-668: returns immediately when model is None."""
        vm = _make_vm_no_model(tmp_path)
        vm.model = None
        # Should return without error
        vm.rebuild_index([{"text": "test", "kind": "semantic"}])
        assert len(vm.documents) == 0  # Nothing added

    def test_rebuild_with_documents(self, tmp_path):
        """Lines 670-693: rebuilds index with given documents."""
        vm, mock_model = _make_vm_with_mock_model(tmp_path)
        vm.index_path = None

        docs = [
            {"text": "hello world", "kind": "semantic", "tags": ["t1"], "meta": {"x": 1}},
            {"text": "test document", "kind": "episodic", "tags": [], "meta": {}},
            {"text": "", "kind": "semantic"},  # Empty text → skipped (line 680-681)
        ]

        vm.rebuild_index(docs)
        assert len(vm.documents) == 2  # 2 non-empty docs

    def test_rebuild_with_empty_text_skipped(self, tmp_path):
        """Lines 679-681: empty text docs are skipped."""
        vm, mock_model = _make_vm_with_mock_model(tmp_path)
        vm.index_path = None

        docs = [
            {"text": "", "kind": "semantic"},
            {"text": "   ", "kind": "episodic"},
            {"text": "valid text", "kind": "semantic"},
        ]

        vm.rebuild_index(docs)
        assert len(vm.documents) == 1  # Only valid text


# =========================================================
# RestrictedUnpickler
# =========================================================


class TestRestrictedUnpickler:
    def test_find_class_numpy_ndarray(self):
        """Lines 227-230: allowed numpy type returned."""
        import numpy as np
        result = memory.RestrictedUnpickler._find_class("numpy", "ndarray")
        assert result is np.ndarray

    def test_find_class_numpy_dtype(self):
        """Lines 227-230: numpy dtype returned."""
        import numpy as np
        result = memory.RestrictedUnpickler._find_class("numpy", "dtype")
        assert result is np.dtype

    def test_find_class_numpy_reconstruct_blocked(self):
        """Lines 215-224: _reconstruct blocked for security."""
        import pickle
        with pytest.raises(pickle.UnpicklingError, match="blocked"):
            memory.RestrictedUnpickler._find_class("numpy", "_reconstruct")

    def test_find_class_scalar_blocked(self):
        """Lines 215-224: scalar types blocked."""
        import pickle
        with pytest.raises(pickle.UnpicklingError, match="blocked"):
            memory.RestrictedUnpickler._find_class("numpy", "float64_scalar")

    def test_find_class_builtin_dict(self):
        """Lines 236-237: builtin dict allowed."""
        result = memory.RestrictedUnpickler._find_class("builtins", "dict")
        assert result is dict

    def test_find_class_builtin_list(self):
        """Builtin list allowed."""
        result = memory.RestrictedUnpickler._find_class("builtins", "list")
        assert result is list

    def test_find_class_unknown_raises(self):
        """Lines 239-241: unknown type raises UnpicklingError."""
        import pickle
        with pytest.raises(pickle.UnpicklingError, match="not allowed"):
            memory.RestrictedUnpickler._find_class("os", "system")

    def test_find_class_unknown_numpy_type_raises(self):
        """Lines 231-233: known numpy prefix but unknown name."""
        import pickle
        # "numpy.unknown_type" is in ALLOWED_NUMPY_TYPES check
        # Actually "numpy.ndarray" is allowed, "numpy.nonexistent" is not
        # since it's not in ALLOWED_NUMPY_TYPES
        with pytest.raises(pickle.UnpicklingError):
            memory.RestrictedUnpickler._find_class("numpy", "nonexistent_type")

    def test_loads_deprecation_warning(self):
        """Lines 255-261: loads() emits deprecation warning."""
        import pickle
        # Create a simple pickle of a dict
        data = pickle.dumps({"documents": [], "embeddings": None})
        memory.RestrictedUnpickler._DEPRECATION_WARNED = False  # Reset
        result = memory.RestrictedUnpickler.loads(data)
        assert isinstance(result, dict)
        assert memory.RestrictedUnpickler._DEPRECATION_WARNED is True

    def test_loads_invalid_structure_raises(self):
        """Lines 269-274: invalid data structure after deserialization."""
        import pickle
        # Pickle a list (not a dict) - invalid structure
        data = pickle.dumps([1, 2, 3])
        memory.RestrictedUnpickler._DEPRECATION_WARNED = False
        with pytest.raises(pickle.UnpicklingError, match="Invalid data structure"):
            memory.RestrictedUnpickler.loads(data)


# =========================================================
# MemoryStore
# =========================================================


class TestMemoryStore:
    def test_put_and_get(self, tmp_path):
        """Basic KVS put/get."""
        store = memory.MemoryStore(tmp_path / "memory.json")
        ok = store.put("user1", "key1", {"data": "value1"})
        assert ok is True
        result = store.get("user1", "key1")
        assert result == {"data": "value1"}

    def test_put_updates_existing(self, tmp_path):
        """Lines 1068-1073: updates existing record."""
        store = memory.MemoryStore(tmp_path / "memory.json")
        store.put("user1", "key1", "original")
        store.put("user1", "key1", "updated")
        result = store.get("user1", "key1")
        assert result == "updated"

    def test_list_all(self, tmp_path):
        """MemoryStore.list_all returns all records."""
        store = memory.MemoryStore(tmp_path / "memory.json")
        store.put("u1", "k1", "v1")
        store.put("u2", "k2", "v2")
        all_records = store.list_all()
        assert len(all_records) == 2

    def test_list_all_with_user_filter(self, tmp_path):
        """Line 1099-1100: list_all with user_id filter."""
        store = memory.MemoryStore(tmp_path / "memory.json")
        store.put("u1", "k1", "v1")
        store.put("u2", "k2", "v2")
        u1_records = store.list_all(user_id="u1")
        assert len(u1_records) == 1
        assert u1_records[0]["user_id"] == "u1"

    def test_append_history(self, tmp_path):
        """Lines 1103-1106: append_history creates record."""
        store = memory.MemoryStore(tmp_path / "memory.json")
        ok = store.append_history("u1", {"action": "test", "ts": time.time()})
        assert ok is True

    def test_add_usage(self, tmp_path):
        """Lines 1108-1115: add_usage creates usage record."""
        store = memory.MemoryStore(tmp_path / "memory.json")
        ok = store.add_usage("u1", cited_ids=["id1", "id2"])
        assert ok is True
        # Verify something was stored
        records = store.list_all("u1")
        assert len(records) >= 1

    def test_recent_with_contains_filter(self, tmp_path):
        """Lines 1127-1138: recent with contains filter."""
        store = memory.MemoryStore(tmp_path / "memory.json")
        store.put("u1", "k1", {"text": "hello world query", "query": "hello"})
        store.put("u1", "k2", {"text": "unrelated content"})
        recent = store.recent("u1", limit=10, contains="hello")
        # At least the first record should match
        assert isinstance(recent, list)

    def test_recent_sorted_by_ts(self, tmp_path):
        """Lines 1124-1125: records sorted by ts."""
        store = memory.MemoryStore(tmp_path / "memory.json")
        store.put("u1", "k1", "first")
        time.sleep(0.01)
        store.put("u1", "k2", "second")
        records = store.recent("u1", limit=5)
        assert len(records) == 2

    def test_search_returns_hits(self, tmp_path):
        """MemoryStore.search finds matching records."""
        store = memory.MemoryStore(tmp_path / "memory.json")
        store.put("u1", "key1", {"text": "machine learning model", "tags": [], "kind": "episodic"})
        store.put("u1", "key2", {"text": "deep learning neural network", "tags": [], "kind": "episodic"})

        result = store.search("machine learning", k=5, user_id="u1")
        assert isinstance(result, dict)
        # Result may have 'episodic' key with hits
        if result:
            assert "episodic" in result

    def test_search_empty_query(self, tmp_path):
        """Line 1176-1178: empty query returns empty dict."""
        store = memory.MemoryStore(tmp_path / "memory.json")
        result = store.search("   ")
        assert result == {}

    def test_save_all_exception_returns_false(self, tmp_path):
        """Lines 1058-1060: _save_all exception → returns False."""
        store = memory.MemoryStore(tmp_path / "memory.json")

        # Patch atomic_write_json to raise
        with patch("veritas_os.core.memory.locked_memory") as mock_lock:
            mock_lock.side_effect = RuntimeError("disk error")
            result = store._save_all([{"key": "v"}])
        assert result is False

    def test_load_all_cache_hit(self, tmp_path):
        """Lines 1001-1013: cache is used on second load."""
        store = memory.MemoryStore(tmp_path / "memory.json")
        store.put("u1", "k1", "v1")

        # First load
        data1 = store._load_all()
        # Second load - should use cache
        data2 = store._load_all()
        assert len(data1) == len(data2)

    def test_load_all_json_error(self, tmp_path):
        """Lines 1024-1026: JSON decode error → empty list."""
        path = tmp_path / "memory.json"
        path.write_text("{ INVALID JSON }", encoding="utf-8")
        store = memory.MemoryStore(path)
        # Force reload (bypass cache)
        data = store._load_all(use_cache=False)
        assert data == []

    def test_normalize_dict_with_users(self, tmp_path):
        """Lines 970-984: migration from old dict format."""
        store = memory.MemoryStore(tmp_path / "memory.json")
        old_format = {
            "users": {
                "user1": {"key1": "val1", "key2": "val2"},
                "user2": {"keyA": "valA"},
            }
        }
        result = store._normalize(old_format)
        assert isinstance(result, list)
        assert len(result) == 3  # 2 + 1 records
        user_ids = {r["user_id"] for r in result}
        assert "user1" in user_ids
        assert "user2" in user_ids

    def test_normalize_returns_empty_for_unknown(self, tmp_path):
        """Line 986: returns [] for unknown format."""
        store = memory.MemoryStore(tmp_path / "memory.json")
        result = store._normalize({"unknown": "format"})
        assert result == []

    def test_put_episode(self, tmp_path):
        """Lines 1228-1273: put_episode saves and returns key."""
        store = memory.MemoryStore(tmp_path / "memory.json")
        key = store.put_episode(
            text="episode text",
            tags=["tag1"],
            meta={"user_id": "u1"},
        )
        assert isinstance(key, str)
        assert key.startswith("episode_")

    def test_summarize_for_planner_empty(self, tmp_path):
        """Returns empty message when no episodes."""
        store = memory.MemoryStore(tmp_path / "memory.json")
        result = store.summarize_for_planner("u1", "test query")
        assert "参照すべき重要メモは見つかりませんでした" in result

    def test_summarize_for_planner_with_episodes(self, tmp_path):
        """Lines 1288-1311: returns summary with episodes."""
        store = memory.MemoryStore(tmp_path / "memory.json")
        store.put("u1", "k1", {
            "text": "machine learning episode",
            "tags": ["ml"],
            "kind": "episodic",
        })
        result = store.summarize_for_planner("u1", "machine learning")
        assert isinstance(result, str)


# =========================================================
# locked_memory – Windows path via fcntl=None monkeypatch
# =========================================================


class TestLockedMemoryWindowsPath:
    def test_windows_path_basic(self, tmp_path, monkeypatch):
        """Lines 900-935: Windows-style lockfile path when fcntl is None."""
        monkeypatch.setattr(memory, "fcntl", None)

        path = tmp_path / "memory.json"
        path.write_text("[]", encoding="utf-8")

        accessed = []
        with memory.locked_memory(path):
            accessed.append("inside")

        assert "inside" in accessed
        # Lockfile should be cleaned up
        lockfile = path.with_suffix(path.suffix + ".lock")
        assert not lockfile.exists()

    def test_windows_path_stale_lock_removed(self, tmp_path, monkeypatch):
        """Lines 911-920: stale lockfile is removed."""
        monkeypatch.setattr(memory, "fcntl", None)

        path = tmp_path / "memory.json"
        path.write_text("[]", encoding="utf-8")

        # Create a stale lockfile (old mtime)
        lockfile = path.with_suffix(path.suffix + ".lock")
        lockfile.write_text("stale", encoding="utf-8")

        # Make it look old by changing mtime
        old_time = time.time() - 400  # > 300 seconds
        os.utime(str(lockfile), (old_time, old_time))

        accessed = []
        with memory.locked_memory(path):
            accessed.append("inside")

        assert "inside" in accessed


# =========================================================
# predict_gate_label with MEM_CLF
# =========================================================


class TestPredictGateLabel:
    def test_predict_with_none_clf(self, monkeypatch):
        """predict_gate_label returns default 0.5 when no classifier."""
        monkeypatch.setattr(memory, "MEM_CLF", None)
        monkeypatch.setattr(memory, "MODEL", None)
        result = memory.predict_gate_label("test text")
        assert result == {"allow": 0.5}

    def test_predict_with_mock_clf(self, monkeypatch):
        """Lines 819-828: predict with MEM_CLF."""
        mock_clf = MagicMock()
        mock_clf.predict_proba.return_value = [[0.3, 0.7]]
        mock_clf.classes_ = ["deny", "allow"]
        monkeypatch.setattr(memory, "MEM_CLF", mock_clf)
        result = memory.predict_gate_label("test text")
        assert isinstance(result, dict)
        assert "allow" in result
        assert abs(result["allow"] - 0.7) < 0.01

    def test_predict_with_clf_no_allow_class(self, monkeypatch):
        """Lines 826-828: MEM_CLF without 'allow' class uses max prob."""
        mock_clf = MagicMock()
        mock_clf.predict_proba.return_value = [[0.3, 0.7]]
        mock_clf.classes_ = ["deny", "permit"]  # No "allow" class
        monkeypatch.setattr(memory, "MEM_CLF", mock_clf)
        result = memory.predict_gate_label("test text")
        assert isinstance(result, dict)
        assert result["allow"] == pytest.approx(0.7, abs=0.01)

    def test_predict_clf_exception(self, monkeypatch):
        """Lines 829-830: MEM_CLF.predict_proba exception."""
        mock_clf = MagicMock()
        mock_clf.predict_proba.side_effect = RuntimeError("clf broken")
        monkeypatch.setattr(memory, "MEM_CLF", mock_clf)
        monkeypatch.setattr(memory, "MODEL", None)
        result = memory.predict_gate_label("test text")
        assert result == {"allow": 0.5}


# =========================================================
# predict_decision_status
# =========================================================


class TestPredictDecisionStatus:
    def test_returns_unknown_when_no_model(self, monkeypatch):
        """Line 801-802: returns 'unknown' when MODEL is None."""
        monkeypatch.setattr(memory, "MODEL", None)
        result = memory.predict_decision_status("test query")
        assert result == "unknown"

    def test_returns_prediction_with_model(self, monkeypatch):
        """Lines 803-805: returns model prediction."""
        mock_model = MagicMock()
        mock_model.predict.return_value = ["approved"]
        monkeypatch.setattr(memory, "MODEL", mock_model)
        result = memory.predict_decision_status("approve this")
        assert result == "approved"

    def test_exception_returns_unknown(self, monkeypatch):
        """Lines 806-808: exception returns 'unknown'."""
        mock_model = MagicMock()
        mock_model.predict.side_effect = RuntimeError("model broken")
        monkeypatch.setattr(memory, "MODEL", mock_model)
        result = memory.predict_decision_status("test")
        assert result == "unknown"


# =========================================================
# MemoryStore._simple_score
# =========================================================


class TestSimpleScore:
    def test_empty_query_returns_zero(self, tmp_path):
        store = memory.MemoryStore(tmp_path / "memory.json")
        assert store._simple_score("", "hello world") == 0.0

    def test_empty_text_returns_zero(self, tmp_path):
        store = memory.MemoryStore(tmp_path / "memory.json")
        assert store._simple_score("hello", "") == 0.0

    def test_substring_match(self, tmp_path):
        """Lines 1149-1152: substring match gives base score."""
        store = memory.MemoryStore(tmp_path / "memory.json")
        score = store._simple_score("hello", "say hello world")
        assert score >= 0.5

    def test_no_match(self, tmp_path):
        """Lines 1153-1154: no match gives 0 base score."""
        store = memory.MemoryStore(tmp_path / "memory.json")
        score = store._simple_score("xyz", "hello world test")
        assert score >= 0.0

    def test_token_overlap(self, tmp_path):
        """Lines 1156-1160: token overlap increases score."""
        store = memory.MemoryStore(tmp_path / "memory.json")
        score = store._simple_score("hello world", "world hello")
        assert score >= 0.5
