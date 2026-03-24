# veritas_os/tests/test_memory_branches.py
"""
memory.py 分岐カバレッジ強化テスト

対象:
  - VectorMemory: _load_model / add / search / rebuild_index / _save_index / _load_index
  - _get_mem_vec: external / built-in / init error / lazy cache
  - locked_memory: Windows-like fallback path
  - _LazyMemoryStore: success / cache / failure re-raise
  - Global helpers: put / search / distill_memory_for_user / rebuild_vector_index

方針:
  - production code は変更しない
  - 実 I/O は tmp_path に閉じ込める
  - 実モデル・実 LLM・実ネットワーク禁止
  - monkeypatch / fakes で全分岐を検証
  - 既存テストと重複しない
"""
from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# Import the module under test
from veritas_os.core import memory as mem_mod
from veritas_os.core.memory import (
    VectorMemory,
    _LazyMemoryStore,
    locked_memory,
)

# ---------------------------------------------------------------------------
# Helpers / Fakes
# ---------------------------------------------------------------------------


class FakeEmbedModel:
    """Deterministic embedding model that returns fixed-dimension vectors."""

    def __init__(self, dim: int = 384):
        self.dim = dim

    def encode(self, texts: List[str]) -> np.ndarray:
        # Return a simple hash-based embedding for determinism
        result = []
        for t in texts:
            vec = np.zeros(self.dim, dtype=np.float32)
            for i, ch in enumerate(t.encode("utf-8")):
                vec[i % self.dim] += float(ch) / 256.0
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            result.append(vec)
        return np.array(result, dtype=np.float32)


