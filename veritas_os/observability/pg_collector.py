"""PostgreSQL pool and backend metrics collector.

This module provides a lightweight, on-demand collector that reads pool
statistics from ``psycopg_pool`` and (optionally) queries lightweight
``pg_stat_activity`` views for long-running / idle-in-transaction sessions.

Design constraints
------------------
* **No extra connections**: re-uses the existing shared pool from
  ``veritas_os.storage.db``.
* **No heavyweight queries**: all SQL is a single ``pg_stat_activity`` scan
  with very low overhead.
* **Fail-safe**: any error during collection silently degrades to partial
  or empty metrics — never breaks the ``/v1/metrics`` endpoint.
* **Backend-aware**: if the PostgreSQL backend is not active, all functions
  return safe defaults.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from veritas_os.observability.metrics import (
    record_db_connect_failure,
    set_advisory_lock_contention_count,
    set_db_backend_selected,
    set_db_health_status,
    set_db_pool_stats,
    set_idle_in_transaction_count,
    set_long_running_query_count,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pool-stats snapshot (synchronous — reads in-memory state only)
# ---------------------------------------------------------------------------


def collect_pool_stats(pool: Any) -> Dict[str, Any]:
    """Return a dict of connection-pool gauge values.

    Reads only in-memory pool attributes — no SQL is executed.

    Args:
        pool: A ``psycopg_pool.AsyncConnectionPool`` (or compatible).

    Returns:
        A dict with keys ``in_use``, ``available``, ``waiting``,
        ``max_size``, ``min_size``.  Values default to ``0`` on any error.
    """
    try:
        stats = pool.get_stats()
        pool_size = stats.get("pool_size", 0)
        pool_available = stats.get("pool_available", 0)
        in_use = pool_size - pool_available
        return {
            "in_use": max(0, in_use),
            "available": max(0, pool_available),
            "waiting": max(0, stats.get("requests_waiting", 0)),
            "max_size": getattr(pool, "max_size", 0),
            "min_size": getattr(pool, "min_size", 0),
        }
    except Exception:
        logger.debug("Failed to read pool stats", exc_info=True)
        return {
            "in_use": 0,
            "available": 0,
            "waiting": 0,
            "max_size": 0,
            "min_size": 0,
        }


def push_pool_gauges(pool: Any) -> Dict[str, Any]:
    """Collect pool stats and push them to Prometheus gauges.

    Returns the raw stats dict for inclusion in the JSON response.
    """
    stats = collect_pool_stats(pool)
    set_db_pool_stats(
        in_use=stats["in_use"],
        available=stats["available"],
        waiting=stats["waiting"],
        max_size=stats["max_size"],
        min_size=stats["min_size"],
    )
    return stats


# ---------------------------------------------------------------------------
# Lightweight pg_stat_activity queries (async — requires a pool connection)
# ---------------------------------------------------------------------------

_PG_STAT_QUERY = """\
SELECT
  count(*) FILTER (
    WHERE state = 'active'
      AND now() - query_start > interval '1 second' * %(timeout_sec)s
  )                                    AS long_running,
  count(*) FILTER (
    WHERE state = 'idle in transaction'
  )                                    AS idle_in_tx,
  count(*) FILTER (
    WHERE wait_event_type = 'Lock'
      AND wait_event = 'advisory'
  )                                    AS advisory_lock_wait
FROM pg_stat_activity
WHERE pid <> pg_backend_pid()
  AND datname = current_database();
