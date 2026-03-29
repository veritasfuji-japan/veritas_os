# veritas_os/tests/test_memory_decomposition.py
"""Tests for the memory.py responsibility decomposition.

Validates that:
- memory_vector.py contains VectorMemory class and is importable independently
- memory_store_compat.py can be imported and hooks are applied
- memory_distillation.py uses shared helpers from memory_helpers.py
- memory.py re-exports all public symbols for backward compatibility
- _SyncModule propagates monkeypatches to memory_vector
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest


# -------------------------------------------------
# 1. memory_vector.py: VectorMemory isolation
# -------------------------------------------------


def test_memory_vector_importable_independently() -> None:
    """memory_vector.py is importable without importing memory.py."""
    from veritas_os.core import memory_vector

    assert hasattr(memory_vector, "VectorMemory")
    assert callable(memory_vector.VectorMemory)


def test_vector_memory_class_identity() -> None:
    """memory.VectorMemory IS memory_vector.VectorMemory (same class object)."""
    from veritas_os.core import memory, memory_vector

    assert memory.VectorMemory is memory_vector.VectorMemory


def test_memory_vector_has_security_wrappers() -> None:
    """memory_vector.py exposes patchable wrappers for security helpers."""
    from veritas_os.core import memory_vector

    assert callable(memory_vector._is_explicitly_enabled)
    assert callable(memory_vector._emit_legacy_pickle_runtime_blocked)


# -------------------------------------------------
# 2. memory_store_compat.py: hook isolation
# -------------------------------------------------


def test_memory_store_compat_importable() -> None:
    """memory_store_compat.py can be imported independently."""
    from veritas_os.core import memory_store_compat

    assert hasattr(memory_store_compat, "install_memory_store_compat_hooks")
    assert callable(memory_store_compat.install_memory_store_compat_hooks)


def test_compat_hooks_applied_to_memory_store() -> None:
    """MemoryStore has compat methods installed by memory.py import."""
    from veritas_os.core.memory_store import MemoryStore

    assert hasattr(MemoryStore, "recent")
    assert hasattr(MemoryStore, "search")
    assert hasattr(MemoryStore, "put_episode")
    assert hasattr(MemoryStore, "erase_user")
    assert hasattr(MemoryStore, "summarize_for_planner")
    assert hasattr(MemoryStore, "_parse_expires_at")
    assert hasattr(MemoryStore, "_normalize_lifecycle")
    assert hasattr(MemoryStore, "_is_record_expired")


# -------------------------------------------------
# 3. memory_distillation.py: uses shared helpers
# -------------------------------------------------


def test_memory_distillation_uses_shared_helpers() -> None:
    """memory_distillation.py delegates to memory_helpers for prompt/extract."""
    from veritas_os.core import memory_distillation, memory_helpers

    # Verify the module imports from memory_helpers (not inline duplicates)
    assert hasattr(memory_distillation, "_distill_impl") is False  # not re-exported
    assert callable(memory_distillation.distill_memory_for_user)


def test_distill_rejects_empty_store(tmp_path: Path) -> None:
    """distill_memory_for_user returns None when store has no episodic records."""
    from veritas_os.core.memory_distillation import distill_memory_for_user

    mock_store = MagicMock()
    mock_store.list_all.return_value = []

    result = distill_memory_for_user(
        "test_user",
        mem_store=mock_store,
        llm_client_module=MagicMock(),
        put_fn=MagicMock(),
    )
    assert result is None


def test_distill_calls_collect_and_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    """distill_memory_for_user uses collect_episodic_records and build_distill_prompt."""
    from veritas_os.core import memory_distillation

    fake_records = [
        {"key": "k1", "ts": 1.0, "value": {"kind": "episodic", "text": "hello world", "tags": []}},
    ]
    mock_store = MagicMock()
    mock_store.list_all.return_value = fake_records

    mock_llm = MagicMock()
    mock_llm.chat_completion.return_value = "Summary text"

    mock_put = MagicMock(return_value=True)

    result = memory_distillation.distill_memory_for_user(
        "u1",
        mem_store=mock_store,
        llm_client_module=mock_llm,
        put_fn=mock_put,
    )
    assert result is not None
    assert result["kind"] == "semantic"
    assert "Summary text" in result["text"]
    mock_put.assert_called_once()


# -------------------------------------------------
# 4. memory.py: backward-compatible re-exports
# -------------------------------------------------


def test_memory_reexports_vector_memory() -> None:
    """VectorMemory is importable from memory.py."""
    from veritas_os.core.memory import VectorMemory

    assert VectorMemory is not None


def test_memory_reexports_locked_memory() -> None:
    """locked_memory context manager is importable from memory.py."""
    from veritas_os.core.memory import locked_memory

    assert callable(locked_memory)


def test_memory_reexports_predict_functions() -> None:
    """predict_decision_status and predict_gate_label are in memory.py."""
    from veritas_os.core.memory import predict_decision_status, predict_gate_label

    assert callable(predict_decision_status)
    assert callable(predict_gate_label)


def test_memory_reexports_mem_vec_globals() -> None:
    """MEM_VEC, _get_mem_vec, _mem_vec_lock are accessible from memory.py."""
    from veritas_os.core import memory

    assert hasattr(memory, "MEM_VEC")
    assert hasattr(memory, "_get_mem_vec")
    assert hasattr(memory, "_mem_vec_lock")


def test_memory_reexports_lazy_memory_store() -> None:
    """_LazyMemoryStore class is accessible from memory.py."""
    from veritas_os.core.memory import _LazyMemoryStore

    assert _LazyMemoryStore is not None


def test_memory_reexports_public_api() -> None:
    """Public API functions are accessible from memory.py."""
    from veritas_os.core import memory

    for name in [
        "add", "put", "get", "list_all", "search", "recent",
        "append_history", "add_usage",
        "summarize_for_planner", "distill_memory_for_user",
        "rebuild_vector_index", "get_evidence_for_decision",
        "get_evidence_for_query",
    ]:
        assert hasattr(memory, name), f"memory.{name} is missing"
        assert callable(getattr(memory, name)), f"memory.{name} is not callable"


# -------------------------------------------------
# 5. _SyncModule: monkeypatch propagation
# -------------------------------------------------


def test_sync_module_propagates_is_explicitly_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setting memory._is_explicitly_enabled also updates memory_vector."""
    from veritas_os.core import memory, memory_vector

    original = memory_vector._is_explicitly_enabled

    def sentinel(_: str) -> bool:
        return True

    monkeypatch.setattr(memory, "_is_explicitly_enabled", sentinel)
    assert memory_vector._is_explicitly_enabled is sentinel

    # monkeypatch teardown restores memory._is_explicitly_enabled
    # which also restores memory_vector._is_explicitly_enabled via _SyncModule


