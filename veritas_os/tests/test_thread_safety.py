# veritas_os/tests/test_thread_safety.py
"""Tests for thread safety of memory components."""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import List
from unittest import mock

import pytest

from veritas_os.memory.index_cosine import CosineIndex


class TestCosineIndexThreadSafety:
    """Tests for CosineIndex thread safety."""

    def test_has_lock(self):
        """Test that CosineIndex has a lock."""
        idx = CosineIndex(dim=4)
        assert hasattr(idx, "_lock")
        assert isinstance(idx._lock, type(threading.RLock()))

    def test_concurrent_add_no_corruption(self, tmp_path: Path):
        """Test that concurrent adds don't corrupt the index."""
        pytest.importorskip("numpy")
        import numpy as np

        idx = CosineIndex(dim=4, path=tmp_path / "test.npz")
        errors: List[Exception] = []
        results: List[str] = []
        lock = threading.Lock()

        def add_items(thread_id: int, count: int):
            try:
                for i in range(count):
                    vec = np.random.rand(1, 4).astype(np.float32)
                    item_id = f"t{thread_id}_i{i}"
                    idx.add(vec, [item_id])
                    with lock:
                        results.append(item_id)
            except Exception as e:
                with lock:
                    errors.append(e)

        # Start multiple threads
        threads = []
        num_threads = 4
        items_per_thread = 10
        for t in range(num_threads):
            thread = threading.Thread(target=add_items, args=(t, items_per_thread))
            threads.append(thread)

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # Check no errors
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Check all items were added
        expected_count = num_threads * items_per_thread
        assert idx.size == expected_count, f"Expected {expected_count}, got {idx.size}"
        assert len(results) == expected_count

    def test_concurrent_search_during_add(self, tmp_path: Path):
        """Test that search works correctly during concurrent adds."""
        pytest.importorskip("numpy")
        import numpy as np

        idx = CosineIndex(dim=4, path=tmp_path / "test.npz")

        # Pre-populate with some data
        initial_vecs = np.random.rand(10, 4).astype(np.float32)
        idx.add(initial_vecs, [f"init_{i}" for i in range(10)])

        errors: List[Exception] = []
        search_results: List[int] = []
        lock = threading.Lock()

        def add_items():
            try:
                for i in range(20):
                    vec = np.random.rand(1, 4).astype(np.float32)
                    idx.add(vec, [f"add_{i}"])
                    time.sleep(0.001)  # Small delay to interleave
            except Exception as e:
                with lock:
                    errors.append(e)

        def search_items():
            try:
                for _ in range(30):
                    qv = np.random.rand(1, 4).astype(np.float32)
                    results = idx.search(qv, k=5)
                    # Should always return valid results
                    assert len(results) == 1
                    assert len(results[0]) <= 5
                    with lock:
                        search_results.append(len(results[0]))
                    time.sleep(0.001)
            except Exception as e:
                with lock:
                    errors.append(e)

        # Run add and search concurrently
        add_thread = threading.Thread(target=add_items)
        search_threads = [threading.Thread(target=search_items) for _ in range(3)]

        add_thread.start()
        for t in search_threads:
            t.start()

        add_thread.join()
        for t in search_threads:
            t.join()

        # Check no errors
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Check all searches returned results
        assert len(search_results) == 90  # 3 threads * 30 searches

    def test_search_returns_consistent_snapshot(self, tmp_path: Path):
        """Test that search returns a consistent view even during modifications."""
        pytest.importorskip("numpy")
        import numpy as np

        idx = CosineIndex(dim=4, path=tmp_path / "test.npz")

        # Add initial data
        vecs = np.eye(4, dtype=np.float32)
        idx.add(vecs, ["a", "b", "c", "d"])

        # Search while data exists
        qv = np.array([[1, 0, 0, 0]], dtype=np.float32)
        results = idx.search(qv, k=4)

        assert len(results) == 1
        assert len(results[0]) == 4
        # First result should be "a" (exact match)
        assert results[0][0][0] == "a"
        assert results[0][0][1] > 0.99  # Very high similarity


