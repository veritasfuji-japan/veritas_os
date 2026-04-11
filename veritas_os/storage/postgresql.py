"""Planned PostgreSQL backends (stub for v2.1)."""

from __future__ import annotations

import os
from typing import Any, AsyncIterator, Dict, List, Optional


class _PostgresBase:
    """Shared PostgreSQL backend base for future implementation."""

    def __init__(self) -> None:
        self.database_url = os.getenv("VERITAS_DATABASE_URL", "")


class PostgresTrustLogStore(_PostgresBase):
    """PostgreSQL TrustLog backend (planned)."""

    async def append(self, entry: Dict[str, Any]) -> str:
        raise NotImplementedError("PostgreSQL backend is planned for v2.1")

    async def get_by_id(self, request_id: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError("PostgreSQL backend is planned for v2.1")

    async def iter_entries(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> AsyncIterator[Dict[str, Any]]:
        raise NotImplementedError("PostgreSQL backend is planned for v2.1")
        # yield is required so Python treats this as an async generator.
        yield  # type: ignore[misc]  # pragma: no cover

    async def get_last_hash(self) -> Optional[str]:
        raise NotImplementedError("PostgreSQL backend is planned for v2.1")


class PostgresMemoryStore(_PostgresBase):
    """PostgreSQL MemoryOS backend (planned)."""

    async def put(self, key: str, value: Dict[str, Any], *, user_id: str) -> None:
        raise NotImplementedError("PostgreSQL backend is planned for v2.1")

    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError("PostgreSQL backend is planned for v2.1")

    async def search(
        self,
        query: str,
        *,
        user_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        raise NotImplementedError("PostgreSQL backend is planned for v2.1")

    async def delete(self, key: str, *, user_id: str) -> bool:
        raise NotImplementedError("PostgreSQL backend is planned for v2.1")

    async def list_all(self, *, user_id: str) -> List[Dict[str, Any]]:
        raise NotImplementedError("PostgreSQL backend is planned for v2.1")

    async def erase_user_data(self, user_id: str) -> int:
        raise NotImplementedError("PostgreSQL backend is planned for v2.1")
