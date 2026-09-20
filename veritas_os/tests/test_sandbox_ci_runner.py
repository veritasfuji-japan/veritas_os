"""CI sandbox startup must work with the repository's pinned FastAPI."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts import run_native_v2_sandbox_service as runner


@pytest.fixture
def sandbox_pool(monkeypatch):
    monkeypatch.setenv("VERITAS_SANDBOX_DATABASE_URL", "postgresql://localhost/test")
    monkeypatch.setenv("VERITAS_SANDBOX_WRITER_TOKEN", "w" * 40)
    monkeypatch.setenv("VERITAS_SANDBOX_READER_TOKEN", "r" * 40)
    pool = MagicMock()
    pool.open = AsyncMock()
    pool.close = AsyncMock()
    connection = AsyncMock()
    pool.connection.return_value.__aenter__.return_value = connection
    monkeypatch.setattr(runner, "AsyncConnectionPool", lambda *args, **kwargs: pool)
    return pool, connection


@pytest.mark.asyncio
async def test_sandbox_lifespan_prepares_database_before_serving_and_closes(sandbox_pool):
    pool, connection = sandbox_pool
    app, returned_pool = runner.build_app()
    assert returned_pool is pool
    pool.open.assert_not_awaited()
    async with app.router.lifespan_context(app):
        pool.open.assert_awaited_once_with(wait=True)
        connection.execute.assert_awaited_once()
        assert "sandbox_events" in connection.execute.call_args.args[0]
        pool.close.assert_not_awaited()
    pool.close.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["connect", "ddl"])
async def test_sandbox_startup_failure_closes_pool_without_serving(sandbox_pool, failure):
    pool, connection = sandbox_pool
    operation = pool.open if failure == "connect" else connection.execute
    operation.side_effect = RuntimeError("controlled startup failure")
    app, _ = runner.build_app()
    with pytest.raises(RuntimeError, match="controlled startup failure"):
        async with app.router.lifespan_context(app):
            pytest.fail("must not serve after failed database initialization")
    pool.close.assert_awaited_once()
