"""Tests for PostgresMemoryStore — unit, parity, and failure handling.

This module exercises the PostgreSQL MemoryOS backend using an in-memory
mock pool so that tests run without a live PostgreSQL instance.  The
mock faithfully emulates the SQL semantics used by ``PostgresMemoryStore``
(INSERT … ON CONFLICT, SELECT, DELETE, LIKE ANY, EXTRACT(EPOCH …)).

Test categories
---------------
* **Unit / contract**: CRUD, search, user-isolation, edge-cases.
* **Parity**: Same operations on JSON and PostgreSQL backends yield
  semantically equivalent results.
* **Failure**: Pool unavailable → ``RuntimeError``.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, patch

import pytest


# ===================================================================
# In-memory mock pool that emulates psycopg3 async pool behaviour
# ===================================================================


class _MockCursor:
    """Minimal cursor returned by ``_MockConnection.execute``."""

    def __init__(
        self,
        rows: List[Tuple[Any, ...]],
        rowcount: int = 0,
    ) -> None:
        self._rows = rows
        self.rowcount = rowcount

    async def fetchone(self) -> Optional[Tuple[Any, ...]]:
        return self._rows[0] if self._rows else None

    async def fetchall(self) -> List[Tuple[Any, ...]]:
        return list(self._rows)


class _MockConnection:
    """Connection stub that interprets SQL against in-memory storage."""

    def __init__(self, storage: _InMemoryStorage) -> None:
        self._storage = storage

    @asynccontextmanager
    async def transaction(self):
        yield

    async def execute(
        self,
        query: str,
        params: Optional[Tuple[Any, ...]] = None,
    ) -> _MockCursor:
        sql = " ".join(query.split())
        params = params or ()
        return self._storage.dispatch(sql, params)


class _InMemoryStorage:
    """Simulates the ``memory_records`` table in-memory."""

    def __init__(self) -> None:
        self._rows: List[Dict[str, Any]] = []
        self._seq: int = 0

    def dispatch(
        self,
        sql: str,
        params: Tuple[Any, ...],
    ) -> _MockCursor:
        sql_upper = sql.upper().strip()

        if sql_upper.startswith("INSERT"):
            return self._handle_insert(params)
        if sql_upper.startswith("SELECT VALUE FROM"):
            return self._handle_get(params)
        if sql_upper.startswith("SELECT USER_ID, VALUE FROM"):
            return self._handle_get_with_user(params)
        if sql_upper.startswith("SELECT KEY, USER_ID, VALUE,"):
            if "LIKE ANY" in sql_upper:
                return self._handle_search(sql, params)
            return self._handle_list(params)
        if sql_upper.startswith("DELETE"):
            if "AND USER_ID" in sql_upper:
                return self._handle_delete_one(params)
            return self._handle_delete_user(params)

        raise ValueError(f"Unhandled SQL: {sql}")

    def _handle_insert(self, params: Tuple[Any, ...]) -> _MockCursor:
        key, user_id, value_wrapper = params
        # psycopg Jsonb wraps the value; extract .obj if available
        value = getattr(value_wrapper, "obj", value_wrapper)
        if isinstance(value, str):
            value = json.loads(value)

        for row in self._rows:
            if row["key"] == key and row["user_id"] == user_id:
                row["value"] = value
                row["updated_at"] = time.time()
                return _MockCursor([], rowcount=1)

        self._seq += 1
        now = time.time()
        self._rows.append(
            {
                "id": self._seq,
                "key": key,
                "user_id": user_id,
                "value": value,
                "created_at": now,
                "updated_at": now,
            }
        )
        return _MockCursor([], rowcount=1)

    def _handle_get(self, params: Tuple[Any, ...]) -> _MockCursor:
        (key,) = params
        for row in sorted(self._rows, key=lambda r: r["id"]):
            if row["key"] == key:
                return _MockCursor([(row["value"],)])
        return _MockCursor([])

    def _handle_get_with_user(self, params: Tuple[Any, ...]) -> _MockCursor:
        (key,) = params
        result: List[Tuple[Any, ...]] = []
        for row in sorted(self._rows, key=lambda r: r["id"]):
            if row["key"] == key:
                result.append((row["user_id"], row["value"]))
        return _MockCursor(result)

    def _handle_list(self, params: Tuple[Any, ...]) -> _MockCursor:
        (user_id,) = params
        result = []
        for row in sorted(self._rows, key=lambda r: r["id"]):
            if row["user_id"] == user_id:
                result.append(
                    (row["key"], row["user_id"], row["value"], row["created_at"])
                )
        return _MockCursor(result)

    def _handle_search(
        self,
        sql: str,
        params: Tuple[Any, ...],
    ) -> _MockCursor:
        user_id, patterns, patterns2 = params
        result = []
        for row in sorted(self._rows, key=lambda r: r["id"]):
            if row["user_id"] != user_id:
                continue
            val = row["value"] if isinstance(row["value"], dict) else {}
            text_field = str(val.get("text") or "").lower()
            query_field = str(val.get("query") or "").lower()
            matched = False
            for pat in patterns:
                # Convert SQL LIKE pattern to substring check
                substr = pat.strip("%").lower()
                if substr in text_field or substr in query_field:
                    matched = True
                    break
            if matched:
                result.append(
                    (row["key"], row["user_id"], row["value"], row["created_at"])
                )
        return _MockCursor(result)

    def _handle_delete_one(self, params: Tuple[Any, ...]) -> _MockCursor:
        key, user_id = params
        before = len(self._rows)
        self._rows = [
            r
            for r in self._rows
            if not (r["key"] == key and r["user_id"] == user_id)
        ]
        return _MockCursor([], rowcount=before - len(self._rows))

    def _handle_delete_user(self, params: Tuple[Any, ...]) -> _MockCursor:
        (user_id,) = params
        before = len(self._rows)
        self._rows = [r for r in self._rows if r["user_id"] != user_id]
        return _MockCursor([], rowcount=before - len(self._rows))


class _MockPool:
    """Async connection pool backed by in-memory storage."""

    def __init__(self) -> None:
        self._storage = _InMemoryStorage()

    @asynccontextmanager
    async def connection(self):
        yield _MockConnection(self._storage)


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture()
def mock_pool():
    """Return a fresh in-memory mock pool."""
    return _MockPool()


@pytest.fixture()
def pg_memory_store(mock_pool):
    """PostgresMemoryStore wired to the in-memory mock pool."""
    from veritas_os.storage.postgresql import PostgresMemoryStore

    store = PostgresMemoryStore()

    async def _fake_pool():
        return mock_pool

    store._get_pool = _fake_pool  # type: ignore[assignment]
    return store


@pytest.fixture()
def json_memory_store(tmp_path):
    """JSON file-backed MemoryStore for parity comparison."""
    from veritas_os.storage.json_kv import JsonMemoryStore

    return JsonMemoryStore(tmp_path / "memory.json")


# ===================================================================
# PostgresMemoryStore contract tests (mirrors JSON contract suite)
# ===================================================================


class TestPostgresMemoryStoreCRUD:
    """Basic CRUD operations."""

    def test_put_and_get_roundtrip(self, pg_memory_store) -> None:
        async def _go():
            await pg_memory_store.put("k1", {"text": "hello"}, user_id="u1")
            return await pg_memory_store.get("k1")

        result = asyncio.run(_go())
        assert result is not None
        assert result["text"] == "hello"

    def test_get_missing_key_returns_none(self, pg_memory_store) -> None:
        result = asyncio.run(pg_memory_store.get("nonexistent"))
        assert result is None

    def test_put_upsert_overwrites(self, pg_memory_store) -> None:
        async def _go():
            await pg_memory_store.put("k1", {"v": 1}, user_id="u1")
            await pg_memory_store.put("k1", {"v": 2}, user_id="u1")
            return await pg_memory_store.get("k1")

        result = asyncio.run(_go())
        assert result is not None
        assert result["v"] == 2

    def test_put_same_key_different_users(self, pg_memory_store) -> None:
        """Same key for different users should not conflict."""

        async def _go():
            await pg_memory_store.put("k1", {"v": "u1"}, user_id="u1")
            await pg_memory_store.put("k1", {"v": "u2"}, user_id="u2")
            u1 = await pg_memory_store.list_all(user_id="u1")
            u2 = await pg_memory_store.list_all(user_id="u2")
            return u1, u2

        u1_records, u2_records = asyncio.run(_go())
        assert len(u1_records) == 1
        assert len(u2_records) == 1
        assert u1_records[0]["value"]["v"] == "u1"
        assert u2_records[0]["value"]["v"] == "u2"


class TestPostgresMemoryStoreUserIsolation:
    """User-scoped operations must never leak data across users."""

    def test_list_all_scoped_to_user(self, pg_memory_store) -> None:
        async def _go():
            await pg_memory_store.put("k1", {"v": 1}, user_id="u1")
            await pg_memory_store.put("k2", {"v": 2}, user_id="u2")
            u1 = await pg_memory_store.list_all(user_id="u1")
            u2 = await pg_memory_store.list_all(user_id="u2")
            return u1, u2

        u1_records, u2_records = asyncio.run(_go())
        assert len(u1_records) == 1
        assert len(u2_records) == 1
        u1_keys = {r["key"] for r in u1_records}
        u2_keys = {r["key"] for r in u2_records}
        assert "k2" not in u1_keys
        assert "k1" not in u2_keys

    def test_delete_scoped_to_user(self, pg_memory_store) -> None:
        """Delete for user A must not affect user B's record with same key."""

        async def _go():
            await pg_memory_store.put("shared", {"v": "A"}, user_id="uA")
            await pg_memory_store.put("shared", {"v": "B"}, user_id="uB")
            deleted = await pg_memory_store.delete("shared", user_id="uA")
            remaining = await pg_memory_store.list_all(user_id="uB")
            return deleted, remaining

        deleted, remaining = asyncio.run(_go())
        assert deleted is True
        assert len(remaining) == 1
        assert remaining[0]["value"]["v"] == "B"

    def test_erase_user_data_does_not_affect_others(self, pg_memory_store) -> None:
        async def _go():
            await pg_memory_store.put("a", {"v": 1}, user_id="u1")
            await pg_memory_store.put("b", {"v": 2}, user_id="u2")
            count = await pg_memory_store.erase_user_data("u1")
            u2 = await pg_memory_store.list_all(user_id="u2")
            return count, u2

        count, u2_records = asyncio.run(_go())
        assert count == 1
        assert len(u2_records) == 1


