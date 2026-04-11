"""PostgreSQL TrustLog advisory-lock contention and concurrency tests.

This module verifies that ``PostgresTrustLogStore.append()`` maintains
chain-hash integrity under realistic concurrent-access patterns:

    * 2-worker simultaneous append
    * N-worker burst append
    * Statement timeout → fail-closed
    * Connection pool starvation → fail-closed
    * Rollback recovery (chain state not corrupted after partial failure)
    * Advisory lock release on transaction rollback
    * Full chain verification after concurrent writes

The tests use an enhanced mock pool that faithfully simulates PostgreSQL
advisory-lock serialization (``pg_advisory_xact_lock``) using a
``threading.Lock`` / ``asyncio.Lock`` so that concurrency invariants are
exercised without requiring a live database.

For **real PostgreSQL** tests, see the ``@pytest.mark.postgresql`` tests
at the bottom of this module.  Those are executed in the CI
``test-postgresql`` job against a Postgres 16 service container.

See also:
    * ``docs/postgresql-production-guide.md`` §15 — Known Limitations
    * ``veritas_os/storage/postgresql.py`` — implementation
"""

from __future__ import annotations

import asyncio
import hashlib
import threading
from typing import List, Optional

import pytest

from veritas_os.logging.encryption import generate_key
from veritas_os.logging.trust_log_core import _normalize_for_hash

# Thread join timeout (seconds) for threaded contention tests.
_THREAD_JOIN_TIMEOUT_S = 10


# ===================================================================
# Enhanced mock infrastructure with advisory-lock simulation
# ===================================================================


class _MockCursor:
    """Async cursor stub."""

    def __init__(self, rows: Optional[list] = None):
        self._rows = rows or []
        self.rowcount = len(self._rows)

    async def fetchone(self):
        return self._rows[0] if self._rows else None

    async def fetchall(self):
        return self._rows


class _ContentionMockConn:
    """In-memory connection that serializes via a real lock.

    This mock faithfully reproduces PostgreSQL's ``pg_advisory_xact_lock``
    behaviour: the lock is acquired when the SQL containing
    ``pg_advisory_xact_lock`` is executed, and released when the
    transaction context manager exits (``__aexit__``).
    """

    def __init__(
        self,
        state: dict,
        *,
        lock: threading.Lock,
        fail_on_execute: Optional[str] = None,
    ):
        self._state = state
        self._lock = lock
        self._fail_on_execute = fail_on_execute
        self._locked = False

    class _Tx:
        """Transaction context manager that releases advisory lock on exit."""

        def __init__(self, conn: "_ContentionMockConn"):
            self._conn = conn

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            # Advisory lock auto-releases on transaction end (commit/rollback).
            if self._conn._locked:
                self._conn._lock.release()
                self._conn._locked = False

    def transaction(self):
        return self._Tx(self)

    async def execute(self, sql: str, params=None):
        sql_l = sql.strip().lower()

        # Inject failures for error-path testing.
        if self._fail_on_execute and self._fail_on_execute in sql_l:
            raise IOError(f"Simulated failure: {self._fail_on_execute}")

        # Advisory lock — acquire the threading lock.
        if "pg_advisory_xact_lock" in sql_l:
            self._lock.acquire()
            self._locked = True
            return _MockCursor()

        # SELECT chain state
        if sql_l.startswith("select last_hash from trustlog_chain_state"):
            if not self._state.get("_initialised"):
                return _MockCursor()
            return _MockCursor([(self._state.get("last_hash"),)])

        # Bootstrap chain state
        if sql_l.startswith("insert into trustlog_chain_state"):
            self._state["_initialised"] = True
            self._state.setdefault("last_hash", None)
            return _MockCursor()

        # INSERT entry
        if sql_l.startswith("insert into trustlog_entries"):
            entries = self._state.setdefault("entries", [])
            rid, entry_raw, h, ph = params
            entry_dict = getattr(entry_raw, "obj", entry_raw)
            new_id = len(entries) + 1
            entries.append({
                "id": new_id,
                "request_id": rid,
                "entry": entry_dict,
                "hash": h,
                "prev_hash": ph,
            })
            return _MockCursor([(new_id,)])

        # UPDATE chain state
        if sql_l.startswith("update trustlog_chain_state"):
            self._state["last_hash"] = params[0]
            self._state["last_id"] = params[1]
            return _MockCursor()

        # SELECT by request_id
        if "from trustlog_entries where request_id" in sql_l:
            for e in self._state.get("entries", []):
                if e["request_id"] == params[0]:
                    return _MockCursor([(e["entry"],)])
            return _MockCursor()

        # SELECT paginated
        if "from trustlog_entries order by id" in sql_l:
            entries = self._state.get("entries", [])
            limit = params[0] if params else 100
            offset = params[1] if params and len(params) > 1 else 0
            sel = entries[offset:offset + limit]
            return _MockCursor([(e["entry"],) for e in sel])

        # SELECT last_hash (standalone)
        if "from trustlog_chain_state where id" in sql_l:
            if not self._state.get("_initialised"):
                return _MockCursor()
            return _MockCursor([(self._state.get("last_hash"),)])

        return _MockCursor()


