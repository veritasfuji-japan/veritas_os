"""SQL-file-based database migrator for VERITAS OS.

Design goals:
* No ORM — plain SQL files in ``veritas_os/storage/migrations/sql/``.
* Idempotent / re-run safe (each file runs at most once).
* Version tracking via ``schema_migrations`` table.
* Usable in local dev, CI, and ``VERITAS_DB_AUTO_MIGRATE=true`` startup.
"""

from __future__ import annotations

import logging
import os
from importlib import resources as importlib_resources
from pathlib import Path
from typing import Sequence

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

_SQL_SUBPACKAGE = "veritas_os.storage.migrations.sql"


def _discover_sql_files() -> list[Path]:
    """Return sorted list of ``*.sql`` migration files from the sql/ dir.

    Files are expected to follow the naming convention::

        NNNN_short_description.sql

    where ``NNNN`` is a zero-padded integer (e.g. ``0001``).  Files are
    sorted lexicographically so that numbering determines execution order.
    """
    try:
        traversable = importlib_resources.files(_SQL_SUBPACKAGE)
    except (ModuleNotFoundError, TypeError):
        # Fallback: resolve from filesystem relative to this file.
        traversable = Path(__file__).resolve().parent / "sql"

    paths: list[Path] = []
    for item in traversable.iterdir():  # type: ignore[union-attr]
        name = str(item.name) if hasattr(item, "name") else str(item)
        if name.endswith(".sql"):
            # importlib Traversable → materialise to real Path
            if isinstance(item, Path):
                paths.append(item)
            else:
                paths.append(Path(str(item)))
    paths.sort(key=lambda p: p.name)
    return paths


def _read_sql(path: Path) -> str:
    """Read SQL content from a file path or importlib traversable."""
    # Try importlib.resources first for packaged data
    try:
        traversable = importlib_resources.files(_SQL_SUBPACKAGE)
        content = (traversable / path.name).read_text(encoding="utf-8")
        return content
    except Exception:
        pass
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Bootstrap: ensure the migration-tracking table exists
# ---------------------------------------------------------------------------

_BOOTSTRAP_SQL = """\
CREATE TABLE IF NOT EXISTS schema_migrations (
    version  TEXT PRIMARY KEY,
    applied  TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


async def _ensure_migrations_table(conn) -> None:
    """Create the ``schema_migrations`` table if it does not exist."""
    await conn.execute(_BOOTSTRAP_SQL)


# ---------------------------------------------------------------------------
# Core migration runner
# ---------------------------------------------------------------------------


async def _applied_versions(conn) -> set[str]:
    """Return the set of already-applied migration versions."""
    cur = await conn.execute("SELECT version FROM schema_migrations")
    rows = await cur.fetchall()
    return {row[0] for row in rows}


async def run_migrations(pool=None) -> Sequence[str]:
    """Execute all pending SQL migrations.

    Parameters
    ----------
    pool : psycopg_pool.AsyncConnectionPool, optional
        If *None*, the process-wide pool from :mod:`veritas_os.storage.db`
        is used.

    Returns
    -------
    list[str]
        Names of newly applied migration files.
    """
    if pool is None:
        from veritas_os.storage.db import get_pool

        pool = await get_pool()

    sql_files = _discover_sql_files()
    if not sql_files:
        logger.info("No SQL migration files found")
        return []

    applied: list[str] = []
    async with pool.connection() as conn:
        await _ensure_migrations_table(conn)
        already = await _applied_versions(conn)

        for path in sql_files:
            version = path.name
            if version in already:
                logger.debug("Migration %s already applied — skipping", version)
                continue

            sql = _read_sql(path)
            logger.info("Applying migration %s …", version)
            await conn.execute(sql)
            await conn.execute(
                "INSERT INTO schema_migrations (version) VALUES (%s)",
                (version,),
            )
            applied.append(version)
            logger.info("Migration %s applied successfully", version)

    return applied


# ---------------------------------------------------------------------------
# CLI helper
# ---------------------------------------------------------------------------


async def migrate_cli() -> None:
    """Run migrations from a CLI / script entry-point.

    Convenience wrapper that creates the pool, runs all pending
    migrations, then closes the pool.
    """
    from veritas_os.storage.db import close_pool, get_pool

    pool = await get_pool()
    try:
        applied = await run_migrations(pool)
        if applied:
            logger.info("Applied %d migration(s): %s", len(applied), applied)
        else:
            logger.info("Database is up-to-date — no pending migrations")
    finally:
        await close_pool()


def main() -> None:
    """Synchronous entry-point for ``python -m veritas_os.storage.migrations``."""
    import asyncio

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    asyncio.run(migrate_cli())
