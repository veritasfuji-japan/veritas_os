"""PostgreSQL connection pool and lifecycle management.

Provides a process-wide connection pool backed by ``psycopg_pool``.
All PostgreSQL-backed stores should obtain connections through this module
rather than creating their own pools.

Environment variables
---------------------
VERITAS_DATABASE_URL          PostgreSQL DSN  (required when backend=postgresql)
VERITAS_DB_POOL_MIN_SIZE      Minimum idle connections  (default 2)
VERITAS_DB_POOL_MAX_SIZE      Maximum connections       (default 10)
VERITAS_DB_CONNECT_TIMEOUT    TCP connect timeout in seconds  (default 5)
VERITAS_DB_STATEMENT_TIMEOUT_MS  Per-statement timeout in ms  (default 30 000)
VERITAS_DB_SSLMODE            libpq sslmode parameter  (default "prefer")
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy import helpers — psycopg / psycopg_pool are optional dependencies.
# ---------------------------------------------------------------------------


def _require_psycopg() -> None:
    """Raise a clear error when psycopg is not installed."""
    try:
        import psycopg  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "psycopg is required for the PostgreSQL backend. "
            'Install it with: pip install "psycopg[binary]" psycopg-pool'
        ) from exc


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

_MISSING = ""


def _get_database_url() -> str:
    """Return the configured database URL or raise with guidance."""
    url = os.getenv("VERITAS_DATABASE_URL", _MISSING).strip()
    if not url:
        raise RuntimeError(
            "VERITAS_DATABASE_URL is not set. "
            "Set it to a PostgreSQL DSN, e.g. "
            "postgresql://user:pass@localhost:5432/veritas"
        )
    return url


def _pool_min_size() -> int:
    return int(os.getenv("VERITAS_DB_POOL_MIN_SIZE", "2"))


def _pool_max_size() -> int:
    return int(os.getenv("VERITAS_DB_POOL_MAX_SIZE", "10"))


def _connect_timeout() -> int:
    return int(os.getenv("VERITAS_DB_CONNECT_TIMEOUT", "5"))


def _statement_timeout_ms() -> int:
    return int(os.getenv("VERITAS_DB_STATEMENT_TIMEOUT_MS", "30000"))


def _sslmode() -> str:
    return os.getenv("VERITAS_DB_SSLMODE", "prefer")


# ---------------------------------------------------------------------------
# Connection-string builder
# ---------------------------------------------------------------------------


def build_conninfo() -> str:
    """Build a libpq-compatible connection string from environment.

    Appends ``connect_timeout``, ``sslmode``, and
    ``options=-c statement_timeout=…`` if they are not already present
    in the DSN.
    """
    dsn = _get_database_url()

    params: list[str] = []
    if "connect_timeout" not in dsn:
        params.append(f"connect_timeout={_connect_timeout()}")
    if "sslmode" not in dsn:
        params.append(f"sslmode={_sslmode()}")
    if "statement_timeout" not in dsn:
        params.append(
            f"options=-c%20statement_timeout={_statement_timeout_ms()}"
        )

    if params:
        sep = "&" if "?" in dsn else "?"
        dsn = dsn + sep + "&".join(params)
    return dsn


# ---------------------------------------------------------------------------
# Process-wide async pool singleton
# ---------------------------------------------------------------------------

_pool: Optional[object] = None  # AsyncConnectionPool | None


async def get_pool():
    """Return (and lazily create) the process-wide ``AsyncConnectionPool``.

    The pool is created on first call and reused for the lifetime of the
    process.  Call :func:`close_pool` during shutdown to release all
    connections.

    Returns
    -------
    psycopg_pool.AsyncConnectionPool
    """
    global _pool
    if _pool is not None:
        return _pool

    _require_psycopg()
    from psycopg_pool import AsyncConnectionPool

    conninfo = build_conninfo()
    min_size = _pool_min_size()
    max_size = _pool_max_size()

    logger.info(
        "Creating PostgreSQL connection pool (min=%d, max=%d)", min_size, max_size
    )

    pool = AsyncConnectionPool(
        conninfo=conninfo,
        min_size=min_size,
        max_size=max_size,
        open=False,
    )
    await pool.open(wait=True)
    _pool = pool
    logger.info("PostgreSQL connection pool ready")
    return _pool


async def close_pool() -> None:
    """Gracefully close the process-wide connection pool.

    Safe to call even when no pool has been created.
    """
    global _pool
    if _pool is None:
        return
    try:
        await _pool.close()  # type: ignore[union-attr]
        logger.info("PostgreSQL connection pool closed")
    except Exception:
        logger.exception("Error closing PostgreSQL connection pool")
    finally:
        _pool = None