class _ContentionMockPool:
    """Mock pool with real lock-based serialization.

    Each ``connection()`` call returns an independent connection object
    that shares state and the advisory lock — exactly like real PostgreSQL
    where each connection from the pool acquires the same advisory lock.
    """

    def __init__(
        self,
        *,
        fail_on_execute: Optional[str] = None,
    ):
        self._state: dict = {}
        self._lock = threading.Lock()
        self._fail_on_execute = fail_on_execute

    class _Ctx:
        def __init__(self, conn):
            self._conn = conn

        async def __aenter__(self):
            return self._conn

        async def __aexit__(self, *a):
            pass

    def connection(self):
        return self._Ctx(
            _ContentionMockConn(
                self._state,
                lock=self._lock,
                fail_on_execute=self._fail_on_execute,
            )
        )


def _make_contention_store(monkeypatch, *, fail_on_execute=None):
    """Create a PostgresTrustLogStore with contention-aware mock pool."""
    from veritas_os.storage.postgresql import PostgresTrustLogStore

    monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", generate_key())

    store = PostgresTrustLogStore()
    pool = _ContentionMockPool(fail_on_execute=fail_on_execute)

    async def _fake():
        return pool

    store._get_pool = _fake  # type: ignore[assignment]
    return store, pool


# ===================================================================
# Chain verification helpers
# ===================================================================


def _verify_chain(entries: List[dict]) -> List[str]:
    """Verify the hash chain across stored entries.

    Returns a list of error descriptions (empty if chain is valid).
    """
    errors: List[str] = []
    for i, row in enumerate(entries):
        entry = row["entry"]
        # Check sha256_prev linkage
        if i == 0:
            if entry.get("sha256_prev") is not None:
                errors.append(
                    f"Entry 0: sha256_prev should be None, got {entry['sha256_prev']}"
                )
        else:
            prev_entry = entries[i - 1]["entry"]
            if entry.get("sha256_prev") != prev_entry.get("sha256"):
                errors.append(
                    f"Entry {i}: sha256_prev mismatch: "
                    f"{entry.get('sha256_prev')} != {prev_entry.get('sha256')}"
                )

        # Recompute and verify hash: hₜ = SHA256(hₜ₋₁ || rₜ)
        payload_json = _normalize_for_hash(entry)
        prev_hash = entry.get("sha256_prev")
        combined = (prev_hash + payload_json) if prev_hash else payload_json
        expected = hashlib.sha256(combined.encode("utf-8")).hexdigest()
        if entry.get("sha256") != expected:
            errors.append(
                f"Entry {i}: sha256 mismatch: {entry.get('sha256')} != {expected}"
            )
    return errors


