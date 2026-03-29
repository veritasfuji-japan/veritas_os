from __future__ import annotations

import asyncio
from typing import Any, Dict

from veritas_os.storage.base import MemoryStore, TrustLogStore
from veritas_os.storage.json_kv import JsonMemoryStore
from veritas_os.storage.jsonl import JsonlTrustLogStore


def test_jsonl_store_conforms_trustlog_protocol() -> None:
    store: TrustLogStore = JsonlTrustLogStore()
    assert hasattr(store, "append")
    assert hasattr(store, "get_by_id")
    assert hasattr(store, "iter_entries")
    assert hasattr(store, "get_last_hash")


def test_json_memory_store_conforms_memory_protocol(tmp_path) -> None:
    store: MemoryStore = JsonMemoryStore(tmp_path / "memory.json")
    assert hasattr(store, "put")
    assert hasattr(store, "get")
    assert hasattr(store, "search")
    assert hasattr(store, "delete")
    assert hasattr(store, "list_all")
    assert hasattr(store, "erase_user_data")


def test_json_memory_store_basic_async_ops(tmp_path) -> None:
    async def _run() -> Dict[str, Any]:
        store = JsonMemoryStore(tmp_path / "memory.json")
        await store.put("k1", {"text": "hello world"}, user_id="u1")
        loaded = await store.get("k1")
        hits = await store.search("hello", user_id="u1", limit=5)
        return {
            "loaded": loaded,
            "hits": hits,
        }

    result = asyncio.run(_run())
    assert result["loaded"] is not None
    assert result["loaded"].get("text") == "hello world"
    assert len(result["hits"]) == 1