class TestPostgresMemoryStoreSearch:
    """Search operations."""

    def test_search_respects_limit(self, pg_memory_store) -> None:
        async def _go():
            for i in range(5):
                await pg_memory_store.put(
                    f"k{i}", {"text": f"word {i}"}, user_id="u1"
                )
            return await pg_memory_store.search("word", user_id="u1", limit=2)

        results = asyncio.run(_go())
        assert len(results) <= 2

    def test_search_empty_returns_empty(self, pg_memory_store) -> None:
        results = asyncio.run(
            pg_memory_store.search("nothing", user_id="u1", limit=5)
        )
        assert results == []

    def test_search_empty_query_returns_empty(self, pg_memory_store) -> None:
        async def _go():
            await pg_memory_store.put("k1", {"text": "hello"}, user_id="u1")
            return await pg_memory_store.search("", user_id="u1")

        assert asyncio.run(_go()) == []

    def test_search_zero_limit_returns_empty(self, pg_memory_store) -> None:
        async def _go():
            await pg_memory_store.put("k1", {"text": "hello"}, user_id="u1")
            return await pg_memory_store.search("hello", user_id="u1", limit=0)

        assert asyncio.run(_go()) == []

    def test_search_returns_matching_records(self, pg_memory_store) -> None:
        async def _go():
            await pg_memory_store.put(
                "k1", {"text": "hello world"}, user_id="u1"
            )
            await pg_memory_store.put(
                "k2", {"text": "goodbye"}, user_id="u1"
            )
            return await pg_memory_store.search("hello", user_id="u1")

        results = asyncio.run(_go())
        assert len(results) >= 1
        assert any(r["id"] == "k1" for r in results)

    def test_search_result_shape(self, pg_memory_store) -> None:
        """Search results must have the expected fields."""

        async def _go():
            await pg_memory_store.put(
                "k1",
                {"text": "foo bar", "tags": ["t1"], "kind": "episodic"},
                user_id="u1",
            )
            return await pg_memory_store.search("foo", user_id="u1")

        results = asyncio.run(_go())
        assert len(results) == 1
        r = results[0]
        assert r["id"] == "k1"
        assert r["text"] == "foo bar"
        assert isinstance(r["score"], float)
        assert r["score"] > 0.0
        assert r["tags"] == ["t1"]
        assert r["meta"]["user_id"] == "u1"
        assert r["meta"]["kind"] == "episodic"

    def test_search_scoped_to_user(self, pg_memory_store) -> None:
        async def _go():
            await pg_memory_store.put(
                "k1", {"text": "shared term"}, user_id="u1"
            )
            await pg_memory_store.put(
                "k2", {"text": "shared term"}, user_id="u2"
            )
            return await pg_memory_store.search("shared", user_id="u1")

        results = asyncio.run(_go())
        assert all(r["meta"]["user_id"] == "u1" for r in results)

    def test_search_matches_query_field(self, pg_memory_store) -> None:
        """Records with 'query' field (instead of 'text') should be found."""

        async def _go():
            await pg_memory_store.put(
                "k1", {"query": "important question"}, user_id="u1"
            )
            return await pg_memory_store.search("important", user_id="u1")

        results = asyncio.run(_go())
        assert len(results) >= 1