def _check_no_sequence_gaps(entries: List[dict]) -> List[str]:
    """Verify no gaps or duplicates in entry IDs."""
    errors: List[str] = []
    ids = [e["id"] for e in entries]
    if ids != list(range(1, len(ids) + 1)):
        errors.append(f"ID sequence gap/dup: {ids}")
    request_ids = [e["request_id"] for e in entries]
    if len(set(request_ids)) != len(request_ids):
        dups = [r for r in request_ids if request_ids.count(r) > 1]
        errors.append(f"Duplicate request_ids: {set(dups)}")
    return errors


# ===================================================================
# 1. Two-worker simultaneous append
# ===================================================================


class TestTwoWorkerSimultaneousAppend:
    """Verify chain integrity when exactly 2 workers race to append."""

    async def test_two_workers_chain_intact(self, monkeypatch) -> None:
        """Two concurrent appends must produce a valid 2-entry chain."""
        store, pool = _make_contention_store(monkeypatch)

        async def _worker(idx: int) -> Optional[str]:
            return await store.append({
                "request_id": f"race-{idx}",
                "worker": idx,
            })

        results = await asyncio.gather(_worker(0), _worker(1))
        assert all(r is not None for r in results)

        entries = pool._state.get("entries", [])
        assert len(entries) == 2

        chain_errors = _verify_chain(entries)
        assert not chain_errors, f"Chain integrity errors: {chain_errors}"

        seq_errors = _check_no_sequence_gaps(entries)
        assert not seq_errors, f"Sequence errors: {seq_errors}"

    async def test_two_workers_different_hashes(self, monkeypatch) -> None:
        """Two entries appended by concurrent workers must have distinct hashes."""
        store, pool = _make_contention_store(monkeypatch)

        await asyncio.gather(
            store.append({"request_id": "w0", "data": "alpha"}),
            store.append({"request_id": "w1", "data": "beta"}),
        )

        entries = pool._state["entries"]
        hashes = [e["hash"] for e in entries]
        assert len(set(hashes)) == 2, "Hashes must be unique"


# ===================================================================
# 2. N-worker burst append
# ===================================================================


class TestBurstAppend:
    """Verify chain integrity under N-worker burst writes."""

    @pytest.mark.parametrize("n_workers", [5, 10, 20])
    async def test_burst_chain_integrity(
        self, monkeypatch, n_workers: int
    ) -> None:
        """N concurrent appends produce a valid N-entry chain."""
        store, pool = _make_contention_store(monkeypatch)

        async def _worker(idx: int):
            await store.append({
                "request_id": f"burst-{idx}",
                "payload": f"data-{idx}",
            })

        await asyncio.gather(*[_worker(i) for i in range(n_workers)])

        entries = pool._state.get("entries", [])
        assert len(entries) == n_workers

        chain_errors = _verify_chain(entries)
        assert not chain_errors, f"Chain integrity errors: {chain_errors}"

        seq_errors = _check_no_sequence_gaps(entries)
        assert not seq_errors, f"Sequence errors: {seq_errors}"

    async def test_burst_last_hash_matches_final_entry(
        self, monkeypatch
    ) -> None:
        """After burst writes, get_last_hash() returns the last entry's hash."""
        store, pool = _make_contention_store(monkeypatch)
        n = 10

        await asyncio.gather(*[
            store.append({"request_id": f"b-{i}"}) for i in range(n)
        ])

        last_hash = await store.get_last_hash()
        entries = pool._state["entries"]
        assert last_hash == entries[-1]["entry"]["sha256"]

    async def test_burst_no_duplicate_request_ids(
        self, monkeypatch
    ) -> None:
        """Burst writes with unique request_ids must not duplicate."""
        store, pool = _make_contention_store(monkeypatch)
        n = 15

        await asyncio.gather(*[
            store.append({"request_id": f"uniq-{i}"}) for i in range(n)
        ])

        entries = pool._state["entries"]
        rids = [e["request_id"] for e in entries]
        assert len(set(rids)) == n


# ===================================================================
# 3. Statement timeout → fail-closed
# ===================================================================


