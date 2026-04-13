"""initial schema — memory_records, trustlog_entries, trustlog_chain_state

Revision ID: 0001
Revises: None
Create Date: 2026-04-11

This migration creates the foundational PostgreSQL schema for VERITAS OS:

- **memory_records**: MemoryOS key-value store with JSONB payload.
- **trustlog_entries**: Append-only, hash-chained audit log.
- **trustlog_chain_state**: Single-row tracker for the latest chain hash.

Column design notes
-------------------
* ``metadata`` JSONB columns are reserved for future signed-witness /
  provenance fields without requiring further DDL changes.
* BIGSERIAL primary keys support high-throughput write patterns.
* TIMESTAMPTZ columns ensure timezone-aware datetime handling.

Downgrade warning
-----------------
Running ``downgrade`` drops all three tables and their data.
This is **destructive** and **irreversible** in production.
See ``docs/en/operations/database-migrations.md`` for the operational policy.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # memory_records
    # ------------------------------------------------------------------
    op.create_table(
        "memory_records",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("key", sa.Text, nullable=False),
        sa.Column("user_id", sa.Text, nullable=False),
        sa.Column(
            "value",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_unique_constraint(
        "uq_memory_records_key_user",
        "memory_records",
        ["key", "user_id"],
    )
    op.create_index(
        "ix_memory_records_user_id",
        "memory_records",
        ["user_id"],
    )
    op.create_index(
        "ix_memory_records_value_gin",
        "memory_records",
        ["value"],
        postgresql_using="gin",
    )

    # ------------------------------------------------------------------
    # trustlog_entries
    # ------------------------------------------------------------------
    op.create_table(
        "trustlog_entries",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("request_id", sa.Text, nullable=False, unique=True),
        sa.Column(
            "entry",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("hash", sa.Text, nullable=True),
        sa.Column("prev_hash", sa.Text, nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_trustlog_entries_request_id",
        "trustlog_entries",
        ["request_id"],
    )
    op.create_index(
        "ix_trustlog_entries_created_at",
        "trustlog_entries",
        ["created_at"],
    )

    # ------------------------------------------------------------------
    # trustlog_chain_state (single-row table)
    # ------------------------------------------------------------------
    op.create_table(
        "trustlog_chain_state",
        sa.Column(
            "id",
            sa.Integer,
            primary_key=True,
            server_default=sa.text("1"),
        ),
        sa.Column("last_hash", sa.Text, nullable=True),
        sa.Column("last_id", sa.BigInteger, nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("id = 1", name="ck_trustlog_chain_state_singleton"),
    )


def downgrade() -> None:
    # Reverse order: dependents first, then standalone tables.
    op.drop_table("trustlog_chain_state")
    op.drop_table("trustlog_entries")
    op.drop_table("memory_records")
