from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from types import SimpleNamespace

from veritas_os.api import dependency_resolver


@dataclass
class DummyState:
    obj: object = None
    err: str | None = None
    attempted: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)


def _make_state() -> DummyState:
    return DummyState(lock=threading.Lock())


def _errstr(exc: Exception) -> str:
    return str(exc)


def _is_placeholder(obj: object) -> bool:
    return bool(getattr(obj, "__veritas_placeholder__", False))


def test_resolve_cfg_returns_fallback_on_import_error(monkeypatch):
    state = _make_state()

    def _raise(_: str):
        raise RuntimeError("missing")

    monkeypatch.setattr(dependency_resolver.importlib, "import_module", _raise)
    resolved = dependency_resolver.resolve_cfg(
        state,
        errstr=_errstr,
        logger=logging.getLogger(__name__),
    )

    assert resolved.cors_allow_origins == []
    assert resolved.api_key == ""
    assert state.attempted is True
    assert state.err == "missing"


def test_resolve_fuji_core_respects_monkeypatched_placeholder():
    state = _make_state()
    custom = object()
    placeholder = SimpleNamespace(
        __veritas_placeholder__=True,
        validate_action=custom,
        validate=object(),
    )

    resolved, updated = dependency_resolver.resolve_fuji_core(
        state,
        current_fuji_core=placeholder,
        is_placeholder=_is_placeholder,
        fuji_validate_stub=object(),
        errstr=_errstr,
        logger=logging.getLogger(__name__),
    )

    assert resolved is placeholder
    assert updated is placeholder
    assert state.attempted is False


def test_resolve_memory_store_uses_module_when_mem_missing(monkeypatch):
    state = _make_state()
    placeholder = SimpleNamespace(
        __veritas_placeholder__=True,
        search=lambda *_: [],
        get=lambda *_: None,
    )

    module_like_memory = SimpleNamespace(search=lambda *_: [], put=lambda *_: None, get=lambda *_: None)

    def _import(name: str):
        assert name == "veritas_os.core.memory"
        return module_like_memory

    monkeypatch.setattr(dependency_resolver.importlib, "import_module", _import)
    resolved, updated = dependency_resolver.resolve_memory_store(
        state,
        current_memory_store=placeholder,
        is_placeholder=_is_placeholder,
        memory_search_stub=placeholder.search,
        memory_get_stub=placeholder.get,
        errstr=_errstr,
        logger=logging.getLogger(__name__),
    )

    assert resolved is module_like_memory
    assert updated is module_like_memory
    assert state.err is None


def test_lazy_state_defaults_are_thread_safe():
    first = dependency_resolver.LazyState()
    second = dependency_resolver.LazyState()

    assert first.obj is None
    assert first.err is None
    assert first.attempted is False
    assert first.lock is not second.lock