class TestPostgresMemoryStoreDelete:
    """Delete operations."""

    def test_delete_returns_true_when_exists(self, pg_memory_store) -> None:
        async def _go():
            await pg_memory_store.put("k1", {"v": 1}, user_id="u1")
            return await pg_memory_store.delete("k1", user_id="u1")

        assert asyncio.run(_go()) is True

    def test_delete_returns_false_when_missing(self, pg_memory_store) -> None:
        assert asyncio.run(
            pg_memory_store.delete("ghost", user_id="u1")
        ) is False

    def test_get_after_delete_returns_none(self, pg_memory_store) -> None:
        async def _go():
            await pg_memory_store.put("k1", {"v": 1}, user_id="u1")
            await pg_memory_store.delete("k1", user_id="u1")
            return await pg_memory_store.get("k1")

        assert asyncio.run(_go()) is None


class TestPostgresMemoryStoreErase:
    """erase_user_data operations."""

    def test_erase_returns_count(self, pg_memory_store) -> None:
        async def _go():
            await pg_memory_store.put("a", {"v": 1}, user_id="u1")
            await pg_memory_store.put("b", {"v": 2}, user_id="u1")
            return await pg_memory_store.erase_user_data("u1")

        count = asyncio.run(_go())
        assert isinstance(count, int)
        assert count == 2

    def test_erase_on_empty_returns_zero(self, pg_memory_store) -> None:
        assert asyncio.run(pg_memory_store.erase_user_data("nobody")) == 0

    def test_list_all_empty_after_erase(self, pg_memory_store) -> None:
        async def _go():
            await pg_memory_store.put("k1", {"v": 1}, user_id="u1")
            await pg_memory_store.erase_user_data("u1")
            return await pg_memory_store.list_all(user_id="u1")

        assert asyncio.run(_go()) == []


