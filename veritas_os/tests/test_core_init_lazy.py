from __future__ import annotations

import importlib
from types import SimpleNamespace

import veritas_os.core as core_pkg


def test___getattr___loads_and_caches_lazy_export(monkeypatch) -> None:
    """`__getattr__` が遅延ロードし、2回目はキャッシュを返すことを検証する。"""
    calls: list[tuple[str, str]] = []
    fake_mod = SimpleNamespace(name="fake-kernel")

    def fake_import_module(name: str, package: str):
        calls.append((name, package))
        assert name == ".kernel"
        assert package == core_pkg.__name__
        return fake_mod

    monkeypatch.setattr(importlib, "import_module", fake_import_module)
    core_pkg._CACHE.clear()

    loaded_once = core_pkg.__getattr__("veritas_core")
    loaded_twice = core_pkg.__getattr__("veritas_core")

    assert loaded_once is fake_mod
    assert loaded_twice is fake_mod
    assert calls == [(".kernel", core_pkg.__name__)]


def test___getattr___raises_for_unknown_export() -> None:
    """未定義属性では AttributeError を送出する。"""
    core_pkg._CACHE.clear()

    try:
        core_pkg.__getattr__("not_defined")
    except AttributeError as exc:
        assert "not_defined" in str(exc)
    else:
        raise AssertionError("AttributeError was not raised")


def test_try_import_experiments_failure_is_cached(monkeypatch) -> None:
    """実験モジュール読込失敗後は再試行せず None を返す。"""
    call_count = {"n": 0}

    def fake_import_module(name: str, package: str):
        call_count["n"] += 1
        raise RuntimeError("boom")

    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    first = core_pkg.try_import_experiments(force=True)
    second = core_pkg.try_import_experiments()

    assert first is None
    assert second is None
    assert core_pkg.EXPERIMENTS_OK is False
    assert core_pkg.EXPERIMENTS_ATTEMPTED is True
    assert "RuntimeError" in (core_pkg.EXPERIMENTS_IMPORT_ERROR or "")
    assert call_count["n"] == 1


def test_try_import_experiments_force_retries_after_failure(monkeypatch) -> None:
    """`force=True` 指定時は失敗キャッシュをクリアして再試行する。"""
    sequence: list[str] = []
    fake_module = SimpleNamespace(marker="ok")

    def fake_import_module(name: str, package: str):
        sequence.append("called")
        if len(sequence) == 1:
            raise ImportError("first fail")
        return fake_module

    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    first = core_pkg.try_import_experiments(force=True)
    second = core_pkg.try_import_experiments(force=True)

    assert first is None
    assert second is fake_module
    assert core_pkg.experiments is fake_module
    assert core_pkg.EXPERIMENTS_OK is True
    assert core_pkg.EXPERIMENTS_IMPORT_ERROR is None
    assert len(sequence) == 2