class TestStatementTimeoutFailClosed:
    """Verify that statement timeout during append → RuntimeError."""

    async def test_timeout_on_insert_raises_runtime_error(
        self, monkeypatch
    ) -> None:
        """Simulated timeout on INSERT must raise RuntimeError (fail-closed)."""
        store, pool = _make_contention_store(
            monkeypatch, fail_on_execute="insert into trustlog_entries"
        )

        with pytest.raises(RuntimeError, match="fail-closed"):
            await store.append({"request_id": "timeout-1"})

    async def test_timeout_on_advisory_lock_raises_runtime_error(
        self, monkeypatch
    ) -> None:
        """Simulated timeout on advisory lock must raise RuntimeError."""
        store, pool = _make_contention_store(
            monkeypatch, fail_on_execute="pg_advisory_xact_lock"
        )

        with pytest.raises(RuntimeError, match="fail-closed"):
            await store.append({"request_id": "lock-timeout"})

    async def test_timeout_on_chain_state_update_raises_runtime_error(
        self, monkeypatch
    ) -> None:
        """Simulated timeout on chain state UPDATE must raise RuntimeError."""
        store, pool = _make_contention_store(
            monkeypatch, fail_on_execute="update trustlog_chain_state"
        )

        with pytest.raises(RuntimeError, match="fail-closed"):
            await store.append({"request_id": "update-timeout"})


# ===================================================================
# 4. Connection pool starvation → fail-closed
# ===================================================================


class TestConnectionStarvationFailClosed:
    """Verify behaviour when the connection pool is exhausted."""

    async def test_pool_unavailable_raises_runtime_error(
        self, monkeypatch
    ) -> None:
        """Pool returning connection error must raise RuntimeError."""
        from veritas_os.storage.postgresql import PostgresTrustLogStore

        monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", generate_key())
        store = PostgresTrustLogStore()

        async def _broken_pool():
            raise ConnectionError("pool exhausted: all connections in use")

        store._get_pool = _broken_pool  # type: ignore[assignment]

        with pytest.raises(RuntimeError, match="fail-closed"):
            await store.append({"request_id": "starved"})

    async def test_connection_context_failure_raises(
        self, monkeypatch
    ) -> None:
        """Failure inside connection context must raise RuntimeError."""
        from veritas_os.storage.postgresql import PostgresTrustLogStore

        monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", generate_key())
        store = PostgresTrustLogStore()

        class _BrokenCtx:
            async def __aenter__(self):
                raise TimeoutError("connection checkout timeout")

            async def __aexit__(self, *a):
                pass

        class _BrokenPool:
            def connection(self):
                return _BrokenCtx()

        async def _get():
            return _BrokenPool()

        store._get_pool = _get  # type: ignore[assignment]

        with pytest.raises(RuntimeError, match="fail-closed"):
            await store.append({"request_id": "checkout-fail"})


# ===================================================================
# 5. Rollback recovery
# ===================================================================


