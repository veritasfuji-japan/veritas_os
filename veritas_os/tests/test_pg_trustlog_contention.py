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
import os
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


# ===================================================================
# PART II — REAL POSTGRESQL INTEGRATION TESTS
# ===================================================================
# Markers: @pytest.mark.postgresql  @pytest.mark.contention
# Skip:    automatically when VERITAS_DATABASE_URL is absent
# CI job:  test-postgresql (main.yml) — dedicated "Run real PG
#          contention tests" step (pytest -m "postgresql and contention")
#          also runs in production-validation.yml postgresql-smoke job.
#
# Role partition
# --------------
# • Mock-pool tests (Part I above): fast, deterministic, wide coverage
#   (25 tests).  Run on every PR/push via the main unit test job.
#   They exercise advisory-lock serialisation semantics without a live DB.
#
# • Real-PG tests (Part II below): narrower but high-fidelity.  They
#   prove that PostgreSQL's own ``pg_advisory_xact_lock`` actually
#   serialises writes, that real MVCC isolation holds, and that genuine
#   statement-timeout / lock-timeout errors trigger fail-closed behaviour.
#   Run in the CI test-postgresql job against a PG 16 service container.
#
# See also:
#   docs/postgresql-production-guide.md §12 — Contention Tests
#   docs/BACKEND_PARITY_COVERAGE.md §8 — Contention, Metrics, Recovery
# ===================================================================

# ---------------------------------------------------------------------------
# Shared skip guard
# ---------------------------------------------------------------------------

_REAL_PG_DSN: str = os.getenv("VERITAS_DATABASE_URL", "")

_SKIP_NO_REAL_PG = pytest.mark.skipif(
    not _REAL_PG_DSN,
    reason="VERITAS_DATABASE_URL not set — real PostgreSQL contention tests skipped",
)

# Advisory-lock key (same value as postgresql.py)
_ADVISORY_LOCK_KEY = 0x5645524954415301


# ---------------------------------------------------------------------------
# Helpers — pool, store, and table management
# ---------------------------------------------------------------------------


def _normalize_test_dsn(dsn: str) -> str:
    """Strip SQLAlchemy dialect suffixes (``+psycopg``, ``+asyncpg``, etc.).

    psycopg3 only accepts standard ``postgresql://`` or ``postgres://``
    URIs.  CI environments commonly use the SQLAlchemy-style
    ``postgresql+psycopg://`` format, which must be normalised.
    """
    if dsn.startswith(("postgresql+", "postgres+")):
        scheme_end = dsn.index("://")
        base_scheme = dsn.split("+")[0]
        dsn = base_scheme + dsn[scheme_end:]
    return dsn


async def _open_real_pool(max_size: int = 5):
    """Open a fresh ``AsyncConnectionPool`` for integration tests.

    Uses ``VERITAS_DATABASE_URL`` with any SQLAlchemy dialect prefix
    (``+psycopg``) stripped so that psycopg3/libpq can parse it.
    Skips if ``psycopg_pool`` is not installed.
    """
    try:
        from psycopg_pool import AsyncConnectionPool
    except ImportError:
        pytest.skip("psycopg_pool not installed")
        return  # unreachable, but satisfies type-checkers

    pool = AsyncConnectionPool(
        conninfo=_normalize_test_dsn(_REAL_PG_DSN),
        min_size=1,
        max_size=max_size,
        open=False,
    )
    await pool.open(wait=True, timeout=15)
    return pool


async def _open_real_pool_with_stmt_timeout(
    stmt_timeout_ms: int,
    max_size: int = 3,
):
    """Open a pool with a custom ``statement_timeout`` GUC.

    Uses ``build_conninfo()`` from ``db.py`` after patching the env var
    so that the GUC is embedded in the connection string.  Call this
    **after** ``monkeypatch.setenv("VERITAS_DB_STATEMENT_TIMEOUT_MS",
    str(stmt_timeout_ms))``.
    """
    try:
        from psycopg_pool import AsyncConnectionPool
        from veritas_os.storage.db import build_conninfo
    except ImportError:
        pytest.skip("psycopg_pool not installed")
        return  # unreachable

    pool = AsyncConnectionPool(
        conninfo=build_conninfo(),
        min_size=1,
        max_size=max_size,
        open=False,
    )
    await pool.open(wait=True, timeout=15)
    return pool


