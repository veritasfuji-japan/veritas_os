"""CI sandbox startup must work with the repository's pinned FastAPI."""

from unittest.mock import AsyncMock, MagicMock
from pathlib import Path
import shlex
from string import Template
import subprocess
import sys

import pytest
import yaml

from scripts import run_native_v2_sandbox_service as runner


@pytest.mark.parametrize("workflow_name", [
    "reproducible-decision-to-effect-e2e.yml",
    "reproducible-reconciliation-capable-execution-profile.yml",
])
def test_service_launch_explicit_environment_survives_clean_parent(workflow_name):
    """Exercise actual workflow assignments without sudo, DB or socket effects."""
    root = Path(__file__).resolve().parents[2]
    workflow = yaml.load(
        (root / ".github/workflows" / workflow_name).read_text(), Loader=yaml.BaseLoader,
    )
    job = next(iter(workflow["jobs"].values()))
    step = next(s for s in job["steps"] if s.get("name") == "Start independent sandbox HTTPS service")
    # Extract only the env/interpreter prefix, never execute the service command.
    lines = step["run"].splitlines()
    start = next(i for i, line in enumerate(lines) if line.lstrip().startswith("sudo "))
    command = "\n".join(lines[start:])
    prefix = command.split("sudo ", 1)[1].split("scripts/run_native_v2_sandbox_service.py", 1)[0]
    tokens = shlex.split(prefix.replace("\\\n", " "))
    assert tokens[0] == "env"
    assert tokens[-1] == "$(which python)"
    inputs = {
        "GITHUB_WORKSPACE": str(root),
        "VERITAS_SANDBOX_DATABASE_URL": "postgresql://localhost/synthetic_only",
        "VERITAS_SANDBOX_WRITER_TOKEN": "w" * 40,
        "VERITAS_SANDBOX_READER_TOKEN": "r" * 40,
        "VERITAS_SANDBOX_LOOKUP_OUTAGE_FLAG": "/synthetic/lookup-outage",
    }
    assignments = [Template(token).substitute(inputs) for token in tokens[1:-1]]
    code = """
import os
from scripts import run_native_v2_sandbox_service as runner
assert runner._dsn() == 'postgresql://localhost/synthetic_only'
assert runner._token('VERITAS_SANDBOX_WRITER_TOKEN') == 'w' * 40
assert runner._token('VERITAS_SANDBOX_READER_TOKEN') == 'r' * 40
assert os.environ['VERITAS_SANDBOX_LOOKUP_OUTAGE_FLAG'] == '/synthetic/lookup-outage'
assert 'UNRELATED_PARENT_VALUE' not in os.environ
"""
    subprocess.run(
        ["env", "-i", *assignments, sys.executable, "-c", code],
        cwd=root, env={"UNRELATED_PARENT_VALUE": "must-not-be-forwarded"},
        check=True, capture_output=True, text=True, timeout=15,
    )


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
