"""Exercise local revocation against the real PostgreSQL sandbox dispatch path."""

import asyncio
from contextlib import asynccontextmanager
from contextvars import ContextVar
import os
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import SecretBytes

from veritas_os.policy.bind_effect_reconciliation import (
    EffectExecutionState,
    InMemoryAtomicEffectStateStore,
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


@asynccontextmanager
async def operator_session(admin_pool, authorization_id):
    import psycopg
    from psycopg import sql
    from psycopg.errors import InsufficientPrivilege

    role = f"sandbox_operator_{uuid4().hex}"
    password = uuid4().hex
    principal = sql.Identifier(role)
    async with admin_pool.connection() as admin:
        await admin.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(principal, sql.Literal(password)))
    try:
        async with await psycopg.AsyncConnection.connect(
            db.build_conninfo(), user=role, password=password, autocommit=True,
        ) as operator:
            call = "SELECT * FROM public.revoke_sandbox_authorization(%s, %s)"
            with pytest.raises(InsufficientPrivilege, match="permission denied for function"):
                await operator.execute(call, (authorization_id, "fixture cancellation"))
            async with admin_pool.connection() as admin:
                await admin.execute(
                    sql.SQL("GRANT EXECUTE ON FUNCTION public.revoke_sandbox_authorization(text, text) TO {}")
                    .format(principal)
                )
            with pytest.raises(InsufficientPrivilege, match="scope denied"):
                await operator.execute(call, (authorization_id, "fixture cancellation"))
            with pytest.raises(InsufficientPrivilege):
                await operator.execute("SELECT * FROM public.bind_sandbox_revocation_audit")
            async with admin_pool.connection() as admin:
                await admin.execute(
                    "INSERT INTO public.bind_sandbox_revocation_grants (operator_role, authorization_id) "
                    "SELECT oid, %s FROM pg_catalog.pg_roles WHERE rolname = %s",
                    (authorization_id, role),
                )
            yield operator, role
    finally:
        async with admin_pool.connection() as admin:
            await admin.execute(
                "DELETE FROM public.bind_sandbox_revocation_grants "
                "WHERE operator_role = (SELECT oid FROM pg_catalog.pg_roles WHERE rolname = %s)", (role,),
            )
            await admin.execute(
                sql.SQL("REVOKE EXECUTE ON FUNCTION public.revoke_sandbox_authorization(text, text) FROM {}")
                .format(principal)
            )
            await admin.execute(sql.SQL("DROP ROLE {}").format(principal))


@pytest.mark.asyncio
@pytest.mark.parametrize("store_type", [InMemoryAtomicEffectStateStore, PostgresAtomicEffectStateStore])
async def test_revocation_rejects_noncanonical_ids(store_type, monkeypatch):
    async def unexpected_pool():
        pytest.fail("Malformed revocation must not reach PostgreSQL")

    monkeypatch.setattr(db, "get_pool", unexpected_pool)
    store = store_type()
    canonical = "laba:v2:sha256:" + "a" * 64
    for invalid in ("", f" {canonical}", f"{canonical}\n", canonical.upper(), canonical[:-1]):
        with pytest.raises(ValueError, match="canonical native sandbox authorization ID"):
            await store.revoke_sandbox_authorization(invalid)


def test_downgrade_preserves_committed_revocations():
    import psycopg
    from alembic.config import Config
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from alembic.script import ScriptDirectory
    from sqlalchemy import create_engine
    from sqlalchemy.exc import DBAPIError

    root = Path(__file__).resolve().parents[2]
    migration = ScriptDirectory.from_config(Config(str(root / "alembic.ini"))).get_revision("0014")
    assert migration is not None
    engine = create_engine("postgresql+psycopg://", creator=lambda: psycopg.connect(db.build_conninfo()))
    try:
        with engine.begin() as conn:
            # Shadow the migrated table within this connection only.
            conn.exec_driver_sql(
                "CREATE TEMP TABLE bind_sandbox_dispatch_order "
                "(authorization_id text PRIMARY KEY, resolution text NOT NULL) ON COMMIT DROP"
            )
            conn.exec_driver_sql(
                "INSERT INTO bind_sandbox_dispatch_order VALUES "
                "('revoked', 'REVOKED_BEFORE_DISPATCH'), ('dispatched', 'DISPATCH_ALREADY_COMMITTED')"
            )
            with Operations.context(MigrationContext.configure(conn)):
                with pytest.raises(DBAPIError, match="Cannot downgrade 0014"), conn.begin_nested():
                    migration.module.downgrade()
                assert conn.exec_driver_sql(
                    "SELECT resolution FROM pg_temp.bind_sandbox_dispatch_order WHERE authorization_id = 'revoked'"
                ).scalar_one() == "REVOKED_BEFORE_DISPATCH"
                conn.exec_driver_sql("DELETE FROM pg_temp.bind_sandbox_dispatch_order WHERE authorization_id = 'revoked'")
                migration.module.downgrade()
            assert conn.exec_driver_sql(
                "SELECT to_regclass('pg_temp.bind_sandbox_dispatch_order')"
            ).scalar_one() is None
    finally:
        engine.dispose()


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

        async def revoke_as_operator():
            reason = "Fixture cancellation"
            statement = "SELECT * FROM public.revoke_sandbox_authorization(%s, %s)"
            async with operator_session(revoker, artifact.authorization_id) as (operator, role):
                if order == "revoke_first":
                    async with operator.transaction(force_rollback=True):
                        await operator.execute(statement, (artifact.authorization_id, reason))
                    async with revoker.connection() as admin:
                        cur = await admin.execute(
                            "SELECT (SELECT count(*) FROM public.bind_sandbox_dispatch_order WHERE authorization_id = %s), "
                            "(SELECT count(*) FROM public.bind_sandbox_revocation_audit WHERE authorization_id = %s)",
                            (artifact.authorization_id, artifact.authorization_id),
                        )
                        assert await cur.fetchone() == (0, 0)
                cur = await operator.execute(statement, (artifact.authorization_id, reason))
                audit_id, resolution = await cur.fetchone()
                async with revoker.connection() as admin:
                    cur = await admin.execute(
                        "SELECT operator_name, authorization_id, reason, resolution "
                        "FROM public.bind_sandbox_revocation_audit WHERE audit_id = %s", (audit_id,),
                    )
                    assert await cur.fetchone() == (role, artifact.authorization_id, reason, resolution)
                return SandboxAuthorizationRevocation(resolution)

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
                result = await revoke_as_operator()
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