class TestPostgresMemoryStoreListAll:
    """list_all ordering and content."""

    def test_list_all_insertion_order(self, pg_memory_store) -> None:
        async def _go():
            await pg_memory_store.put("b", {"v": 2}, user_id="u1")
            await pg_memory_store.put("a", {"v": 1}, user_id="u1")
            await pg_memory_store.put("c", {"v": 3}, user_id="u1")
            return await pg_memory_store.list_all(user_id="u1")

        records = asyncio.run(_go())
        keys = [r["key"] for r in records]
        assert keys == ["b", "a", "c"]

    def test_list_all_record_shape(self, pg_memory_store) -> None:
        async def _go():
            await pg_memory_store.put("k1", {"v": 1}, user_id="u1")
            return await pg_memory_store.list_all(user_id="u1")

        records = asyncio.run(_go())
        assert len(records) == 1
        r = records[0]
        assert r["key"] == "k1"
        assert r["user_id"] == "u1"
        assert r["value"] == {"v": 1}
        assert "ts" in r


# ===================================================================
# Scoring parity test
# ===================================================================


class TestSimpleScoreParity:
    """Verify _simple_score matches JSON backend's scoring logic."""

    def test_exact_match(self) -> None:
        from veritas_os.storage.postgresql import PostgresMemoryStore

        assert PostgresMemoryStore._simple_score("hello", "hello") == 1.0

    def test_substring_match(self) -> None:
        from veritas_os.storage.postgresql import PostgresMemoryStore

        score = PostgresMemoryStore._simple_score("hello", "say hello world")
        assert score > 0.0

    def test_no_match(self) -> None:
        from veritas_os.storage.postgresql import PostgresMemoryStore

        assert PostgresMemoryStore._simple_score("xyz", "abc") == 0.0

    def test_empty_inputs(self) -> None:
        from veritas_os.storage.postgresql import PostgresMemoryStore

        assert PostgresMemoryStore._simple_score("", "text") == 0.0
        assert PostgresMemoryStore._simple_score("query", "") == 0.0

    def test_parity_with_json_backend(self) -> None:
        """Score function must match MemoryStore._simple_score exactly."""
        from veritas_os.core.memory.memory_store_helpers import (
            simple_score as json_simple_score,
        )
        from veritas_os.storage.postgresql import PostgresMemoryStore

        test_cases = [
            ("hello", "hello world"),
            ("foo bar", "the foo is bar"),
            ("test", "testing"),
            ("abc", "xyz"),
            ("multi token query", "this has multi things and token"),
            ("", "text"),
            ("query", ""),
        ]
        for query, text in test_cases:
            json_score = json_simple_score(query, text)
            pg_score = PostgresMemoryStore._simple_score(query, text)
            assert json_score == pg_score, (
                f"Score mismatch for ({query!r}, {text!r}): "
                f"json={json_score}, pg={pg_score}"
            )


# ===================================================================
# JSON ↔ PostgreSQL backend parity tests
# ===================================================================


