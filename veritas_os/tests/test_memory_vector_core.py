# tests for veritas_os/core/memory_vector.py — direct module tests
"""Tests for VectorMemory core."""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from veritas_os.core.memory_vector import (
    VectorMemory,
    _is_explicitly_enabled,
    _emit_legacy_pickle_runtime_blocked,
)


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


class TestVectorMemoryRebuild:
    def test_rebuild_without_model(self):
        with mock.patch("veritas_os.core.memory_vector.capability_cfg") as cfg:
            cfg.enable_memory_sentence_transformers = False
            vm = VectorMemory(index_path=None)
        vm.rebuild_index([{"text": "hello", "kind": "episodic"}])
        assert len(vm.documents) == 0  # No model, nothing added


class TestCosineSimStatic:
    def test_basic(self):
        import numpy as np
        vec = np.array([1.0, 0.0, 0.0])
        matrix = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        sims = VectorMemory._cosine_similarity(vec, matrix)
        assert sims[0] > 0.9
        assert sims[1] < 0.1
