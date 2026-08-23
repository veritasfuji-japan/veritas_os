"""Real-PostgreSQL contention tests for authorization consume-once semantics."""

from __future__ import annotations

import asyncio
import hashlib
import os
from uuid import uuid4

import pytest

from veritas_os.policy.live_adapter_bind_authorization_consumption_store import (
    PostgresAtomicAuthorizationConsumptionStore,
    build_authorization_consumption_record,
)
from veritas_os.storage.db import get_pool

pytestmark = [pytest.mark.postgresql, pytest.mark.contention]


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _require_real_postgresql() -> None:
    url = os.getenv("VERITAS_DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("real PostgreSQL service container is required")


def _record(token: str, *, authorization_id: str | None = None, idempotency_key: str | None = None):
    auth_hash = _digest("authorization:" + token)
    return build_authorization_consumption_record(
        live_adapter_bind_authorization_id=(
            authorization_id or f"laba:v1:sha256:{auth_hash}"
        ),
        live_adapter_bind_authorization_hash=auth_hash,
        idempotency_key=(
            idempotency_key or f"laba-idem:v1:sha256:{_digest('idem:' + token)}"
        ),
        bind_context_hash=_digest("bind-context:" + token),
        execution_intent_id="intent:" + token,
        execution_intent_hash=_digest("intent:" + token),
        endpoint_identity_binding_digest=_digest("endpoint:" + token),
        credential_reference_digest=_digest("credential:" + token),
        credential_scope_binding_digest=_digest("scope:" + token),
        consumed_at="2026-08-23T06:00:00+00:00",
    )


async def _count_rows(*, authorization_id: str | None = None, idempotency_key: str | None = None) -> int:
    pool = await get_pool()
    async with pool.connection() as conn:
        if authorization_id is not None:
            cur = await conn.execute(
                "SELECT count(*) FROM bind_authorization_consumptions "
                "WHERE authorization_id = %s",
                (authorization_id,),
            )
        elif idempotency_key is not None:
            cur = await conn.execute(
                "SELECT count(*) FROM bind_authorization_consumptions "
                "WHERE idempotency_key = %s",
                (idempotency_key,),
            )
        else:
            raise AssertionError("one lookup key is required")
        row = await cur.fetchone()
    return int(row[0]) if row else 0


@pytest.mark.asyncio
async def test_real_postgres_allows_exactly_one_concurrent_consumer() -> None:
    """32 concurrent workers racing one authorization produce one winner."""
    _require_real_postgresql()
    token = uuid4().hex
    record = _record(token)
    store = PostgresAtomicAuthorizationConsumptionStore()

    outcomes = await asyncio.gather(*(store.consume_once(record) for _ in range(32)))

    assert outcomes.count(True) == 1
    assert outcomes.count(False) == 31
    assert (
        await _count_rows(
            authorization_id=record.live_adapter_bind_authorization_id
        )
        == 1
    )


@pytest.mark.asyncio
async def test_real_postgres_idempotency_key_is_unique_across_authorizations() -> None:
    """Different authorization IDs cannot consume the same idempotency key."""
    _require_real_postgresql()
    token = uuid4().hex
    shared_idempotency_key = f"laba-idem:v1:sha256:{_digest('shared:' + token)}"
    first = _record(
        token + ":a",
        idempotency_key=shared_idempotency_key,
    )
    second = _record(
        token + ":b",
        idempotency_key=shared_idempotency_key,
    )
    assert first.live_adapter_bind_authorization_id != second.live_adapter_bind_authorization_id

    store = PostgresAtomicAuthorizationConsumptionStore()
    outcomes = await asyncio.gather(
        store.consume_once(first),
        store.consume_once(second),
    )

    assert sorted(outcomes) == [False, True]
    assert await _count_rows(idempotency_key=shared_idempotency_key) == 1