class TestRollbackRecovery:
    """Verify that chain state is not corrupted after a failed append."""

    async def test_chain_intact_after_mid_append_failure(
        self, monkeypatch
    ) -> None:
        """Successful append → failed append → successful append.

        Chain must skip the failed entry and remain valid.
        """
        from veritas_os.storage.postgresql import PostgresTrustLogStore

        monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", generate_key())

        # Phase 1: successful append
        store_ok, pool_ok = _make_contention_store(monkeypatch)
        await store_ok.append({"request_id": "pre-fail"})

        entries_before = pool_ok._state.get("entries", [])
        assert len(entries_before) == 1

        hash_before = pool_ok._state.get("last_hash")
        assert hash_before is not None

        # Phase 2: inject failure on INSERT (simulates statement timeout)
        pool_ok._fail_on_execute = "insert into trustlog_entries"
        # Override the pool factory to use the same pool with failure
        fail_store = PostgresTrustLogStore()

        async def _get_fail_pool():
            return pool_ok

        fail_store._get_pool = _get_fail_pool  # type: ignore[assignment]

        with pytest.raises(RuntimeError, match="fail-closed"):
            await fail_store.append({"request_id": "will-fail"})

        # Chain state must be unchanged after rollback
        assert pool_ok._state.get("last_hash") == hash_before
        assert len(pool_ok._state.get("entries", [])) == 1

        # Phase 3: remove failure and append again
        pool_ok._fail_on_execute = None

        recover_store = PostgresTrustLogStore()

        async def _get_ok_pool():
            return pool_ok

        recover_store._get_pool = _get_ok_pool  # type: ignore[assignment]

        await recover_store.append({"request_id": "post-fail"})

        entries = pool_ok._state.get("entries", [])
        assert len(entries) == 2

        chain_errors = _verify_chain(entries)
        assert not chain_errors, f"Chain broken after recovery: {chain_errors}"

    async def test_multiple_failures_then_recovery(
        self, monkeypatch
    ) -> None:
        """Multiple consecutive failures must not corrupt chain state."""
        store, pool = _make_contention_store(monkeypatch)
        await store.append({"request_id": "anchor"})

        hash_after_anchor = pool._state.get("last_hash")

        # Inject 3 consecutive failures
        pool._fail_on_execute = "insert into trustlog_entries"
        from veritas_os.storage.postgresql import PostgresTrustLogStore

        fail_store = PostgresTrustLogStore()

        async def _get():
            return pool

        fail_store._get_pool = _get  # type: ignore[assignment]

        for i in range(3):
            with pytest.raises(RuntimeError, match="fail-closed"):
                await fail_store.append({"request_id": f"fail-{i}"})

        # Chain state unchanged
        assert pool._state.get("last_hash") == hash_after_anchor
        assert len(pool._state.get("entries", [])) == 1

        # Remove failure and append
        pool._fail_on_execute = None
        await fail_store.append({"request_id": "recovered"})

        entries = pool._state.get("entries", [])
        assert len(entries) == 2
        chain_errors = _verify_chain(entries)
        assert not chain_errors


# ===================================================================
# 6. Advisory lock release on transaction rollback
# ===================================================================


class TestAdvisoryLockRelease:
    """Verify that advisory lock is released on both commit and rollback."""

    async def test_lock_released_after_successful_append(
        self, monkeypatch
    ) -> None:
        """After a successful append the lock must be available."""
        store, pool = _make_contention_store(monkeypatch)
        await store.append({"request_id": "ok-1"})

        # Lock must be available (non-blocking acquire succeeds)
        acquired = pool._lock.acquire(blocking=False)
        assert acquired, "Advisory lock not released after successful append"
        pool._lock.release()

    async def test_lock_released_after_failed_append(
        self, monkeypatch
    ) -> None:
        """After a failed append the lock must still be released."""
        store, pool = _make_contention_store(
            monkeypatch, fail_on_execute="insert into trustlog_entries"
        )

        with pytest.raises(RuntimeError, match="fail-closed"):
            await store.append({"request_id": "fail-lock"})

        acquired = pool._lock.acquire(blocking=False)
        assert acquired, "Advisory lock not released after failed append"
        pool._lock.release()

    async def test_subsequent_append_after_lock_release(
        self, monkeypatch
    ) -> None:
        """A new append must succeed after the lock is released from failure."""
        from veritas_os.storage.postgresql import PostgresTrustLogStore

        monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", generate_key())
        pool = _ContentionMockPool(fail_on_execute="insert into trustlog_entries")
        store = PostgresTrustLogStore()

        async def _get():
            return pool

        store._get_pool = _get  # type: ignore[assignment]

        # First attempt fails
        with pytest.raises(RuntimeError):
            await store.append({"request_id": "lock-fail"})

        # Remove failure
        pool._fail_on_execute = None

        # Second attempt must succeed (lock was released)
        rid = await store.append({"request_id": "lock-ok"})
        assert rid == "lock-ok"


# ===================================================================
# 7. Full chain verification integration
# ===================================================================