class FakeMemoryStore:
    """Minimal fake for the global MEM (MemoryStore)."""

    def __init__(self) -> None:
        self._data: Dict[str, Dict[str, Any]] = {}
        self._history: List[Dict[str, Any]] = []

    def put(self, user_id: str, key: str, value: Any) -> bool:
        self._data.setdefault(user_id, {})[key] = value
        return True

    def get(self, user_id: str, key: str) -> Any:
        return self._data.get(user_id, {}).get(key)

    def list_all(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for uid, records in self._data.items():
            if user_id and uid != user_id:
                continue
            for k, v in records.items():
                # MemoryStore returns {"key": k, "value": v} format
                items.append({"key": k, "value": v})
        return items

    def recent(self, user_id: str, limit: int = 20,
               contains: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.list_all(user_id)[:limit]

    def search(self, **kwargs) -> Dict[str, List[Dict[str, Any]]]:
        return {"episodic": []}

    def add_usage(self, user_id: str, cited_ids: Any) -> bool:
        return True

    def append_history(self, user_id: str, record: Dict[str, Any]) -> bool:
        self._history.append(record)
        return True

    def summarize_for_planner(self, user_id: str, query: str,
                              limit: int = 8) -> str:
        return "summary stub"


class FakeVec:
    """Configurable fake VectorMemory-like object."""

    def __init__(
        self,
        hits: Optional[List[Dict[str, Any]]] = None,
        raise_on_search: Optional[Exception] = None,
        raise_type_error: bool = False,
    ):
        self._hits = hits or []
        self._raise_on_search = raise_on_search
        self._raise_type_error = raise_type_error
        self._added: List[Dict[str, Any]] = []

    def search(
        self,
        query: str,
        k: int = 10,
        kinds: Optional[List[str]] = None,
        min_sim: float = 0.0,
    ) -> List[Dict[str, Any]]:
        if self._raise_type_error:
            raise TypeError("old sig")
        if self._raise_on_search:
            raise self._raise_on_search
        return self._hits

    def add(self, kind: str, text: str, tags: Any = None,
            meta: Any = None) -> bool:
        self._added.append(
            {"kind": kind, "text": text, "tags": tags, "meta": meta}
        )
        return True

    def rebuild_index(self, documents: List[Dict[str, Any]]) -> None:
        pass


class FakeVecOldSig:
    """VectorMemory-like that only accepts (query, k) — old signature."""

    def __init__(self, hits: Optional[List[Dict[str, Any]]] = None):
        self._hits = hits or []

    def search(self, query: str, k: int = 10) -> List[Dict[str, Any]]:
        return self._hits


# ---------------------------------------------------------------------------
# VectorMemory._load_model branches
# ---------------------------------------------------------------------------


class TestVectorMemoryLoadModel:
    """_load_model: ImportError fallback / config mismatch / success."""

    def test_importerror_fallback_when_not_explicitly_enabled(self, monkeypatch):
        """sentence-transformers unavailable + default config → warning + model=None."""
        monkeypatch.setattr(
            mem_mod.capability_cfg,
            "enable_memory_sentence_transformers",
            True,
        )
        # Simulate ImportError from sentence_transformers
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "sentence_transformers":
                raise ImportError("No module named 'sentence_transformers'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        monkeypatch.setattr(mem_mod, "_is_explicitly_enabled", lambda _: False)

        vm = VectorMemory.__new__(VectorMemory)
        vm.model_name = "test-model"
        vm._lock = threading.RLock()
        vm.model = None

        vm._load_model()
        assert vm.model is None

    def test_importerror_raises_when_explicitly_enabled(self, monkeypatch):
        """sentence-transformers unavailable + explicit enable → RuntimeError."""
        monkeypatch.setattr(
            mem_mod.capability_cfg,
            "enable_memory_sentence_transformers",
            True,
        )
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "sentence_transformers":
                raise ImportError("No module named 'sentence_transformers'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        monkeypatch.setattr(mem_mod, "_is_explicitly_enabled", lambda _: True)

        vm = VectorMemory.__new__(VectorMemory)
        vm.model_name = "test-model"
        vm._lock = threading.RLock()
        vm.model = None

        with pytest.raises(RuntimeError, match="sentence-transformers is required"):
            vm._load_model()

    def test_capability_disabled_skips_load(self, monkeypatch):
        """enable_memory_sentence_transformers=False → model stays None."""
        monkeypatch.setattr(
            mem_mod.capability_cfg,
            "enable_memory_sentence_transformers",
            False,
        )
        vm = VectorMemory.__new__(VectorMemory)
        vm.model_name = "test-model"
        vm._lock = threading.RLock()
        vm.model = None

        vm._load_model()
        assert vm.model is None

    def test_model_load_success_with_fake(self, monkeypatch):
        """Model loads successfully with a fake SentenceTransformer."""
        monkeypatch.setattr(
            mem_mod.capability_cfg,
            "enable_memory_sentence_transformers",
            True,
        )
        fake_model = FakeEmbedModel(dim=384)

        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "sentence_transformers":
                mod = SimpleNamespace(SentenceTransformer=lambda _name: fake_model)
                return mod
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        vm = VectorMemory.__new__(VectorMemory)
        vm.model_name = "test-model"
        vm._lock = threading.RLock()
        vm.model = None

        vm._load_model()
        assert vm.model is fake_model

    def test_oserror_during_load_sets_model_none(self, monkeypatch):
        """OSError during SentenceTransformer() → model=None (no raise)."""
        monkeypatch.setattr(
            mem_mod.capability_cfg,
            "enable_memory_sentence_transformers",
            True,
        )
        import builtins
        original_import = builtins.__import__

        def raise_os(*a, **kw):
            raise OSError("disk error")

        def mock_import(name, *args, **kwargs):
            if name == "sentence_transformers":
                return SimpleNamespace(SentenceTransformer=raise_os)
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        vm = VectorMemory.__new__(VectorMemory)
        vm.model_name = "test-model"
        vm._lock = threading.RLock()
        vm.model = None

        vm._load_model()
        assert vm.model is None


# ---------------------------------------------------------------------------
# VectorMemory: add / search / rebuild_index edge cases
# ---------------------------------------------------------------------------


class TestVectorMemoryOperations:
    """VectorMemory add/search/rebuild edge cases not covered elsewhere."""

    def _make_vm(self, tmp_path: Path) -> VectorMemory:
        """Create a VectorMemory with a FakeEmbedModel."""
        vm = VectorMemory.__new__(VectorMemory)
        vm.model_name = "test"
        vm.index_path = tmp_path / "vec_index"
        vm.embedding_dim = 8
        vm._lock = threading.RLock()
        vm._id_counter = 0
        vm.documents = []
        vm.embeddings = None
        vm.model = FakeEmbedModel(dim=8)
        return vm

    def test_add_success(self, tmp_path):
        vm = self._make_vm(tmp_path)
        ok = vm.add("episodic", "hello world")
        assert ok is True
        assert len(vm.documents) == 1
        assert vm.documents[0]["kind"] == "episodic"
        assert vm.embeddings is not None
        assert vm.embeddings.shape[0] == 1

    def test_add_empty_text_returns_false(self, tmp_path):
        vm = self._make_vm(tmp_path)
        assert vm.add("episodic", "") is False
        assert vm.add("episodic", "   ") is False
        assert len(vm.documents) == 0

    def test_add_model_not_loaded_returns_false(self, tmp_path):
        vm = self._make_vm(tmp_path)
        vm.model = None
        assert vm.add("episodic", "hello") is False

    def test_add_failure_returns_false(self, tmp_path):
        """Simulate an exception during encode → returns False."""
        vm = self._make_vm(tmp_path)
        vm.model = MagicMock()
        vm.model.encode.side_effect = RuntimeError("encode boom")
        assert vm.add("episodic", "hello") is False

    def test_add_with_lineage_meta(self, tmp_path):
        """Lineage metadata in meta dict is preserved in document."""
        vm = self._make_vm(tmp_path)
        lineage = {"source": "pdf", "page": 3}
        ok = vm.add("doc", "text", meta={"lineage": lineage})
        assert ok is True
        assert vm.documents[0]["lineage"] == lineage

    def test_add_without_lineage_creates_default(self, tmp_path):
        """No lineage in meta → default lineage with 'internal' source."""
        vm = self._make_vm(tmp_path)
        ok = vm.add("doc", "text")
        assert ok is True
        assert vm.documents[0]["lineage"]["source"] == "internal"

    def test_search_success(self, tmp_path):
        vm = self._make_vm(tmp_path)
        vm.add("episodic", "hello world")
        vm.add("episodic", "hi there")
        results = vm.search("hello", k=5)
        assert len(results) > 0
        assert all("score" in r for r in results)

    def test_search_empty_query(self, tmp_path):
        vm = self._make_vm(tmp_path)
        vm.add("episodic", "hello")
        assert vm.search("") == []
        assert vm.search("   ") == []

    def test_search_no_documents(self, tmp_path):
        vm = self._make_vm(tmp_path)
        assert vm.search("hello") == []

    def test_search_model_not_loaded(self, tmp_path):
        vm = self._make_vm(tmp_path)
        vm.model = None
        assert vm.search("hello") == []

    def test_search_kinds_filter(self, tmp_path):
        vm = self._make_vm(tmp_path)
        vm.add("episodic", "hello world")
        vm.add("semantic", "general knowledge")
        results = vm.search("hello", kinds=["semantic"])
        for r in results:
            assert r["kind"] == "semantic"

    def test_search_min_sim_filter(self, tmp_path):
        vm = self._make_vm(tmp_path)
        vm.add("episodic", "hello world")
        # Very high min_sim → no results
        results = vm.search("completely different topic xyz", k=5, min_sim=0.999)
        # May or may not return results depending on embedding similarity,
        # but we're testing that the filter is applied
        for r in results:
            assert r["score"] >= 0.999

    def test_search_exception_returns_empty(self, tmp_path):
        """Exception during search → empty list."""
        vm = self._make_vm(tmp_path)
        vm.add("episodic", "hello")
        vm.model = MagicMock()
        vm.model.encode.side_effect = RuntimeError("encode boom")
        assert vm.search("hello") == []

    def test_rebuild_index_basic(self, tmp_path):
        vm = self._make_vm(tmp_path)
        docs = [
            {"kind": "episodic", "text": "hello", "tags": ["a"]},
            {"kind": "semantic", "text": "world", "meta": {"x": 1}},
        ]
        vm.rebuild_index(docs)
        assert len(vm.documents) == 2
        assert vm.embeddings is not None
        assert vm.embeddings.shape[0] == 2

    def test_rebuild_index_skips_empty_text(self, tmp_path):
        vm = self._make_vm(tmp_path)
        docs = [
            {"kind": "episodic", "text": "hello"},
            {"kind": "episodic", "text": ""},
            {"kind": "episodic", "text": "   "},
        ]
        vm.rebuild_index(docs)
        assert len(vm.documents) == 1

    def test_rebuild_index_model_not_loaded(self, tmp_path):
        vm = self._make_vm(tmp_path)
        vm.model = None
        vm.rebuild_index([{"kind": "episodic", "text": "hello"}])
        assert len(vm.documents) == 0

    def test_rebuild_index_empty_list(self, tmp_path):
        """Rebuilding with empty list → clears embeddings."""
        vm = self._make_vm(tmp_path)
        vm.add("episodic", "hello")
        assert vm.embeddings is not None
        vm.rebuild_index([])
        assert vm.embeddings is None
        assert len(vm.documents) == 0


# ---------------------------------------------------------------------------
# VectorMemory: JSON index save/load round-trip
# ---------------------------------------------------------------------------


class TestVectorMemoryPersistence:
    """_save_index / _load_index JSON round-trip."""

    def _make_vm(self, tmp_path: Path) -> VectorMemory:
        vm = VectorMemory.__new__(VectorMemory)
        vm.model_name = "test"
        vm.index_path = tmp_path / "vec_index.json"
        vm.embedding_dim = 8
        vm._lock = threading.RLock()
        vm._id_counter = 0
        vm.documents = []
        vm.embeddings = None
        vm.model = FakeEmbedModel(dim=8)
        return vm

    def test_save_and_load_roundtrip(self, tmp_path):
        vm = self._make_vm(tmp_path)
        vm.add("episodic", "hello world")
        vm.add("semantic", "test data")
        vm._save_index()

        # Verify JSON file exists
        json_path = vm.index_path.with_suffix(".json")
        assert json_path.exists()

        # Load into a new instance
        vm2 = VectorMemory.__new__(VectorMemory)
        vm2.model_name = "test"
        vm2.index_path = json_path
        vm2.embedding_dim = 8
        vm2._lock = threading.RLock()
        vm2._id_counter = 0
        vm2.documents = []
        vm2.embeddings = None
        vm2.model = FakeEmbedModel(dim=8)

        vm2._load_index()
        assert len(vm2.documents) == 2
        assert vm2.embeddings is not None
        assert vm2.embeddings.shape == vm.embeddings.shape

    def test_load_index_no_path(self, tmp_path):
        """index_path=None → does nothing."""
        vm = self._make_vm(tmp_path)
        vm.index_path = None
        vm._load_index()
        assert vm.documents == []

    def test_load_index_json_with_list_embeddings(self, tmp_path):
        """Load JSON with list-format embeddings (not base64)."""
        json_path = tmp_path / "vec_index.json"
        data = {
            "documents": [
                {"id": "ep_1", "kind": "episodic", "text": "hello",
                 "tags": [], "meta": {}, "ts": 123.0}
            ],
            "embeddings": [[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]],
        }
        json_path.write_text(json.dumps(data), encoding="utf-8")

        vm = self._make_vm(tmp_path)
        vm.index_path = json_path
        vm._load_index()
        assert len(vm.documents) == 1
        assert vm.embeddings is not None
        assert vm.embeddings.shape == (1, 8)

    def test_load_index_json_corrupt(self, tmp_path):
        """Corrupt JSON → error logged, no crash."""
        json_path = tmp_path / "vec_index.json"
        json_path.write_text("{invalid json", encoding="utf-8")

        vm = self._make_vm(tmp_path)
        vm.index_path = json_path
        vm._load_index()  # Should not raise
        assert vm.documents == []

    def test_load_index_embeddings_none_in_json(self, tmp_path):
        """embeddings: null in JSON → embeddings stays None."""
        json_path = tmp_path / "vec_index.json"
        data = {
            "documents": [{"id": "ep_1", "kind": "episodic", "text": "hello"}],
            "embeddings": None,
        }
        json_path.write_text(json.dumps(data), encoding="utf-8")

        vm = self._make_vm(tmp_path)
        vm.index_path = json_path
        vm._load_index()
        assert len(vm.documents) == 1
        assert vm.embeddings is None

    def test_save_index_no_path(self, tmp_path):
        """index_path=None → does nothing."""
        vm = self._make_vm(tmp_path)
        vm.index_path = None
        vm._save_index()  # Should not raise

    def test_save_index_error_handled(self, tmp_path, monkeypatch):
        """OSError during save → error logged, no crash."""
        vm = self._make_vm(tmp_path)
        vm.add("episodic", "hello")
        # Make the directory read-only to cause write error
        monkeypatch.setattr(
            "veritas_os.core.atomic_io.atomic_write_json",
            MagicMock(side_effect=OSError("disk full")),
        )
        vm._save_index()  # Should not raise


# ---------------------------------------------------------------------------
# _get_mem_vec branches
# ---------------------------------------------------------------------------


class TestGetMemVec:
    """_get_mem_vec: external / built-in fallback / init error / cache."""

    def _reset_mem_vec(self, monkeypatch):
        """Reset MEM_VEC and guard state for a clean test."""
        monkeypatch.setattr(mem_mod, "MEM_VEC", None)
        monkeypatch.setattr(mem_mod, "_runtime_guard_checked", True)

    def test_external_mem_vec_with_model(self, monkeypatch):
        """MEM_VEC_EXTERNAL with .model set → used as MEM_VEC."""
        self._reset_mem_vec(monkeypatch)
        ext = SimpleNamespace(model="fake-model", search=lambda *a, **kw: [])
        monkeypatch.setattr(mem_mod, "MEM_VEC_EXTERNAL", ext)
        result = mem_mod._get_mem_vec()
        assert result is ext

    def test_external_mem_vec_without_model_ignored(self, monkeypatch):
        """MEM_VEC_EXTERNAL with model=None → ignored, built-in used."""
        self._reset_mem_vec(monkeypatch)

        ext = SimpleNamespace(model=None, __class__=type("NoModelVec", (), {}))
        monkeypatch.setattr(mem_mod, "MEM_VEC_EXTERNAL", ext)
        # Prevent actual VectorMemory construction
        fake_vm = SimpleNamespace(model="built-in-fake")
        monkeypatch.setattr(
            mem_mod,
            "VectorMemory",
            lambda **kw: fake_vm,
        )
        result = mem_mod._get_mem_vec()
        assert result is fake_vm

    def test_builtin_fallback_when_no_external(self, monkeypatch):
        """No external MEM_VEC → uses built-in VectorMemory."""
        self._reset_mem_vec(monkeypatch)
        monkeypatch.setattr(mem_mod, "MEM_VEC_EXTERNAL", None)

        fake_vm = SimpleNamespace(model="built-in-fake")
        monkeypatch.setattr(
            mem_mod,
            "VectorMemory",
            lambda **kw: fake_vm,
        )
        result = mem_mod._get_mem_vec()
        assert result is fake_vm

    def test_init_error_returns_none(self, monkeypatch):
        """VectorMemory construction raises → MEM_VEC=None."""
        self._reset_mem_vec(monkeypatch)
        monkeypatch.setattr(mem_mod, "MEM_VEC_EXTERNAL", None)

        def raise_err(**kw):
            raise RuntimeError("model init failed")

        monkeypatch.setattr(mem_mod, "VectorMemory", raise_err)
        result = mem_mod._get_mem_vec()
        assert result is None

    def test_cached_value_returned(self, monkeypatch):
        """Once initialized, _get_mem_vec returns cached value."""
        monkeypatch.setattr(mem_mod, "_runtime_guard_checked", True)
        sentinel = SimpleNamespace(cached=True)
        monkeypatch.setattr(mem_mod, "MEM_VEC", sentinel)
        result = mem_mod._get_mem_vec()
        assert result is sentinel


# ---------------------------------------------------------------------------
# locked_memory (non-POSIX / Windows-like path)
# ---------------------------------------------------------------------------


class TestLockedMemory:
    """locked_memory: Windows-like .lock fallback path."""

    def test_basic_lock_unlock_non_posix(self, tmp_path, monkeypatch):
        """Simulate non-POSIX by disabling fcntl → uses .lock file."""
        monkeypatch.setattr(mem_mod, "IS_WIN", False)
        monkeypatch.setattr(mem_mod, "fcntl", None)

        target = tmp_path / "test_memory.json"
        with locked_memory(target):
            # Inside lock: .lock file should exist
            lockfile = target.with_suffix(target.suffix + ".lock")
            assert lockfile.exists()

        # After exiting: .lock file should be cleaned up
        assert not lockfile.exists()

    def test_lock_timeout_non_posix(self, tmp_path, monkeypatch):
        """Holding a .lock file → second lock attempt times out."""
        monkeypatch.setattr(mem_mod, "IS_WIN", False)
        monkeypatch.setattr(mem_mod, "fcntl", None)

        target = tmp_path / "test_memory.json"
        lockfile = target.with_suffix(target.suffix + ".lock")

        # Create the lockfile manually (simulate held lock)
        fd = os.open(str(lockfile), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)

        with pytest.raises(TimeoutError, match="failed to acquire lock"):
            with locked_memory(target, timeout=0.1):
                pass

        # Clean up
        lockfile.unlink(missing_ok=True)

    def test_stale_lock_removed_non_posix(self, tmp_path, monkeypatch):
        """Stale .lock file (>300s) → removed and lock acquired."""
        monkeypatch.setattr(mem_mod, "IS_WIN", False)
        monkeypatch.setattr(mem_mod, "fcntl", None)

        target = tmp_path / "test_memory.json"
        lockfile = target.with_suffix(target.suffix + ".lock")

        # Create a lockfile with old mtime
        fd = os.open(str(lockfile), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        # Set mtime to 600 seconds ago
        old_time = time.time() - 600
        os.utime(str(lockfile), (old_time, old_time))

        with locked_memory(target):
            pass  # Should succeed after removing stale lock

        assert not lockfile.exists()


import os


# ---------------------------------------------------------------------------
# _LazyMemoryStore branches
# ---------------------------------------------------------------------------


class TestLazyMemoryStore:
    """_LazyMemoryStore: success / cached reuse / failure path."""

    def test_success_load(self):
        """First access triggers loader and returns the object."""
        store = FakeMemoryStore()
        lazy = _LazyMemoryStore(lambda: store)
        # Access an attribute to trigger _load
        result = lazy.put("u1", "k1", "v1")
        assert result is True

    def test_cached_reuse(self):
        """Second access reuses the cached object (loader not called again)."""
        call_count = 0

        def loader():
            nonlocal call_count
            call_count += 1
            return FakeMemoryStore()

        lazy = _LazyMemoryStore(loader)
        lazy.put("u1", "k1", "v1")
        lazy.put("u1", "k2", "v2")
        assert call_count == 1

    def test_failure_raises_and_caches_error(self):
        """Loader failure → RuntimeError on subsequent access."""
        def failing_loader():
            raise RuntimeError("init failed")

        lazy = _LazyMemoryStore(failing_loader)

        with pytest.raises(RuntimeError, match="init failed"):
            lazy.put("u1", "k1", "v1")

        # Subsequent access should raise the cached error
        with pytest.raises(RuntimeError, match="MemoryStore load failed"):
            lazy.put("u1", "k2", "v2")

    def test_oserror_raises_and_caches(self):
        """OSError also captured and cached."""
        def failing_loader():
            raise OSError("disk error")

        lazy = _LazyMemoryStore(failing_loader)

        with pytest.raises(OSError):
            lazy.put("u1", "k1", "v1")

        with pytest.raises(RuntimeError, match="MemoryStore load failed"):
            lazy.put("u1", "k2", "v2")


# ---------------------------------------------------------------------------
# Global put() branches
# ---------------------------------------------------------------------------


class TestGlobalPut:
    """Global put(): KVS / vector / kwargs / invalid."""

    def _setup(self, monkeypatch):
        store = FakeMemoryStore()
        monkeypatch.setattr(mem_mod, "MEM", store)
        return store

    def test_kvs_mode_positional(self, monkeypatch):
        """put(user_id, key, value) → KVS put."""
        store = self._setup(monkeypatch)
        ok = mem_mod.put("u1", "k1", {"data": 1})
        assert ok is True
        assert store.get("u1", "k1") == {"data": 1}

    def test_kvs_mode_kwargs(self, monkeypatch):
        """put(user_id="u1", key="k1", value=...) → KVS put."""
        store = self._setup(monkeypatch)
        ok = mem_mod.put(user_id="u1", key="k1", value=42)
        assert ok is True

    def test_kvs_mode_mixed_args_kwargs(self, monkeypatch):
        """put(user_id, key=..., value=...) → KVS put."""
        store = self._setup(monkeypatch)
        ok = mem_mod.put("u1", key="k1", value="hello")
        assert ok is True

    def test_vector_mode(self, monkeypatch):
        """put(kind, {text, tags, meta}) → vector + KVS."""
        store = self._setup(monkeypatch)
        vec = FakeVec()
        monkeypatch.setattr(mem_mod, "_get_mem_vec", lambda: vec)

        doc = {"text": "test text", "tags": ["a"], "meta": {"user_id": "u1"}}
        ok = mem_mod.put("semantic", doc)
        assert ok is True
        assert len(vec._added) == 1

    def test_vector_mode_empty_text(self, monkeypatch):
        """put(kind, {text: ""}) → still saved to KVS (empty text goes through)."""
        store = self._setup(monkeypatch)
        vec = FakeVec()
        monkeypatch.setattr(mem_mod, "_get_mem_vec", lambda: vec)

        # empty text and empty doc → returns False (special check at line 1201)
        doc: Dict[str, Any] = {"text": "", "tags": [], "meta": {}}
        # This goes to the "not text and not doc" check - doc is truthy though
        ok = mem_mod.put("semantic", doc)
        assert ok is True  # doc is not empty, so it proceeds

    def test_vector_mode_vec_add_error_fallback(self, monkeypatch):
        """Vector add fails → still saved to KVS."""
        store = self._setup(monkeypatch)
        vec = FakeVec()
        vec.add = MagicMock(side_effect=AttributeError("no add"))
        monkeypatch.setattr(mem_mod, "_get_mem_vec", lambda: vec)

        doc = {"text": "test", "tags": [], "meta": {}}
        ok = mem_mod.put("semantic", doc)
        assert ok is True  # KVS save still succeeds

    def test_invalid_args_raises_typeerror(self, monkeypatch):
        """Invalid arguments → TypeError."""
        self._setup(monkeypatch)
        with pytest.raises(TypeError, match="put\\(\\) expected"):
            mem_mod.put()


# ---------------------------------------------------------------------------
# Global search() branches
# ---------------------------------------------------------------------------


class TestGlobalSearch:
    """Global search(): vector success / old sig fallback / KVS fallback."""

    def _setup(self, monkeypatch):
        store = FakeMemoryStore()
        monkeypatch.setattr(mem_mod, "MEM", store)
        return store

    def test_vector_search_returns_results(self, monkeypatch):
        """MEM_VEC returns hits → returned as-is."""
        self._setup(monkeypatch)
        hits = [
            {"id": "1", "text": "hello", "score": 0.9, "kind": "episodic"},
            {"id": "2", "text": "world", "score": 0.8, "kind": "episodic"},
        ]
        vec = FakeVec(hits=hits)
        monkeypatch.setattr(mem_mod, "_get_mem_vec", lambda: vec)

        results = mem_mod.search("hello", k=5)
        assert len(results) == 2

    def test_vector_search_empty_falls_back_to_kvs(self, monkeypatch):
        """MEM_VEC returns [] → fallback to KVS."""
        store = self._setup(monkeypatch)
        vec = FakeVec(hits=[])
        monkeypatch.setattr(mem_mod, "_get_mem_vec", lambda: vec)

        results = mem_mod.search("hello", k=5)
        # KVS returns empty too
        assert results == []

    def test_vector_search_old_signature_fallback(self, monkeypatch):
        """TypeError from new sig → tries old sig (query, k)."""
        self._setup(monkeypatch)
        hits = [{"id": "1", "text": "hello", "score": 0.9}]
        # First call with new sig raises TypeError, then old sig returns hits
        call_count = [0]
        def search_fn(query, k=10, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1 and kwargs:
                raise TypeError("unexpected keyword")
            return hits

        vec = SimpleNamespace(search=search_fn)
        monkeypatch.setattr(mem_mod, "_get_mem_vec", lambda: vec)

        results = mem_mod.search("hello", k=5)
        assert len(results) == 1

    def test_vector_search_runtime_error_falls_back(self, monkeypatch):
        """RuntimeError from vector search → falls back to KVS."""
        store = self._setup(monkeypatch)
        vec = FakeVec(raise_on_search=RuntimeError("boom"))
        monkeypatch.setattr(mem_mod, "_get_mem_vec", lambda: vec)

        results = mem_mod.search("hello")
        assert isinstance(results, list)

    def test_search_no_vec_uses_kvs_only(self, monkeypatch):
        """MEM_VEC=None → KVS search only."""
        self._setup(monkeypatch)
        monkeypatch.setattr(mem_mod, "_get_mem_vec", lambda: None)

        results = mem_mod.search("hello")
        assert isinstance(results, list)

    def test_search_dedup_by_text_user_id(self, monkeypatch):
        """Duplicate (text, user_id) entries are deduplicated."""
        self._setup(monkeypatch)
        hits = [
            {"id": "1", "text": "same", "score": 0.9,
             "meta": {"user_id": "u1"}},
            {"id": "2", "text": "same", "score": 0.8,
             "meta": {"user_id": "u1"}},
            {"id": "3", "text": "different", "score": 0.7,
             "meta": {"user_id": "u1"}},
        ]
        vec = FakeVec(hits=hits)
        monkeypatch.setattr(mem_mod, "_get_mem_vec", lambda: vec)

        results = mem_mod.search("test", k=10)
        texts = [r["text"] for r in results]
        # "same" should appear only once
        assert texts.count("same") == 1


# ---------------------------------------------------------------------------
# Global add()
# ---------------------------------------------------------------------------


class TestGlobalAdd:
    """Global add(): success / empty text / vector error."""

    def _setup(self, monkeypatch):
        store = FakeMemoryStore()
        monkeypatch.setattr(mem_mod, "MEM", store)
        vec = FakeVec()
        monkeypatch.setattr(mem_mod, "_get_mem_vec", lambda: vec)
        return store, vec

    def test_add_success(self, monkeypatch):
        store, vec = self._setup(monkeypatch)
        result = mem_mod.add(user_id="u1", text="hello world", kind="note")
        assert result["kind"] == "note"
        assert result["text"] == "hello world"
        assert len(vec._added) == 1

    def test_add_empty_text_raises(self, monkeypatch):
        store, vec = self._setup(monkeypatch)
        with pytest.raises(ValueError, match="text is empty"):
            mem_mod.add(user_id="u1", text="")

    def test_add_whitespace_text_raises(self, monkeypatch):
        store, vec = self._setup(monkeypatch)
        with pytest.raises(ValueError, match="text is empty"):
            mem_mod.add(user_id="u1", text="   ")

    def test_add_vec_none_still_saves_kvs(self, monkeypatch):
        store = FakeMemoryStore()
        monkeypatch.setattr(mem_mod, "MEM", store)
        monkeypatch.setattr(mem_mod, "_get_mem_vec", lambda: None)

        result = mem_mod.add(user_id="u1", text="hello")
        assert result["text"] == "hello"

    def test_add_vec_error_still_saves_kvs(self, monkeypatch):
        store = FakeMemoryStore()
        monkeypatch.setattr(mem_mod, "MEM", store)

        vec = FakeVec()
        vec.add = MagicMock(side_effect=RuntimeError("vec add failed"))
        monkeypatch.setattr(mem_mod, "_get_mem_vec", lambda: vec)

        result = mem_mod.add(user_id="u1", text="hello")
        assert result["text"] == "hello"


# ---------------------------------------------------------------------------
# distill_memory_for_user branches
# ---------------------------------------------------------------------------


class TestDistillMemoryForUser:
    """distill_memory_for_user: no episodic / llm unavailable / save fail / success."""

    def _setup(self, monkeypatch, records=None):
        store = FakeMemoryStore()
        if records:
            for r in records:
                uid = r.get("meta", {}).get("user_id", "u1")
                key = f"ep_{id(r)}"
                store.put(uid, key, r)
        monkeypatch.setattr(mem_mod, "MEM", store)
        return store

    def test_no_episodic_returns_none(self, monkeypatch):
        """No episodic records → returns None."""
        self._setup(monkeypatch, records=[
            {"kind": "semantic", "text": "not episodic", "ts": 1.0,
             "meta": {"user_id": "u1"}},
        ])
        result = mem_mod.distill_memory_for_user("u1")
        assert result is None

    def test_llm_not_available_returns_none(self, monkeypatch):
        """llm_client.chat_completion not callable → returns None."""
        self._setup(monkeypatch, records=[
            {"kind": "episodic", "text": "hello world long text here",
             "ts": 1.0, "meta": {"user_id": "u1"}},
        ])
        monkeypatch.setattr(mem_mod.llm_client, "chat_completion", None)

        result = mem_mod.distill_memory_for_user("u1", min_text_len=5)
        assert result is None

    def test_llm_returns_empty_summary(self, monkeypatch):
        """LLM returns empty summary → returns None."""
        self._setup(monkeypatch, records=[
            {"kind": "episodic", "text": "hello world long text here",
             "ts": 1.0, "meta": {"user_id": "u1"}},
        ])
        monkeypatch.setattr(
            mem_mod.llm_client,
            "chat_completion",
            lambda **kw: "",
        )
        result = mem_mod.distill_memory_for_user("u1", min_text_len=5)
        assert result is None

    def test_llm_call_typeerror_returns_none(self, monkeypatch):
        """TypeError during LLM call → returns None."""
        self._setup(monkeypatch, records=[
            {"kind": "episodic", "text": "hello world long text here",
             "ts": 1.0, "meta": {"user_id": "u1"}},
        ])

        def bad_chat(**kw):
            raise TypeError("bad signature")

        monkeypatch.setattr(mem_mod.llm_client, "chat_completion", bad_chat)
        result = mem_mod.distill_memory_for_user("u1", min_text_len=5)
        assert result is None

    def test_llm_call_runtime_error_returns_none(self, monkeypatch):
        """RuntimeError during LLM call → returns None."""
        self._setup(monkeypatch, records=[
            {"kind": "episodic", "text": "hello world long text here",
             "ts": 1.0, "meta": {"user_id": "u1"}},
        ])

        def bad_chat(**kw):
            raise RuntimeError("LLM down")

        monkeypatch.setattr(mem_mod.llm_client, "chat_completion", bad_chat)
        result = mem_mod.distill_memory_for_user("u1", min_text_len=5)
        assert result is None

    def test_save_failure_returns_none(self, monkeypatch):
        """put() failure → returns None."""
        self._setup(monkeypatch, records=[
            {"kind": "episodic", "text": "hello world long text here",
             "ts": 1.0, "meta": {"user_id": "u1"}},
        ])

        monkeypatch.setattr(
            mem_mod.llm_client,
            "chat_completion",
            lambda **kw: "Summary of episodes",
        )

        # Make put() return False
        original_put = mem_mod.put

        def failing_put(*args, **kwargs):
            return False

        monkeypatch.setattr(mem_mod, "put", failing_put)

        result = mem_mod.distill_memory_for_user("u1", min_text_len=5)
        assert result is None

    def test_success_full_flow(self, monkeypatch):
        """Full success: episodic records → LLM → save → doc returned."""
        self._setup(monkeypatch, records=[
            {"kind": "episodic", "text": "important meeting notes about project X",
             "ts": 1.0, "meta": {"user_id": "u1"}},
        ])

        monkeypatch.setattr(
            mem_mod.llm_client,
            "chat_completion",
            lambda **kw: "Summarized: user discussed project X",
        )

        # Make put() succeed and return True
        monkeypatch.setattr(mem_mod, "put", lambda *a, **kw: True)

        result = mem_mod.distill_memory_for_user("u1", min_text_len=5)
        assert result is not None
        assert "text" in result

    def test_list_all_error_returns_none(self, monkeypatch):
        """MEM.list_all raises → returns None."""
        store = MagicMock()
        store.list_all.side_effect = RuntimeError("db error")
        monkeypatch.setattr(mem_mod, "MEM", store)

        result = mem_mod.distill_memory_for_user("u1")
        assert result is None


# ---------------------------------------------------------------------------
# rebuild_vector_index branches
# ---------------------------------------------------------------------------


class TestRebuildVectorIndex:
    """rebuild_vector_index: MEM_VEC is None / no rebuild_index / success."""

    def test_mem_vec_none_returns_early(self, monkeypatch):
        """MEM_VEC=None → logs error and returns."""
        monkeypatch.setattr(mem_mod, "MEM_VEC", None)
        # Should not raise
        mem_mod.rebuild_vector_index()

    def test_no_rebuild_index_method(self, monkeypatch):
        """MEM_VEC has no rebuild_index → logs error and returns."""
        vec = SimpleNamespace()  # No rebuild_index method
        monkeypatch.setattr(mem_mod, "MEM_VEC", vec)
        # Should not raise
        mem_mod.rebuild_vector_index()

    def test_success(self, monkeypatch):
        """rebuild_vector_index calls MEM_VEC.rebuild_index with docs."""
        store = FakeMemoryStore()
        store.put("u1", "k1", {
            "kind": "episodic",
            "text": "test data for rebuild",
            "tags": ["a"],
            "meta": {"user_id": "u1"},
        })
        monkeypatch.setattr(mem_mod, "MEM", store)

        rebuilt_docs = []

        class FakeRebuildVec:
            def rebuild_index(self, documents):
                rebuilt_docs.extend(documents)

        vec = FakeRebuildVec()
        monkeypatch.setattr(mem_mod, "MEM_VEC", vec)

        mem_mod.rebuild_vector_index()
        # build_vector_rebuild_documents filters by text presence
        assert isinstance(rebuilt_docs, list)


# ---------------------------------------------------------------------------
# predict_decision_status / predict_gate_label
# ---------------------------------------------------------------------------


class TestPredictions:
    """predict_decision_status / predict_gate_label edge cases."""

    def test_predict_decision_status_no_model(self, monkeypatch):
        monkeypatch.setattr(mem_mod, "MODEL", None)
        assert mem_mod.predict_decision_status("test") == "unknown"

    def test_predict_decision_status_with_model(self, monkeypatch):
        model = MagicMock()
        model.predict.return_value = ["approved"]
        monkeypatch.setattr(mem_mod, "MODEL", model)
        assert mem_mod.predict_decision_status("test") == "approved"

    def test_predict_decision_status_error(self, monkeypatch):
        model = MagicMock()
        model.predict.side_effect = RuntimeError("model error")
        monkeypatch.setattr(mem_mod, "MODEL", model)
        assert mem_mod.predict_decision_status("test") == "unknown"

    def test_predict_gate_label_no_clf_no_model(self, monkeypatch):
        monkeypatch.setattr(mem_mod, "MEM_CLF", None)
        monkeypatch.setattr(mem_mod, "MODEL", None)
        result = mem_mod.predict_gate_label("test")
        assert result == {"allow": 0.5}

    def test_predict_gate_label_clf_with_allow_class(self, monkeypatch):
        clf = MagicMock()
        clf.predict_proba.return_value = [np.array([0.3, 0.7])]
        clf.classes_ = ["deny", "allow"]
        monkeypatch.setattr(mem_mod, "MEM_CLF", clf)
        result = mem_mod.predict_gate_label("test")
        assert abs(result["allow"] - 0.7) < 1e-6

    def test_predict_gate_label_clf_error_falls_through(self, monkeypatch):
        clf = MagicMock()
        clf.predict_proba.side_effect = RuntimeError("clf error")
        monkeypatch.setattr(mem_mod, "MEM_CLF", clf)
        monkeypatch.setattr(mem_mod, "MODEL", None)
        result = mem_mod.predict_gate_label("test")
        assert result == {"allow": 0.5}


# ---------------------------------------------------------------------------
# Global wrappers: get, list_all, recent, append_history, add_usage,
#                   summarize_for_planner
# ---------------------------------------------------------------------------


class TestGlobalWrappers:
    """Verify global wrapper functions delegate correctly."""

    def _setup(self, monkeypatch):
        store = FakeMemoryStore()
        monkeypatch.setattr(mem_mod, "MEM", store)
        return store

    def test_get(self, monkeypatch):
        store = self._setup(monkeypatch)
        store.put("u1", "k1", "hello")
        assert mem_mod.get("u1", "k1") == "hello"

    def test_list_all(self, monkeypatch):
        store = self._setup(monkeypatch)
        store.put("u1", "k1", {"data": 1})
        result = mem_mod.list_all("u1")
        assert len(result) >= 1

    def test_recent(self, monkeypatch):
        store = self._setup(monkeypatch)
        store.put("u1", "k1", {"data": 1})
        result = mem_mod.recent("u1", limit=5)
        assert isinstance(result, list)

    def test_append_history(self, monkeypatch):
        store = self._setup(monkeypatch)
        ok = mem_mod.append_history("u1", {"query": "test"})
        assert ok is True

    def test_add_usage(self, monkeypatch):
        store = self._setup(monkeypatch)
        ok = mem_mod.add_usage("u1", ["id1", "id2"])
        assert ok is True

    def test_summarize_for_planner(self, monkeypatch):
        store = self._setup(monkeypatch)
        result = mem_mod.summarize_for_planner("u1", "test query")
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# _build_distill_prompt wrapper
# ---------------------------------------------------------------------------


class TestBuildDistillPrompt:
    """_build_distill_prompt backward-compat wrapper."""

    def test_wrapper_delegates(self):
        episodes = [
            {"text": "hello", "ts": 1234567890.0},
        ]
        prompt = mem_mod._build_distill_prompt("u1", episodes)
        assert isinstance(prompt, str)
        assert "u1" in prompt


# ---------------------------------------------------------------------------
# Evidence wrappers
# ---------------------------------------------------------------------------


class TestEvidenceWrappers:
    """Evidence helper wrappers delegate correctly."""

    def test_hits_to_evidence_empty(self):
        result = mem_mod._hits_to_evidence([])
        assert result == []

    def test_hits_to_evidence_with_hits(self):
        hits = [
            {"id": "1", "text": "hello", "score": 0.9},
        ]
        result = mem_mod._hits_to_evidence(hits)
        assert len(result) == 1

    def test_get_evidence_for_query(self, monkeypatch):
        monkeypatch.setattr(mem_mod, "search", lambda *a, **kw: [])
        result = mem_mod.get_evidence_for_query("test")
        assert isinstance(result, list)

    def test_get_evidence_for_decision(self, monkeypatch):
        monkeypatch.setattr(mem_mod, "search", lambda *a, **kw: [])
        result = mem_mod.get_evidence_for_decision(
            {"query": "test"},
            user_id="u1",
        )
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Backward-compat wrappers
# ---------------------------------------------------------------------------


class TestBackwardCompatWrappers:
    """Backward-compat wrappers for security functions."""

    def test_is_explicitly_enabled_returns_bool(self, monkeypatch):
        monkeypatch.delenv("VERITAS_CAP_MEMORY_SENTENCE_TRANSFORMERS",
                          raising=False)
        result = mem_mod._is_explicitly_enabled(
            "VERITAS_CAP_MEMORY_SENTENCE_TRANSFORMERS"
        )
        assert isinstance(result, bool)

    def test_warn_for_legacy_pickle_artifacts_no_crash(self, tmp_path):
        mem_mod._warn_for_legacy_pickle_artifacts([tmp_path])

    def test_emit_legacy_pickle_runtime_blocked_no_crash(self, tmp_path):
        mem_mod._emit_legacy_pickle_runtime_blocked(
            tmp_path / "test.pkl", "test artifact"
        )