class TestBackendParity:
    """Run identical operations on both backends; compare results."""

    def test_put_get_parity(self, json_memory_store, pg_memory_store) -> None:
        """Both backends return the same value for get().

        Note: The JSON backend applies lifecycle metadata normalization
        (adds ``meta.retention_class``, ``meta.legal_hold``,
        ``meta.expires_at``) when the value looks like a MemoryOS document
        (has text/kind/tags/meta keys).  The PG backend stores values
        as-is.  For parity, we compare only the fields that were
        explicitly set.
        """

        async def _go(store):
            await store.put("k1", {"v": "hello"}, user_id="u1")
            return await store.get("k1")

        json_val = asyncio.run(_go(json_memory_store))
        pg_val = asyncio.run(_go(pg_memory_store))
        # Non-document values (no text/kind/tags/meta) must be identical
        assert json_val == pg_val

    def test_list_all_parity(
        self, json_memory_store, pg_memory_store
    ) -> None:
        async def _go(store):
            await store.put("k1", {"v": 1}, user_id="u1")
            await store.put("k2", {"v": 2}, user_id="u1")
            records = await store.list_all(user_id="u1")
            return [(r["key"], r["value"]) for r in records]

        json_res = asyncio.run(_go(json_memory_store))
        pg_res = asyncio.run(_go(pg_memory_store))
        assert json_res == pg_res

    def test_delete_parity(
        self, json_memory_store, pg_memory_store
    ) -> None:
        async def _go(store):
            await store.put("k1", {"v": 1}, user_id="u1")
            d1 = await store.delete("k1", user_id="u1")
            d2 = await store.delete("k1", user_id="u1")
            val = await store.get("k1")
            return d1, d2, val

        json_res = asyncio.run(_go(json_memory_store))
        pg_res = asyncio.run(_go(pg_memory_store))
        assert json_res == pg_res

    def test_erase_user_data_parity(
        self, json_memory_store, pg_memory_store
    ) -> None:
        """Both backends erase all user records; list_all returns empty.

        Known parity difference: The JSON backend's ``erase_user_data``
        returns the count from the compliance report's ``deleted_count``
        field, which may be 0 when the value dict has no lifecycle
        metadata.  The PG backend returns the true SQL rowcount.  We
        therefore verify the *effect* (empty list_all) rather than the
        exact count.
        """

        async def _go(store):
            await store.put("a", {"v": 1}, user_id="u1")
            await store.put("b", {"v": 2}, user_id="u1")
            count = await store.erase_user_data("u1")
            remaining = await store.list_all(user_id="u1")
            return count, remaining

        json_count, json_rem = asyncio.run(_go(json_memory_store))
        pg_count, pg_rem = asyncio.run(_go(pg_memory_store))
        # Both must leave no records
        assert json_rem == pg_rem == []
        # PG returns the actual delete count
        assert pg_count == 2

    def test_search_result_ids_parity(
        self, json_memory_store, pg_memory_store
    ) -> None:
        """Search on both backends returns the same matching record IDs.

        Known parity note: The JSON backend iterates *all* records and
        includes those with score == 0.0 (because the check is
        ``score < min_sim`` with ``min_sim=0.0``).  The PG backend
        pre-filters via SQL ``LIKE``, which is inherently stricter and
        excludes completely unrelated records.  We use a query where
        both backends agree on matches (substring / token overlap > 0).
        """

        async def _go(store):
            await store.put(
                "k1", {"text": "hello world"}, user_id="u1"
            )
            await store.put(
                "k2", {"text": "world peace"}, user_id="u1"
            )
            await store.put(
                "k3", {"text": "unrelated xyz"}, user_id="u1"
            )
            results = await store.search("hello world", user_id="u1")
            return sorted(r["id"] for r in results if r.get("score", 0) > 0)

        json_ids = asyncio.run(_go(json_memory_store))
        pg_ids = asyncio.run(_go(pg_memory_store))
        assert json_ids == pg_ids

    def test_user_isolation_parity(
        self, json_memory_store, pg_memory_store
    ) -> None:
        async def _go(store):
            await store.put("k1", {"v": 1}, user_id="u1")
            await store.put("k2", {"v": 2}, user_id="u2")
            u1 = await store.list_all(user_id="u1")
            u2 = await store.list_all(user_id="u2")
            return (
                sorted(r["key"] for r in u1),
                sorted(r["key"] for r in u2),
            )

        json_res = asyncio.run(_go(json_memory_store))
        pg_res = asyncio.run(_go(pg_memory_store))
        assert json_res == pg_res


# ===================================================================
# DB unavailable / failure tests
# ===================================================================


