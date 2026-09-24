"""Real-PostgreSQL contention tests for bind effect-state CAS semantics."""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest

from veritas_os.policy.bind_effect_reconciliation import (
    EffectExecutionState,
    SandboxOwnershipState,
    PostgresAtomicEffectStateStore,
    _build_record,
    _immutable_effect_lineage_digest,
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
async def test_real_postgres_unknown_never_releases_business_event_claim() -> None:
    _require_real_postgresql()
    key = "sandbox-business-event:v1:sha256:" + uuid4().hex + uuid4().hex
    first = _consumption(uuid4().hex)
    replacement = _consumption(uuid4().hex)
    store = PostgresAtomicEffectStateStore()
    original = _build_record(
        consumption=first, state=EffectExecutionState.IN_FLIGHT,
        revision=1, updated_at=first.consumed_at,
        reason_code="SANDBOX_PRE_EFFECT_ATTEMPT_CLAIMED",
    )
    assert await store.create_in_flight(original, business_event_key=key)
    unknown = _build_record(
        consumption=first, state=EffectExecutionState.EFFECT_UNKNOWN,
        revision=2, updated_at="2026-08-24T00:00:01+00:00",
        reason_code="SANDBOX_DISPATCH_INTENT_PERSISTED_EFFECT_UNCONFIRMED",
    )
    assert await store.transition(
        operation_id=original.operation_id,
        expected_state=EffectExecutionState.IN_FLIGHT,
        record=unknown,
    )
    replacement_record = _build_record(
        consumption=replacement, state=EffectExecutionState.IN_FLIGHT,
        revision=1, updated_at=replacement.consumed_at,
        reason_code="SANDBOX_PRE_EFFECT_ATTEMPT_CLAIMED",
    )
    results = await asyncio.gather(*(
        PostgresAtomicEffectStateStore().create_in_flight(
            replacement_record, business_event_key=key,
        )
        for _ in range(8)
    ))
    assert results == [False] * 8
    assert await store.get(replacement_record.operation_id) is None

    no_effect = _build_record(
        consumption=first, state=EffectExecutionState.CONFIRMED_NO_EFFECT,
        revision=3, updated_at="2026-08-24T00:00:02+00:00",
        reason_code="VERIFIED_EXTERNAL_NO_EFFECT_CONFIRMED",
    )
    assert not await store.transition(
        operation_id=unknown.operation_id,
        expected_state=EffectExecutionState.EFFECT_UNKNOWN,
        record=no_effect,
    )
    assert not await PostgresAtomicEffectStateStore().create_in_flight(
        replacement_record, business_event_key=key,
    )


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


@pytest.mark.asyncio
async def test_real_postgres_receipt_pair_write_once_rollback_and_lost_ack(monkeypatch):
    """Storage semantics for an owning publisher's already reconstructed pair."""
    from contextlib import asynccontextmanager
    from veritas_os.storage import db
    from veritas_os.policy.sandbox_receipt_store import _persist_receipts
    from veritas_os.tests.test_sandbox_reconciliation_archive import archive_case

    _require_real_postgresql()
    original, record, archive = archive_case(uuid4().hex)
    store = PostgresAtomicEffectStateStore()
    assert await store.create_in_flight(original)
    assert await store.confirm_reconciliation(expected=original, record=record, archive=archive)
    # Synthetic pair sent only to the internal storage seam, never claimed as verified artifacts.
    pair = {"bind_receipt": {"test": "bind"}, "outcome_receipt": {"test": "outcome"}}
    real_get_pool = db.get_pool
    pool = await real_get_pool()

    class FaultPool:
        def __init__(self, mode):
            self.mode = mode

        @asynccontextmanager
        async def connection(self):
            async with pool.connection() as conn:
                yield conn
                if self.mode == "rollback":
                    raise RuntimeError("synthetic rollback")
            if self.mode == "lost_ack":
                raise RuntimeError("synthetic lost acknowledgement")

    for mode in ("rollback", "lost_ack"):
        async def faulty_pool(mode=mode):
            return FaultPool(mode)
        monkeypatch.setattr(db, "get_pool", faulty_pool)
        with pytest.raises(RuntimeError):
            await _persist_receipts(store, record=record, archive=archive, bundle=pair)
        monkeypatch.setattr(db, "get_pool", real_get_pool)
        async with pool.connection() as conn:
            cur = await conn.execute("SELECT sandbox_receipt_bundle FROM bind_effect_states WHERE operation_id=%s", (record.operation_id,))
            assert (await cur.fetchone())[0] == (None if mode == "rollback" else pair)
        assert await store.get(record.operation_id) == record
        assert await store.get_reconciliation(record.operation_id) == archive

    await _persist_receipts(PostgresAtomicEffectStateStore(), record=record, archive=archive, bundle=pair)
    with pytest.raises(ValueError):
        await _persist_receipts(store, record=record, archive=archive, bundle={"different": True})
    original, record, archive = archive_case(uuid4().hex)
    assert await store.create_in_flight(original)
    assert await store.confirm_reconciliation(expected=original, record=record, archive=archive)
    await asyncio.gather(*(_persist_receipts(PostgresAtomicEffectStateStore(), record=record, archive=archive, bundle=pair) for _ in range(16)))
    async with pool.connection() as conn:
        cur = await conn.execute("SELECT sandbox_receipt_bundle FROM bind_effect_states WHERE operation_id=%s", (record.operation_id,))
        assert (await cur.fetchone())[0] == pair
    assert await store.get(record.operation_id) == record


@pytest.mark.asyncio
async def test_real_postgres_pre_dispatch_recovery_releases_business_event_claim() -> None:
    """Crash recovery closes only exact pre-dispatch state and permits a fresh claim."""
    from veritas_os.policy.sandbox_recovery import _confirm_pre_dispatch_no_effect

    _require_real_postgresql()
    key = "sandbox-business-event:v1:sha256:" + uuid4().hex + uuid4().hex
    first = _consumption(uuid4().hex)
    replacement = _consumption(uuid4().hex)
    store = PostgresAtomicEffectStateStore()
    inflight = await store.create_sandbox_pre_dispatch_attempt(
        consumption=first,
        updated_at=first.consumed_at,
        business_event_key=key,
        ownership_digest="d" * 64,
    )
    assert inflight is not None

    terminal = await _confirm_pre_dispatch_no_effect(
        consumption=first,
        current=inflight,
        effect_store=PostgresAtomicEffectStateStore(),
        observed_at="2026-08-24T00:00:01+00:00",
    )
    assert terminal.state == EffectExecutionState.CONFIRMED_NO_EFFECT
    assert await PostgresAtomicEffectStateStore().get(inflight.operation_id) == terminal

    replacement_record = _build_record(
        consumption=replacement,
        state=EffectExecutionState.IN_FLIGHT,
        revision=1,
        updated_at=replacement.consumed_at,
        reason_code="SANDBOX_PRE_EFFECT_ATTEMPT_CLAIMED",
    )
    assert await PostgresAtomicEffectStateStore().create_in_flight(
        replacement_record,
        business_event_key=key,
    )



@pytest.mark.asyncio
async def test_real_postgres_ownership_and_no_effect_share_one_arbitration_predicate() -> None:
    """32 ownership contenders and recovery can produce only one durable winner."""
    _require_real_postgresql()
    token = uuid4().hex
    consumption = _consumption(token)
    key = "sandbox-business-event:v1:sha256:" + uuid4().hex + uuid4().hex
    ownership_digest = "d" * 64
    creator = PostgresAtomicEffectStateStore()
    origin = await creator.create_sandbox_pre_dispatch_attempt(
        consumption=consumption,
        updated_at=consumption.consumed_at,
        business_event_key=key,
        ownership_digest=ownership_digest,
    )
    assert origin is not None
    lineage = _immutable_effect_lineage_digest(origin)

    start = asyncio.Event()

    async def consume(index: int):
        await start.wait()
        return await PostgresAtomicEffectStateStore().consume_sandbox_ownership(
            expected=origin,
            ownership_digest=ownership_digest,
            immutable_lineage_digest=lineage,
            updated_at=f"2026-08-24T00:00:{index + 1:02d}+00:00",
        )

    async def recover():
        await start.wait()
        return await PostgresAtomicEffectStateStore().confirm_pre_dispatch_no_effect(
            expected=origin,
            updated_at="2026-08-24T00:01:00+00:00",
        )

    ownership_tasks = [asyncio.create_task(consume(i)) for i in range(32)]
    recovery_task = asyncio.create_task(recover())
    start.set()
    ownership_results = await asyncio.gather(*ownership_tasks)
    recovery_result = await recovery_task

    ownership_successes = ownership_results.count(True)
    no_effect_successes = int(recovery_result is not None)
    assert ownership_successes <= 1
    assert no_effect_successes <= 1
    assert ownership_successes + no_effect_successes == 1

    restarted = PostgresAtomicEffectStateStore()
    effect = await restarted.get(origin.operation_id)
    ownership = await restarted.get_sandbox_ownership(origin.operation_id)
    assert effect is not None and ownership is not None
    assert not (
        ownership.state == SandboxOwnershipState.CONSUMED
        and effect.state == EffectExecutionState.CONFIRMED_NO_EFFECT
    )

    if ownership_successes == 1:
        assert ownership.state == SandboxOwnershipState.CONSUMED
        assert effect.state == EffectExecutionState.IN_FLIGHT
        assert await restarted.confirm_pre_dispatch_no_effect(
            expected=origin,
            updated_at="2026-08-24T00:02:00+00:00",
        ) is None
    else:
        assert ownership.state == SandboxOwnershipState.CANCELLED
        assert effect.state == EffectExecutionState.CONFIRMED_NO_EFFECT
        assert not await restarted.consume_sandbox_ownership(
            expected=origin,
            ownership_digest=ownership_digest,
            immutable_lineage_digest=lineage,
            updated_at="2026-08-24T00:02:00+00:00",
        )


@pytest.mark.asyncio
async def test_real_postgres_consumed_ownership_survives_restart_and_blocks_no_effect() -> None:
    _require_real_postgresql()
    consumption = _consumption(uuid4().hex)
    key = "sandbox-business-event:v1:sha256:" + uuid4().hex + uuid4().hex
    digest = "e" * 64
    store = PostgresAtomicEffectStateStore()
    origin = await store.create_sandbox_pre_dispatch_attempt(
        consumption=consumption,
        updated_at=consumption.consumed_at,
        business_event_key=key,
        ownership_digest=digest,
    )
    assert origin is not None
    assert await store.consume_sandbox_ownership(
        expected=origin,
        ownership_digest=digest,
        immutable_lineage_digest=_immutable_effect_lineage_digest(origin),
        updated_at="2026-08-24T00:00:01+00:00",
    )

    restarted = PostgresAtomicEffectStateStore()
    assert await restarted.confirm_pre_dispatch_no_effect(
        expected=origin,
        updated_at="2026-08-24T00:00:02+00:00",
    ) is None
    effect = await restarted.get(origin.operation_id)
    ownership = await restarted.get_sandbox_ownership(origin.operation_id)
    assert effect is not None and effect.state == EffectExecutionState.IN_FLIGHT
    assert ownership is not None and ownership.state == SandboxOwnershipState.CONSUMED


@pytest.mark.asyncio
async def test_real_postgres_no_effect_cancels_ownership_and_releases_replacement_claim() -> None:
    _require_real_postgresql()
    key = "sandbox-business-event:v1:sha256:" + uuid4().hex + uuid4().hex
    first = _consumption(uuid4().hex)
    replacement = _consumption(uuid4().hex)
    digest = "f" * 64
    store = PostgresAtomicEffectStateStore()
    origin = await store.create_sandbox_pre_dispatch_attempt(
        consumption=first,
        updated_at=first.consumed_at,
        business_event_key=key,
        ownership_digest=digest,
    )
    assert origin is not None
    terminal = await store.confirm_pre_dispatch_no_effect(
        expected=origin,
        updated_at="2026-08-24T00:00:01+00:00",
    )
    assert terminal is not None and terminal.state == EffectExecutionState.CONFIRMED_NO_EFFECT

    restarted = PostgresAtomicEffectStateStore()
    ownership = await restarted.get_sandbox_ownership(origin.operation_id)
    assert ownership is not None and ownership.state == SandboxOwnershipState.CANCELLED
    assert not await restarted.consume_sandbox_ownership(
        expected=origin,
        ownership_digest=digest,
        immutable_lineage_digest=_immutable_effect_lineage_digest(origin),
        updated_at="2026-08-24T00:00:02+00:00",
    )

    replacement_origin = await restarted.create_sandbox_pre_dispatch_attempt(
        consumption=replacement,
        updated_at=replacement.consumed_at,
        business_event_key=key,
        ownership_digest="1" * 64,
    )
    assert replacement_origin is not None



@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["ownership", "no_effect"])
async def test_real_postgres_arbitration_update_failure_rolls_back_atomically(
    monkeypatch, target,
) -> None:
    """Raise after the security-sensitive UPDATE but before transaction commit."""
    from contextlib import asynccontextmanager
    from veritas_os.storage import db
    from veritas_os.policy.bind_effect_reconciliation import BindEffectStateError

    _require_real_postgresql()
    consumption = _consumption(uuid4().hex)
    key = "sandbox-business-event:v1:sha256:" + uuid4().hex + uuid4().hex
    digest = "7" * 64
    store = PostgresAtomicEffectStateStore()
    origin = await store.create_sandbox_pre_dispatch_attempt(
        consumption=consumption,
        updated_at=consumption.consumed_at,
        business_event_key=key,
        ownership_digest=digest,
    )
    assert origin is not None
    lineage = _immutable_effect_lineage_digest(origin)

    real_get_pool = db.get_pool
    pool = await real_get_pool()

    class FaultConn:
        def __init__(self, conn):
            self._conn = conn

        def transaction(self):
            return self._conn.transaction()

        async def execute(self, sql, params=()):
            cur = await self._conn.execute(sql, params)
            normalized = " ".join(sql.split())
            if (
                target == "ownership"
                and normalized.startswith("UPDATE bind_effect_states SET ownership_state=")
            ) or (
                target == "no_effect"
                and normalized.startswith("UPDATE bind_effect_states SET state=")
                and "business_event_key=NULL" in normalized
            ):
                raise RuntimeError("synthetic pre-commit connection loss")
            return cur

    class FaultPool:
        @asynccontextmanager
        async def connection(self):
            async with pool.connection() as conn:
                yield FaultConn(conn)

    async def faulty_pool():
        return FaultPool()

    monkeypatch.setattr(db, "get_pool", faulty_pool)
    if target == "ownership":
        with pytest.raises(BindEffectStateError, match="BES_POSTGRES_OWNERSHIP_CONSUME_FAILED"):
            await PostgresAtomicEffectStateStore().consume_sandbox_ownership(
                expected=origin,
                ownership_digest=digest,
                immutable_lineage_digest=lineage,
                updated_at="2026-08-24T00:00:01+00:00",
            )
    else:
        with pytest.raises(BindEffectStateError, match="BES_POSTGRES_NO_EFFECT_ARBITRATION_FAILED"):
            await PostgresAtomicEffectStateStore().confirm_pre_dispatch_no_effect(
                expected=origin,
                updated_at="2026-08-24T00:00:01+00:00",
            )

    monkeypatch.setattr(db, "get_pool", real_get_pool)
    restarted = PostgresAtomicEffectStateStore()
    effect = await restarted.get(origin.operation_id)
    ownership = await restarted.get_sandbox_ownership(origin.operation_id)
    assert effect == origin
    assert ownership is not None and ownership.state == SandboxOwnershipState.AVAILABLE

    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT business_event_key FROM bind_effect_states WHERE operation_id=%s",
            (origin.operation_id,),
        )
        assert (await cur.fetchone())[0] == key


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["ownership", "no_effect"])
async def test_real_postgres_arbitration_commit_ack_loss_is_classified_only_by_readback(
    monkeypatch, target,
) -> None:
    """Commit may succeed before result loss; durable readback must show one winner."""
    from veritas_os.storage import db
    from veritas_os.policy.bind_effect_reconciliation import BindEffectStateError

    _require_real_postgresql()
    consumption = _consumption(uuid4().hex)
    key = "sandbox-business-event:v1:sha256:" + uuid4().hex + uuid4().hex
    digest = "8" * 64
    store = PostgresAtomicEffectStateStore()
    origin = await store.create_sandbox_pre_dispatch_attempt(
        consumption=consumption,
        updated_at=consumption.consumed_at,
        business_event_key=key,
        ownership_digest=digest,
    )
    assert origin is not None
    lineage = _immutable_effect_lineage_digest(origin)

    if target == "ownership":
        original = store.consume_sandbox_ownership

        async def lost_ack(**kwargs):
            assert await original(**kwargs) is True
            raise BindEffectStateError("BES_POSTGRES_OWNERSHIP_CONSUME_FAILED")

        monkeypatch.setattr(store, "consume_sandbox_ownership", lost_ack)
        with pytest.raises(BindEffectStateError):
            await store.consume_sandbox_ownership(
                expected=origin,
                ownership_digest=digest,
                immutable_lineage_digest=lineage,
                updated_at="2026-08-24T00:00:01+00:00",
            )
    else:
        original = store.confirm_pre_dispatch_no_effect

        async def lost_ack(**kwargs):
            assert await original(**kwargs) is not None
            raise BindEffectStateError("BES_POSTGRES_NO_EFFECT_ARBITRATION_FAILED")

        monkeypatch.setattr(store, "confirm_pre_dispatch_no_effect", lost_ack)
        with pytest.raises(BindEffectStateError):
            await store.confirm_pre_dispatch_no_effect(
                expected=origin,
                updated_at="2026-08-24T00:00:01+00:00",
            )

    restarted = PostgresAtomicEffectStateStore()
    effect = await restarted.get(origin.operation_id)
    ownership = await restarted.get_sandbox_ownership(origin.operation_id)
    assert effect is not None and ownership is not None

    if target == "ownership":
        assert ownership.state == SandboxOwnershipState.CONSUMED
        assert effect.state == EffectExecutionState.IN_FLIGHT
        assert await restarted.confirm_pre_dispatch_no_effect(
            expected=origin,
            updated_at="2026-08-24T00:00:02+00:00",
        ) is None
    else:
        assert ownership.state == SandboxOwnershipState.CANCELLED
        assert effect.state == EffectExecutionState.CONFIRMED_NO_EFFECT
        assert not await restarted.consume_sandbox_ownership(
            expected=origin,
            ownership_digest=digest,
            immutable_lineage_digest=lineage,
            updated_at="2026-08-24T00:00:02+00:00",
        )