def test_rejects_non_finite_vectors(tmp_path: Path):
    """CosineIndex should reject NaN/Inf vectors to avoid poisoned results."""
    pytest.importorskip("numpy")
    import numpy as np

    idx = CosineIndex(dim=2, path=tmp_path / "test.npz")

    with pytest.raises(ValueError, match="finite"):
        idx.add(np.array([[np.nan, 0.0]], dtype=np.float32), ["bad_nan"])

    idx.add(np.array([[1.0, 0.0]], dtype=np.float32), ["ok"])

    with pytest.raises(ValueError, match="finite"):
        idx.search(np.array([[np.inf, 0.0]], dtype=np.float32), k=1)


class TestMemoryStoreThreadSafety:
    """Tests for MemoryStore thread safety."""

    def test_has_lock(self, tmp_path: Path, monkeypatch):
        """Test that MemoryStore has a lock."""
        # Patch the global paths to use tmp_path
        from veritas_os.memory import store
        monkeypatch.setattr(store, "BASE", tmp_path)
        monkeypatch.setattr(store, "FILES", {
            "episodic": tmp_path / "episodic.jsonl",
            "semantic": tmp_path / "semantic.jsonl",
            "skills": tmp_path / "skills.jsonl",
        })
        monkeypatch.setattr(store, "INDEX", {
            "episodic": tmp_path / "episodic.index.npz",
            "semantic": tmp_path / "semantic.index.npz",
            "skills": tmp_path / "skills.index.npz",
        })

        from veritas_os.memory.store import MemoryStore
        ms = MemoryStore(dim=4)
        assert hasattr(ms, "_lock")
        assert isinstance(ms._lock, type(threading.RLock()))

    def test_concurrent_put_operations(self, tmp_path: Path, monkeypatch):
        """Test that concurrent put operations don't cause data loss."""
        from veritas_os.memory import store
        monkeypatch.setattr(store, "BASE", tmp_path)
        monkeypatch.setattr(store, "FILES", {
            "episodic": tmp_path / "episodic.jsonl",
            "semantic": tmp_path / "semantic.jsonl",
            "skills": tmp_path / "skills.jsonl",
        })
        monkeypatch.setattr(store, "INDEX", {
            "episodic": tmp_path / "episodic.index.npz",
            "semantic": tmp_path / "semantic.index.npz",
            "skills": tmp_path / "skills.index.npz",
        })

        from veritas_os.memory.store import MemoryStore
        ms = MemoryStore(dim=4)

        errors: List[Exception] = []
        ids: List[str] = []
        lock = threading.Lock()

        def put_items(thread_id: int, count: int):
            try:
                for i in range(count):
                    item_id = ms.put("episodic", {
                        "text": f"Thread {thread_id} item {i}",
                        "tags": ["test"],
                    })
                    with lock:
                        ids.append(item_id)
            except Exception as e:
                with lock:
                    errors.append(e)

        # Start multiple threads
        threads = []
        num_threads = 4
        items_per_thread = 5
        for t in range(num_threads):
            thread = threading.Thread(target=put_items, args=(t, items_per_thread))
            threads.append(thread)

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # Check no errors
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Check all items were added
        expected_count = num_threads * items_per_thread
        assert len(ids) == expected_count

        # Check index has all items
        assert ms.idx["episodic"].size == expected_count

    def test_concurrent_put_and_search(self, tmp_path: Path, monkeypatch):
        """Test that concurrent put and search operations work correctly."""
        from veritas_os.memory import store
        monkeypatch.setattr(store, "BASE", tmp_path)
        monkeypatch.setattr(store, "FILES", {
            "episodic": tmp_path / "episodic.jsonl",
            "semantic": tmp_path / "semantic.jsonl",
            "skills": tmp_path / "skills.jsonl",
        })
        monkeypatch.setattr(store, "INDEX", {
            "episodic": tmp_path / "episodic.index.npz",
            "semantic": tmp_path / "semantic.index.npz",
            "skills": tmp_path / "skills.index.npz",
        })

        from veritas_os.memory.store import MemoryStore
        ms = MemoryStore(dim=4)

        # Pre-populate
        for i in range(5):
            ms.put("episodic", {"text": f"Initial item {i}", "tags": ["init"]})

        errors: List[Exception] = []
        search_succeeded: List[bool] = []
        lock = threading.Lock()

        def put_items():
            try:
                for i in range(10):
                    ms.put("episodic", {"text": f"New item {i}", "tags": ["new"]})
                    time.sleep(0.002)
            except Exception as e:
                with lock:
                    errors.append(e)

        def search_items():
            try:
                for _ in range(15):
                    result = ms.search("item", k=5, kinds=["episodic"])
                    # Should always get some results (at least initial items)
                    with lock:
                        search_succeeded.append("episodic" in result)
                    time.sleep(0.002)
            except Exception as e:
                with lock:
                    errors.append(e)

        # Run concurrently
        put_thread = threading.Thread(target=put_items)
        search_threads = [threading.Thread(target=search_items) for _ in range(2)]

        put_thread.start()
        for t in search_threads:
            t.start()

        put_thread.join()
        for t in search_threads:
            t.join()

        # Check no errors
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Check all searches completed
        assert len(search_succeeded) == 30  # 2 threads * 15 searches
        assert all(search_succeeded)


