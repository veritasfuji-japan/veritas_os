from __future__ import annotations

import importlib
import threading
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Callable, Optional, Tuple

from fastapi import Request

from veritas_os.storage.base import MemoryStore, TrustLogStore


class SupportsLazyState:
    """Protocol-like structural type for lazy import cache state."""

    obj: Any
    err: Optional[str]
    attempted: bool
    lock: Any


@dataclass
class LazyState:
    """Thread-safe lazy import cache state used by API dependency resolvers."""

    obj: Any = None
    err: Optional[str] = None
    attempted: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)


def resolve_cfg(
    state: SupportsLazyState,
    *,
    errstr: Callable[[Exception], str],
    logger: Any,
) -> Any:
    """Resolve runtime config safely with fallback to a minimal namespace."""
    with state.lock:
        if state.obj is not None:
            return state.obj
        if state.attempted and state.err is not None:
            return state.obj

        state.attempted = True
        try:
            mod = importlib.import_module("veritas_os.core.config")
            cfg = getattr(mod, "cfg")
            state.obj = cfg
            state.err = None
            return cfg
        except Exception as exc:  # pragma: no cover - defensive fallback
            state.err = errstr(exc)
            state.obj = SimpleNamespace(cors_allow_origins=[], api_key="")
            logger.warning("cfg import failed -> fallback: %s", state.err)
            return state.obj


def resolve_decision_pipeline(
    state: SupportsLazyState,
    *,
    errstr: Callable[[Exception], str],
    logger: Any,
) -> Optional[Any]:
    """Resolve decision pipeline lazily; return ``None`` when unavailable."""
    with state.lock:
        if state.obj is not None:
            return state.obj
        if state.attempted and state.err is not None:
            return None

        state.attempted = True
        try:
            pipeline = importlib.import_module("veritas_os.core.pipeline")
            state.obj = pipeline
            state.err = None
            return pipeline
        except Exception as exc:
            state.err = errstr(exc)
            state.obj = None
            logger.warning("decision pipeline import failed: %s", state.err)
            return None


def resolve_fuji_core(
    state: SupportsLazyState,
    *,
    current_fuji_core: Any,
    is_placeholder: Callable[[Any], bool],
    fuji_validate_stub: Any,
    errstr: Callable[[Exception], str],
    logger: Any,
) -> Tuple[Optional[Any], Any]:
    """Resolve Fuji core while preserving monkeypatched test doubles."""
    if not is_placeholder(current_fuji_core):
        return current_fuji_core, current_fuji_core

    if getattr(current_fuji_core, "validate_action", None) is not fuji_validate_stub:
        return current_fuji_core, current_fuji_core
    if getattr(current_fuji_core, "validate", None) is not fuji_validate_stub:
        return current_fuji_core, current_fuji_core

    with state.lock:
        if state.obj is not None:
            return state.obj, state.obj
        if state.attempted and state.err is not None:
            return None, current_fuji_core

        state.attempted = True
        try:
            module = importlib.import_module("veritas_os.core.fuji")
            state.obj = module
            state.err = None
            return module, module
        except Exception as exc:
            state.err = errstr(exc)
            state.obj = None
            logger.warning("fuji_core import failed: %s", state.err)
            return None, current_fuji_core


def resolve_value_core(
    state: SupportsLazyState,
    *,
    current_value_core: Any,
    is_placeholder: Callable[[Any], bool],
    append_trust_log_stub: Any,
    errstr: Callable[[Exception], str],
    logger: Any,
) -> Tuple[Optional[Any], Any]:
    """Resolve value_core lazily while respecting monkeypatched appenders."""
    if is_placeholder(current_value_core):
        if getattr(current_value_core, "append_trust_log", None) is not append_trust_log_stub:
            return current_value_core, current_value_core
    else:
        if hasattr(current_value_core, "append_trust_log"):
            return current_value_core, current_value_core

    with state.lock:
        if state.obj is not None:
            return state.obj, state.obj
        if state.attempted and state.err is not None:
            return None, current_value_core

        state.attempted = True
        try:
            module = importlib.import_module("veritas_os.core.value_core")
            state.obj = module
            state.err = None
            return module, module
        except Exception as exc:
            state.err = errstr(exc)
            state.obj = None
            logger.warning("value_core import failed: %s", state.err)
            return None, current_value_core


def resolve_memory_store(
    state: SupportsLazyState,
    *,
    current_memory_store: Any,
    is_placeholder: Callable[[Any], bool],
    memory_search_stub: Any,
    memory_get_stub: Any,
    errstr: Callable[[Exception], str],
    logger: Any,
) -> Tuple[Optional[Any], Any]:
    """Resolve memory store (MEM or module APIs) with safe fallback semantics."""
    if is_placeholder(current_memory_store):
        if getattr(current_memory_store, "search", None) is not memory_search_stub:
            return current_memory_store, current_memory_store
        if getattr(current_memory_store, "get", None) is not memory_get_stub:
            return current_memory_store, current_memory_store
    else:
        attrs = ("search", "get", "put", "put_episode", "recent", "add_usage")
        if any(hasattr(current_memory_store, attr) for attr in attrs):
            return current_memory_store, current_memory_store

    with state.lock:
        if state.obj is not None:
            return state.obj, state.obj
        if state.attempted and state.err is not None:
            return None, current_memory_store

        state.attempted = True
        try:
            module = importlib.import_module("veritas_os.core.memory")
            store = getattr(module, "MEM", None)
            if store is None:
                if any(hasattr(module, attr) for attr in ("search", "put", "get")):
                    store = module
                else:
                    raise RuntimeError("MEM not found in veritas_os.core.memory")
            state.obj = store
            state.err = None
            return store, store
        except Exception as exc:
            state.err = errstr(exc)
            state.obj = None
            logger.warning("memory store import failed: %s", state.err)
            return None, current_memory_store


def get_trust_log_store(request: Request) -> TrustLogStore:
    """Resolve TrustLogStore instance from FastAPI app state."""
    store = getattr(request.app.state, "trust_log_store", None)
    if store is None:
        raise RuntimeError("trust_log_store is not initialized in app.state")
    return store


def get_memory_store(request: Request) -> MemoryStore:
    """Resolve MemoryStore instance from FastAPI app state."""
    store = getattr(request.app.state, "memory_store", None)
    if store is None:
        raise RuntimeError("memory_store is not initialized in app.state")
    return store