class TestPostgresMemoryStoreFailure:
    """Verify graceful error handling when PostgreSQL is unavailable."""

    def test_pool_unavailable_raises_runtime_error(self) -> None:
        from veritas_os.storage.postgresql import PostgresMemoryStore

        store = PostgresMemoryStore()

        async def _fail_pool():
            raise RuntimeError("PostgreSQL connection pool unavailable: cannot connect")

        store._get_pool = _fail_pool  # type: ignore[assignment]

        with pytest.raises(RuntimeError, match="cannot connect"):
            asyncio.run(store.put("k", {}, user_id="u"))

    def test_get_pool_wraps_errors(self) -> None:
        """_get_pool re-raises as RuntimeError for any pool failure."""
        from veritas_os.storage.postgresql import PostgresMemoryStore

        store = PostgresMemoryStore()

        async def _go():
            with patch(
                "veritas_os.storage.db.get_pool",
                new_callable=AsyncMock,
                side_effect=RuntimeError("psycopg not installed"),
            ):
                await store._get_pool()

        with pytest.raises(RuntimeError, match="psycopg not installed"):
            asyncio.run(_go())

    def test_put_propagates_connection_checkout_failure(self) -> None:
        """put() propagates exceptions raised during pool.connection() checkout."""
        from veritas_os.storage.postgresql import PostgresMemoryStore

        store = PostgresMemoryStore()

        class _FailingPool:
            @asynccontextmanager
            async def connection(self):
                raise ConnectionError("Connection checkout failed: pool exhausted")
                yield  # pragma: no cover

        async def _get_pool():
            return _FailingPool()

        store._get_pool = _get_pool  # type: ignore[assignment]

        with pytest.raises(ConnectionError, match="Connection checkout failed"):
            asyncio.run(store.put("k", {"v": 1}, user_id="u"))

    def test_put_propagates_execute_failure(self) -> None:
        """put() propagates exceptions raised during SQL execution."""
        from veritas_os.storage.postgresql import PostgresMemoryStore

        store = PostgresMemoryStore()

        class _FailingConnection:
            @asynccontextmanager
            async def transaction(self):
                yield

            async def execute(self, query: str, params=None):
                raise RuntimeError("SQL execution error: disk full")

        class _PoolWithFailingConnection:
            @asynccontextmanager
            async def connection(self):
                yield _FailingConnection()

        async def _get_pool():
            return _PoolWithFailingConnection()

        store._get_pool = _get_pool  # type: ignore[assignment]

        with pytest.raises(RuntimeError, match="SQL execution error: disk full"):
            asyncio.run(store.put("k", {"v": 1}, user_id="u"))

    def test_put_propagates_commit_failure_after_execute(self) -> None:
        """put() propagates transaction-exit failure simulating a commit error.

        Ensures SQL execution completes before the transaction-exit exception is raised.
        """
        from veritas_os.storage.postgresql import PostgresMemoryStore

        store = PostgresMemoryStore()
        executed = False

        class _CommitFailingConnection:
            @asynccontextmanager
            async def transaction(self):
                yield
                # Simulate commit-time error after execution inside block finishes
                raise RuntimeError("Simulated transaction commit failure")

            async def execute(self, query: str, params=None):
                nonlocal executed
                executed = True

        class _PoolWithCommitFailingConnection:
            @asynccontextmanager
            async def connection(self):
                yield _CommitFailingConnection()

        async def _get_pool():
            return _PoolWithCommitFailingConnection()

        store._get_pool = _get_pool  # type: ignore[assignment]

        with pytest.raises(RuntimeError, match="Simulated transaction commit failure"):
            asyncio.run(store.put("k", {"v": 1}, user_id="u"))

        assert executed is True, "SQL execute must complete before transaction commit failure occurs"

    def test_put_cancellation_during_sql_execution(self) -> None:
        """Cancellation while awaiting execute() triggers proper context cleanup.

        Verifies that:
        1. pool.connection() and conn.transaction() context managers exit in strict order
           (transaction exits before connection).
        2. Both context managers receive asyncio.CancelledError and do not suppress it.
        3. execute() is called and awaited exactly once with no retries.
        4. Bounded timeouts prevent hangs and a finally block ensures task cleanup on failure.
        """
        from unittest.mock import AsyncMock, MagicMock
        from veritas_os.storage.postgresql import PostgresMemoryStore

        store = PostgresMemoryStore()
        execute_started = asyncio.Event()
        hold_execution = asyncio.Event()
        cleanup_events = []

        async def fake_execute(*args, **kwargs):
            execute_started.set()
            await hold_execution.wait()

        mock_execute = AsyncMock(side_effect=fake_execute)

        class MockTransactionContext:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                cleanup_events.append(("transaction_exit", exc_type))
                return False

        mock_conn = MagicMock()
        mock_conn.execute = mock_execute
        mock_conn.transaction.return_value = MockTransactionContext()

        class MockConnectionContext:
            async def __aenter__(self):
                return mock_conn

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                cleanup_events.append(("connection_exit", exc_type))
                return False

        class MockPool:
            def connection(self):
                return MockConnectionContext()

        async def _get_pool():
            return MockPool()

        store._get_pool = _get_pool  # type: ignore[assignment]

        async def _run_test():
            put_task = asyncio.create_task(
                store.put("cancel_key", {"data": "test"}, user_id="test_user")
            )

            try:
                # Bounded timeout so regressions produce a failure instead of hanging
                await asyncio.wait_for(execute_started.wait(), timeout=2.0)

                # Cancel the task while it is awaiting inside execute()
                put_task.cancel()

                # Bounded wait for cancelled task with shield so timeout propagates directly without waiting on task cancellation
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(asyncio.shield(put_task), timeout=2.0)
            finally:
                # Release hold_execution so execute() does not block indefinitely
                hold_execution.set()
                # Clean up any unfinished task with a bounded wait
                if not put_task.done():
                    put_task.cancel()
                    try:
                        await asyncio.wait_for(
                            asyncio.shield(put_task), timeout=2.0
                        )
                    except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                        pass

        asyncio.run(_run_test())

        # Assert execute was called once and awaited once
        mock_execute.assert_called_once()
        mock_execute.assert_awaited_once()

        # Assert strict context manager cleanup order and cancellation propagation
        assert len(cleanup_events) == 2, f"Expected 2 cleanup events, got {cleanup_events}"
        assert cleanup_events[0] == ("transaction_exit", asyncio.CancelledError)
        assert cleanup_events[1] == ("connection_exit", asyncio.CancelledError)

    def test_put_propagates_transaction_entry_failure(self) -> None:
        """put() propagates exception raised during conn.transaction() __aenter__.

        Verifies that:
        1. pool.connection() is checked out once and its __aexit__ is awaited exactly once,
           receiving the transaction-entry exception without suppressing it.
        2. conn.transaction() is invoked once and its __aenter__ is awaited once.
        3. conn.transaction() __aexit__ is never called because transaction entry failed.
        4. SQL execute() is neither called nor awaited.
        5. The identical exception instance reaches the caller.
        """
        from unittest.mock import AsyncMock, MagicMock
        from veritas_os.storage.postgresql import PostgresMemoryStore

        store = PostgresMemoryStore()
        tx_entry_error = RuntimeError("Simulated transaction entry failure")

        mock_tx_aenter = AsyncMock(side_effect=tx_entry_error)
        mock_tx_aexit = AsyncMock(return_value=False)
        mock_tx_ctx = MagicMock()
        mock_tx_ctx.__aenter__ = mock_tx_aenter
        mock_tx_ctx.__aexit__ = mock_tx_aexit

        mock_execute = AsyncMock()
        mock_conn = MagicMock()
        mock_conn.execute = mock_execute
        mock_transaction_factory = MagicMock(return_value=mock_tx_ctx)
        mock_conn.transaction = mock_transaction_factory

        conn_aexit_calls = []

        class MockConnectionContext:
            async def __aenter__(self):
                return mock_conn

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                conn_aexit_calls.append((exc_type, exc_val, exc_tb))
                return False

        mock_pool = MagicMock()
        mock_pool.connection = MagicMock(return_value=MockConnectionContext())

        async def _get_pool():
            return mock_pool

        store._get_pool = _get_pool  # type: ignore[assignment]

        with pytest.raises(RuntimeError) as exc_info:
            asyncio.run(
                store.put("test_key", {"data": 123}, user_id="test_user")
            )

        # 1. Exactly the same exception instance reaches the caller
        assert exc_info.value is tx_entry_error

        # 2. execute() was neither called nor awaited
        mock_execute.assert_not_called()
        mock_execute.assert_not_awaited()

        # 3. Connection checkout and cleanup
        mock_pool.connection.assert_called_once()
        assert len(conn_aexit_calls) == 1
        assert conn_aexit_calls[0][0] is RuntimeError
        assert conn_aexit_calls[0][1] is tx_entry_error

        # 4. Transaction entered once, but __aexit__ never called
        mock_transaction_factory.assert_called_once_with()
        mock_tx_aenter.assert_awaited_once()
        mock_tx_aexit.assert_not_called()
        mock_tx_aexit.assert_not_awaited()

    def test_put_propagates_connection_exit_failure_after_successful_transaction(self) -> None:
        """put() propagates exception raised during pool.connection() __aexit__

        following a successful transaction-context exit.

        Verifies that:
        1. pool.connection() and conn.transaction() are each invoked once with no SQL retry.
        2. SQL execute() is called and awaited exactly once.
        3. Transaction-context exit completes successfully before connection __aexit__ raises.
        4. Both aexit handlers receive (None, None, None) since no exception occurred
           within their respective context blocks.
        5. Both aexit handlers are awaited exactly once.
        6. The identical connection-exit exception instance reaches the caller.
        """
        from unittest.mock import AsyncMock, MagicMock
        from veritas_os.storage.postgresql import PostgresMemoryStore

        store = PostgresMemoryStore()
        conn_exit_error = RuntimeError("Simulated connection cleanup failure")

        lifecycle_events = []
        tx_aexit_args = []
        conn_aexit_args = []

        # 1. SQL execute mock
        async def fake_execute(*args, **kwargs):
            lifecycle_events.append("execute_done")

        mock_execute = AsyncMock(side_effect=fake_execute)

        # 2. Transaction context manager mock
        async def fake_tx_aenter():
            return None

        async def fake_tx_aexit(exc_type, exc_val, exc_tb):
            tx_aexit_args.append((exc_type, exc_val, exc_tb))
            lifecycle_events.append("tx_exit_done")
            return False

        mock_tx_aenter = AsyncMock(side_effect=fake_tx_aenter)
        mock_tx_aexit = AsyncMock(side_effect=fake_tx_aexit)
        mock_tx_ctx = MagicMock()
        mock_tx_ctx.__aenter__ = mock_tx_aenter
        mock_tx_ctx.__aexit__ = mock_tx_aexit

        mock_conn = MagicMock()
        mock_conn.execute = mock_execute
        mock_transaction_factory = MagicMock(return_value=mock_tx_ctx)
        mock_conn.transaction = mock_transaction_factory

        # 3. Connection context manager mock
        async def fake_conn_aenter():
            return mock_conn

        async def fake_conn_aexit(exc_type, exc_val, exc_tb):
            conn_aexit_args.append((exc_type, exc_val, exc_tb))
            lifecycle_events.append("conn_exit_invoked")
            raise conn_exit_error

        mock_conn_aenter = AsyncMock(side_effect=fake_conn_aenter)
        mock_conn_aexit = AsyncMock(side_effect=fake_conn_aexit)
        mock_conn_ctx = MagicMock()
        mock_conn_ctx.__aenter__ = mock_conn_aenter
        mock_conn_ctx.__aexit__ = mock_conn_aexit

        mock_pool = MagicMock()
        mock_pool.connection = MagicMock(return_value=mock_conn_ctx)

        async def _get_pool():
            return mock_pool

        store._get_pool = _get_pool  # type: ignore[assignment]

        with pytest.raises(RuntimeError) as exc_info:
            asyncio.run(
                store.put("test_key", {"data": 456}, user_id="test_user")
            )

        # 1. The identical connection-exit exception instance reaches the caller
        assert exc_info.value is conn_exit_error

        # 2. execute() was called and awaited exactly once (no retry)
        mock_execute.assert_called_once()
        mock_execute.assert_awaited_once()

        # 3. Single checkout and single transaction creation
        mock_pool.connection.assert_called_once_with()
        mock_transaction_factory.assert_called_once_with()

        # 4. Strict lifecycle ordering: execute completes, transaction-context exits,
        #    then connection __aexit__ is invoked and raises
        assert lifecycle_events == ["execute_done", "tx_exit_done", "conn_exit_invoked"]

        # 5. Both aexit handlers are awaited exactly once
        mock_tx_aexit.assert_awaited_once()
        mock_conn_aexit.assert_awaited_once()

        # 6. Both exit handlers received (None, None, None) as no exception occurred in their blocks
        assert len(tx_aexit_args) == 1
        assert tx_aexit_args[0] == (None, None, None)

        assert len(conn_aexit_args) == 1
        assert conn_aexit_args[0] == (None, None, None)


