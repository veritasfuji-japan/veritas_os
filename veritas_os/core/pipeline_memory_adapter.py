# veritas_os/core/pipeline_memory_adapter.py
# -*- coding: utf-8 -*-
"""
Pipeline メモリストアアダプタ。

mem.search / mem.MEM.search など複数の MemoryOS インターフェイスの差異を吸収し、
統一した API を提供する。

pipeline.py の module-level 定義をここに移動した。
"""
from __future__ import annotations

import inspect
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---- memory (RECOMMENDED) ----
try:
    from . import memory as _mem_module  # type: ignore
except Exception as e:  # pragma: no cover
    _mem_module = None  # type: ignore
    logger.warning("[pipeline_memory_adapter] memory import failed: %s", repr(e))


# =========================================================
# メモリストア取得
# =========================================================

def _get_memory_store(mem: Any = None) -> Optional[Any]:
    """
    MemoryOS ストアオブジェクトを返す。

    Args:
        mem: 外部から渡す memory モジュール（省略時はモジュール変数を使用）

    Returns:
        store オブジェクト、または None
    """
    m = mem if mem is not None else _mem_module
    if m is None:
        return None
    if hasattr(m, "search") or hasattr(m, "put") or hasattr(m, "get"):
        return m
    store = getattr(m, "MEM", None)
    if store is not None:
        return store
    return None


# =========================================================
# 関数呼び出しアダプタ
# =========================================================

def _call_with_accepted_kwargs(fn: Any, kwargs: Dict[str, Any]) -> Any:
    """
    inspect で受け取れる kwargs だけ渡す（put/search/add_usage などのシグネチャ差異を吸収）。
    """
    try:
        sig = inspect.signature(fn)
        accepted = set(sig.parameters.keys())
        filtered = {k: v for k, v in kwargs.items() if k in accepted}
        return fn(**filtered)
    except Exception:
        return fn(**kwargs)


def _memory_has(store: Any, name: str) -> bool:
    """store が name という callable を持つか確認する。"""
    try:
        return callable(getattr(store, name))
    except Exception:
        return False


# =========================================================
# メモリ検索
# =========================================================

def _memory_search(store: Any, **kwargs: Any) -> Any:
    """
    store.search をシグネチャ差異を吸収しつつ呼び出す（ベストエフォート）。
    """
    if not _memory_has(store, "search"):
        raise RuntimeError("memory.search not available")

    fn = getattr(store, "search")

    try:
        return _call_with_accepted_kwargs(fn, dict(kwargs))
    except TypeError:
        pass

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


# =========================================================
# メモリ書き込み
# =========================================================

def _memory_put(store: Any, user_id: Any, *, key: str, value: Any, meta: Any = None) -> None:
    """store.put を複数シグネチャで試みる（ベストエフォート）。"""
    if not _memory_has(store, "put"):
        return None
    fn = getattr(store, "put")

    try:
        _call_with_accepted_kwargs(
            fn,
            {"user_id": user_id, "key": key, "value": value, "meta": meta},
        )
        return None
    except Exception:
        pass

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
    """store.add_usage を複数シグネチャで試みる（ベストエフォート）。"""
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


__all__ = [
    "_get_memory_store",
    "_call_with_accepted_kwargs",
    "_memory_has",
    "_memory_search",
    "_memory_put",
    "_memory_add_usage",
]
