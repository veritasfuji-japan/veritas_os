"""JSON key-value based MemoryOS backend implementation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from veritas_os.core.memory.memory_store import MemoryStore as LegacyMemoryStore


class JsonMemoryStore:
    """MemoryOS store adapter backed by the existing JSON file implementation."""

    def __init__(self, path: Path):
        self._store = LegacyMemoryStore.load(path)

    async def put(self, key: str, value: Dict[str, Any], *, user_id: str) -> None:
        self._store.put(user_id=user_id, key=key, value=value)

    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        records = self._store.list_all()
        for record in records:
            if record.get("key") == key:
                stored = record.get("value")
                return stored if isinstance(stored, dict) else None
        return None

    async def search(
        self,
        query: str,
        *,
        user_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        result = self._store.search(query=query, k=limit, user_id=user_id)
        if isinstance(result, dict):
            return list(result.get("episodic") or [])
        if isinstance(result, list):
            return result
        return []

    async def delete(self, key: str, *, user_id: str) -> bool:
        records = self._store._load_all(copy=True, use_cache=False)
        kept = [
            record for record in records
            if not (
                record.get("user_id") == user_id
                and record.get("key") == key
            )
        ]
        if len(kept) == len(records):
            return False
        return bool(self._store._save_all(kept))

    async def list_all(self, *, user_id: str) -> List[Dict[str, Any]]:
        return self._store.list_all(user_id=user_id)

    async def erase_user_data(self, user_id: str) -> int:
        report = self._store.erase_user(
            user_id=user_id,
            reason="api.erase_user_data",
            actor="storage.json_kv",
        )
        if isinstance(report, dict):
            return int(report.get("deleted", 0))
        return 0
