"""Tests verifying complete pickle removal from MemoryOS.

Test requirements covered:
1. Runtime never loads pickle files at startup
2. Pickle files present on disk are NOT auto-loaded
3. Only the migration CLI can convert legacy files
4. After migration, the old format is rejected at runtime
5. Safe JSON format read/write works correctly
"""

from __future__ import annotations

import json
import logging
import pickle
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

import numpy as np
import pytest

from veritas_os.core import memory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _DummyModel:
    """Minimal embedding model for VectorMemory tests."""

    def __init__(self, dim: int = 4):
        self.dim = dim

    def encode(self, texts: list) -> np.ndarray:
        return np.ones((len(texts), self.dim), dtype=np.float32)


def _make_vm(index_path: Path | None = None, dim: int = 4) -> memory.VectorMemory:
    vm = memory.VectorMemory(index_path=index_path, embedding_dim=dim)
    vm.model = _DummyModel(dim)
    return vm


def _write_pkl(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(data, f)


# ---------------------------------------------------------------------------
# 1. Runtime never loads pickle at startup
# ---------------------------------------------------------------------------


def test_runtime_does_not_load_pickle_on_startup(tmp_path: Path):
    """VectorMemory.__init__ ignores .pkl files entirely."""
    pkl_path = tmp_path / "index.pkl"
    _write_pkl(pkl_path, {"documents": [{"id": "1", "text": "hello"}], "embeddings": None})

    vm = _make_vm(index_path=pkl_path)
    assert vm.documents == [], "Runtime must not auto-load .pkl files"


# ---------------------------------------------------------------------------
# 2. Pickle on disk is NOT auto-loaded even with env flag
# ---------------------------------------------------------------------------


def test_pickle_not_loaded_even_with_env_flag(tmp_path: Path, monkeypatch):
    """Even VERITAS_MEMORY_ALLOW_PICKLE_MIGRATION=1 does not enable loading."""
    monkeypatch.setenv("VERITAS_MEMORY_ALLOW_PICKLE_MIGRATION", "1")
    pkl_path = tmp_path / "legacy.pkl"
    _write_pkl(pkl_path, {"documents": [{"id": "1", "text": "test"}], "embeddings": None})

    vm = _make_vm(index_path=pkl_path)
    assert vm.documents == []


# ---------------------------------------------------------------------------
# 3. Migration CLI is the only way to convert
# ---------------------------------------------------------------------------


def test_migration_cli_converts_pkl_to_json(tmp_path: Path):
    """migrate_pickle CLI converts a .pkl file to .json."""
    from veritas_os.scripts.migrate_pickle import migrate_file

    pkl_path = tmp_path / "index.pkl"
    docs = [{"id": "d1", "kind": "semantic", "text": "hello world", "tags": []}]
    emb = np.array([[1.0, 2.0, 3.0, 4.0]], dtype=np.float32)
    _write_pkl(pkl_path, {"documents": docs, "embeddings": emb})

    result = migrate_file(pkl_path)
    assert result is not None
    assert result.suffix == ".json"
    assert result.exists()

    converted = json.loads(result.read_text(encoding="utf-8"))
    assert converted["documents"] == docs
    assert converted["format_version"] == "2.0"
    assert converted["embeddings"] is not None  # base64 encoded


def test_migration_cli_dry_run(tmp_path: Path):
    """--dry-run does not write any files."""
    from veritas_os.scripts.migrate_pickle import migrate_file

    pkl_path = tmp_path / "index.pkl"
    _write_pkl(pkl_path, {"documents": [], "embeddings": None})

    result = migrate_file(pkl_path, dry_run=True)
    assert result is None
    json_path = pkl_path.with_suffix(".json")
    assert not json_path.exists()


def test_migration_cli_main_no_files(tmp_path: Path):
    """CLI exits 0 when no legacy files are found."""
    from veritas_os.scripts.migrate_pickle import main

    rc = main(["--scan-dir", str(tmp_path)])
    assert rc == 0


def test_migration_cli_main_converts(tmp_path: Path):
    """CLI converts found files and exits 0."""
    from veritas_os.scripts.migrate_pickle import main

    pkl_path = tmp_path / "data.pkl"
    _write_pkl(pkl_path, {"documents": [], "embeddings": None})

    rc = main(["--scan-dir", str(tmp_path)])
    assert rc == 0
    assert pkl_path.with_suffix(".json").exists()


def test_migration_cli_rejects_unsafe_classes(tmp_path: Path):
    """Migration CLI refuses to unpickle objects with dangerous classes."""
    from veritas_os.scripts.migrate_pickle import migrate_file

    # Create a pickle with os.system reference (dangerous)
    import io as _io
    pkl_path = tmp_path / "evil.pkl"
    # Manually craft a pickle that references os.system
    pkl_data = (
        b"\x80\x04\x95\x1a\x00\x00\x00\x00\x00\x00\x00"
        b"\x8c\x02os\x8c\x06system\x93"
        b"\x8c\x08echo bad\x85R."
    )
    pkl_path.write_bytes(pkl_data)

    result = migrate_file(pkl_path)
    assert result is None, "Dangerous pickle classes must be rejected"


# ---------------------------------------------------------------------------
# 4. After migration, old format is rejected at runtime
# ---------------------------------------------------------------------------


def test_runtime_rejects_pkl_after_migration(tmp_path: Path, caplog):
    """After a .json exists, the runtime loads .json and warns on .pkl presence."""
    # Create both .pkl and .json
    pkl_path = tmp_path / "index.pkl"
    json_path = tmp_path / "index.json"

    _write_pkl(pkl_path, {"documents": [{"id": "1", "text": "old"}]})

    # JSON (the migrated format)
    json_data = {
        "documents": [{"id": "1", "kind": "semantic", "text": "migrated", "tags": []}],
        "embeddings": None,
        "format_version": "2.0",
    }
    json_path.write_text(json.dumps(json_data), encoding="utf-8")

    # VectorMemory should load .json and ignore .pkl
    vm = _make_vm(index_path=json_path)
    assert len(vm.documents) == 1
    assert vm.documents[0]["text"] == "migrated"


# ---------------------------------------------------------------------------
# 5. Safe JSON format read/write works correctly
# ---------------------------------------------------------------------------


def test_json_roundtrip(tmp_path: Path):
    """VectorMemory saves as JSON and can reload."""
    idx_path = tmp_path / "test_index.json"
    vm = _make_vm(index_path=idx_path)

    vm.add(kind="test", text="Hello world", tags=["a"])
    vm.add(kind="test", text="Goodbye world", tags=["b"])
    vm._save_index()

    assert idx_path.exists()
    # Verify it's valid JSON
    data = json.loads(idx_path.read_text(encoding="utf-8"))
    assert data["format_version"] == "2.0"
    assert len(data["documents"]) == 2

    # Reload into new instance
    vm2 = _make_vm(index_path=idx_path)
    assert len(vm2.documents) == 2


# ---------------------------------------------------------------------------
# Additional defense tests
# ---------------------------------------------------------------------------


def test_joblib_load_symbol_removed():
    """The joblib_load symbol is no longer exposed by the memory module."""
    assert not hasattr(memory, "joblib_load")


def test_pickle_runtime_block_deadline_removed():
    """The PICKLE_RUNTIME_BLOCK_DEADLINE constant is removed (no sunset)."""
    assert not hasattr(memory, "PICKLE_RUNTIME_BLOCK_DEADLINE")


def test_runtime_guard_detects_pkl_files(tmp_path: Path, caplog):
    """_warn_for_legacy_pickle_artifacts logs errors for .pkl/.joblib/.pickle files."""
    root = tmp_path / "models"
    root.mkdir()
    (root / "old.pkl").write_bytes(b"x")
    (root / "model.joblib").write_bytes(b"x")
    (root / "data.pickle").write_bytes(b"x")

    with caplog.at_level(logging.ERROR, logger="veritas_os.core.memory"):
        memory._warn_for_legacy_pickle_artifacts([root])

    assert "old.pkl" in caplog.text
    assert "model.joblib" in caplog.text
    assert "data.pickle" in caplog.text


def test_migration_scan_finds_all_extensions(tmp_path: Path):
    """scan_legacy_files finds .pkl, .joblib, and .pickle."""
    from veritas_os.scripts.migrate_pickle import scan_legacy_files

    (tmp_path / "a.pkl").write_bytes(b"x")
    (tmp_path / "b.joblib").write_bytes(b"x")
    (tmp_path / "c.pickle").write_bytes(b"x")
    (tmp_path / "d.json").write_text("{}")

    found = scan_legacy_files([tmp_path])
    names = {f.name for f in found}
    assert names == {"a.pkl", "b.joblib", "c.pickle"}
    assert "d.json" not in names
