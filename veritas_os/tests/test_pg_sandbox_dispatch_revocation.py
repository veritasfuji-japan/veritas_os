"""Exercise local revocation against the real PostgreSQL sandbox dispatch path."""

import asyncio
from contextvars import ContextVar
import os
from uuid import uuid4

import pytest
from pydantic import SecretBytes

from veritas_os.policy.bind_effect_reconciliation import (
    EffectExecutionState,
    PostgresAtomicEffectStateStore,
    SandboxAuthorizationRevocation,
)
from veritas_os.policy.live_adapter_bind_authorization_consumption_store import (
    PostgresAtomicAuthorizationConsumptionStore,
)
from veritas_os.policy.sandbox_bind_execution import SandboxBindExecutionError
from veritas_os.policy.sandbox_https_transport import SandboxHTTPSTransport
from veritas_os.storage import db
from veritas_os.tests.test_sandbox_bind_execution import PAYLOAD, Provider, run
from veritas_os.tests.test_sandbox_https_transport import TOKEN, setup
from veritas_os.tests.test_sandbox_pre_effect import (
    _args,
    issued as issued_fixture,
    prepared_inputs as prepared_inputs_fixture,
)

pytestmark = [
    pytest.mark.postgresql,
    pytest.mark.contention,
    pytest.mark.skipif(not os.getenv("VERITAS_DATABASE_URL"), reason="requires PostgreSQL"),
]

# Issue distinct signed authorizations so permutations do not clear durable rows.
@pytest.fixture
def issued(tmp_path_factory, monkeypatch):
    monkeypatch.setitem(PAYLOAD, "event_id", str(uuid4()))
    return issued_fixture.__wrapped__(tmp_path_factory)


prepared_inputs = pytest.fixture(prepared_inputs_fixture.__wrapped__)


class TransportProvider(Provider):
    """Use a synthetic token that meets the real transport's length contract."""

    async def resolve(self, request, *, expected_metadata_digest):
        resolved = await super().resolve(request, expected_metadata_digest=expected_metadata_digest)
        return resolved.model_copy(update={"material": SecretBytes(TOKEN)})


@pytest.mark.asyncio
@pytest.mark.parametrize("order", ["revoke_first", "dispatch_first", "lost_ack"])
async def test_postgres_orders_revocation_and_dispatch(prepared_inputs, monkeypatch, order):
    from psycopg_pool import AsyncConnectionPool

    artifact, args = await _args(prepared_inputs)
    consumption = prepared_inputs[2]
    effects = PostgresAtomicEffectStateStore()
    consumptions = PostgresAtomicAuthorizationConsumptionStore()
    args.update(effect_store=effects, consumption_store=consumptions, allow_in_memory_for_testing=False)
    transport = SandboxHTTPSTransport(endpoint_url=args["deployment"].endpoint_url)
    writer, connections, _, _ = setup(monkeypatch, b"")  # No external response or network.
    original_transition = effects.transition
    reached = asyncio.Event()
    resume = asyncio.Event()

    async def controlled_transition(**kwargs):
        if order == "revoke_first":
            reached.set()
            await resume.wait()
        committed = await original_transition(**kwargs)
        if order == "dispatch_first":
            reached.set()
            await resume.wait()
        if order == "lost_ack":
            assert committed
            raise OSError("fixture lost the commit response")
        return committed

    monkeypatch.setattr(effects, "transition", controlled_transition)

    async with (
        AsyncConnectionPool(db.build_conninfo(), min_size=1, max_size=1, open=False) as revoker,
        AsyncConnectionPool(db.build_conninfo(), min_size=1, max_size=1, open=False) as dispatcher,
    ):
        current_pool = ContextVar("sandbox_test_pool", default=revoker)

        async def get_pool():
            return current_pool.get()

        async with revoker.connection() as first, dispatcher.connection() as second:
            assert first.info.backend_pid != second.info.backend_pid
        monkeypatch.setattr(db, "get_pool", get_pool)
        assert await consumptions.consume_once(consumption)

        token = current_pool.set(dispatcher)
        try:
            worker = asyncio.create_task(run(artifact, args, TransportProvider(prepared_inputs, args), transport))
        finally:
            current_pool.reset(token)

        if order == "lost_ack":
            with pytest.raises(SandboxBindExecutionError):
                await worker
        else:
            try:
                await asyncio.wait_for(reached.wait(), timeout=10)
                result = await effects.revoke_sandbox_authorization(artifact.authorization_id)
                assert result == (
                    SandboxAuthorizationRevocation.REVOKED_BEFORE_DISPATCH
                    if order == "revoke_first"
                    else SandboxAuthorizationRevocation.DISPATCH_ALREADY_COMMITTED
                )
                assert transport.send_calls == 0 and not writer.writes
            except BaseException:
                worker.cancel()
                await asyncio.gather(worker, return_exceptions=True)
                raise
            finally:
                resume.set()
            if order == "revoke_first":
                with pytest.raises(SandboxBindExecutionError, match="SBE_FAILED_ATTEMPT_NOT_RELEASED"):
                    await worker
            else:
                assert (await worker).state == "UNKNOWN"

        restarted = PostgresAtomicEffectStateStore()
        row = await restarted.get(consumption.consumption_id)
        assert row is not None
        assert row.state == (
            EffectExecutionState.IN_FLIGHT if order == "revoke_first"
            else EffectExecutionState.EFFECT_UNKNOWN
        )
        expected_revocation = (
            SandboxAuthorizationRevocation.REVOKED_BEFORE_DISPATCH if order == "revoke_first"
            else SandboxAuthorizationRevocation.DISPATCH_ALREADY_COMMITTED
        )
        assert await restarted.revoke_sandbox_authorization(artifact.authorization_id) == expected_revocation
        assert not await consumptions.consume_once(consumption)
        args["effect_store"] = restarted
        with pytest.raises(SandboxBindExecutionError):
            await run(artifact, args, TransportProvider(prepared_inputs, args), transport)
        expected_writes = int(order == "dispatch_first")
        assert transport.send_calls == len(connections) == len(writer.writes) == expected_writes