class TestRLockReentrancy:
    """Tests to verify RLock works correctly for reentrant calls."""

    def test_rlock_allows_reentrant_acquisition(self):
        """Test that RLock allows same thread to acquire multiple times."""
        lock = threading.RLock()

        # Same thread can acquire multiple times
        with lock:
            with lock:
                with lock:
                    pass  # Should not deadlock

    def test_cosine_index_nested_calls(self, tmp_path: Path):
        """Test that nested calls to CosineIndex don't deadlock."""
        pytest.importorskip("numpy")
        import numpy as np

        idx = CosineIndex(dim=4, path=tmp_path / "test.npz")

        # add() internally calls save(), both need lock
        vec = np.random.rand(1, 4).astype(np.float32)
        idx.add(vec, ["test"])  # Should not deadlock

        # Check size (uses lock) after add (which also uses lock)
        assert idx.size == 1


class TestDatasetWriterThreadSafety:
    """
    Tests for dataset_writer.py thread safety (C-1 fix).

    ★ C-1: dataset_writer.append_dataset_record にスレッド同期を追加。
    このテストは並行書き込み時にデータ破損しないことを確認します。
    """

    def test_has_lock(self):
        """Test that dataset_writer has a lock."""
        from veritas_os.logging import dataset_writer
        assert hasattr(dataset_writer, "_dataset_lock")
        assert isinstance(dataset_writer._dataset_lock, type(threading.RLock()))

    def test_concurrent_append_no_corruption(self, tmp_path: Path):
        """
        Test that concurrent appends don't corrupt the JSONL file.

        Multiple threads write records simultaneously and we verify:
        - All records are written
        - Each line is valid JSON
        - No interleaving/corruption
        """
        import json
        from veritas_os.logging.dataset_writer import (
            build_dataset_record,
            append_dataset_record,
        )

        path = tmp_path / "dataset.jsonl"
        errors: List[Exception] = []
        lock = threading.Lock()

        def dummy_request(i: int):
            return {"query": f"Query {i}", "context": {}}

        def dummy_response(i: int):
            return {
                "chosen": {"id": f"opt{i}", "title": f"Option {i}", "score": 0.9},
                "alternatives": [],
                "evidence": [],
                "fuji": {"status": "ok", "reasons": [], "violations": []},
                "gate": {"decision_status": "allow", "risk": 0.1, "telos_score": 0.8},
                "memory": {"used": False, "citations": 0},
            }

        def dummy_meta():
            return {"api_version": "v2.0", "kernel_version": "2.0.0"}

        def append_records(thread_id: int, count: int):
            try:
                for i in range(count):
                    rec = build_dataset_record(
                        dummy_request(thread_id * 100 + i),
                        dummy_response(thread_id * 100 + i),
                        dummy_meta(),
                    )
                    append_dataset_record(rec, path=path, validate=True)
            except Exception as e:
                with lock:
                    errors.append(e)

        # Start multiple threads
        threads = []
        num_threads = 4
        items_per_thread = 10
        for t in range(num_threads):
            thread = threading.Thread(target=append_records, args=(t, items_per_thread))
            threads.append(thread)

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # Check no errors
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Verify all records were written and are valid JSON
        with path.open("r", encoding="utf-8") as f:
            lines = f.readlines()

        assert len(lines) == num_threads * items_per_thread, \
            f"Expected {num_threads * items_per_thread} lines, got {len(lines)}"

        # Each line should be valid JSON
        for i, line in enumerate(lines):
            try:
                data = json.loads(line)
                assert "ts" in data
                assert "request" in data
                assert "response" in data
            except json.JSONDecodeError as e:
                pytest.fail(f"Line {i+1} is not valid JSON: {e}\nContent: {line[:200]}...")
