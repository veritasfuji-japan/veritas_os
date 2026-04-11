"""Alembic environment configuration for VERITAS OS.

Reads the database URL from the ``VERITAS_DATABASE_URL`` environment variable
so that alembic.ini never contains credentials.

Supports both *online* (live connection) and *offline* (SQL script generation)
migration modes.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

# ---------------------------------------------------------------------------
# Alembic Config object — provides access to alembic.ini values.
# ---------------------------------------------------------------------------
config = context.config

# Interpret the config file for Python logging (if present).
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# No SQLAlchemy MetaData for autogenerate — we write migrations by hand.
target_metadata = None


# ---------------------------------------------------------------------------
# Database URL resolution
# ---------------------------------------------------------------------------

def _get_url() -> str:
    """Return the database URL from environment or raise with guidance.

    If the URL uses the bare ``postgresql://`` scheme, it is rewritten to
    ``postgresql+psycopg://`` so that SQLAlchemy uses the **psycopg 3**
    driver that the project depends on (instead of the legacy psycopg2).
    """
    url = os.getenv("VERITAS_DATABASE_URL", "").strip()
    if not url:
        print(
            "ERROR: VERITAS_DATABASE_URL is not set.\n"
            "Set it to a PostgreSQL DSN, e.g.\n"
            "  export VERITAS_DATABASE_URL="
            "postgresql+psycopg://veritas:veritas@localhost:5432/veritas",
            file=sys.stderr,
        )
        raise SystemExit(1)

    # Ensure SQLAlchemy uses the psycopg 3 driver, not the legacy psycopg2.
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]

    return url


# ---------------------------------------------------------------------------
# Offline mode — generate SQL script without a live database.
# ---------------------------------------------------------------------------

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Generates the SQL statements to stdout without requiring a database
    connection.  Useful for DBA review or air-gapped environments.
    """
    context.configure(
        url=_get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online mode — execute migrations against a live database.
# ---------------------------------------------------------------------------

def run_migrations_online() -> None:
    """Run migrations in 'online' mode with a live database connection."""
    connectable = create_engine(
        _get_url(),
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


# ---------------------------------------------------------------------------
# Entry point — Alembic calls this automatically.
# ---------------------------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
