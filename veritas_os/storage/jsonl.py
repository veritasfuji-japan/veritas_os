"""JSONL-based TrustLog backend implementation."""

from __future__ import annotations

from typing import Any, AsyncIterator, Dict, Optional

from veritas_os.logging import trust_log


class JsonlTrustLogStore:
    """File-backed TrustLog store based on existing trust_log module logic.

    Hash-chain and encryption behavior remain encapsulated in the underlying
    TrustLog implementation to preserve existing security guarantees.
    """

    async def append(self, entry: Dict[str, Any]) -> str:
        saved = trust_log.append_trust_log(entry)
        request_id = str(saved.get("request_id") or saved.get("sha256") or "")
        return request_id

    async def get_by_id(self, request_id: str) -> Optional[Dict[str, Any]]:
        return trust_log.get_trust_log_entry(request_id)

    async def iter_entries(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> AsyncIterator[Dict[str, Any]]:
        if limit <= 0:
            return

        items = trust_log.load_trust_log(limit=None)
        selected = items[offset:offset + limit]
        for entry in selected:
            yield entry

    async def get_last_hash(self) -> Optional[str]:
        return trust_log.get_last_hash()
