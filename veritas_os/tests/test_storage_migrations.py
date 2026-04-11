"""Tests for veritas_os.storage.migrations — SQL-file-based migrator.

These tests validate migration discovery, idempotency, and the runner
logic without requiring a live PostgreSQL database — all DB interactions
are mocked.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from veritas_os.storage.migrations import (
    _BOOTSTRAP_SQL,
    _applied_versions,
    _discover_sql_files,
    _ensure_migrations_table,
    run_migrations,
)


# ── SQL file discovery ─────────────────────────────────────────


class TestDiscoverSqlFiles:
    """Tests for _discover_sql_files()."""

    def test_discovers_real_sql_files(self):
        """The shipped migration SQL files should be discoverable."""
        files = _discover_sql_files()
        names = [f.name for f in files]
        assert "0001_create_memory_records.sql" in names
        assert "0002_create_trustlog_entries.sql" in names

    def test_files_are_sorted(self):
        files = _discover_sql_files()
        names = [f.name for f in files]
        assert names == sorted(names)
        # Verify numeric prefix ordering is correct
        assert names.index("0001_create_memory_records.sql") < names.index(
            "0002_create_trustlog_entries.sql"
        )

    def test_sql_files_are_not_empty(self):
        for path in _discover_sql_files():
            content = path.read_text(encoding="utf-8")
            assert len(content) > 0, f"{path.name} is empty"


# ── Bootstrap table ────────────────────────────────────────────


class TestEnsureMigrationsTable:
    @pytest.mark.asyncio
    async def test_creates_table(self):
        conn = AsyncMock()
        await _ensure_migrations_table(conn)
        conn.execute.assert_awaited_once_with(_BOOTSTRAP_SQL)


# ── Applied versions ───────────────────────────────────────────


class TestAppliedVersions:
    @pytest.mark.asyncio
    async def test_returns_set_of_versions(self):
        cur = AsyncMock()
        cur.fetchall = AsyncMock(
            return_value=[("0001_create_memory_records.sql",)]
        )
        conn = AsyncMock()
        conn.execute = AsyncMock(return_value=cur)

        result = await _applied_versions(conn)
        assert result == {"0001_create_memory_records.sql"}


# ── Migration runner ───────────────────────────────────────────


class TestRunMigrations:
    @pytest.mark.asyncio
    async def test_applies_pending_migrations(self):
        """All discovered files should run when none are applied yet."""
        cur = AsyncMock()
        cur.fetchall = AsyncMock(return_value=[])

        conn = AsyncMock()
        conn.execute = AsyncMock(return_value=cur)

        # Context manager for pool.connection()
        conn_ctx = AsyncMock()
        conn_ctx.__aenter__ = AsyncMock(return_value=conn)
        conn_ctx.__aexit__ = AsyncMock(return_value=False)

        pool = MagicMock()
        pool.connection = MagicMock(return_value=conn_ctx)

        applied = await run_migrations(pool)

        assert len(applied) >= 2
        assert "0001_create_memory_records.sql" in applied
        assert "0002_create_trustlog_entries.sql" in applied

    @pytest.mark.asyncio
    async def test_skips_already_applied(self):
        """Migrations that were already applied should be skipped."""
        cur = AsyncMock()
        cur.fetchall = AsyncMock(
            return_value=[
                ("0001_create_memory_records.sql",),
                ("0002_create_trustlog_entries.sql",),
            ]
        )

        conn = AsyncMock()
        conn.execute = AsyncMock(return_value=cur)

        conn_ctx = AsyncMock()
        conn_ctx.__aenter__ = AsyncMock(return_value=conn)
        conn_ctx.__aexit__ = AsyncMock(return_value=False)

        pool = MagicMock()
        pool.connection = MagicMock(return_value=conn_ctx)

        applied = await run_migrations(pool)

        assert applied == []

    @pytest.mark.asyncio
    async def test_partial_apply(self):
        """Only un-applied files should be executed."""
        cur = AsyncMock()
        cur.fetchall = AsyncMock(
            return_value=[("0001_create_memory_records.sql",)]
        )

        conn = AsyncMock()
        conn.execute = AsyncMock(return_value=cur)

        conn_ctx = AsyncMock()
        conn_ctx.__aenter__ = AsyncMock(return_value=conn)
        conn_ctx.__aexit__ = AsyncMock(return_value=False)

        pool = MagicMock()
        pool.connection = MagicMock(return_value=conn_ctx)

        applied = await run_migrations(pool)

        assert "0001_create_memory_records.sql" not in applied
        assert "0002_create_trustlog_entries.sql" in applied

    @pytest.mark.asyncio
    async def test_records_version_after_apply(self):
        """Each applied migration should be recorded in schema_migrations."""
        cur = AsyncMock()
        cur.fetchall = AsyncMock(return_value=[])

        conn = AsyncMock()
        conn.execute = AsyncMock(return_value=cur)

        conn_ctx = AsyncMock()
        conn_ctx.__aenter__ = AsyncMock(return_value=conn)
        conn_ctx.__aexit__ = AsyncMock(return_value=False)

        pool = MagicMock()
        pool.connection = MagicMock(return_value=conn_ctx)

        await run_migrations(pool)

        # Check that INSERT INTO schema_migrations was called for each file
        insert_calls = [
            c
            for c in conn.execute.await_args_list
            if "INSERT INTO schema_migrations" in str(c)
        ]
        assert len(insert_calls) >= 2
