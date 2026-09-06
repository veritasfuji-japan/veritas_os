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
from veritas_os.policy.native_bind_authorization_consumption import (
    consume_native_bind_authorization,
    NativeAuthorizationConsumptionResult,
    NativeAuthorizationConsumptionError,
)
from veritas_os.tests.test_native_bind_authorization_consumption import (
    consumable as native_consumable_fixture,
    issued as native_issued_fixture,
    api_risk_source as native_source_fixture,
)

consumable = native_consumable_fixture
issued = native_issued_fixture
api_risk_source = native_source_fixture

pytestmark = [pytest.mark.postgresql, pytest.mark.contention]


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _require_real_postgresql() -> None:
    url = os.getenv("VERITAS_DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("real PostgreSQL service container is required")


def _record(
    token: str,
    *,
    authorization_id: str | None = None,
    idempotency_key: str | None = None,
):
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


async def _count_rows(
    *, authorization_id: str | None = None, idempotency_key: str | None = None
) -> int:
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
        await _count_rows(authorization_id=record.live_adapter_bind_authorization_id)
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
    assert (
        first.live_adapter_bind_authorization_id
        != second.live_adapter_bind_authorization_id
    )

    store = PostgresAtomicAuthorizationConsumptionStore()
    outcomes = await asyncio.gather(
        store.consume_once(first),
        store.consume_once(second),
    )

    assert sorted(outcomes) == [False, True]
    assert await _count_rows(idempotency_key=shared_idempotency_key) == 1


@pytest.mark.skipif(
    not os.getenv("VERITAS_DATABASE_URL", "").startswith("postgresql"),
    reason="real PostgreSQL service container is required",
)
@pytest.mark.asyncio
async def test_native_v2_real_verification_and_postgres_race(consumable) -> None:
    """Genuine API lineage, real signatures and four full consumers: one row."""
    from veritas_os.storage.db import close_pool

    authorization, inputs, _ = consumable
    await close_pool()
    try:
        store = PostgresAtomicAuthorizationConsumptionStore()
        outcomes = await asyncio.gather(
            *(
                consume_native_bind_authorization(
                    authorization,
                    **inputs,
                    consumption_store=store,
                )
                for _ in range(4)
            ),
            return_exceptions=True,
        )
        winners = [
            x for x in outcomes if isinstance(x, NativeAuthorizationConsumptionResult)
        ]
        assert len(winners) == 1, outcomes
        assert winners[0].durable_store_used
        losers = [
            x for x in outcomes if isinstance(x, NativeAuthorizationConsumptionError)
        ]
        assert len(losers) == 3
        assert all(str(x) == "NABC_ALREADY_CONSUMED" for x in losers)
        assert await _count_rows(authorization_id=authorization.authorization_id) == 1
        assert await _count_rows(idempotency_key=authorization.idempotency_key) == 1
        assert not winners[0].credential_material_accessed
        assert not winners[0].bind_invoked
        assert not winners[0].external_action_executed
    finally:
        await close_pool()