"""


async def collect_pg_activity(
    pool: Any,
    *,
    statement_timeout_sec: int = 30,
) -> Dict[str, int]:
    """Run a single lightweight query against ``pg_stat_activity``.

    Args:
        pool: The ``AsyncConnectionPool``.
        statement_timeout_sec: Threshold (seconds) to classify a query
            as "long running".  Defaults to 30 seconds.

    Returns:
        A dict with ``long_running``, ``idle_in_tx``,
        ``advisory_lock_wait`` keys.
    """
    defaults: Dict[str, int] = {
        "long_running": 0,
        "idle_in_tx": 0,
        "advisory_lock_wait": 0,
    }
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    _PG_STAT_QUERY,
                    {"timeout_sec": statement_timeout_sec},
                )
                row = await cur.fetchone()
                if row is None:
                    return defaults
                return {
                    "long_running": row[0] or 0,
                    "idle_in_tx": row[1] or 0,
                    "advisory_lock_wait": row[2] or 0,
                }
    except Exception:
        logger.debug("pg_stat_activity collection failed", exc_info=True)
        return defaults


async def push_pg_activity_gauges(
    pool: Any,
    *,
    statement_timeout_sec: int = 30,
) -> Dict[str, int]:
    """Collect pg_stat_activity metrics and push to Prometheus gauges."""
    stats = await collect_pg_activity(
        pool, statement_timeout_sec=statement_timeout_sec
    )
    set_long_running_query_count(stats["long_running"])
    set_idle_in_transaction_count(stats["idle_in_tx"])
    set_advisory_lock_contention_count(stats["advisory_lock_wait"])
    return stats


# ---------------------------------------------------------------------------
# Health-check helper
# ---------------------------------------------------------------------------


async def check_db_health(pool: Any) -> bool:
    """Execute ``SELECT 1`` and return True on success.

    Updates the ``db_health_status`` gauge.
    """
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1")
                healthy = True
    except Exception:
        healthy = False
        record_db_connect_failure("health_check")
        logger.debug("DB health check failed", exc_info=True)
    set_db_health_status(healthy)
    return healthy


# ---------------------------------------------------------------------------
# Backend-label emitter
# ---------------------------------------------------------------------------


def emit_backend_labels(backend_info: Dict[str, str]) -> None:
    """Push ``db_backend_selected`` gauges for current backend config."""
    for component, backend in backend_info.items():
        set_db_backend_selected(component, backend)


# ---------------------------------------------------------------------------
# High-level collector (entry point for routes_system.py)
# ---------------------------------------------------------------------------


async def collect_all_pg_metrics(
    backend_info: Dict[str, str],
    pool: Optional[Any] = None,
    *,
    statement_timeout_ms: int = 30000,
    include_activity: bool = True,
) -> Dict[str, Any]:
    """Collect all PostgreSQL metrics in one call.

    This is the main entry point used by the ``/v1/metrics`` endpoint.
    When no pool is available (file backend), returns a minimal stub.

    Args:
        backend_info: Output of ``get_backend_info()``.
        pool: The ``AsyncConnectionPool``, or *None* for file backends.
        statement_timeout_ms: Statement timeout in ms (for long-running
            query classification).
        include_activity: Whether to query ``pg_stat_activity``.

    Returns:
        A dict suitable for inclusion in the ``/v1/metrics`` JSON response.
    """
    emit_backend_labels(backend_info)

    is_pg = any(v == "postgresql" for v in backend_info.values())

    if not is_pg or pool is None:
        set_db_health_status(True)
        return {
            "db_backend": backend_info,
            "db_pool": None,
            "db_health": True,
            "db_activity": None,
        }

    t0 = time.monotonic()

    pool_stats = push_pool_gauges(pool)
    db_healthy = await check_db_health(pool)

    activity: Optional[Dict[str, int]] = None
    if include_activity and db_healthy:
        timeout_sec = max(1, statement_timeout_ms // 1000)
        activity = await push_pg_activity_gauges(
            pool, statement_timeout_sec=timeout_sec
        )

    elapsed_ms = (time.monotonic() - t0) * 1000
    logger.debug("pg metrics collection took %.1f ms", elapsed_ms)

    return {
        "db_backend": backend_info,
        "db_pool": pool_stats,
        "db_health": db_healthy,
        "db_activity": activity,
    }
