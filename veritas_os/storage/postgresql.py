"""PostgreSQL backends for MemoryOS and TrustLog.

MemoryOS backend (``PostgresMemoryStore``) is fully implemented and
backed by the ``memory_records`` table created in the 0001 Alembic
migration.  TrustLog backend remains a stub for v2.1.

All connections are obtained from the shared pool in
``veritas_os.storage.db``.
"""

from __future__ import annotations

import logging
import os
from typing import Any, AsyncIterator, Dict, List, Optional

logger = logging.getLogger(__name__)


class _PostgresBase:
    """Shared PostgreSQL backend base."""

    def __init__(self) -> None:
        self.database_url = os.getenv("VERITAS_DATABASE_URL", "")


class PostgresTrustLogStore(_PostgresBase):
    """PostgreSQL TrustLog backend (planned for v2.1)."""

    async def append(self, entry: Dict[str, Any]) -> str:
        raise NotImplementedError("PostgreSQL TrustLog backend is planned for v2.1")

    async def get_by_id(self, request_id: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError("PostgreSQL TrustLog backend is planned for v2.1")

    async def iter_entries(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> AsyncIterator[Dict[str, Any]]:
        # The yield makes Python treat this as an async generator so that
        # callers can use ``async for``.  The raise executes first.
        raise NotImplementedError("PostgreSQL TrustLog backend is planned for v2.1")
        yield  # type: ignore[misc]  # unreachable; satisfies async-generator requirement

    async def get_last_hash(self) -> Optional[str]:
        raise NotImplementedError("PostgreSQL TrustLog backend is planned for v2.1")


class PostgresMemoryStore(_PostgresBase):
    """PostgreSQL MemoryOS backend using the shared async connection pool.

    Backed by the ``memory_records`` table (see ``alembic/versions/0001``):

    ======== ============ ==========================================
    Column   Type         Notes
    ======== ============ ==========================================
    id       BIGSERIAL    auto-increment PK (insertion order)
    key      TEXT         record key (unique with user_id)
    user_id  TEXT         owner
    value    JSONB        payload (text/tags/kind/meta …)
    metadata JSONB        reserved for provenance / witness fields
    created_at TIMESTAMPTZ server-side ``now()``
    updated_at TIMESTAMPTZ updated on upsert
    ======== ============ ==========================================

    Search implementation
    ---------------------
    Uses ``LIKE ANY(…)`` with token patterns on the ``value->>'text'``
    and ``value->>'query'`` JSONB fields.  The existing GIN index on
    ``value`` accelerates containment queries; full-text ranking is
    computed in Python using the same ``_simple_score`` algorithm as the
    JSON backend to guarantee search-result parity.

    Upgrading to pgvector in a future PR requires only adding an
    ``embedding`` column + index; the search method signature stays the
    same.
    """

    # ------------------------------------------------------------------ pool

    async def _get_pool(self):
        """Obtain the process-wide connection pool.

        Raises
        ------
        RuntimeError
            When psycopg is not installed or the pool cannot be created.
        """
        from veritas_os.storage.db import get_pool

        try:
            return await get_pool()
        except Exception as exc:
            raise RuntimeError(
                f"PostgreSQL connection pool unavailable: {exc}"
            ) from exc

    # ------------------------------------------------------------------ put

    async def put(
        self,
        key: str,
        value: Dict[str, Any],
        *,
        user_id: str,
    ) -> None:
        """Store *value* under *key* for *user_id* (upsert semantics).

        Uses ``ON CONFLICT … DO UPDATE`` on the ``(key, user_id)``
        unique constraint so that repeated puts overwrite cleanly.
        """
        from psycopg.types.json import Jsonb

        pool = await self._get_pool()
        async with pool.connection() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO memory_records (key, user_id, value,
                                                created_at, updated_at)
                    VALUES (%s, %s, %s, now(), now())
                    ON CONFLICT ON CONSTRAINT uq_memory_records_key_user
                    DO UPDATE SET value      = EXCLUDED.value,
                                  updated_at = now()
                    """,
                    (key, user_id, Jsonb(value)),
                )

    # ------------------------------------------------------------------ get

    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Return the value stored under *key*, or ``None``.

        When multiple users share the same key the earliest-inserted
        record wins (``ORDER BY id LIMIT 1``), matching the linear-scan
        behaviour of the JSON backend.
        """
        pool = await self._get_pool()
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT value FROM memory_records"
                " WHERE key = %s ORDER BY id LIMIT 1",
                (key,),
            )
            row = await cur.fetchone()
            if row is None:
                return None
            val = row[0]
            return val if isinstance(val, dict) else None

    # --------------------------------------------------------- text extraction

    @staticmethod
    def _extract_searchable_text(val: Dict[str, Any]) -> str:
        """Return the searchable text from a JSONB value dict.

        Checks ``text`` first, then ``query`` — matching the field
        priority used in both the SQL ``WHERE`` clause and the
        Python-side scoring loop.
        """
        return str(val.get("text") or val.get("query") or "").strip()

    # ---------------------------------------------------------------- search

    async def search(
        self,
        query: str,
        *,
        user_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Return up to *limit* records matching *query* for *user_id*.

        Filtering is done server-side via ``LIKE ANY(…)`` on JSONB text
        fields; scoring uses the same ``_simple_score`` algorithm as the
        JSON backend to guarantee ranking parity.
        """
        query_str = (query or "").strip()
        if not query_str:
            return []
        if limit <= 0:
            return []

        tokens = query_str.lower().split()
        patterns = [f"%{t}%" for t in tokens if t]
        if not patterns:
            return []

        pool = await self._get_pool()
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT key, user_id, value,
                       EXTRACT(EPOCH FROM created_at) AS ts
                FROM memory_records
                WHERE user_id = %s
                  AND (
                      LOWER(COALESCE(value ->> 'text',  '')) LIKE ANY(%s)
                   OR LOWER(COALESCE(value ->> 'query', '')) LIKE ANY(%s)
                  )
                ORDER BY id
                """,
                (user_id, patterns, patterns),
            )
            rows = await cur.fetchall()

        results: List[Dict[str, Any]] = []
        for row_key, row_uid, row_val, row_ts in rows:
            val = row_val if isinstance(row_val, dict) else {}
            text = self._extract_searchable_text(val)
            if not text:
                continue
            score = self._simple_score(query_str, text)
            if score <= 0.0:
                continue
            tags = val.get("tags") or []
            kind = val.get("kind", "episodic")
            ts = float(row_ts) if row_ts is not None else None
            results.append(
                {
                    "id": row_key,
                    "text": text,
                    "score": float(score),
                    "tags": tags,
                    "ts": ts,
                    "meta": {
                        "user_id": row_uid,
                        "created_at": ts,
                        "kind": kind,
                    },
                }
            )

        results.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        return results[:limit]

    # -------------------------------------------------------------- scoring

    @staticmethod
    def _simple_score(query: str, text: str) -> float:
        """Score text relevance using substring + token overlap.

        Mirrors ``MemoryStore._simple_score`` in
        ``veritas_os/core/memory/memory_store.py`` so that search
        ranking is backend-independent.
        """
        q = (query or "").strip().lower()
        t = (text or "").strip().lower()
        if not q or not t:
            return 0.0

        base = 0.5 if q in t else (0.5 if t in q else 0.0)

        q_tokens = set(q.split())
        t_tokens = set(t.split())
        if q_tokens and t_tokens:
            inter = q_tokens & t_tokens
            token_score = len(inter) / max(len(q_tokens), 1)
        else:
            token_score = 0.0

        return min(1.0, base + 0.5 * token_score)

    # ---------------------------------------------------------------- delete

    async def delete(self, key: str, *, user_id: str) -> bool:
        """Delete the record for *key*/*user_id*; return whether it existed."""
        pool = await self._get_pool()
        async with pool.connection() as conn:
            async with conn.transaction():
                cur = await conn.execute(
                    "DELETE FROM memory_records"
                    " WHERE key = %s AND user_id = %s",
                    (key, user_id),
                )
                return cur.rowcount > 0

    # -------------------------------------------------------------- list_all

    async def list_all(self, *, user_id: str) -> List[Dict[str, Any]]:
        """Return all records for *user_id* in insertion order."""
        pool = await self._get_pool()
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT key, user_id, value,
                       EXTRACT(EPOCH FROM created_at) AS ts
                FROM memory_records
                WHERE user_id = %s
                ORDER BY id
                """,
                (user_id,),
            )
            rows = await cur.fetchall()

        return [
            {
                "key": row_key,
                "user_id": row_uid,
                "value": row_val if isinstance(row_val, dict) else {},
                "ts": float(row_ts) if row_ts is not None else None,
            }
            for row_key, row_uid, row_val, row_ts in rows
        ]

    # -------------------------------------------------------- erase_user_data

    async def erase_user_data(self, user_id: str) -> int:
        """Erase **all** records for *user_id* and return the delete count."""
        pool = await self._get_pool()
        async with pool.connection() as conn:
            async with conn.transaction():
                cur = await conn.execute(
                    "DELETE FROM memory_records WHERE user_id = %s",
                    (user_id,),
                )
                return cur.rowcount
