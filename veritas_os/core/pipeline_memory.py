# veritas_os/core/pipeline_memory.py
# -*- coding: utf-8 -*-
"""
VERITAS Pipeline — Memory adapter layer.

Supports mem.search OR mem.MEM.search interfaces with signature-agnostic
calling conventions (kwargs filtering, positional fallbacks).
"""
from __future__ import annotations

import inspect
from typing import Any, Dict, List, Optional


def _get_memory_store(mem: Any) -> Optional[Any]:
    """Get usable memory store from the memory module."""
    if mem is None:
        return None
    # module-level functions
    if hasattr(mem, "search") or hasattr(mem, "put") or hasattr(mem, "get"):
        return mem
    # store object
    store = getattr(mem, "MEM", None)
    if store is not None:
        return store
    return None


def _call_with_accepted_kwargs(fn, kwargs: Dict[str, Any]) -> Any:
    """inspectで受け取れるkwargsだけ渡す（put/search/add_usageなどの差異吸収）"""
    try:
        sig = inspect.signature(fn)
        accepted = set(sig.parameters.keys())
        filtered = {k: v for k, v in kwargs.items() if k in accepted}
        return fn(**filtered)
    except Exception:
        # signatureが取れない/壊れてる場合はそのまま投げる
        return fn(**kwargs)


def _memory_has(store: Any, name: str) -> bool:
    try:
        return callable(getattr(store, name))
    except Exception:
        return False


def _memory_search(store: Any, **kwargs: Any) -> Any:
    """
    Try best-effort to call store.search with varying signatures.
    """
    if not _memory_has(store, "search"):
        raise RuntimeError("memory.search not available")

    fn = getattr(store, "search")
    # 1) 可能なkwargsだけ渡す
    try:
        return _call_with_accepted_kwargs(fn, dict(kwargs))
    except TypeError:
        pass

    # 2) Minimal fallbacks
    q = kwargs.get("query")
    k = kwargs.get("k", 8)

    try:
        return fn(query=q, k=k)  # type: ignore
    except Exception:
        pass

    try:
        return fn(q, k)  # type: ignore
    except Exception:
        return fn(query=q)  # type: ignore


def _memory_put(store: Any, user_id: Any, *, key: str, value: Any, meta: Any = None) -> None:
    if not _memory_has(store, "put"):
        return None
    fn = getattr(store, "put")
    # 1) kwargs filtering
    try:
        _call_with_accepted_kwargs(
            fn,
            {"user_id": user_id, "key": key, "value": value, "meta": meta},
        )
        return None
    except Exception:
        pass

    # 2) positional variants
    try:
        fn(user_id, key=key, value=value, meta=meta)  # type: ignore
        return None
    except Exception:
        pass
    try:
        fn(user_id, key, value)  # type: ignore
        return None
    except Exception:
        pass
    try:
        fn(key, value)  # type: ignore
        return None
    except Exception:
        return None


def _memory_add_usage(store: Any, user_id: Any, cited_ids: List[str]) -> None:
    if not _memory_has(store, "add_usage"):
        return None
    fn = getattr(store, "add_usage")
    try:
        _call_with_accepted_kwargs(fn, {"user_id": user_id, "cited_ids": cited_ids})
        return None
    except Exception:
        pass
    try:
        fn(user_id, cited_ids)  # type: ignore
    except Exception:
        return None
