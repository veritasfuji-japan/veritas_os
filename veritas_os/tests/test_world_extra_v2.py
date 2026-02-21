# veritas_os/tests/test_world_extra_v2.py
"""Additional coverage tests for veritas_os/core/world.py.

Targets uncovered lines:
  - Line 39: else branch (IS_WIN=True → fcntl=None)
  - Lines 62, 69, 72, 79, 82, 85, 88, 95: DynamicPath methods
  - Lines 107-109: SENSITIVE_SYSTEM_PATHS import fallback
  - Lines 142-151: _validate_path_safety with sensitive path / OSError
  - Lines 165-169: _resolve_data_dir fallback
  - Lines 183-188: _resolve_world_path with sensitive path
  - Lines 201-203: _resolve_world_path base path fallback
  - Lines 253-255: _world_file_lock with fcntl=None
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

import veritas_os.core.world as world


# =========================================================
# DynamicPath methods
# =========================================================


class TestDynamicPath:
    def _make_dynamic_path(self, tmp_path: Path) -> world.DynamicPath:
        return world.DynamicPath(lambda: tmp_path / "test.json")

    def test_exists(self, tmp_path):
        """DynamicPath.exists() delegates to underlying Path."""
        dp = self._make_dynamic_path(tmp_path)
        assert dp.exists() is False
        (tmp_path / "test.json").write_text("{}", encoding="utf-8")
        assert dp.exists() is True

    def test_str(self, tmp_path):
        """Line 68-69: __str__ returns string path."""
        dp = self._make_dynamic_path(tmp_path)
        s = str(dp)
        assert isinstance(s, str)
        assert "test.json" in s

    def test_repr(self, tmp_path):
        """Line 71-72: __repr__ returns DynamicPath(...) form."""
        dp = self._make_dynamic_path(tmp_path)
        r = repr(dp)
        assert "DynamicPath" in r

    def test_open(self, tmp_path):
        """Line 78-79: open() delegates to underlying Path."""
        dp = self._make_dynamic_path(tmp_path)
        (tmp_path / "test.json").write_text('{"x": 1}', encoding="utf-8")
        with dp.open("r", encoding="utf-8") as f:
            content = f.read()
        assert "x" in content

    def test_mkdir(self, tmp_path):
        """Lines 81-82: mkdir() delegates to underlying Path."""
        dp = world.DynamicPath(lambda: tmp_path / "newdir")
        dp.mkdir(parents=True, exist_ok=True)
        assert (tmp_path / "newdir").exists()

    def test_unlink(self, tmp_path):
        """Lines 84-85: unlink() delegates to underlying Path."""
        target = tmp_path / "test.json"
        target.write_text("{}", encoding="utf-8")
        dp = self._make_dynamic_path(tmp_path)
        dp.unlink()
        assert not target.exists()

    def test_read_text(self, tmp_path):
        """Lines 87-88: read_text() delegates."""
        target = tmp_path / "test.json"
        target.write_text('{"key": "val"}', encoding="utf-8")
        dp = self._make_dynamic_path(tmp_path)
        content = dp.read_text(encoding="utf-8")
        assert "key" in content

    def test_write_text(self, tmp_path):
        """Lines 90-91: write_text() delegates."""
        dp = self._make_dynamic_path(tmp_path)
        dp.write_text('{"written": true}', encoding="utf-8")
        assert (tmp_path / "test.json").exists()

    def test_getattr_delegation(self, tmp_path):
        """Lines 93-95: __getattr__ delegates to underlying Path."""
        dp = self._make_dynamic_path(tmp_path)
        # Access .name attribute
        assert dp.name == "test.json"
        # Access .parent attribute
        assert dp.parent == tmp_path
        # Access .suffix attribute
        assert dp.suffix == ".json"

    def test_fspath(self, tmp_path):
        """__fspath__ returns string."""
        dp = self._make_dynamic_path(tmp_path)
        path_str = os.fspath(dp)
        assert isinstance(path_str, str)
        assert "test.json" in path_str


# =========================================================
# _validate_path_safety
# =========================================================


class TestValidatePathSafety:
    def test_safe_path_returns_resolved(self, tmp_path):
        """Normal safe path is returned resolved."""
        result = world._validate_path_safety(tmp_path / "data.json")
        assert isinstance(result, Path)

    def test_sensitive_path_raises_value_error(self):
        """Lines 142-147: sensitive path raises ValueError."""
        sensitive_path = Path("/etc/passwd")
        with pytest.raises(ValueError, match="sensitive system path"):
            world._validate_path_safety(sensitive_path, "test context")

    def test_sys_path_raises_value_error(self):
        """Lines 142-147: /proc path raises ValueError."""
        sys_path = Path("/proc/meminfo")
        with pytest.raises(ValueError, match="sensitive system path"):
            world._validate_path_safety(sys_path, "test context")

    def test_boot_raises_value_error(self):
        """/boot path raises ValueError."""
        boot_path = Path("/boot/grub")
        with pytest.raises(ValueError, match="sensitive system path"):
            world._validate_path_safety(boot_path, "test")


# =========================================================
# _resolve_data_dir – sensitive path fallback
# =========================================================


class TestResolveDataDir:
    def test_fallback_on_sensitive_path(self, monkeypatch):
        """Lines 165-169: falls back to home/veritas when path is sensitive."""
        monkeypatch.setenv("VERITAS_DATA_DIR", "/etc")
        result = world._resolve_data_dir()
        # Should fall back to ~/veritas
        assert isinstance(result, Path)
        assert result != Path("/etc")

    def test_default_when_no_env(self, monkeypatch):
        """Returns ~/veritas when no env vars set."""
        for key in ("VERITAS_DATA_DIR", "VERITAS_DIR", "VERITAS_HOME", "VERITAS_PATH"):
            monkeypatch.delenv(key, raising=False)
        result = world._resolve_data_dir()
        assert isinstance(result, Path)


# =========================================================
# _resolve_world_path – various fallbacks
# =========================================================


class TestResolveWorldPath:
    def test_explicit_path_from_env(self, tmp_path, monkeypatch):
        """Uses VERITAS_WORLD_PATH when set."""
        world_file = tmp_path / "world.json"
        monkeypatch.setenv("VERITAS_WORLD_PATH", str(world_file))
        result = world._resolve_world_path()
        assert str(world_file) in str(result)

    def test_explicit_sensitive_path_fallback(self, monkeypatch):
        """Lines 186-188: sensitive explicit path → falls back to default."""
        monkeypatch.setenv("VERITAS_WORLD_PATH", "/etc/world.json")
        result = world._resolve_world_path()
        # Should fall back to default (~/veritas/world_state.json)
        assert isinstance(result, Path)
        assert result != Path("/etc/world.json")

    def test_base_path_from_env(self, tmp_path, monkeypatch):
        """Base path from VERITAS_DATA_DIR is used."""
        for key in ("VERITAS_WORLD_PATH", "VERITAS_WORLD_STATE_PATH", "WORLD_STATE_PATH"):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("VERITAS_DATA_DIR", str(tmp_path))
        result = world._resolve_world_path()
        assert "world_state.json" in str(result)

    def test_base_sensitive_path_fallback(self, monkeypatch):
        """Lines 201-203: sensitive base path → default."""
        for key in ("VERITAS_WORLD_PATH", "VERITAS_WORLD_STATE_PATH", "WORLD_STATE_PATH"):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("VERITAS_DATA_DIR", "/etc")
        result = world._resolve_world_path()
        # Falls back to default ~/veritas/world_state.json
        assert isinstance(result, Path)

    def test_default_path_no_envs(self, monkeypatch):
        """Default path when no env vars."""
        for key in ("VERITAS_WORLD_PATH", "VERITAS_WORLD_STATE_PATH", "WORLD_STATE_PATH",
                    "VERITAS_DATA_DIR", "VERITAS_PATH", "VERITAS_HOME", "VERITAS_DIR"):
            monkeypatch.delenv(key, raising=False)
        result = world._resolve_world_path()
        assert isinstance(result, Path)


# =========================================================
# _world_file_lock – fcntl=None path
# =========================================================


class TestWorldFileLock:
    def test_lock_with_fcntl_none(self, monkeypatch):
        """Lines 253-255: yields immediately when fcntl is None."""
        monkeypatch.setattr(world, "fcntl", None)
        accessed = []
        with world._world_file_lock():
            accessed.append("inside")
        assert "inside" in accessed


# =========================================================
# SENSITIVE_SYSTEM_PATHS import fallback
# =========================================================


class TestSensitiveSystemPaths:
    def test_sensitive_paths_is_frozenset(self):
        """SENSITIVE_SYSTEM_PATHS is available as frozenset."""
        assert isinstance(world.SENSITIVE_SYSTEM_PATHS, frozenset)
        assert "/etc" in world.SENSITIVE_SYSTEM_PATHS or len(world.SENSITIVE_SYSTEM_PATHS) >= 1