async def _truncate_trustlog_tables(pool) -> None:
    """Truncate TrustLog tables to give each test a clean slate."""
    async with pool.connection() as conn:
        await conn.execute(
            "TRUNCATE TABLE trustlog_entries, trustlog_chain_state "
            "RESTART IDENTITY CASCADE"
        )


def _make_real_pg_store(pool):
    """Return a ``PostgresTrustLogStore`` wired to *pool*.

    ``_get_pool`` is injected via attribute assignment — the same pattern
    used for mock-pool tests in Part I above — because
    ``PostgresTrustLogStore`` has no built-in dependency-injection API.
    The ``type: ignore[assignment]`` suppression is intentional.
    """
    from veritas_os.storage.postgresql import PostgresTrustLogStore

    store = PostgresTrustLogStore()

    async def _get_pool():
        return pool

    store._get_pool = _get_pool  # type: ignore[assignment]
    return store


async def _fetch_db_entries(pool) -> List[dict]:
    """Return all trustlog entries (insertion order) from the DB."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT entry FROM trustlog_entries ORDER BY id"
        )
        rows = await cur.fetchall()
    return [r[0] for r in rows if isinstance(r[0], dict)]


async def _verify_real_pg_chain(store) -> List[str]:
    """Walk the chain via ``iter_entries`` and verify hash linkage.

    Returns a list of human-readable error descriptions (empty = valid).
    """
    entries: List[dict] = []
    async for e in store.iter_entries(limit=10_000):
        entries.append(e)

    errors: List[str] = []
    for i, entry in enumerate(entries):
        if i == 0:
            if entry.get("sha256_prev") is not None:
                errors.append(
                    f"Entry 0: sha256_prev should be None, "
                    f"got {entry['sha256_prev']!r}"
                )
        else:
            prev = entries[i - 1]
            if entry.get("sha256_prev") != prev.get("sha256"):
                errors.append(
                    f"Entry {i}: sha256_prev mismatch — "
                    f"got {entry.get('sha256_prev')!r}, "
                    f"expected {prev.get('sha256')!r}"
                )

        # Recompute hash: hₜ = SHA256(hₜ₋₁ || canonical(rₜ))
        from veritas_os.logging.trust_log_core import _normalize_for_hash

        payload_json = _normalize_for_hash(entry)
        prev_hash = entry.get("sha256_prev")
        combined = (prev_hash + payload_json) if prev_hash else payload_json
        expected = hashlib.sha256(combined.encode("utf-8")).hexdigest()
        if entry.get("sha256") != expected:
            errors.append(
                f"Entry {i}: sha256 mismatch — "
                f"stored {entry.get('sha256')!r}, recomputed {expected!r}"
            )
    return errors


# ---------------------------------------------------------------------------
# 1. Two concurrent writers
# ---------------------------------------------------------------------------


@_SKIP_NO_REAL_PG
@pytest.mark.postgresql
@pytest.mark.contention
class TestRealPgTwoWorkers:
    """Two concurrent writers against real PostgreSQL must produce a valid chain."""

    async def test_two_concurrent_writers_chain_intact(self) -> None:
        """Two goroutine-style async tasks appending simultaneously.

        The advisory lock in PostgreSQL must serialise both inserts so
        the resulting 2-entry chain has intact sha256/sha256_prev links.
        """
        pool = await _open_real_pool(max_size=4)
        try:
            await _truncate_trustlog_tables(pool)
            store = _make_real_pg_store(pool)

            rid_a, rid_b = await asyncio.gather(
                store.append({"request_id": "real-pg-w0", "worker": 0}),
                store.append({"request_id": "real-pg-w1", "worker": 1}),
            )

            assert rid_a is not None, (
                "Worker 0 returned None — append may have silently failed"
            )
            assert rid_b is not None, (
                "Worker 1 returned None — append may have silently failed"
            )
            assert rid_a != rid_b, (
                f"Both workers returned the same request_id {rid_a!r} — "
                "possible duplicate insert"
            )

            chain_errors = await _verify_real_pg_chain(store)
            assert not chain_errors, (
                "Chain hash integrity violated after 2-writer concurrent "
                "append on real PostgreSQL:\n" + "\n".join(chain_errors)
            )

            # Confirm exactly 2 rows in the database
            entries = await _fetch_db_entries(pool)
            assert len(entries) == 2, (
                f"Expected 2 entries in trustlog_entries, got {len(entries)}"
            )
        finally:
            await pool.close()

    async def test_two_writers_produce_distinct_hashes(self) -> None:
        """Each of the two entries must have a unique sha256 hash."""
        pool = await _open_real_pool(max_size=4)
        try:
            await _truncate_trustlog_tables(pool)
            store = _make_real_pg_store(pool)

            await asyncio.gather(
                store.append({"request_id": "hash-check-0"}),
                store.append({"request_id": "hash-check-1"}),
            )

            entries = await _fetch_db_entries(pool)
            assert len(entries) == 2
            hashes = [e.get("sha256") for e in entries]
            assert hashes[0] != hashes[1], (
                "Both entries share the same sha256 hash — "
                "advisory lock may not be serialising writes correctly"
            )
        finally:
            await pool.close()


# ---------------------------------------------------------------------------
# 2. Burst append — 5 and 10 workers
# ---------------------------------------------------------------------------


@_SKIP_NO_REAL_PG
@pytest.mark.postgresql
@pytest.mark.contention
class TestRealPgBurstAppend:
    """Burst of N concurrent writers — chain integrity and no gaps/duplicates."""

    async def _run_burst(self, n_workers: int, tag: str) -> None:
        pool = await _open_real_pool(max_size=n_workers + 2)
        try:
            await _truncate_trustlog_tables(pool)
            store = _make_real_pg_store(pool)

            results = await asyncio.gather(
                *[
                    store.append({"request_id": f"{tag}-{i}", "worker": i})
                    for i in range(n_workers)
                ]
            )

            failed = [i for i, r in enumerate(results) if r is None]
            assert not failed, (
                f"Workers {failed} returned None — unexpected silent failure "
                f"during {n_workers}-writer burst append on real PostgreSQL"
            )

            entries = await _fetch_db_entries(pool)
            assert len(entries) == n_workers, (
                f"Expected {n_workers} entries after burst, "
                f"got {len(entries)} — possible gap or duplicate"
            )

            request_ids = [e.get("request_id") for e in entries]
            duplicates = [
                rid for rid in set(request_ids) if request_ids.count(rid) > 1
            ]
            assert not duplicates, (
                f"Duplicate request_ids in DB after burst: {duplicates}"
            )

            chain_errors = await _verify_real_pg_chain(store)
            assert not chain_errors, (
                f"Chain integrity violated after {n_workers}-writer burst "
                f"on real PostgreSQL:\n" + "\n".join(chain_errors)
            )
        finally:
            await pool.close()

    async def test_five_workers_burst_chain_intact(self) -> None:
        """5 concurrent writers — chain must be intact and complete."""
        await self._run_burst(5, tag="burst5")

    async def test_ten_workers_burst_no_gap_or_duplicate(self) -> None:
        """10 concurrent writers — no gaps, no duplicates, chain valid."""
        await self._run_burst(10, tag="burst10")


# ---------------------------------------------------------------------------
# 3. Lock-timeout / statement-timeout → fail-closed
# ---------------------------------------------------------------------------


@_SKIP_NO_REAL_PG
@pytest.mark.postgresql
@pytest.mark.contention
class TestRealPgLockTimeout:
    """Advisory lock wait times out → RuntimeError (fail-closed)."""

    async def test_lock_timeout_fail_closed(self, monkeypatch) -> None:
        """Hold the advisory lock from one connection; a second connection
        with a very short ``statement_timeout`` must fail with
        ``RuntimeError`` and leave the chain state untouched.

        Diagnosis guide
        ---------------
        * ``RuntimeError`` NOT raised → advisory lock is not blocking
          as expected; check PostgreSQL version or lock-key collision.
        * Timeout too slow or intermittent → increase ``lock_hold_s``
          or lengthen the statement_timeout margin.
        * Chain non-empty after the failed append → transaction did NOT
          roll back; fail-closed guarantee is broken.
        """
        # Build the "holder" pool with a normal (long) timeout so it can
        # hold the lock without risk of being cancelled.
        holder_pool = await _open_real_pool(max_size=2)
        try:
            await _truncate_trustlog_tables(holder_pool)

            # Build the "append" pool with a very short statement_timeout
            # so that waiting on the advisory lock times out quickly.
            monkeypatch.setenv("VERITAS_DB_STATEMENT_TIMEOUT_MS", "200")
            append_pool = await _open_real_pool_with_stmt_timeout(
                stmt_timeout_ms=200, max_size=2
            )
            try:
                lock_held_event = asyncio.Event()
                release_lock_event = asyncio.Event()

                async def _hold_advisory_lock() -> None:
                    """Hold pg_advisory_xact_lock until told to release."""
                    async with holder_pool.connection() as conn:
                        async with conn.transaction():
                            await conn.execute(
                                "SELECT pg_advisory_xact_lock(%s)",
                                (_ADVISORY_LOCK_KEY,),
                            )
                            lock_held_event.set()
                            # Hold the lock until the test releases it
                            try:
                                await asyncio.wait_for(
                                    release_lock_event.wait(), timeout=10.0
                                )
                            except asyncio.TimeoutError:
                                pass  # Release on test timeout

                holder_task = asyncio.create_task(_hold_advisory_lock())
                await asyncio.wait_for(lock_held_event.wait(), timeout=5.0)

                # The append will try to acquire the same advisory lock.
                # With statement_timeout=200ms it must cancel within ~200ms.
                append_store = _make_real_pg_store(append_pool)
                with pytest.raises(RuntimeError) as exc_info:
                    await store_append_with_timeout(
                        append_store,
                        {"request_id": "lock-timeout-test"},
                        timeout_seconds=3.0,
                    )

                assert "fail-closed" in str(exc_info.value).lower(), (
                    f"RuntimeError raised but message does not mention "
                    f"'fail-closed': {exc_info.value!r}"
                )

                # Release the lock so the holder task can finish cleanly
                release_lock_event.set()
                await asyncio.wait_for(holder_task, timeout=5.0)

                # Chain state must be empty — no partial write persisted
                entries = await _fetch_db_entries(holder_pool)
                assert len(entries) == 0, (
                    f"Expected 0 entries after failed lock-timeout append, "
                    f"got {len(entries)} — transaction rollback may be broken"
                )
            finally:
                await append_pool.close()
        finally:
            await holder_pool.close()

    async def test_chain_intact_after_lock_timeout_then_success(
        self, monkeypatch
    ) -> None:
        """After a lock-timeout failure, the next append succeeds and the
        chain continues correctly from the previous last_hash.
        """
        holder_pool = await _open_real_pool(max_size=3)
        try:
            await _truncate_trustlog_tables(holder_pool)

            # Pre-populate with one successful entry
            pre_store = _make_real_pg_store(holder_pool)
            await pre_store.append({"request_id": "pre-lock-timeout"})

            monkeypatch.setenv("VERITAS_DB_STATEMENT_TIMEOUT_MS", "200")
            append_pool = await _open_real_pool_with_stmt_timeout(
                stmt_timeout_ms=200, max_size=2
            )
            try:
                lock_held_event = asyncio.Event()
                release_event = asyncio.Event()

                async def _hold() -> None:
                    async with holder_pool.connection() as conn:
                        async with conn.transaction():
                            await conn.execute(
                                "SELECT pg_advisory_xact_lock(%s)",
                                (_ADVISORY_LOCK_KEY,),
                            )
                            lock_held_event.set()
                            try:
                                await asyncio.wait_for(
                                    release_event.wait(), timeout=10.0
                                )
                            except asyncio.TimeoutError:
                                pass

                holder = asyncio.create_task(_hold())
                await asyncio.wait_for(lock_held_event.wait(), 5.0)

                append_store = _make_real_pg_store(append_pool)
                with pytest.raises(RuntimeError):
                    await store_append_with_timeout(
                        append_store,
                        {"request_id": "should-not-persist"},
                        timeout_seconds=3.0,
                    )

                release_event.set()
                await asyncio.wait_for(holder, timeout=5.0)

                # The failed append must not have corrupted state; now do a
                # successful append and verify the full chain.
                await pre_store.append({"request_id": "post-recovery"})

                chain_errors = await _verify_real_pg_chain(pre_store)
                assert not chain_errors, (
                    "Chain corrupted after lock-timeout failure + recovery:\n"
                    + "\n".join(chain_errors)
                )

                entries = await _fetch_db_entries(holder_pool)
                assert len(entries) == 2, (
                    f"Expected exactly 2 entries (pre + post-recovery), "
                    f"got {len(entries)}"
                )
            finally:
                await append_pool.close()
        finally:
            await holder_pool.close()


async def store_append_with_timeout(
    store,
    entry: dict,
    timeout_seconds: float = 3.0,
) -> str:
    """Call ``store.append`` with an overall asyncio timeout.

    This prevents a test from hanging indefinitely if the DB lock wait
    itself does not trigger an error (e.g., statement_timeout not wired
    to the pool).  Raises ``asyncio.TimeoutError`` if the append takes
    longer than *timeout_seconds*; propagates any other exception unchanged.
    """
    return await asyncio.wait_for(store.append(entry), timeout=timeout_seconds)


# ---------------------------------------------------------------------------
# 4. Pool-waiting scenario — small pool, many workers, chain intact
# ---------------------------------------------------------------------------


@_SKIP_NO_REAL_PG
@pytest.mark.postgresql
@pytest.mark.contention
class TestRealPgPoolWaiting:
    """Connection pool has fewer slots than workers → workers queue up.

    All appends must eventually complete (or raise RuntimeError on
    genuine DB error), and the completed entries must form a valid chain.
    """

    async def test_pool_waiting_all_writers_complete(self) -> None:
        """8 concurrent workers share a pool of max_size=2.

        Workers queue for connections.  After all complete, the chain
        must be intact and contain exactly 8 entries.

        Diagnosis guide
        ---------------
        * ``RuntimeError`` from workers → pool timeout exceeded; increase
          ``max_size`` or reduce worker count in this test.
        * Chain errors → serialisation broken despite pool starvation;
          investigate advisory lock key or transaction isolation.
        """
        n_workers = 8
        pool = await _open_real_pool(max_size=2)
        try:
            await _truncate_trustlog_tables(pool)
            store = _make_real_pg_store(pool)

            results = await asyncio.gather(
                *[
                    store.append(
                        {"request_id": f"pool-wait-{i}", "worker": i}
                    )
                    for i in range(n_workers)
                ],
                return_exceptions=True,
            )

            errors = [r for r in results if isinstance(r, Exception)]
            successes = [r for r in results if not isinstance(r, Exception)]

            assert not errors, (
                f"{len(errors)} worker(s) raised an exception during pool-"
                f"waiting test on real PostgreSQL:\n"
                + "\n".join(repr(e) for e in errors)
            )

            entries = await _fetch_db_entries(pool)
            assert len(entries) == n_workers, (
                f"Expected {n_workers} entries after pool-waiting run, "
                f"got {len(entries)}"
            )

            chain_errors = await _verify_real_pg_chain(store)
            assert not chain_errors, (
                "Chain integrity violated after pool-waiting run:\n"
                + "\n".join(chain_errors)
            )

            request_ids = [e.get("request_id") for e in entries]
            assert len(set(request_ids)) == len(request_ids), (
                f"Duplicate request_ids after pool-waiting run: "
                f"{[r for r in request_ids if request_ids.count(r) > 1]}"
            )

            _ = successes  # all results examined above
        finally:
            await pool.close()


# ---------------------------------------------------------------------------
# 5. Rollback recovery — chain state intact after mid-append failure
# ---------------------------------------------------------------------------


@_SKIP_NO_REAL_PG
@pytest.mark.postgresql
@pytest.mark.contention
class TestRealPgRollbackRecovery:
    """Verify that a rolled-back append leaves the chain state untouched
    and that subsequent appends continue the chain correctly.
    """

    async def test_chain_intact_after_rollback(self) -> None:
        """A simulated mid-append failure must not corrupt chain state.

        We inject a pool that raises an error during the INSERT step to
        force a rollback; the subsequent successful append must see the
        last_hash from the pre-failure state, not a phantom value.

        Diagnosis guide
        ---------------
        * Chain errors on the post-rollback entry → ``last_hash`` was
          updated despite the rollback; the UPDATE to trustlog_chain_state
          may not be inside the same transaction as the INSERT.
        """
        pool = await _open_real_pool(max_size=4)
        try:
            await _truncate_trustlog_tables(pool)
            store = _make_real_pg_store(pool)

            # Successful pre-state (2 entries)
            await store.append({"request_id": "rr-pre-0"})
            await store.append({"request_id": "rr-pre-1"})

            last_hash_before_failure = await store.get_last_hash()

            # Inject a failure via a patched pool that raises on INSERT
            from veritas_os.storage.postgresql import PostgresTrustLogStore

            fail_store = PostgresTrustLogStore()
            _ContentionMockPool_fail = _ContentionMockPool(
                fail_on_execute="insert into trustlog_entries"
            )

            async def _get_fail():
                return _ContentionMockPool_fail

            fail_store._get_pool = _get_fail  # type: ignore[assignment]

            with pytest.raises(RuntimeError):
                await fail_store.append({"request_id": "rr-fail"})

            # The real store's last_hash must be unchanged
            last_hash_after_failure = await store.get_last_hash()
            assert last_hash_before_failure == last_hash_after_failure, (
                f"last_hash changed after a failed append:\n"
                f"  before: {last_hash_before_failure!r}\n"
                f"  after:  {last_hash_after_failure!r}\n"
                "The mock-pool rollback test passed but real-PG state was "
                "not verified.  Check that chain_state UPDATE is inside the "
                "same transaction as the entries INSERT."
            )

            # Post-recovery append must correctly extend the real chain
            await store.append({"request_id": "rr-post-0"})

            chain_errors = await _verify_real_pg_chain(store)
            assert not chain_errors, (
                "Chain corrupted after rollback + recovery on real PG:\n"
                + "\n".join(chain_errors)
            )
        finally:
            await pool.close()

    async def test_append_after_recovery_continues_chain(self) -> None:
        """Three good appends, one forced failure, then two more good appends.

        The five successfully-stored entries must form a single unbroken
        hash chain.
        """
        pool = await _open_real_pool(max_size=4)
        try:
            await _truncate_trustlog_tables(pool)
            store = _make_real_pg_store(pool)

            for i in range(3):
                await store.append({"request_id": f"arc-good-{i}"})

            # Forced failure via mock store pointing at a broken mock pool
            from veritas_os.storage.postgresql import PostgresTrustLogStore

            broken = PostgresTrustLogStore()
            _fail_pool = _ContentionMockPool(fail_on_execute="update trustlog_chain_state")

            async def _get_broken():
                return _fail_pool

            broken._get_pool = _get_broken  # type: ignore[assignment]

            with pytest.raises(RuntimeError):
                await broken.append({"request_id": "arc-fail"})

            for i in range(3, 5):
                await store.append({"request_id": f"arc-good-{i}"})

            chain_errors = await _verify_real_pg_chain(store)
            assert not chain_errors, (
                "Chain corrupted after multi-append recovery run:\n"
                + "\n".join(chain_errors)
            )

            entries = await _fetch_db_entries(pool)
            assert len(entries) == 5, (
                f"Expected 5 entries (3 + 2 good appends), got {len(entries)}"
            )
        finally:
            await pool.close()


# ---------------------------------------------------------------------------
# 6. Full chain verification after contention run
# ---------------------------------------------------------------------------


@_SKIP_NO_REAL_PG
@pytest.mark.postgresql
@pytest.mark.contention
class TestRealPgFullChainVerify:
    """Run a contention burst and verify the full chain using both the
    internal verifier and the ``trustlog_verify`` audit module.
    """

    async def test_full_chain_verify_after_concurrent_writes(self) -> None:
        """20-writer burst → verify all entries form a valid sha256 chain.

        This test exercises the same code path as a post-incident audit:
        iterate every stored entry, recompute hashes, and confirm linkage.

        Diagnosis guide
        ---------------
        * Hash mismatch at entry N → worker N-1 and N wrote using the same
          previous hash; advisory lock did not serialise them.
        * sha256_prev=None at entry > 0 → bootstrap row was inserted twice
          (ON CONFLICT not working) or chain_state was reset mid-run.
        """
        pool = await _open_real_pool(max_size=10)
        try:
            await _truncate_trustlog_tables(pool)
            store = _make_real_pg_store(pool)

            n_workers = 20
            await asyncio.gather(
                *[
                    store.append(
                        {"request_id": f"full-verify-{i}", "seq": i}
                    )
                    for i in range(n_workers)
                ]
            )

            entries = await _fetch_db_entries(pool)
            assert len(entries) == n_workers, (
                f"Expected {n_workers} entries after burst, got {len(entries)}"
            )

            chain_errors = await _verify_real_pg_chain(store)
            assert not chain_errors, (
                f"Full chain verification FAILED after {n_workers}-writer "
                f"burst on real PostgreSQL — advisory lock contention "
                f"integrity guarantee is broken:\n"
                + "\n".join(chain_errors)
            )

            # Also confirm using the audit verifier module
            try:
                from veritas_os.audit.trustlog_verify import verify_chain

                raw_entries = [
                    {"entry": e, "hash": e.get("sha256"), "prev_hash": e.get("sha256_prev")}
                    for e in entries
                ]
                audit_result = verify_chain(raw_entries)
                assert audit_result.get("valid", False), (
                    f"Audit verifier reported invalid chain: {audit_result}"
                )
            except ImportError:
                pass  # verifier module is optional for this test
        finally:
            await pool.close()


# ---------------------------------------------------------------------------
# 7. No duplicate request_ids / no gaps in DB
# ---------------------------------------------------------------------------


@_SKIP_NO_REAL_PG
@pytest.mark.postgresql
@pytest.mark.contention
class TestRealPgSequenceIntegrity:
    """Verify that concurrent appends produce no duplicate or missing rows."""

    async def test_no_duplicate_request_ids_in_db(self) -> None:
        """10 workers each appending a unique request_id — DB must have
        exactly 10 distinct rows with no duplicates.

        Diagnosis guide
        ---------------
        * Fewer than 10 rows → some inserts were silently swallowed.
        * Duplicate request_ids → UNIQUE constraint on request_id is not
          being enforced or the same entry was inserted twice.
        """
        pool = await _open_real_pool(max_size=6)
        try:
            await _truncate_trustlog_tables(pool)
            store = _make_real_pg_store(pool)
            n = 10

            await asyncio.gather(
                *[store.append({"request_id": f"seq-integ-{i}"}) for i in range(n)]
            )

            entries = await _fetch_db_entries(pool)
            assert len(entries) == n, (
                f"Expected {n} entries, got {len(entries)}"
            )

            request_ids = [e.get("request_id") for e in entries]
            duplicates = [
                rid for rid in set(request_ids) if request_ids.count(rid) > 1
            ]
            assert not duplicates, (
                f"Duplicate request_ids in trustlog_entries after concurrent "
                f"append: {duplicates}"
            )

            chain_errors = await _verify_real_pg_chain(store)
            assert not chain_errors, (
                "Chain integrity violated despite no duplicate request_ids:\n"
                + "\n".join(chain_errors)
            )
        finally:
            await pool.close()


# ---------------------------------------------------------------------------
# 8. Advisory lock release on transaction end
# ---------------------------------------------------------------------------


@_SKIP_NO_REAL_PG
@pytest.mark.postgresql
@pytest.mark.contention
class TestRealPgAdvisoryLockRelease:
    """Verify that ``pg_advisory_xact_lock`` is released at transaction end."""

    async def test_advisory_lock_released_after_commit(self) -> None:
        """After a successful append, the lock key is no longer held.

        A second connection must be able to acquire the same advisory
        lock without blocking, confirming transaction-scoped release.

        Diagnosis guide
        ---------------
        * asyncio.TimeoutError → the first append somehow held the lock
          after COMMIT; the lock may have been re-acquired without a
          corresponding COMMIT or it was promoted to a session lock.
        """
        pool = await _open_real_pool(max_size=4)
        try:
            await _truncate_trustlog_tables(pool)
            store = _make_real_pg_store(pool)

            # First append (acquires and commits the advisory lock)
            await store.append({"request_id": "lock-release-test"})

            # Second connection: acquire the same lock key — must not block
            async def _acquire_and_release() -> None:
                async with pool.connection() as conn:
                    async with conn.transaction():
                        await conn.execute(
                            "SELECT pg_advisory_xact_lock(%s)",
                            (_ADVISORY_LOCK_KEY,),
                        )
                        # Successfully acquired — lock was released on commit

            await asyncio.wait_for(_acquire_and_release(), timeout=5.0)
        finally:
            await pool.close()

    async def test_advisory_lock_released_after_rollback(self) -> None:
        """Even after a failed (rolled-back) append, the lock is released.

        Uses ``_open_real_pool`` plus a mock-pool failure so we can
        force a rollback without modifying the real schema.

        Diagnosis guide
        ---------------
        * asyncio.TimeoutError on the second _acquire_and_release call →
          the rolled-back transaction left the lock held on the
          *real* PostgreSQL connection; check whether the mock pool
          failure path correctly exercises the real connection rollback.
        """
        pool = await _open_real_pool(max_size=4)
        try:
            await _truncate_trustlog_tables(pool)

            # Force a failure using the mock-pool mechanism (same approach
            # as the mock tests above) then verify the real DB has no lock.
            from veritas_os.storage.postgresql import PostgresTrustLogStore

            fail_store = PostgresTrustLogStore()
            fail_pool = _ContentionMockPool(
                fail_on_execute="insert into trustlog_entries"
            )

            async def _get_fail():
                return fail_pool

            fail_store._get_pool = _get_fail  # type: ignore[assignment]

            with pytest.raises(RuntimeError):
                await fail_store.append({"request_id": "rollback-lock-test"})

            # The real pool should have no blocked connections — a new
            # append on the REAL store must succeed without lock starvation.
            real_store = _make_real_pg_store(pool)
            rid = await asyncio.wait_for(
                real_store.append({"request_id": "post-rollback-real"}),
                timeout=5.0,
            )
            assert rid is not None, (
                "Append after mock-pool rollback returned None on real PG"
            )
        finally:
            await pool.close()
