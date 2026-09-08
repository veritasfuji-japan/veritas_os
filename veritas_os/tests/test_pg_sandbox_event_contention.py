"""Real PostgreSQL arbitration, rollback and lost-ack recovery in an isolated schema."""

import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest

from veritas_os.policy.sandbox_event_store import (
    PostgresSandboxEventStore, SandboxEventConflict, SandboxEventStoreError,
)

pytestmark = [pytest.mark.postgresql, pytest.mark.contention]


@asynccontextmanager
async def database():
    dsn = os.getenv("VERITAS_DATABASE_URL", "")
    if not dsn.startswith("postgresql"):
        pytest.skip("real PostgreSQL test service required")
    import psycopg
    from psycopg_pool import AsyncConnectionPool

    dsn = dsn.replace("postgresql+psycopg://", "postgresql://", 1)
    schema = "sandbox_test_" + uuid4().hex
    admin = await psycopg.AsyncConnection.connect(dsn, autocommit=True)
    await admin.execute(f"CREATE SCHEMA {schema}")
    pool = AsyncConnectionPool(
        dsn, kwargs={"options": f"-c search_path={schema}"},
        min_size=0, max_size=16, open=False,
    )
    try:
        await pool.open()
        async with pool.connection() as conn:
            ddl = Path(__file__).parents[1] / "policy" / "sandbox_events.sql"
            await conn.execute(ddl.read_text())
        yield pool
    finally:
        await pool.close()
        # Only this randomly named test schema; never an application schema.
        await admin.execute(f"DROP SCHEMA {schema} CASCADE")
        await admin.close()


def payload(event=None, message="synthetic"):
    return json.dumps({"event_id": event or str(uuid4()), "message": message}).encode()


@pytest.mark.asyncio
async def test_concurrent_same_key_and_payload_commits_one_event():
    async with database() as pool:
        raw = payload()
        results = await asyncio.gather(*(
            PostgresSandboxEventStore(pool).register(raw, "original-key") for _ in range(32)
        ))
        assert sum(created for _, created in results) == 1
        assert all(operation == results[0][0] for operation, _ in results)
        async with pool.connection() as conn:
            assert (await (await conn.execute("SELECT count(*) FROM sandbox_events")).fetchone())[0] == 1
        operation = results[0][0]
        # A fresh store/connection observes the committed operation, not local memory.
        assert await PostgresSandboxEventStore(pool).lookup(operation_id=operation.operation_id) == operation
        assert await PostgresSandboxEventStore(pool).lookup(key="original-key") == operation


@pytest.mark.asyncio
@pytest.mark.parametrize("same_key", [True, False])
async def test_conflicting_requests_never_create_a_second_row(same_key):
    async with database() as pool:
        event = str(uuid4())
        results = await asyncio.gather(*(
            PostgresSandboxEventStore(pool).register(
                payload(event, message=f"synthetic-{i}"), "key" if same_key else f"key-{i}",
            ) for i in range(16)
        ), return_exceptions=True)
        assert sum(isinstance(r, tuple) for r in results) == 1
        assert sum(isinstance(r, SandboxEventConflict) for r in results) == 15
        async with pool.connection() as conn:
            assert (await (await conn.execute("SELECT count(*) FROM sandbox_events")).fetchone())[0] == 1


class InterruptingPool:
    def __init__(self, pool, *, lost_ack):
        self.pool, self.lost_ack = pool, lost_ack

    @asynccontextmanager
    async def connection(self):
        async with self.pool.connection() as conn:
            if self.lost_ack:
                yield conn
            else:
                yield FailingConnection(conn)
        if self.lost_ack:
            raise RuntimeError("synthetic lost commit response")


class FailingConnection:
    def __init__(self, conn):
        self.conn = conn

    def transaction(self):
        return self.conn.transaction()

    async def execute(self, sql, args=None):
        if sql.startswith("SELECT"):
            raise RuntimeError("synthetic crash before commit")
        return await self.conn.execute(sql, args)


@pytest.mark.asyncio
@pytest.mark.parametrize("lost_ack", [True, False])
async def test_rollback_or_committed_but_ack_lost_is_never_false_success(lost_ack):
    async with database() as pool:
        store = PostgresSandboxEventStore(InterruptingPool(pool, lost_ack=lost_ack))
        raw = payload()
        with pytest.raises(SandboxEventStoreError):
            await store.register(raw, "original-key")
        restarted = PostgresSandboxEventStore(pool)
        found = await restarted.lookup(key="original-key")
        assert (found is not None) == lost_ack
        async with pool.connection() as conn:
            count = (await (await conn.execute("SELECT count(*) FROM sandbox_events")).fetchone())[0]
        assert count == int(lost_ack)
