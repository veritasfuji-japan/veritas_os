"""bind authorization atomic consumption records

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-23
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "bind_authorization_consumptions",
        sa.Column("consumption_id", sa.Text(), primary_key=True),
        sa.Column("consumption_hash", sa.Text(), nullable=False),
        sa.Column("authorization_id", sa.Text(), nullable=False, unique=True),
        sa.Column("authorization_hash", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False, unique=True),
        sa.Column("bind_context_hash", sa.Text(), nullable=False),
        sa.Column("execution_intent_id", sa.Text(), nullable=False),
        sa.Column("execution_intent_hash", sa.Text(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "btrim(authorization_id) <> ''",
            name="ck_bind_authorization_consumptions_authorization_id_non_empty",
        ),
        sa.CheckConstraint(
            "btrim(idempotency_key) <> ''",
            name="ck_bind_authorization_consumptions_idempotency_key_non_empty",
        ),
    )
    op.create_index(
        "ix_bind_authorization_consumptions_execution_intent_id",
        "bind_authorization_consumptions",
        ["execution_intent_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_bind_authorization_consumptions_execution_intent_id",
        table_name="bind_authorization_consumptions",
    )
    op.drop_table("bind_authorization_consumptions")