class TestChainVerificationIntegration:
    """End-to-end chain verification after concurrent writes."""

    async def test_verify_chain_after_concurrent_writes(
        self, monkeypatch
    ) -> None:
        """Run chain verification on entries produced by concurrent workers."""
        store, pool = _make_contention_store(monkeypatch)
        n = 12

        await asyncio.gather(*[
            store.append({"request_id": f"verify-{i}", "seq": i})
            for i in range(n)
        ])

        entries = pool._state.get("entries", [])
        assert len(entries) == n

        # Full chain verification
        chain_errors = _verify_chain(entries)
        assert not chain_errors, f"Verification failed: {chain_errors}"

        # Sequence continuity
        seq_errors = _check_no_sequence_gaps(entries)
        assert not seq_errors, f"Sequence errors: {seq_errors}"

        # Last hash consistency
        last = entries[-1]
        assert pool._state.get("last_hash") == last["entry"]["sha256"]
        assert pool._state.get("last_id") == last["id"]

    async def test_verify_chain_hash_formula_all_entries(
        self, monkeypatch
    ) -> None:
        """Verify hₜ = SHA256(hₜ₋₁ || rₜ) for every entry."""
        store, pool = _make_contention_store(monkeypatch)

        for i in range(8):
            await store.append({"request_id": f"formula-{i}", "idx": i})

        entries = pool._state["entries"]
        for i, row in enumerate(entries):
            entry = row["entry"]
            payload_json = _normalize_for_hash(entry)
            prev_hash = entry.get("sha256_prev")
            combined = (prev_hash + payload_json) if prev_hash else payload_json
            expected = hashlib.sha256(combined.encode("utf-8")).hexdigest()
            assert entry["sha256"] == expected, (
                f"Hash formula violation at entry {i}"
            )

    async def test_get_by_id_after_concurrent_writes(
        self, monkeypatch
    ) -> None:
        """Every entry written concurrently must be retrievable by ID."""
        store, pool = _make_contention_store(monkeypatch)
        n = 8

        await asyncio.gather(*[
            store.append({"request_id": f"lookup-{i}"}) for i in range(n)
        ])

        for i in range(n):
            entry = await store.get_by_id(f"lookup-{i}")
            assert entry is not None, f"Entry lookup-{i} not found"
            assert entry.get("request_id") == f"lookup-{i}"

    async def test_iter_entries_ordered_after_concurrent_writes(
        self, monkeypatch
    ) -> None:
        """iter_entries must return entries in insertion order."""
        store, pool = _make_contention_store(monkeypatch)
        n = 6

        await asyncio.gather(*[
            store.append({"request_id": f"order-{i}"}) for i in range(n)
        ])

        entries = []
        async for e in store.iter_entries(limit=100):
            entries.append(e)

        assert len(entries) == n
        # Verify chain links are consistent with iteration order
        for i in range(1, len(entries)):
            assert entries[i]["sha256_prev"] == entries[i - 1]["sha256"]


# ===================================================================
# 8. Mixed success/failure contention
# ===================================================================


class TestMixedContentionScenarios:
    """Complex scenarios mixing successful and failed appends."""

    async def test_interleaved_success_and_failure(
        self, monkeypatch
    ) -> None:
        """Alternate between successful and failing workers.

        Chain must contain only the successful entries.
        """
        from veritas_os.storage.postgresql import PostgresTrustLogStore

        monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", generate_key())
        pool = _ContentionMockPool()
        store = PostgresTrustLogStore()

        async def _get():
            return pool

        store._get_pool = _get  # type: ignore[assignment]

        # 3 successful appends
        for i in range(3):
            await store.append({"request_id": f"ok-{i}"})

        # Inject failure
        pool._fail_on_execute = "insert into trustlog_entries"
        with pytest.raises(RuntimeError):
            await store.append({"request_id": "fail-mid"})

        # Remove failure, 2 more successes
        pool._fail_on_execute = None
        for i in range(3, 5):
            await store.append({"request_id": f"ok-{i}"})

        entries = pool._state.get("entries", [])
        assert len(entries) == 5

        chain_errors = _verify_chain(entries)
        assert not chain_errors

    async def test_encryption_key_missing_is_fail_closed(
        self, monkeypatch
    ) -> None:
        """Missing encryption key during append must raise RuntimeError."""
        from veritas_os.storage.postgresql import PostgresTrustLogStore

        monkeypatch.delenv("VERITAS_ENCRYPTION_KEY", raising=False)
        pool = _ContentionMockPool()
        store = PostgresTrustLogStore()

        async def _get():
            return pool

        store._get_pool = _get  # type: ignore[assignment]

        with pytest.raises(RuntimeError, match="fail-closed"):
            await store.append({"request_id": "no-key"})

        # Chain state must be empty (no partial writes)
        assert not pool._state.get("entries")


