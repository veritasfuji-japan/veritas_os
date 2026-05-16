"""Tests for optional governance PostgreSQL dependencies."""

from __future__ import annotations

import builtins
import importlib
import sys
import threading
from pathlib import Path

import pytest


def _block_psycopg_import(monkeypatch: pytest.MonkeyPatch) -> None:
    """Block psycopg imports to emulate a core-only installation."""
    original_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "psycopg" or name.startswith("psycopg."):
            raise ModuleNotFoundError("No module named 'psycopg'")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)


def _drop_governance_modules() -> None:
    """Drop governance modules so each test can re-import with fresh state."""
    for name in [
        "veritas_os.governance.factory",
        "veritas_os.governance.postgresql_repository",
    ]:
        sys.modules.pop(name, None)


def test_governance_factory_import_does_not_require_psycopg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _block_psycopg_import(monkeypatch)
    _drop_governance_modules()

    importlib.import_module("veritas_os.governance.factory")

    assert "veritas_os.governance.postgresql_repository" not in sys.modules


def test_postgresql_repository_module_import_does_not_require_psycopg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _block_psycopg_import(monkeypatch)
    _drop_governance_modules()

    importlib.import_module("veritas_os.governance.postgresql_repository")


def test_file_governance_repository_creation_does_not_require_psycopg(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _block_psycopg_import(monkeypatch)
    _drop_governance_modules()
    monkeypatch.setenv("VERITAS_GOVERNANCE_BACKEND", "file")

    factory = importlib.import_module("veritas_os.governance.factory")

    repository = factory.create_governance_repository(
        policy_path=tmp_path / "governance.json",
        history_path=tmp_path / "history.jsonl",
        lock=threading.Lock(),
        policy_history_max=10,
        has_atomic_io=True,
    )

    assert repository.__class__.__name__ == "FileGovernanceRepository"
    assert "veritas_os.governance.postgresql_repository" not in sys.modules


def test_postgresql_governance_backend_requires_postgresql_extra_when_psycopg_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _block_psycopg_import(monkeypatch)
    _drop_governance_modules()
    monkeypatch.setenv("VERITAS_GOVERNANCE_BACKEND", "postgresql")
    monkeypatch.setenv("VERITAS_DATABASE_URL", "postgresql://example/example")

    factory = importlib.import_module("veritas_os.governance.factory")

    with pytest.raises(RuntimeError, match="postgresql"):
        factory.create_governance_repository(
            policy_path=tmp_path / "governance.json",
            history_path=tmp_path / "history.jsonl",
            lock=threading.Lock(),
            policy_history_max=10,
            has_atomic_io=True,
        )
