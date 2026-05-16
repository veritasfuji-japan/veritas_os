"""Tests for optional governance PostgreSQL dependencies."""

from __future__ import annotations

import builtins
import importlib
import sys
import threading
from pathlib import Path

import pytest


def _block_psycopg_import(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Block psycopg imports and record attempted import names."""
    original_import = builtins.__import__
    attempted: list[str] = []

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "psycopg" or name.startswith("psycopg."):
            attempted.append(name)
            raise ModuleNotFoundError("No module named 'psycopg'")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    return attempted


def _drop_governance_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    """Temporarily drop governance modules so tests can re-import fresh state."""
    for name in [
        "veritas_os.governance",
        "veritas_os.governance.factory",
        "veritas_os.governance.postgresql_repository",
    ]:
        monkeypatch.delitem(sys.modules, name, raising=False)


def test_governance_factory_import_does_not_require_psycopg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempted = _block_psycopg_import(monkeypatch)
    _drop_governance_modules(monkeypatch)

    importlib.import_module("veritas_os.governance.factory")

    assert attempted == []


def test_postgresql_repository_module_import_does_not_require_psycopg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempted = _block_psycopg_import(monkeypatch)
    _drop_governance_modules(monkeypatch)

    importlib.import_module("veritas_os.governance.postgresql_repository")

    assert attempted == []


def test_file_governance_repository_creation_does_not_require_psycopg(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    attempted = _block_psycopg_import(monkeypatch)
    _drop_governance_modules(monkeypatch)
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
    assert attempted == []


def test_postgresql_governance_backend_requires_postgresql_extra_when_psycopg_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    attempted = _block_psycopg_import(monkeypatch)
    _drop_governance_modules(monkeypatch)
    monkeypatch.setenv("VERITAS_GOVERNANCE_BACKEND", "postgresql")
    monkeypatch.setenv("VERITAS_DATABASE_URL", "postgresql://example/example")

    factory = importlib.import_module("veritas_os.governance.factory")

    with pytest.raises(RuntimeError) as exc_info:
        factory.create_governance_repository(
            policy_path=tmp_path / "governance.json",
            history_path=tmp_path / "history.jsonl",
            lock=threading.Lock(),
            policy_history_max=10,
            has_atomic_io=True,
        )
    assert "veritas-os[postgresql]" in str(exc_info.value)
    assert any(name == "psycopg" or name.startswith("psycopg.") for name in attempted)