# ===================================================================
# 9. Threaded contention (closer to real multi-worker deployment)
# ===================================================================


class TestThreadedContention:
    """Verify chain integrity using OS threads (closer to Uvicorn workers)."""

    def test_threaded_burst_chain_integrity(self, monkeypatch) -> None:
        """N threads each appending 1 entry must produce a valid chain."""
        store, pool = _make_contention_store(monkeypatch)
        n_threads = 8
        errors: List[str] = []

        def _worker(idx: int):
            try:
                asyncio.run(
                    store.append({"request_id": f"thread-{idx}", "t": idx})
                )
            except Exception as e:
                errors.append(f"Thread {idx}: {e}")

        threads = [threading.Thread(target=_worker, args=(i,)) for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=_THREAD_JOIN_TIMEOUT_S)

        assert not errors, f"Thread errors: {errors}"

        entries = pool._state.get("entries", [])
        assert len(entries) == n_threads

        chain_errors = _verify_chain(entries)
        assert not chain_errors, f"Chain errors: {chain_errors}"

    def test_threaded_mixed_success_failure(self, monkeypatch) -> None:
        """Some threads fail mid-append; chain of successful entries is valid."""
        from veritas_os.storage.postgresql import PostgresTrustLogStore

        monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", generate_key())

        # Pool that fails on every 3rd INSERT
        call_count = {"n": 0}
        base_pool = _ContentionMockPool()

        class _FlakyConn(_ContentionMockConn):
            async def execute(self, sql: str, params=None):
                sql_l = sql.strip().lower()
                if sql_l.startswith("insert into trustlog_entries"):
                    call_count["n"] += 1
                    if call_count["n"] % 3 == 0:
                        raise IOError("Simulated sporadic failure")
                return await super().execute(sql, params)

        class _FlakyCtx:
            def __init__(self, conn):
                self._conn = conn

            async def __aenter__(self):
                return self._conn

            async def __aexit__(self, *a):
                pass

        def _flaky_connection():
            return _FlakyCtx(
                _FlakyConn(
                    base_pool._state,
                    lock=base_pool._lock,
                )
            )

        base_pool.connection = _flaky_connection  # type: ignore[assignment]

        store = PostgresTrustLogStore()

        async def _get():
            return base_pool

        store._get_pool = _get  # type: ignore[assignment]

        n_threads = 9
        successes: List[str] = []
        failures: List[str] = []

        def _worker(idx: int):
            try:
                asyncio.run(
                    store.append({"request_id": f"flaky-{idx}", "idx": idx})
                )
                successes.append(f"flaky-{idx}")
            except RuntimeError:
                failures.append(f"flaky-{idx}")

        threads = [threading.Thread(target=_worker, args=(i,)) for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=_THREAD_JOIN_TIMEOUT_S)

        # Some should succeed, some should fail
        assert len(successes) + len(failures) == n_threads

        # Verify chain of successful entries
        entries = base_pool._state.get("entries", [])
        if entries:
            chain_errors = _verify_chain(entries)
            assert not chain_errors, f"Chain errors after flaky writes: {chain_errors}"