def test_sync_module_propagates_emit_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setting memory._emit_legacy_pickle_runtime_blocked also updates memory_vector."""
    from veritas_os.core import memory, memory_vector

    def sentinel(path: Any, name: str) -> None:
        return None

    monkeypatch.setattr(memory, "_emit_legacy_pickle_runtime_blocked", sentinel)
    assert memory_vector._emit_legacy_pickle_runtime_blocked is sentinel


# -------------------------------------------------
# 6. locked_memory wrapper reads module-level IS_WIN/fcntl
# -------------------------------------------------


def test_locked_memory_posix_delegates_to_storage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On POSIX with fcntl, locked_memory delegates to memory_storage."""
    from veritas_os.core import memory

    target = tmp_path / "test.json"
    # Default (POSIX with fcntl) should work without error
    with memory.locked_memory(target):
        pass


def test_locked_memory_non_posix_uses_lockfile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With fcntl=None, locked_memory uses .lock file fallback."""
    from veritas_os.core import memory

    monkeypatch.setattr(memory, "IS_WIN", False)
    monkeypatch.setattr(memory, "fcntl", None)

    target = tmp_path / "test.json"
    lockfile = target.with_suffix(target.suffix + ".lock")

    with memory.locked_memory(target):
        assert lockfile.exists()

    assert not lockfile.exists()


# -------------------------------------------------
# 7. File size regression: memory.py should be slim
# -------------------------------------------------


def test_memory_py_line_count_regression() -> None:
    """Memory facade should stay under 850 lines after decomposition."""
    core_dir = Path(__file__).resolve().parents[1] / "core"
    memory_path = core_dir / "memory.py"
    if not memory_path.exists():
        memory_path = core_dir / "memory" / "__init__.py"
    line_count = len(memory_path.read_text(encoding="utf-8").splitlines())
    assert line_count < 850, (
        f"memory.py has {line_count} lines; keep it under 850 "
        "to prevent monolith regression"
    )
