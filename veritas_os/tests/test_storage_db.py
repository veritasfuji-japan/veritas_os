"""Tests for veritas_os.storage.db — connection pool helpers.

These tests do NOT require a running PostgreSQL instance; they validate
configuration parsing, error messages, and pool lifecycle logic using
mocks.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from veritas_os.storage import db


# ── Configuration helpers ──────────────────────────────────────


class TestBuildConninfo:
    """Tests for build_conninfo()."""

    def test_missing_database_url_raises(self, monkeypatch):
        monkeypatch.delenv("VERITAS_DATABASE_URL", raising=False)
        with pytest.raises(RuntimeError, match="VERITAS_DATABASE_URL is not set"):
            db.build_conninfo()

    def test_empty_database_url_raises(self, monkeypatch):
        monkeypatch.setenv("VERITAS_DATABASE_URL", "  ")
        with pytest.raises(RuntimeError, match="VERITAS_DATABASE_URL is not set"):
            db.build_conninfo()

    def test_basic_dsn_appends_defaults(self, monkeypatch):
        monkeypatch.setenv(
            "VERITAS_DATABASE_URL",
            "postgresql://u:p@host:5432/db",
        )
        monkeypatch.delenv("VERITAS_DB_CONNECT_TIMEOUT", raising=False)
        monkeypatch.delenv("VERITAS_DB_SSLMODE", raising=False)
        monkeypatch.delenv("VERITAS_DB_STATEMENT_TIMEOUT_MS", raising=False)

        result = db.build_conninfo()

        assert "connect_timeout=5" in result
        assert "sslmode=prefer" in result
        assert "statement_timeout=30000" in result

    def test_custom_timeouts(self, monkeypatch):
        monkeypatch.setenv(
            "VERITAS_DATABASE_URL",
            "postgresql://u:p@host:5432/db",
        )
        monkeypatch.setenv("VERITAS_DB_CONNECT_TIMEOUT", "10")
        monkeypatch.setenv("VERITAS_DB_SSLMODE", "require")
        monkeypatch.setenv("VERITAS_DB_STATEMENT_TIMEOUT_MS", "60000")

        result = db.build_conninfo()

        assert "connect_timeout=10" in result
        assert "sslmode=require" in result
        assert "statement_timeout=60000" in result

    def test_dsn_with_existing_params_uses_ampersand(self, monkeypatch):
        monkeypatch.setenv(
            "VERITAS_DATABASE_URL",
            "postgresql://u:p@host/db?application_name=veritas",
        )
        result = db.build_conninfo()
        # Should use & separator since ? already present
        assert "&connect_timeout=" in result

    def test_dsn_already_contains_params_not_duplicated(self, monkeypatch):
        monkeypatch.setenv(
            "VERITAS_DATABASE_URL",
            "postgresql://u:p@host/db?connect_timeout=20&sslmode=verify-full"
            "&options=-c%20statement_timeout=5000",
        )
        result = db.build_conninfo()
        # Should not append duplicates
        assert result.count("connect_timeout") == 1
        assert result.count("sslmode") == 1
        assert result.count("statement_timeout") == 1
        # Existing values must be preserved
        assert "connect_timeout=20" in result
        assert "sslmode=verify-full" in result
        assert "statement_timeout=5000" in result


class TestPoolMinMax:
    """Tests for pool size env parsing."""

    def test_defaults(self, monkeypatch):
        monkeypatch.delenv("VERITAS_DB_POOL_MIN_SIZE", raising=False)
        monkeypatch.delenv("VERITAS_DB_POOL_MAX_SIZE", raising=False)
        assert db._pool_min_size() == 2
        assert db._pool_max_size() == 10

    def test_custom(self, monkeypatch):
        monkeypatch.setenv("VERITAS_DB_POOL_MIN_SIZE", "5")
        monkeypatch.setenv("VERITAS_DB_POOL_MAX_SIZE", "20")
        assert db._pool_min_size() == 5
        assert db._pool_max_size() == 20


# ── Pool lifecycle ─────────────────────────────────────────────


class TestGetPool:
    """Tests for get_pool() / close_pool()."""

    @pytest.fixture(autouse=True)
    def _reset_pool(self):
        """Ensure pool is cleared between tests."""
        db._pool = None
        yield
        db._pool = None

    @pytest.mark.asyncio
    async def test_get_pool_creates_and_caches(self, monkeypatch):
        monkeypatch.setenv(
            "VERITAS_DATABASE_URL",
            "postgresql://u:p@host/db",
        )

        mock_pool = AsyncMock()
        mock_pool.open = AsyncMock()
        mock_pool_cls = MagicMock(return_value=mock_pool)

        with patch("veritas_os.storage.db._require_psycopg"):
            with patch(
                "veritas_os.storage.db.AsyncConnectionPool",
                mock_pool_cls,
                create=True,
            ):
                # Patch the import inside get_pool
                with patch.dict(
                    "sys.modules",
                    {"psycopg_pool": MagicMock(AsyncConnectionPool=mock_pool_cls)},
                ):
                    pool = await db.get_pool()
                    assert pool is mock_pool
                    mock_pool.open.assert_awaited_once_with(wait=True)

                    # Second call returns cached pool
                    pool2 = await db.get_pool()
                    assert pool2 is pool

    @pytest.mark.asyncio
    async def test_close_pool_noop_when_none(self):
        """close_pool should be safe when no pool exists."""
        await db.close_pool()
        assert db._pool is None

    @pytest.mark.asyncio
    async def test_close_pool_closes_and_clears(self):
        mock_pool = AsyncMock()
        db._pool = mock_pool

        await db.close_pool()

        mock_pool.close.assert_awaited_once()
        assert db._pool is None

    @pytest.mark.asyncio
    async def test_close_pool_clears_on_exception(self):
        mock_pool = AsyncMock()
        mock_pool.close = AsyncMock(side_effect=RuntimeError("boom"))
        db._pool = mock_pool

        # Should not raise
        await db.close_pool()
        assert db._pool is None


# ── Dependency check ───────────────────────────────────────────


class TestRequirePsycopg:
    def test_raises_when_missing(self):
        with patch.dict("sys.modules", {"psycopg": None}):
            with pytest.raises(RuntimeError, match="psycopg is required"):
                db._require_psycopg()