# ===================================================================
# Backend switch integration test
# ===================================================================


class TestBackendSwitch:
    """Verify factory correctly instantiates both backends."""

    def test_factory_switch_json_to_postgresql(self, monkeypatch) -> None:
        from veritas_os.storage.factory import create_memory_store
        from veritas_os.storage.json_kv import JsonMemoryStore
        from veritas_os.storage.postgresql import PostgresMemoryStore

        monkeypatch.setenv("VERITAS_MEMORY_BACKEND", "json")
        store_json = create_memory_store()
        assert isinstance(store_json, JsonMemoryStore)

        monkeypatch.setenv("VERITAS_MEMORY_BACKEND", "postgresql")
        monkeypatch.setenv("VERITAS_DATABASE_URL", "postgresql://x:x@localhost/x")
        store_pg = create_memory_store()
        assert isinstance(store_pg, PostgresMemoryStore)

    def test_factory_rejects_unknown_backend(self, monkeypatch) -> None:
        from veritas_os.storage.factory import create_memory_store

        monkeypatch.setenv("VERITAS_MEMORY_BACKEND", "mysql")
        with pytest.raises(ValueError, match="Unknown VERITAS_MEMORY_BACKEND"):
            create_memory_store()


# ===================================================================
# Migration startup test
# ===================================================================


class TestMigrationStartup:
    """Verify PostgresMemoryStore can be constructed without a DB."""

    def test_constructor_does_not_require_db(self) -> None:
        """Construction must not connect to the database eagerly."""
        from veritas_os.storage.postgresql import PostgresMemoryStore

        store = PostgresMemoryStore()
        assert store is not None
        # database_url defaults to empty when env var is not set
        assert isinstance(store.database_url, str)
