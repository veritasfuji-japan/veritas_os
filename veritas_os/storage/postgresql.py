"""PostgreSQL backends for MemoryOS and TrustLog.

MemoryOS backend (``PostgresMemoryStore``) is fully implemented and
backed by the ``memory_records`` table created in the 0001 Alembic
migration.  TrustLog backend (``PostgresTrustLogStore``) uses the
``trustlog_entries`` and ``trustlog_chain_state`` tables.

Concurrency control
-------------------
``PostgresTrustLogStore.append`` uses **PostgreSQL advisory locks**
(``pg_advisory_xact_lock``) combined with ``SELECT … FOR UPDATE``
on the ``trustlog_chain_state`` singleton row to serialize chain-hash
writes.  This guarantees that:

* Only one transaction at a time can read the previous hash and insert
  the next entry.
* ``hₜ = SHA256(hₜ₋₁ || rₜ)`` is never computed against a stale
  ``hₜ₋₁``.
* Any failure (connection drop, statement timeout, deadlock) rolls
  back the transaction — **fail-closed**.

The advisory lock key ``0x5645524954415301`` is derived from
``b'VERITAS\\x01'`` to avoid collisions with application-level locks.

All connections are obtained from the shared pool in
``veritas_os.storage.db``.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, AsyncIterator, Dict, List, Optional

from veritas_os.logging.trust_log_core import prepare_entry

logger = logging.getLogger(__name__)

# Advisory lock key for TrustLog chain serialization.
# Derived from b'VERITAS\x01' interpreted as a 64-bit integer.
_TRUSTLOG_ADVISORY_LOCK_KEY = 0x5645524954415301


def _jsonb_wrap(obj: Any) -> Any:
    """Wrap *obj* for JSONB insertion.

    Uses ``psycopg.types.json.Jsonb`` when available; falls back to the
    raw dict for test mock pools that don't need the wrapper.
    """
    try:
        from psycopg.types.json import Jsonb
        return Jsonb(obj)
    except ImportError:
        return obj


class _PostgresBase:
    """Shared PostgreSQL backend base."""

    def __init__(self) -> None:
        self.database_url = os.getenv("VERITAS_DATABASE_URL", "")

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


class PostgresTrustLogStore(_PostgresBase):
    """PostgreSQL TrustLog backend with advisory-lock chain serialization.

    Schema (created by Alembic migration ``0001``):

    ============= ============ ==========================================
    Table         Column       Notes
    ============= ============ ==========================================
    trustlog_entries
                  id           BIGSERIAL PK (insertion order)
                  request_id   TEXT UNIQUE NOT NULL
                  entry        JSONB — full redacted+hashed entry
                  hash         TEXT — sha256 chain hash
                  prev_hash    TEXT — sha256_prev
                  metadata     JSONB — reserved
                  created_at   TIMESTAMPTZ server-side now()
    trustlog_chain_state
                  id           INTEGER = 1 (singleton)
                  last_hash    TEXT — latest chain hash
                  last_id      BIGINT — id of latest entry
                  updated_at   TIMESTAMPTZ
    ============= ============ ==========================================

    Concurrency control
    -------------------
    ``append`` acquires a transaction-scoped advisory lock
    (``pg_advisory_xact_lock``) **and** ``SELECT … FOR UPDATE`` on the
    chain-state row.  The lock is released automatically on COMMIT or
    ROLLBACK.
    """

    async def append(self, entry: Dict[str, Any]) -> str:
        """Append *entry* with chain-hash integrity under advisory lock.

        Returns the ``request_id`` of the stored entry.

        Raises
        ------
        RuntimeError
            On any database or infrastructure failure (fail-closed).
        """
        try:
            pool = await self._get_pool()
            async with pool.connection() as conn:
                async with conn.transaction():
                    # ── Serialize: advisory lock + SELECT FOR UPDATE ──
                    await conn.execute(
                        "SELECT pg_advisory_xact_lock(%s)",
                        (_TRUSTLOG_ADVISORY_LOCK_KEY,),
                    )

                    cur = await conn.execute(
                        "SELECT last_hash FROM trustlog_chain_state "
                        "WHERE id = 1 FOR UPDATE"
                    )
                    row = await cur.fetchone()
                    if row is None:
                        # First-ever append: bootstrap the singleton row.
                        await conn.execute(
                            "INSERT INTO trustlog_chain_state (id, last_hash, last_id, updated_at) "
                            "VALUES (1, NULL, NULL, now())"
                        )
                        previous_hash: Optional[str] = None
                    else:
                        previous_hash = row[0]

                    # ── Backend-independent crypto pipeline ──
                    prepared, _encrypted_line = prepare_entry(
                        entry, previous_hash=previous_hash,
                    )

                    request_id = str(
                        prepared.get("request_id")
                        or prepared.get("sha256")
                        or ""
                    )
                    chain_hash = prepared.get("sha256")

                    # ── Persist entry ──
                    entry_jsonb = _jsonb_wrap(prepared)

                    cur = await conn.execute(
                        "INSERT INTO trustlog_entries "
                        "(request_id, entry, hash, prev_hash, created_at) "
                        "VALUES (%s, %s, %s, %s, now()) "
                        "RETURNING id",
                        (
                            request_id,
                            entry_jsonb,
                            chain_hash,
                            previous_hash,
                        ),
                    )
                    new_row = await cur.fetchone()
                    new_id = new_row[0] if new_row else None

                    # ── Update chain state ──
                    await conn.execute(
                        "UPDATE trustlog_chain_state "
                        "SET last_hash = %s, last_id = %s, updated_at = now() "
                        "WHERE id = 1",
                        (chain_hash, new_id),
                    )

            return request_id
        except Exception as exc:
            raise RuntimeError(
                f"PostgreSQL TrustLog append failed (fail-closed): {exc}"
            ) from exc

    async def get_by_id(self, request_id: str) -> Optional[Dict[str, Any]]:
        """Return the entry matching *request_id*, or ``None``."""
        pool = await self._get_pool()
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT entry FROM trustlog_entries WHERE request_id = %s",
                (request_id,),
            )
            row = await cur.fetchone()
            if row is None:
                return None
            val = row[0]
            return val if isinstance(val, dict) else None

    async def iter_entries(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Yield entries in insertion order (oldest first)."""
        if limit <= 0:
            return

        pool = await self._get_pool()
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT entry FROM trustlog_entries ORDER BY id LIMIT %s OFFSET %s",
                (limit, offset),
            )
            rows = await cur.fetchall()

        for (val,) in rows:
            if isinstance(val, dict):
                yield val

    async def get_last_hash(self) -> Optional[str]:
        """Return the chain hash of the newest entry, or ``None``."""
        pool = await self._get_pool()
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT last_hash FROM trustlog_chain_state WHERE id = 1"
            )
            row = await cur.fetchone()
            if row is None:
                return None
            return row[0]

    async def import_entry(
        self,
        entry: Dict[str, Any],
        *,
        dry_run: bool = False,
    ) -> tuple:
        """Import a pre-prepared TrustLog entry preserving original cryptographic hashes.

        Unlike :meth:`append`, this method does **not** call ``prepare_entry``.
        The entry's existing ``sha256`` / ``sha256_prev`` / ``request_id`` values
        are stored verbatim so that a JSONL → PostgreSQL migration preserves the
        original hash chain without recomputing it.

        Duplicate detection is based on ``request_id`` (unique constraint on
        ``trustlog_entries``).  When a matching row already exists the method
        returns ``(request_id, False)`` without performing any write.

        Chain state is updated (via conditional upsert) only when the newly
        inserted row's auto-increment ``id`` is greater than the current
        ``trustlog_chain_state.last_id``.  This makes repeated import runs
        idempotent with respect to chain-state management.

        Args:
            entry: Fully-formed TrustLog entry dict.  Must contain a ``sha256``
                field (or a ``request_id`` field) to serve as the unique key.
            dry_run: When ``True``, only checks for duplicates; no writes are
                performed.

        Returns:
            ``(request_id, was_inserted)`` — ``was_inserted`` is ``False`` for
            duplicates and ``True`` when the entry was written (or *would* be
            written in dry-run mode).

        Raises:
            ValueError: When the entry has no usable ``request_id`` or ``sha256``.
            RuntimeError: On any database or infrastructure failure (fail-closed).
        """
        request_id = str(entry.get("request_id") or entry.get("sha256") or "")
        if not request_id:
            raise ValueError("Entry has no 'request_id' or 'sha256' field")

        try:
            pool = await self._get_pool()
            async with pool.connection() as conn:
                # ── Duplicate check (read-only; no lock needed) ──
                cur = await conn.execute(
                    "SELECT id FROM trustlog_entries WHERE request_id = %s",
                    (request_id,),
                )
                row = await cur.fetchone()
                if row is not None:
                    return request_id, False  # duplicate — skip

                if dry_run:
                    return request_id, True  # would be inserted

                chain_hash = entry.get("sha256")
                prev_hash = entry.get("sha256_prev")

                async with conn.transaction():
                    entry_jsonb = _jsonb_wrap(dict(entry))
                    cur = await conn.execute(
                        "INSERT INTO trustlog_entries "
                        "(request_id, entry, hash, prev_hash, created_at) "
                        "VALUES (%s, %s, %s, %s, now()) "
                        "RETURNING id",
                        (request_id, entry_jsonb, chain_hash, prev_hash),
                    )
                    new_row = await cur.fetchone()
                    new_id = new_row[0] if new_row else None

                    # ── Update chain state (conditional: only advance, never retreat) ──
                    await conn.execute(
                        """
                        INSERT INTO trustlog_chain_state
                            (id, last_hash, last_id, updated_at)
                        VALUES (1, %s, %s, now())
                        ON CONFLICT (id) DO UPDATE
                        SET last_hash  = EXCLUDED.last_hash,
                            last_id    = EXCLUDED.last_id,
                            updated_at = now()
                        WHERE trustlog_chain_state.last_id IS NULL
                           OR trustlog_chain_state.last_id < EXCLUDED.last_id
                        """,
                        (chain_hash, new_id),
                    )

            return request_id, True

        except Exception as exc:
            raise RuntimeError(
                f"PostgreSQL TrustLog import_entry failed (fail-closed): {exc}"
            ) from exc


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

    # -------------------------------------------------------------- import

    async def import_record(
        self,
        key: str,
        value: Dict[str, Any],
        *,
        user_id: str,
        dry_run: bool = False,
    ) -> bool:
        """Import a single memory record, skipping existing ``(key, user_id)`` pairs.

        Unlike :meth:`put`, which uses ``ON CONFLICT … DO UPDATE`` (upsert)
        semantics, this method uses ``ON CONFLICT … DO NOTHING`` so that
        repeated migration runs do not overwrite records that were updated
        after the first pass.

        Args:
            key: Record key.
            value: Record payload dict.
            user_id: Owner identifier.
            dry_run: When ``True``, only checks for an existing record; no
                write is performed.

        Returns:
            ``True`` if the record was inserted (or *would* be in dry-run
            mode), ``False`` if a matching ``(key, user_id)`` already exists.
        """
        pool = await self._get_pool()
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT id FROM memory_records WHERE key = %s AND user_id = %s",
                (key, user_id),
            )
            existing = await cur.fetchone()
            if existing is not None:
                return False  # duplicate — skip

            if dry_run:
                return True  # would be inserted

            from psycopg.types.json import Jsonb  # noqa: PLC0415

            async with conn.transaction():
                cur = await conn.execute(
                    """
                    INSERT INTO memory_records
                        (key, user_id, value, created_at, updated_at)
                    VALUES (%s, %s, %s, now(), now())
                    ON CONFLICT ON CONSTRAINT uq_memory_records_key_user
                    DO NOTHING
                    RETURNING id
                    """,
                    (key, user_id, Jsonb(value)),
                )
                row = await cur.fetchone()
                return row is not None  # True if inserted, False if race-condition duplicate

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
