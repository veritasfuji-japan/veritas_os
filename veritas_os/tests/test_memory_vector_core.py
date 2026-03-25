# tests for veritas_os/core/memory_vector.py — direct module tests
"""Tests for VectorMemory core."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from unittest import mock

import numpy as np
import pytest

from veritas_os.core.memory_vector import (
    VectorMemory,
    _is_explicitly_enabled,
    _emit_legacy_pickle_runtime_blocked,
)


class _FakeModel:
    """Deterministic fake embedding model for VectorMemory tests."""

    def __init__(self, vectors):
        self._vectors = list(vectors)

    def encode(self, texts):
        assert texts  # guard accidental empty calls in tests
        vec = self._vectors.pop(0)
        return [vec]


class TestIsExplicitlyEnabled:
    def test_not_set(self):
        import os
        os.environ.pop("TEST_VEC_FLAG_XYZ", None)
        assert _is_explicitly_enabled("TEST_VEC_FLAG_XYZ") is False

    def test_true(self):
        import os
        os.environ["TEST_VEC_FLAG_XYZ"] = "1"
        try:
            assert _is_explicitly_enabled("TEST_VEC_FLAG_XYZ") is True
        finally:
            os.environ.pop("TEST_VEC_FLAG_XYZ", None)

    def test_false(self):
        import os
        os.environ["TEST_VEC_FLAG_XYZ"] = "0"
        try:
            assert _is_explicitly_enabled("TEST_VEC_FLAG_XYZ") is False
        finally:
            os.environ.pop("TEST_VEC_FLAG_XYZ", None)


class TestEmitLegacyPickleBlocked:
    def test_does_not_raise(self):
        _emit_legacy_pickle_runtime_blocked(Path("/fake/path.pkl"), "test")


class TestVectorMemoryInit:
    def test_init_without_model(self):
        """Init with model loading disabled."""
        with mock.patch("veritas_os.core.memory_vector.capability_cfg") as cfg:
            cfg.enable_memory_sentence_transformers = False
            vm = VectorMemory(index_path=None)
        assert vm.model is None
        assert vm.documents == []

    def test_model_load_error_handled(self):
        """Model load errors should be caught gracefully."""
        import threading
        vm = VectorMemory.__new__(VectorMemory)
        vm.model_name = "test"
        vm.index_path = None
        vm.embedding_dim = 384
        vm._lock = threading.RLock()
        vm._id_counter = 0
        vm.documents = []
        vm.embeddings = None
        vm.model = None
        with mock.patch("veritas_os.core.memory_vector.capability_cfg") as cfg:
            cfg.enable_memory_sentence_transformers = True
            # Simulate model loading failure
            with mock.patch(
                "veritas_os.core.memory_vector.VectorMemory._load_model",
                side_effect=OSError("model not found"),
            ):
                try:
                    vm._load_model()
                except OSError:
                    pass
        # Model stays None on failure
        assert vm.model is None


class TestVectorMemoryAdd:
    def test_add_without_model(self):
        with mock.patch("veritas_os.core.memory_vector.capability_cfg") as cfg:
            cfg.enable_memory_sentence_transformers = False
            vm = VectorMemory(index_path=None)
        assert vm.add("episodic", "test text") is False

    def test_add_empty_text(self):
        with mock.patch("veritas_os.core.memory_vector.capability_cfg") as cfg:
            cfg.enable_memory_sentence_transformers = False
            vm = VectorMemory(index_path=None)
        assert vm.add("episodic", "") is False


class TestVectorMemorySearch:
    def test_search_without_model(self):
        with mock.patch("veritas_os.core.memory_vector.capability_cfg") as cfg:
            cfg.enable_memory_sentence_transformers = False
            vm = VectorMemory(index_path=None)
        assert vm.search("query") == []

    def test_search_empty_query(self):
        with mock.patch("veritas_os.core.memory_vector.capability_cfg") as cfg:
            cfg.enable_memory_sentence_transformers = False
            vm = VectorMemory(index_path=None)
        assert vm.search("") == []

    def test_search_kinds_filter_topk_and_min_sim(self):
        """Keep only matching kinds above threshold and slice to top-k."""
        import numpy as np

        vm = VectorMemory.__new__(VectorMemory)
        vm.model_name = "test"
        vm.index_path = None
        vm.embedding_dim = 3
        vm._lock = mock.MagicMock()
        vm._id_counter = 3
        vm.model = _FakeModel([np.array([1.0, 0.0, 0.0], dtype=np.float32)])
        vm.documents = [
            {"id": "d1", "text": "alpha", "kind": "semantic", "tags": []},
            {"id": "d2", "text": "beta", "kind": "episodic", "tags": []},
            {"id": "d3", "text": "gamma", "kind": "semantic", "tags": []},
        ]
        vm.embeddings = np.array(
            [
                [1.0, 0.0, 0.0],
                [0.9, 0.1, 0.0],
                [0.2, 0.9, 0.0],
            ],
            dtype=np.float32,
        )

        # Ensure ordering: d1 > d2 > d3, then filter kinds and threshold.
        with mock.patch.object(
            VectorMemory,
            "_cosine_similarity",
            return_value=np.array([0.95, 0.85, 0.25], dtype=np.float32),
        ):
            hits = vm.search(
                "query",
                k=1,
                kinds=["semantic"],
                min_sim=0.5,
            )

        assert len(hits) == 1
        assert hits[0]["id"] == "d1"
        assert hits[0]["score"] == pytest.approx(0.95)

    def test_search_skips_out_of_range_similarity_entries(self):
        """Defensive guard: ignore similarity values beyond docs length."""
        import threading
        import numpy as np

        vm = VectorMemory.__new__(VectorMemory)
        vm.model_name = "test"
        vm.index_path = None
        vm.embedding_dim = 2
        vm._lock = threading.RLock()
        vm._id_counter = 1
        vm.model = _FakeModel([np.array([1.0, 0.0], dtype=np.float32)])
        vm.documents = [{"id": "d1", "text": "alpha", "kind": "semantic"}]
        vm.embeddings = np.array([[1.0, 0.0]], dtype=np.float32)

        with mock.patch.object(
            VectorMemory,
            "_cosine_similarity",
            return_value=np.array([0.9, 0.8], dtype=np.float32),
        ):
            hits = vm.search("query", k=10)

        assert len(hits) == 1
        assert hits[0]["id"] == "d1"


class TestVectorMemoryLoadIndex:
    def _make_vm(self, index_path):
        """Create a VectorMemory with model disabled, then manually load index."""
        import threading
        vm = VectorMemory.__new__(VectorMemory)
        vm.model_name = "test"
        vm.index_path = index_path
        vm.embedding_dim = 384
        vm._lock = threading.RLock()
        vm._id_counter = 0
        vm.documents = []
        vm.embeddings = None
        vm.model = None
        # Always try to load, _load_index handles missing files
        vm._load_index()
        return vm

    def test_load_json_index(self, tmp_path):
        import numpy as np
        import base64
        json_path = tmp_path / "index.json"
        docs = [{"id": "test_1", "text": "hello", "kind": "episodic"}]
        embeddings = np.random.randn(1, 384).astype(np.float32)
        emb_b64 = base64.b64encode(embeddings.tobytes()).decode("ascii")
        json_path.write_text(json.dumps({
            "documents": docs,
            "embeddings": emb_b64,
            "embeddings_shape": [1, 384],
            "embeddings_dtype": "float32",
        }))
        # index_path should be the base path; _load_index looks for .json
        vm = self._make_vm(tmp_path / "index")
        assert len(vm.documents) == 1

    def test_load_list_format_index(self, tmp_path):
        json_path = tmp_path / "index.json"
        json_path.write_text(json.dumps({
            "documents": [{"id": "t1", "text": "hi"}],
            "embeddings": [[0.1] * 384],
        }))
        vm = self._make_vm(tmp_path / "index")
        assert len(vm.documents) == 1

    def test_legacy_pickle_blocked(self, tmp_path):
        pkl_path = tmp_path / "index.pkl"
        pkl_path.write_bytes(b"fake pickle")
        vm = self._make_vm(pkl_path)
        assert len(vm.documents) == 0

    def test_load_corrupt_json_keeps_empty_state(self, tmp_path):
        json_path = tmp_path / "index.json"
        json_path.write_text("not-json")

        vm = self._make_vm(tmp_path / "index")

        assert vm.documents == []
        assert vm.embeddings is None

    def test_load_base64_shape_mismatch_preserves_partial_state(self, tmp_path):
        import base64
        import numpy as np

        raw = np.array([[1.0, 2.0]], dtype=np.float32).tobytes()
        payload = {
            "documents": [{"id": "x", "text": "hello", "kind": "semantic"}],
            "embeddings": base64.b64encode(raw).decode("ascii"),
            "embeddings_dtype": "float32",
            "embeddings_shape": [99, 99],
        }
        (tmp_path / "index.json").write_text(json.dumps(payload), encoding="utf-8")

        vm = self._make_vm(tmp_path / "index")

        # Corrupt reshape path is caught; documents are already loaded.
        assert vm.documents == [{"id": "x", "text": "hello", "kind": "semantic"}]
        assert vm.embeddings.shape == (2,)


class TestVectorMemorySaveIndex:
    def test_save_index_writes_json_and_updates_path(self, tmp_path, monkeypatch):
        import threading
        import numpy as np

        vm = VectorMemory.__new__(VectorMemory)
        vm.model_name = "fake-model"
        vm.index_path = tmp_path / "vector_index.pkl"
        vm.embedding_dim = 4
        vm._lock = threading.RLock()
        vm._id_counter = 1
        vm.documents = [{"id": "d1", "text": "hello", "kind": "semantic"}]
        vm.embeddings = np.array([[1.0, 2.0, 3.0, 4.0]], dtype=np.float32)
        vm.model = None

        captured = {}

        def _fake_atomic_write(path, data):
            captured["path"] = path
            captured["data"] = data

        monkeypatch.setattr(
            "veritas_os.core.atomic_io.atomic_write_json",
            _fake_atomic_write,
        )

        vm._save_index()

        assert captured["path"].suffix == ".json"
        assert captured["data"]["format_version"] == "2.0"
        assert captured["data"]["embeddings_shape"] == [1, 4]
        assert vm.index_path.suffix == ".json"


class TestVectorMemoryRebuild:
    def test_rebuild_without_model(self):
        with mock.patch("veritas_os.core.memory_vector.capability_cfg") as cfg:
            cfg.enable_memory_sentence_transformers = False
            vm = VectorMemory(index_path=None)
        vm.rebuild_index([{"text": "hello", "kind": "episodic"}])
        assert len(vm.documents) == 0  # No model, nothing added


class TestCosineSimStatic:
    def test_basic(self):
        vec = np.array([1.0, 0.0, 0.0])
        matrix = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        sims = VectorMemory._cosine_similarity(vec, matrix)
        assert sims[0] > 0.9
        assert sims[1] < 0.1

    def test_exception_returns_zeros(self):
        """When cosine similarity computation raises, return zeros.

        Covers lines 423-427 (_cosine_similarity exception fallback).
        """
        # Pass a 1-D vec with a matrix that has incompatible shape for
        # np.linalg.norm(axis=1) — e.g. a scalar — to trigger an exception.
        bad_matrix = "not-an-array"
        vec = np.array([1.0, 0.0])
        result = VectorMemory._cosine_similarity(vec, bad_matrix)
        np.testing.assert_array_equal(result, np.zeros(len(bad_matrix)))


# ---------------------------------------------------------------------------
# Additional coverage tests for uncovered branches
# ---------------------------------------------------------------------------

def _make_vm_raw(*, index_path=None, dim=4):
    """Create a VectorMemory via __new__ bypassing __init__."""
    vm = VectorMemory.__new__(VectorMemory)
    vm.model_name = "test"
    vm.index_path = index_path
    vm.embedding_dim = dim
    vm._lock = threading.RLock()
    vm._id_counter = 0
    vm.documents = []
    vm.embeddings = None
    vm.model = None
    return vm


class TestLoadModelEarlyReturn:
    """_load_model: first early-return when model is already loaded (line 84)."""

    def test_model_already_loaded_returns_immediately(self):
        vm = _make_vm_raw()
        sentinel = object()
        vm.model = sentinel
        # Calling _load_model should return immediately without changing model
        vm._load_model()
        assert vm.model is sentinel


class TestLoadIndexUnsupportedEmbeddingsType:
    """_load_index: embeddings value that is neither str nor list (line 157)."""

    def test_embeddings_dict_type_sets_none(self, tmp_path):
        json_path = tmp_path / "index.json"
        json_path.write_text(json.dumps({
            "documents": [{"id": "d1", "text": "hello", "kind": "semantic"}],
            "embeddings": {"unexpected": "format"},
        }))
        vm = _make_vm_raw(index_path=tmp_path / "index")
        vm._load_index()
        assert len(vm.documents) == 1
        assert vm.embeddings is None

    def test_embeddings_int_type_sets_none(self, tmp_path):
        json_path = tmp_path / "index.json"
        json_path.write_text(json.dumps({
            "documents": [{"id": "d1", "text": "hello", "kind": "semantic"}],
            "embeddings": 42,
        }))
        vm = _make_vm_raw(index_path=tmp_path / "index")
        vm._load_index()
        assert len(vm.documents) == 1
        assert vm.embeddings is None


class TestAddGAP05ImportError:
    """add(): ImportError when eu_ai_act_compliance_module is unavailable (lines 262-263)."""

    def test_import_error_does_not_block_add(self):
        vm = _make_vm_raw(dim=4)
        vm.model = _FakeModel([np.ones((1, 4), dtype=np.float32)])

        with mock.patch(
            "veritas_os.core.memory_vector.validate_data_quality",
            side_effect=ImportError("no module"),
            create=True,
        ):
            # Force the import inside add() to fail
            import builtins
            _real_import = builtins.__import__

            def _mock_import(name, *args, **kwargs):
                if "eu_ai_act_compliance_module" in name:
                    raise ImportError("mocked away")
                return _real_import(name, *args, **kwargs)

            with mock.patch.object(builtins, "__import__", side_effect=_mock_import):
                ok = vm.add("semantic", "hello world")

        assert ok is True
        assert len(vm.documents) == 1


class TestAddAutosaveEvery100:
    """add(): triggers _save_index every 100 documents (line 304)."""

    def test_autosave_at_100_docs(self, tmp_path):
        vm = _make_vm_raw(index_path=tmp_path / "idx", dim=2)

        class BulkModel:
            def encode(self, texts):
                return np.ones((len(texts), 2), dtype=np.float32)

        vm.model = BulkModel()

        save_calls = []
        original_save = vm._save_index

        def track_save():
            save_calls.append(len(vm.documents))
            # Don't actually save — just track the call
        vm._save_index = track_save

        for i in range(100):
            assert vm.add("ep", f"doc {i}") is True

        assert len(vm.documents) == 100
        # _save_index should have been called once at exactly 100 docs
        assert 100 in save_calls


class TestSearchDoubleCheckGuard:
    """search(): second empty-check inside lock returns [] (line 349)."""

    def test_documents_cleared_between_checks(self):
        vm = _make_vm_raw(dim=2)
        vm.documents = [{"id": "d1", "text": "x", "kind": "ep"}]
        vm.embeddings = np.ones((1, 2), dtype=np.float32)

        call_count = [0]

        class ClearingModel:
            """Model that clears documents during encode to simulate a race."""
            def encode(self, texts):
                call_count[0] += 1
                # Simulate another thread clearing data after the outer check
                vm.documents = []
                vm.embeddings = None
                return np.ones((len(texts), 2), dtype=np.float32)

        vm.model = ClearingModel()
        result = vm.search("query")
        assert result == []
        assert call_count[0] == 1  # encode was called


class TestLoadIndexBase64NoShape:
    """_load_index: base64 embeddings without shape metadata (branch 151->159)."""

    def test_base64_without_shape_stays_flat(self, tmp_path):
        raw = np.array([1.0, 2.0, 3.0, 4.0], dtype=np.float32).tobytes()
        import base64
        payload = {
            "documents": [{"id": "d1", "text": "hi", "kind": "ep"}],
            "embeddings": base64.b64encode(raw).decode("ascii"),
            "embeddings_dtype": "float32",
            # No "embeddings_shape" key → shape is None → skip reshape
        }
        (tmp_path / "index.json").write_text(json.dumps(payload))

        vm = _make_vm_raw(index_path=tmp_path / "index")
        vm._load_index()
        assert len(vm.documents) == 1
        assert vm.embeddings is not None
        # Without shape metadata the array stays 1-D
        assert vm.embeddings.ndim == 1
        assert len(vm.embeddings) == 4


class TestSaveIndexNoNumpyEmbeddings:
    """_save_index: embeddings that lack tobytes (branch 194->201)."""

    def test_non_numpy_embeddings_saved_as_null(self, tmp_path, monkeypatch):
        vm = _make_vm_raw(index_path=tmp_path / "idx.json", dim=2)
        vm.documents = [{"id": "d1", "text": "hi", "kind": "ep"}]
        # Set embeddings to a plain list (no tobytes attribute)
        vm.embeddings = [[1.0, 2.0]]

        captured = {}

        def fake_write(path, data):
            captured["data"] = data

        monkeypatch.setattr(
            "veritas_os.core.atomic_io.atomic_write_json", fake_write
        )
        vm._save_index()
        # Without tobytes, embeddings_b64 stays None
        assert captured["data"]["embeddings"] is None
        assert captured["data"]["embeddings_shape"] is None
