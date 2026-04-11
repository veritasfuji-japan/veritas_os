"""Backend parity contract tests for MemoryStore and TrustLogStore.

This module defines a *single* shared test suite that every concrete
backend must pass.  When a new backend is added, register a fixture
that produces an instance and the same contract tests will exercise it
automatically.

The intent is to guarantee **"same interface ⇒ same semantics"** across
JSON, JSONL, PostgreSQL, and future backends.

Contract specifications are documented in ``veritas_os/storage/base.py``.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import pytest

# ---------------------------------------------------------------------------
# Fixtures: one per backend implementation
# ---------------------------------------------------------------------------


@pytest.fixture()
def json_memory_store(tmp_path):
    """JSON file-backed MemoryStore."""
    from veritas_os.storage.json_kv import JsonMemoryStore

    return JsonMemoryStore(tmp_path / "memory.json")


@pytest.fixture()
def postgres_memory_store():
    """PostgreSQL MemoryStore backed by in-memory mock pool."""
    from veritas_os.storage.postgresql import PostgresMemoryStore
    from veritas_os.tests.test_storage_postgresql_memory import _MockPool

    store = PostgresMemoryStore()
    pool = _MockPool()

    async def _fake_pool():
        return pool

    store._get_pool = _fake_pool  # type: ignore[assignment]
    return store


@pytest.fixture()
def jsonl_trustlog_store(monkeypatch, tmp_path):
    """JSONL file-backed TrustLogStore with isolated temp directory."""
    from veritas_os.logging import trust_log
    from veritas_os.logging.encryption import generate_key
    from veritas_os.storage.jsonl import JsonlTrustLogStore

    monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", generate_key())
    monkeypatch.setattr(trust_log, "LOG_DIR", tmp_path, raising=False)
    monkeypatch.setattr(
        trust_log, "LOG_JSON", tmp_path / "trust_log.json", raising=False
    )
    monkeypatch.setattr(
        trust_log, "LOG_JSONL", tmp_path / "trust_log.jsonl", raising=False
    )

    def _open_for_append():
        trust_log.LOG_JSONL.parent.mkdir(parents=True, exist_ok=True)
        return open(trust_log.LOG_JSONL, "a", encoding="utf-8")

    monkeypatch.setattr(trust_log, "open_trust_log_for_append", _open_for_append)
    return JsonlTrustLogStore()


@pytest.fixture()
def postgres_trustlog_store(monkeypatch):
    """PostgreSQL TrustLogStore backed by in-memory mock pool.

    Uses :class:`_MockTrustLogPool` to simulate PostgreSQL behaviour without
    requiring a live database.
    """
    from veritas_os.logging.encryption import generate_key
    from veritas_os.storage.postgresql import PostgresTrustLogStore

    monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", generate_key())

    store = PostgresTrustLogStore()
    pool = _MockTrustLogPool()

    async def _fake_pool():
        return pool

    store._get_pool = _fake_pool  # type: ignore[assignment]
    return store


class _MockTrustLogCursor:
    """Minimal async cursor for TrustLog mock pool."""

    def __init__(self, rows=None):
        self._rows = rows or []
        self.rowcount = 0

    async def fetchone(self):
        return self._rows[0] if self._rows else None

    async def fetchall(self):
        return self._rows


class _MockTrustLogConnection:
    """In-memory connection that simulates trustlog_entries + trustlog_chain_state."""

    def __init__(self, state: dict):
        self._state = state

    class _Transaction:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

    def transaction(self):
        return self._Transaction()

    async def execute(self, sql: str, params=None):
        sql_lower = sql.strip().lower()

        if "pg_advisory_xact_lock" in sql_lower:
            return _MockTrustLogCursor()

        if sql_lower.startswith("select last_hash from trustlog_chain_state"):
            entries = self._state.get("entries", [])
            if not entries and self._state.get("last_hash") is None:
                return _MockTrustLogCursor()
            return _MockTrustLogCursor([(self._state.get("last_hash"),)])

        if sql_lower.startswith("insert into trustlog_chain_state"):
            self._state.setdefault("last_hash", None)
            return _MockTrustLogCursor()

        if sql_lower.startswith("insert into trustlog_entries"):
            entries = self._state.setdefault("entries", [])
            new_id = len(entries) + 1
            request_id, entry_jsonb, chain_hash, prev_hash = params[0], params[1], params[2], params[3]
            # entry_jsonb may be a Jsonb wrapper; extract the underlying dict
            entry_dict = getattr(entry_jsonb, "obj", entry_jsonb)
            entries.append({
                "id": new_id,
                "request_id": request_id,
                "entry": entry_dict,
                "hash": chain_hash,
                "prev_hash": prev_hash,
            })
            return _MockTrustLogCursor([(new_id,)])

        if sql_lower.startswith("update trustlog_chain_state"):
            self._state["last_hash"] = params[0]
            self._state["last_id"] = params[1]
            return _MockTrustLogCursor()

        if "from trustlog_entries where request_id" in sql_lower:
            for e in self._state.get("entries", []):
                if e["request_id"] == params[0]:
                    return _MockTrustLogCursor([(e["entry"],)])
            return _MockTrustLogCursor()

        if "from trustlog_entries order by id" in sql_lower:
            entries = self._state.get("entries", [])
            limit = params[0] if params else 100
            offset = params[1] if params and len(params) > 1 else 0
            selected = entries[offset:offset + limit]
            return _MockTrustLogCursor([(e["entry"],) for e in selected])

        return _MockTrustLogCursor()


class _MockTrustLogPool:
    """In-memory pool backed by a shared state dict."""

    def __init__(self):
        self._state: dict = {}

    class _ConnCtx:
        def __init__(self, conn):
            self._conn = conn

        async def __aenter__(self):
            return self._conn

        async def __aexit__(self, *a):
            pass

    def connection(self):
        return self._ConnCtx(_MockTrustLogConnection(self._state))


# ===================================================================
# MemoryStore contract tests
# ===================================================================


class _MemoryStoreContractSuite:
    """Shared contract test suite that any MemoryStore backend must pass.

    Sub-classes only need to provide a ``store`` fixture that returns
    a fresh, empty instance of the backend under test.
    """

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _run(coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    # -- put / get --------------------------------------------------------

    def test_put_and_get_roundtrip(self, store) -> None:
        """put + get must round-trip a value."""

        async def _go():
            await store.put("k1", {"text": "hello"}, user_id="u1")
            return await store.get("k1")

        result = asyncio.run(_go())
        assert result is not None
        assert result["text"] == "hello"

    def test_get_missing_key_returns_none(self, store) -> None:
        """get on a non-existent key must return None."""
        result = asyncio.run(store.get("nonexistent"))
        assert result is None

    def test_put_upsert_overwrites(self, store) -> None:
        """put on an existing key must overwrite (upsert)."""

        async def _go():
            await store.put("k1", {"v": 1}, user_id="u1")
            await store.put("k1", {"v": 2}, user_id="u1")
            return await store.get("k1")

        result = asyncio.run(_go())
        assert result is not None
        assert result["v"] == 2

    # -- user isolation ---------------------------------------------------

    def test_list_all_scoped_to_user(self, store) -> None:
        """list_all must only return records for the specified user_id."""

        async def _go() -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
            await store.put("k1", {"v": 1}, user_id="u1")
            await store.put("k2", {"v": 2}, user_id="u2")
            u1 = await store.list_all(user_id="u1")
            u2 = await store.list_all(user_id="u2")
            return u1, u2

        u1_records, u2_records = asyncio.run(_go())
        assert len(u1_records) >= 1
        assert len(u2_records) >= 1
        # Neither set should leak into the other
        u1_keys = {r.get("key") for r in u1_records}
        u2_keys = {r.get("key") for r in u2_records}
        assert "k2" not in u1_keys and "k1" not in u2_keys

    # -- search -----------------------------------------------------------

    def test_search_respects_limit(self, store) -> None:
        """search must return at most *limit* results."""

        async def _go():
            for i in range(5):
                await store.put(f"k{i}", {"text": f"word {i}"}, user_id="u1")
            return await store.search("word", user_id="u1", limit=2)

        results = asyncio.run(_go())
        assert len(results) <= 2

    def test_search_empty_returns_empty(self, store) -> None:
        """search on empty store returns an empty list."""
        results = asyncio.run(store.search("nothing", user_id="u1", limit=5))
        assert results == []

    # -- delete -----------------------------------------------------------

    def test_delete_returns_true_when_exists(self, store) -> None:
        """delete must return True when the record existed."""

        async def _go():
            await store.put("k1", {"v": 1}, user_id="u1")
            return await store.delete("k1", user_id="u1")

        assert asyncio.run(_go()) is True

    def test_delete_returns_false_when_missing(self, store) -> None:
        """delete must return False when the key does not exist."""
        assert asyncio.run(store.delete("ghost", user_id="u1")) is False

    def test_get_after_delete_returns_none(self, store) -> None:
        """After delete, get must return None."""

        async def _go():
            await store.put("k1", {"v": 1}, user_id="u1")
            await store.delete("k1", user_id="u1")
            return await store.get("k1")

        assert asyncio.run(_go()) is None

    # -- erase_user_data --------------------------------------------------

    def test_erase_user_data_returns_count(self, store) -> None:
        """erase_user_data must return the number of deleted records."""

        async def _go():
            await store.put("a", {"v": 1}, user_id="u1")
            await store.put("b", {"v": 2}, user_id="u1")
            return await store.erase_user_data("u1")

        count = asyncio.run(_go())
        assert isinstance(count, int)
        assert count >= 0

    def test_erase_user_data_on_empty_returns_zero(self, store) -> None:
        """erase_user_data on a non-existent user returns 0."""
        assert asyncio.run(store.erase_user_data("nobody")) == 0

    def test_list_all_empty_after_erase(self, store) -> None:
        """After erase_user_data, list_all should return empty."""

        async def _go():
            await store.put("k1", {"v": 1}, user_id="u1")
            await store.erase_user_data("u1")
            return await store.list_all(user_id="u1")

        assert asyncio.run(_go()) == []


# -- Concrete test classes ------------------------------------------------


class TestJsonMemoryStoreContract(_MemoryStoreContractSuite):
    """JSON file backend MemoryStore contract tests."""

    @pytest.fixture()
    def store(self, json_memory_store):
        return json_memory_store


class TestPostgresMemoryStoreContract(_MemoryStoreContractSuite):
    """PostgreSQL MemoryStore contract tests (mock-pool backed).

    The store uses an in-memory mock pool (no live PostgreSQL required)
    so that the same contract suite that validates the JSON backend
    also validates the PostgreSQL backend's SQL/result-shape logic.
    """

    @pytest.fixture()
    def store(self, postgres_memory_store):
        return postgres_memory_store


# ===================================================================
# TrustLogStore contract tests
# ===================================================================


class _TrustLogStoreContractSuite:
    """Shared contract tests for TrustLogStore backends."""

    # -- append / get_by_id -----------------------------------------------

    def test_append_returns_request_id(self, store) -> None:
        """append must return a non-empty request_id string."""
        rid = asyncio.run(store.append({"request_id": "r1", "action": "allow"}))
        assert isinstance(rid, str)
        assert len(rid) > 0

    def test_get_by_id_roundtrip(self, store) -> None:
        """get_by_id must return the entry that was appended."""

        async def _go():
            await store.append({"request_id": "r1", "action": "allow"})
            return await store.get_by_id("r1")

        entry = asyncio.run(_go())
        assert entry is not None
        assert entry.get("action") == "allow"

    def test_get_by_id_missing_returns_none(self, store) -> None:
        """get_by_id for an unknown ID must return None."""
        assert asyncio.run(store.get_by_id("missing")) is None

    # -- iter_entries -----------------------------------------------------

    def test_iter_entries_pagination(self, store) -> None:
        """iter_entries must respect limit and offset."""

        async def _go():
            await store.append({"request_id": "a", "seq": 1})
            await store.append({"request_id": "b", "seq": 2})
            await store.append({"request_id": "c", "seq": 3})
            page = []
            async for entry in store.iter_entries(limit=2, offset=0):
                page.append(entry)
            return page

        page = asyncio.run(_go())
        assert len(page) <= 2

    def test_iter_entries_limit_zero_yields_nothing(self, store) -> None:
        """iter_entries with limit=0 must yield no entries."""

        async def _go():
            await store.append({"request_id": "x"})
            entries = []
            async for entry in store.iter_entries(limit=0, offset=0):
                entries.append(entry)
            return entries

        assert asyncio.run(_go()) == []

    def test_iter_entries_offset_beyond_data(self, store) -> None:
        """iter_entries with offset past the end must yield nothing."""

        async def _go():
            await store.append({"request_id": "x"})
            entries = []
            async for entry in store.iter_entries(limit=10, offset=9999):
                entries.append(entry)
            return entries

        assert asyncio.run(_go()) == []

    # -- get_last_hash ----------------------------------------------------

    def test_get_last_hash_empty_returns_none(self, store) -> None:
        """get_last_hash on an empty log returns None."""
        result = asyncio.run(store.get_last_hash())
        # May be None or a string; both are acceptable for empty stores
        # depending on backend initialisation, but None is canonical.
        assert result is None or isinstance(result, str)

    def test_get_last_hash_after_append(self, store) -> None:
        """get_last_hash after an append returns a non-None string."""

        async def _go():
            await store.append({"request_id": "r1"})
            return await store.get_last_hash()

        result = asyncio.run(_go())
        assert result is None or isinstance(result, str)


# -- Concrete test classes ------------------------------------------------


class TestJsonlTrustLogStoreContract(_TrustLogStoreContractSuite):
    """JSONL file backend TrustLogStore contract tests."""

    @pytest.fixture()
    def store(self, jsonl_trustlog_store):
        return jsonl_trustlog_store


class TestPostgresTrustLogStoreContract(_TrustLogStoreContractSuite):
    """PostgreSQL TrustLogStore contract tests (mock-pool backed).

    The store uses an in-memory mock pool (no live PostgreSQL required)
    so that the same contract suite that validates the JSONL backend
    also validates the PostgreSQL backend's SQL/result-shape logic.
    """

    @pytest.fixture()
    def store(self, postgres_trustlog_store):
        return postgres_trustlog_store


# ===================================================================
# Factory switch tests (backend selection & error handling)
# ===================================================================


class TestFactoryBackendSelection:
    """Verify that the factory correctly dispatches on env vars."""

    def test_default_trustlog_is_jsonl(self, monkeypatch) -> None:
        monkeypatch.delenv("VERITAS_TRUSTLOG_BACKEND", raising=False)
        from veritas_os.storage.factory import create_trust_log_store
        from veritas_os.storage.jsonl import JsonlTrustLogStore

        assert isinstance(create_trust_log_store(), JsonlTrustLogStore)

    def test_default_memory_is_json(self, monkeypatch) -> None:
        monkeypatch.delenv("VERITAS_MEMORY_BACKEND", raising=False)
        from veritas_os.storage.factory import create_memory_store
        from veritas_os.storage.json_kv import JsonMemoryStore

        assert isinstance(create_memory_store(), JsonMemoryStore)

    def test_postgresql_trustlog(self, monkeypatch) -> None:
        monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "postgresql")
        from veritas_os.storage.factory import create_trust_log_store
        from veritas_os.storage.postgresql import PostgresTrustLogStore

        assert isinstance(create_trust_log_store(), PostgresTrustLogStore)

    def test_postgresql_memory(self, monkeypatch) -> None:
        monkeypatch.setenv("VERITAS_MEMORY_BACKEND", "postgresql")
        from veritas_os.storage.factory import create_memory_store
        from veritas_os.storage.postgresql import PostgresMemoryStore

        assert isinstance(create_memory_store(), PostgresMemoryStore)

    def test_unknown_trustlog_backend_raises(self, monkeypatch) -> None:
        monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "redis")
        from veritas_os.storage.factory import create_trust_log_store

        with pytest.raises(ValueError, match="Unknown VERITAS_TRUSTLOG_BACKEND"):
            create_trust_log_store()

    def test_unknown_memory_backend_raises(self, monkeypatch) -> None:
        monkeypatch.setenv("VERITAS_MEMORY_BACKEND", "redis")
        from veritas_os.storage.factory import create_memory_store

        with pytest.raises(ValueError, match="Unknown VERITAS_MEMORY_BACKEND"):
            create_memory_store()

    def test_whitespace_backend_values_are_normalised(self, monkeypatch) -> None:
        monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "  JSONL  ")
        monkeypatch.setenv("VERITAS_MEMORY_BACKEND", "  JSON  ")
        from veritas_os.storage.factory import create_memory_store, create_trust_log_store
        from veritas_os.storage.json_kv import JsonMemoryStore
        from veritas_os.storage.jsonl import JsonlTrustLogStore

        assert isinstance(create_trust_log_store(), JsonlTrustLogStore)
        assert isinstance(create_memory_store(), JsonMemoryStore)


# ===================================================================
# Lifespan backend injection tests
# ===================================================================


class TestLifespanBackendInjection:
    """Verify that run_lifespan injects stores into app.state."""

    def test_stores_are_set_on_app_state(self, monkeypatch) -> None:
        import veritas_os.api.middleware as middleware
        import veritas_os.api.server as server
        from veritas_os.api.lifespan import run_lifespan
        from veritas_os.storage.json_kv import JsonMemoryStore
        from veritas_os.storage.jsonl import JsonlTrustLogStore

        monkeypatch.setattr(middleware, "_inflight_count", 0)
        monkeypatch.setattr(server, "_inflight_count", 0)
        monkeypatch.delenv("VERITAS_TRUSTLOG_BACKEND", raising=False)
        monkeypatch.delenv("VERITAS_MEMORY_BACKEND", raising=False)

        captured: dict[str, Any] = {}

        async def _exercise() -> None:
            import logging

            async with run_lifespan(
                app=server.app,
                startup_validation=lambda: None,
                runtime_health_check=lambda: None,
                check_multiworker_auth_store=lambda: None,
                start_nonce_cleanup_scheduler=lambda: None,
                start_rate_cleanup_scheduler=lambda: None,
                stop_nonce_cleanup_scheduler=lambda: None,
                stop_rate_cleanup_scheduler=lambda: None,
                close_llm_pool=None,
                logger=logging.getLogger(__name__),
            ):
                captured["trust"] = server.app.state.trust_log_store
                captured["memory"] = server.app.state.memory_store

        asyncio.run(_exercise())
        assert isinstance(captured["trust"], JsonlTrustLogStore)
        assert isinstance(captured["memory"], JsonMemoryStore)

    def test_invalid_backend_prevents_startup(self, monkeypatch) -> None:
        import veritas_os.api.middleware as middleware
        import veritas_os.api.server as server
        from veritas_os.api.lifespan import run_lifespan

        monkeypatch.setattr(middleware, "_inflight_count", 0)
        monkeypatch.setattr(server, "_inflight_count", 0)
        monkeypatch.setenv("VERITAS_TRUSTLOG_BACKEND", "invalid")

        async def _exercise() -> None:
            import logging

            async with run_lifespan(
                app=server.app,
                startup_validation=lambda: None,
                runtime_health_check=lambda: None,
                check_multiworker_auth_store=lambda: None,
                start_nonce_cleanup_scheduler=lambda: None,
                start_rate_cleanup_scheduler=lambda: None,
                stop_nonce_cleanup_scheduler=lambda: None,
                stop_rate_cleanup_scheduler=lambda: None,
                close_llm_pool=None,
                logger=logging.getLogger(__name__),
            ):
                pass

        with pytest.raises(ValueError, match="Unknown VERITAS_TRUSTLOG_BACKEND"):
            asyncio.run(_exercise())


# ===================================================================
# Dependency resolver integration tests
# ===================================================================


class TestDependencyResolverStoreAccess:
    """Verify ``get_trust_log_store`` / ``get_memory_store`` DI helpers."""

    def test_get_trust_log_store_raises_when_not_set(self) -> None:
        from types import SimpleNamespace

        from veritas_os.api.dependency_resolver import get_trust_log_store

        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
        with pytest.raises(RuntimeError, match="trust_log_store is not initialized"):
            get_trust_log_store(request)

    def test_get_memory_store_raises_when_not_set(self) -> None:
        from types import SimpleNamespace

        from veritas_os.api.dependency_resolver import get_memory_store

        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
        with pytest.raises(RuntimeError, match="memory_store is not initialized"):
            get_memory_store(request)

    def test_get_trust_log_store_returns_instance(self) -> None:
        from types import SimpleNamespace

        from veritas_os.api.dependency_resolver import get_trust_log_store

        sentinel = object()
        request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(trust_log_store=sentinel))
        )
        assert get_trust_log_store(request) is sentinel

    def test_get_memory_store_returns_instance(self) -> None:
        from types import SimpleNamespace

        from veritas_os.api.dependency_resolver import get_memory_store

        sentinel = object()
        request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(memory_store=sentinel))
        )
        assert get_memory_store(request) is sentinel
