"""Fail closed before any staging rehearsal reaches the Keycloak executor."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from psycopg import OperationalError

from veritas_os.api import keycloak_staging_rehearsal as rehearsal
from veritas_os.api import server
from veritas_os.policy.keycloak_role_grant_binding import (
    KeycloakLabDeployment,
    KeycloakRoleGrantTarget,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def staging(monkeypatch):
    settings = {
        "VERITAS_ENV": "staging",
        "VERITAS_POSTURE": "staging",
        "VERITAS_ENABLE_KEYCLOAK_STAGING_REHEARSAL": "1",
        "VERITAS_HALT_BACKEND": "postgresql",
        "VERITAS_DEPLOYMENT_ID": "veritas-rehearsal-test",
        "VERITAS_DATABASE_URL": "postgresql://127.0.0.1/veritas_rehearsal_test",
    }
    for key, value in settings.items():
        monkeypatch.setenv(key, value)
    for key in ("PGSERVICE", "PGHOSTADDR"):
        monkeypatch.delenv(key, raising=False)

    deployment = KeycloakLabDeployment(
        target=rehearsal_target(),
        tls_port=8443,
        ca_pem="fixtures-only",
        writer_user="00000000-0000-4000-8000-000000000001",
        writer_client="writer",
        audit_reader_client="audit",
        mapping_reader_client="mapping",
        writer_reference_id="test",
        writer_scope="test",
    )
    monkeypatch.setenv("VERITAS_KEYCLOAK_STAGING_DEPLOYMENT_SHA256", deployment.digest())

    events = []
    conn = SimpleNamespace(
        info=SimpleNamespace(dbname="veritas_rehearsal_test", hostaddr="127.0.0.1"),
        execute=AsyncMock(return_value=SimpleNamespace(fetchone=AsyncMock(return_value=(False,)))),
    )

    @asynccontextmanager
    async def connection():
        yield conn

    @asynccontextmanager
    async def lifespan(app):
        assert app is server.app
        events.append("startup")
        try:
            yield
        finally:
            events.append("shutdown")

    monkeypatch.setattr(server.app.router, "lifespan_context", lifespan)
    monkeypatch.setattr(rehearsal.db, "get_pool", AsyncMock(return_value=SimpleNamespace(
        connection=connection,
    )))
    close = AsyncMock(side_effect=lambda: events.append("pool-close"))
    monkeypatch.setattr(rehearsal.db, "close_pool", close)
    halt = Mock(return_value={"halted": False})
    monkeypatch.setattr(rehearsal.shared_halt, "status", halt)
    execute = AsyncMock(return_value=None, side_effect=lambda *_a, **_kw: events.append("dispatch"))
    executor = Mock(return_value=SimpleNamespace(execute=execute))
    monkeypatch.setattr(rehearsal, "KeycloakLabExecutor", executor)
    return SimpleNamespace(
        events=events, connection=conn, execute=execute, executor=executor, halt=halt,
        worker=lambda: rehearsal.keycloak_staging_rehearsal_worker(
            deployment,
            authorization=object(),
            event_id="synthetic-event",
            attempt_id="synthetic-attempt",
            issuance_source_inputs=object(),
            governance_inputs=object(),
            trust_inputs=object(),
            trusted_clock=Mock(),
            load_current_inputs=Mock(),
            resolve_writer=AsyncMock(),
        ),
    )


def rehearsal_target():
    return KeycloakRoleGrantTarget(
        origin="https://keycloak.invalid",
        realm_name="veritas-rehearsal-test",
        realm_id="00000000-0000-4000-8000-000000000002",
        user_id="00000000-0000-4000-8000-000000000003",
        client_id="00000000-0000-4000-8000-000000000004",
        role_id="00000000-0000-4000-8000-000000000005",
        role_name="synthetic",
    )


@pytest.mark.parametrize(("key", "value", "reason"), [
    ("VERITAS_ENV", "production", "DISABLED"),
    ("VERITAS_ENABLE_KEYCLOAK_STAGING_REHEARSAL", "0", "DISABLED"),
    ("VERITAS_POSTURE", "prod", "DISABLED"),
    ("VERITAS_KEYCLOAK_STAGING_DEPLOYMENT_SHA256", "different", "DEPLOYMENT_MISMATCH"),
    ("VERITAS_DATABASE_URL", "postgresql://127.0.0.1/veritas", "DATABASE_INVALID"),
    ("VERITAS_DATABASE_URL", "postgresql://10.0.0.1/veritas_rehearsal_test", "DATABASE_INVALID"),
    ("VERITAS_HALT_BACKEND", "memory", "HALT_SCOPE_INVALID"),
])
async def test_configuration_is_checked_before_startup(staging, monkeypatch, key, value, reason):
    monkeypatch.setenv(key, value)
    with pytest.raises(rehearsal.KeycloakStagingRehearsalBlocked, match=reason):
        async with staging.worker():
            pytest.fail("startup must be refused")
    assert staging.events == []
    rehearsal.db.get_pool.assert_not_awaited()


async def test_startup_is_refused_during_restore(staging):
    staging.connection.execute.return_value.fetchone.return_value = (True,)
    with pytest.raises(rehearsal.KeycloakStagingRehearsalBlocked, match="RESTORE_PENDING"):
        async with staging.worker():
            pytest.fail("startup must be refused")
    assert staging.events == ["pool-close"]
    staging.executor.assert_not_called()


@pytest.mark.parametrize("pending", [(True,), None])
async def test_dispatch_rechecks_restore_state(staging, pending):
    async with staging.worker() as dispatch:
        staging.connection.execute.return_value.fetchone.return_value = pending
        with pytest.raises(rehearsal.KeycloakStagingRehearsalBlocked, match="RESTORE_PENDING"):
            await dispatch()
    staging.executor.assert_not_called()


async def test_unreadable_restore_state_stops_dispatch(staging):
    async with staging.worker() as dispatch:
        staging.connection.execute.side_effect = OperationalError("unavailable")
        with pytest.raises(rehearsal.KeycloakStagingRehearsalBlocked, match="RECOVERY_UNAVAILABLE"):
            await dispatch()
    staging.executor.assert_not_called()


async def test_halted_worker_cannot_dispatch(staging):
    staging.halt.return_value = {"halted": True}
    async with staging.worker() as dispatch:
        with pytest.raises(rehearsal.KeycloakStagingRehearsalBlocked, match="STAGING_HALTED"):
            await dispatch()
    staging.executor.assert_not_called()


async def test_one_dispatch_runs_inside_normal_lifespan(staging):
    async with staging.worker() as dispatch:
        with pytest.raises(rehearsal.KeycloakStagingRehearsalBlocked, match="DISPATCH_UNAVAILABLE"):
            await asyncio.create_task(dispatch())
        await dispatch()
        with pytest.raises(rehearsal.KeycloakStagingRehearsalBlocked, match="DISPATCH_UNAVAILABLE"):
            await dispatch()
    with pytest.raises(rehearsal.KeycloakStagingRehearsalBlocked, match="DISPATCH_UNAVAILABLE"):
        await dispatch()
    assert staging.events == ["startup", "dispatch", "shutdown", "pool-close"]
    staging.execute.assert_awaited_once()
