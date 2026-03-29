# veritas_os/core/memory_store_compat.py
"""
MemoryStore compatibility hooks.

Patches ``MemoryStore`` with methods that bridge through importable module-level
symbols, enabling test-time monkeypatching of core behaviours (file locking,
recent-records filtering, search, etc.).

Extracted from ``memory.py`` so the compat-hook wiring is self-contained and
does not inflate the main module.

Typical usage (called once at ``memory.py`` import time)::

    from .memory_store_compat import install_memory_store_compat_hooks
    install_memory_store_compat_hooks(
        locked_memory_fn=_compat_locked_memory,
        get_mem_vec_fn=_get_mem_vec,
    )
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional
import time
import logging

from .memory_lifecycle import (
    is_record_legal_hold,
    parse_expires_at,
    should_cascade_delete_semantic,
)
from .memory_compliance import erase_user_data
from .memory_store_helpers import (
    build_kvs_search_hits,
    erase_user_records,
    filter_recent_records,
    normalize_document_lifecycle as _normalize_document_lifecycle_impl,
    is_record_expired_compat as _is_record_expired_compat_impl,
    put_episode_record,
    recent_records_compat,
    search_records_compat,
    simple_score as _simple_score_impl,
    summarize_records_for_planner,
)
from .memory_summary_helpers import build_planner_summary
from . import memory_store as _memory_store_module
from .memory_store import (
    ALLOWED_RETENTION_CLASSES,
    DEFAULT_RETENTION_CLASS,
    MemoryStore,
)

logger = logging.getLogger(__name__)

# Capture original function references *before* hook installation so that
# erase_user_records / recent_records_compat / search_records_compat can
# detect whether a test has monkeypatched the module-level helper.
_ORIGINAL_ERASE_USER_DATA = erase_user_data
_ORIGINAL_FILTER_RECENT_RECORDS = filter_recent_records
_ORIGINAL_BUILD_KVS_SEARCH_HITS = build_kvs_search_hits


def install_memory_store_compat_hooks(
    *,
    locked_memory_fn: Callable[..., Any],
    get_mem_vec_fn: Callable[[], Any],
    memory_module: Any,
) -> None:
    """Patch ``MemoryStore`` methods to route through importable symbols.

    Parameters
    ----------
    locked_memory_fn:
        A callable that wraps the authoritative ``locked_memory`` context
        manager exposed by ``memory.py`` (typically ``_compat_locked_memory``).
    get_mem_vec_fn:
        Lazy accessor for the ``MEM_VEC`` singleton (typically
        ``memory._get_mem_vec``).
    memory_module:
        The ``memory`` module object so inner helpers can resolve
        monkeypatched module-level symbols at call time.
    """

    def _parse_expires_at_compat(expires_at: Any) -> Optional[str]:
        return parse_expires_at(expires_at)

    def _normalize_lifecycle_compat(value: Any) -> Any:
        return _normalize_document_lifecycle_impl(
            value,
            default_retention_class=DEFAULT_RETENTION_CLASS,
            allowed_retention_classes=ALLOWED_RETENTION_CLASSES,
            parse_expires_at=MemoryStore._parse_expires_at,
        )

    def _is_record_expired_compat(
        record: Dict[str, Any],
        now_ts: Optional[float] = None,
    ) -> bool:
        return _is_record_expired_compat_impl(
            record,
            parse_expires_at=MemoryStore._parse_expires_at,
            now_ts=now_ts,
        )

    def _erase_user_compat(
        self: MemoryStore,
        user_id: str,
        reason: str,
        actor: str,
    ) -> Dict[str, Any]:
        return erase_user_records(
            store=self,
            helper_module=_memory_store_module,
            original_helper=_ORIGINAL_ERASE_USER_DATA,
            fallback_helper=getattr(memory_module, "erase_user_data", erase_user_data),
            user_id=user_id,
            reason=reason,
            actor=actor,
        )

    def _is_record_legal_hold_compat(record: Dict[str, Any]) -> bool:
        return is_record_legal_hold(record)

    def _should_cascade_delete_semantic_compat(
        record: Dict[str, Any],
        user_id: str,
        erased_keys: set[str],
    ) -> bool:
        return should_cascade_delete_semantic(
            record=record,
            user_id=user_id,
            erased_keys=erased_keys,
        )

    def _recent_compat(
        self: MemoryStore,
        user_id: str,
        limit: int = 20,
        contains: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        return recent_records_compat(
            store=self,
            helper_module=_memory_store_module,
            original_helper=_ORIGINAL_FILTER_RECENT_RECORDS,
            fallback_helper=getattr(
                memory_module, "filter_recent_records", filter_recent_records,
            ),
            user_id=user_id,
            contains=contains,
            limit=limit,
        )

    def _simple_score_compat(self: MemoryStore, query: str, text: str) -> float:
        return _simple_score_impl(query, text)

    def _search_compat(
        self: MemoryStore,
        query: str,
        k: int = 10,
        kinds: Optional[List[str]] = None,
        min_sim: float = 0.0,
        user_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, List[Dict[str, Any]]]:
        episodic = search_records_compat(
            store=self,
            helper_module=_memory_store_module,
            original_helper=_ORIGINAL_BUILD_KVS_SEARCH_HITS,
            fallback_helper=getattr(
                memory_module, "build_kvs_search_hits", build_kvs_search_hits,
            ),
            query=query,
            k=k,
            kinds=kinds,
            min_sim=min_sim,
            user_id=user_id,
        )
        if episodic:
            logger.debug(
                "[MemoryOS][KVS] episodic hits=%d",
                len(episodic.get("episodic") or []),
            )
        return episodic

    def _put_episode_compat(
        self: MemoryStore,
        text: str,
        tags: Optional[List[str]] = None,
        meta: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> str:
        return put_episode_record(
            store=self,
            text=text,
            tags=tags,
            meta=meta,
            mem_vec=get_mem_vec_fn(),
            logger=logger,
            time_module=time,
            **kwargs,
        )

    def _summarize_for_planner_compat(
        self: MemoryStore,
        user_id: str,
        query: str,
        limit: int = 8,
    ) -> str:
        return summarize_records_for_planner(
            store=self,
            user_id=user_id,
            query=query,
            limit=limit,
            build_summary=build_planner_summary,
        )

    # ---- Apply patches ----
    _memory_store_module.locked_memory = locked_memory_fn
    _memory_store_module.erase_user_data = erase_user_data
    _memory_store_module.filter_recent_records = filter_recent_records
    _memory_store_module.build_kvs_search_hits = build_kvs_search_hits
    MemoryStore._parse_expires_at = staticmethod(_parse_expires_at_compat)
    MemoryStore._normalize_lifecycle = staticmethod(_normalize_lifecycle_compat)
    MemoryStore._is_record_expired = staticmethod(_is_record_expired_compat)
    MemoryStore.erase_user = _erase_user_compat
    MemoryStore._is_record_legal_hold = staticmethod(_is_record_legal_hold_compat)
    MemoryStore._should_cascade_delete_semantic = staticmethod(
        _should_cascade_delete_semantic_compat
    )
    MemoryStore.recent = _recent_compat
    MemoryStore._simple_score = _simple_score_compat
    MemoryStore.search = _search_compat
    MemoryStore.put_episode = _put_episode_compat
    MemoryStore.summarize_for_planner = _summarize_for_planner_compat
