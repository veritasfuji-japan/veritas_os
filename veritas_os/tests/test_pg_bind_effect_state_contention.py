"""Real-PostgreSQL contention tests for bind effect-state CAS semantics."""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest

from veritas_os.policy.bind_effect_reconciliation import (
    EffectExecutionState,
    PostgresAtomicEffectStateStore,
    _build_record,
)
from veritas_os.policy.live_adapter_bind_authorization_consumption_store import (
    build_authorization_consumption_record,
    PostgresAtomicAuthorizationConsumptionStore,
)

pytestmark = [pytest.mark.postgresql, pytest.mark.contention]


def _require_real_postgresql() -> None:
    if not os.getenv("VERITAS_DATABASE_URL", "").startswith("postgresql"):
        pytest.skip("real PostgreSQL service container is required")


def _consumption(token: str):
    return build_authorization_consumption_record(
        live_adapter_bind_authorization_id=f"auth-{token}",
        live_adapter_bind_authorization_hash="a" * 64,
        idempotency_key=f"idem-{token}",
        bind_context_hash="b" * 64,
        execution_intent_id=f"intent-{token}",
        execution_intent_hash="c" * 64,
        endpoint_identity_binding_digest="endpoint",
        credential_reference_digest="credential",
        credential_scope_binding_digest="scope",
        consumed_at="2026-08-24T00:00:00+00:00",
    )


@pytest.mark.asyncio
async def test_real_postgres_effect_state_transition_has_one_winner() -> None:
    _require_real_postgresql()
    token = uuid4().hex
    consumption = _consumption(token)
    store = PostgresAtomicEffectStateStore()
    inflight = _build_record(
        consumption=consumption,
        state=EffectExecutionState.IN_FLIGHT,
        revision=1,
        updated_at="2026-08-24T00:00:00+00:00",
        reason_code="TEST_IN_FLIGHT",
    )
    assert await store.create_in_flight(inflight)

    candidates = [
        _build_record(
            consumption=consumption,
            state=EffectExecutionState.EFFECT_UNKNOWN,
            revision=2,
            updated_at="2026-08-24T00:00:01+00:00",
            reason_code=f"RACE_{index}",
        )
        for index in range(32)
    ]
    outcomes = await asyncio.gather(
        *(
            store.transition(
                operation_id=consumption.consumption_id,
                expected_state=EffectExecutionState.IN_FLIGHT,
                record=candidate,
            )
            for candidate in candidates
        )
    )
    assert outcomes.count(True) == 1
    assert outcomes.count(False) == 31
    stored = await store.get(consumption.consumption_id)
    assert stored is not None
    assert stored.state == EffectExecutionState.EFFECT_UNKNOWN
    assert stored.revision == 2


@pytest.mark.asyncio
async def test_real_postgres_consumption_read_and_attempt_creation_have_one_winner() -> None:
    """Separate store instances share durable ownership, including after restart."""
    _require_real_postgresql()
    consumption = _consumption(uuid4().hex)
    consumptions = PostgresAtomicAuthorizationConsumptionStore()
    assert await consumptions.get(consumption.live_adapter_bind_authorization_id) is None
    assert await consumptions.consume_once(consumption)
    assert await PostgresAtomicAuthorizationConsumptionStore().get(
        consumption.live_adapter_bind_authorization_id
    ) == consumption
    attempt = _build_record(
        consumption=consumption, state=EffectExecutionState.IN_FLIGHT,
        revision=1, updated_at=consumption.consumed_at,
        reason_code="SANDBOX_PRE_EFFECT_ATTEMPT_CLAIMED",
    )
    outcomes = await asyncio.gather(*(
        PostgresAtomicEffectStateStore().create_in_flight(attempt) for _ in range(32)
    ))
    assert outcomes.count(True) == 1
    assert outcomes.count(False) == 31
    restarted = PostgresAtomicEffectStateStore()
    assert await restarted.get(attempt.operation_id) == attempt
    assert not await restarted.create_in_flight(attempt)


@pytest.mark.asyncio
async def test_real_postgres_archive_atomicity_contention_and_restart(monkeypatch):
    """A failed commit preserves UNKNOWN; an acknowledged-lost commit retains both."""
    from contextlib import asynccontextmanager
    from veritas_os.storage import db
    from veritas_os.policy.bind_effect_reconciliation import BindEffectStateError
    from veritas_os.tests.test_sandbox_reconciliation_archive import archive_case

    _require_real_postgresql()
    real_get_pool = db.get_pool
    pool = await real_get_pool()
    original, terminal, archive = archive_case(uuid4().hex)
    store = PostgresAtomicEffectStateStore()
    assert await store.create_in_flight(original)

    class FaultPool:
        def __init__(self, mode):
            self.mode = mode

        @asynccontextmanager
        async def connection(self):
            async with pool.connection() as conn:
                yield conn
                if self.mode == "rollback":
                    raise RuntimeError("synthetic commit failure")
            if self.mode == "lost_ack":
                raise RuntimeError("synthetic acknowledgement loss")

    for mode in ("rollback", "lost_ack"):
        async def faulty_pool(mode=mode):
            return FaultPool(mode)

        monkeypatch.setattr(db, "get_pool", faulty_pool)
        with pytest.raises(BindEffectStateError) as caught:
            await store.confirm_reconciliation(expected=original, record=terminal, archive=archive)
        assert caught.value.__context__ is None
        monkeypatch.setattr(db, "get_pool", real_get_pool)
        restarted = PostgresAtomicEffectStateStore()
        if mode == "rollback":
            assert await restarted.get(original.operation_id) == original
            async with pool.connection() as conn:
                cur = await conn.execute("SELECT reconciliation_archive FROM bind_effect_states WHERE operation_id=%s", (original.operation_id,))
                assert (await cur.fetchone())[0] is None
        else:
            assert await restarted.get(original.operation_id) == terminal
            assert await restarted.get_reconciliation(original.operation_id) == archive
            assert not await restarted.confirm_reconciliation(expected=original, record=terminal, archive=archive)
            assert not await restarted.transition(operation_id=terminal.operation_id, expected_state=terminal.state,
                                                  record=terminal.model_copy(update={"revision": 4}))

    original, terminal, archive = archive_case(uuid4().hex)
    assert await store.create_in_flight(original)
    outcomes = await asyncio.gather(*(PostgresAtomicEffectStateStore().confirm_reconciliation(
        expected=original, record=terminal, archive=archive,
    ) for _ in range(16)))
    assert outcomes.count(True) == 1
    assert await PostgresAtomicEffectStateStore().get_reconciliation(original.operation_id) == archive
    # Corrupt the persisted evidence while retaining the terminal row: reads must fail.
    async with pool.connection() as conn:
        await conn.execute("UPDATE bind_effect_states SET reconciliation_archive=NULL WHERE operation_id=%s", (original.operation_id,))
    with pytest.raises(BindEffectStateError):
        await store.get_reconciliation(original.operation_id)
