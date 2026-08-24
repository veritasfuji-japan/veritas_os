"""bind effect execution and reconciliation states

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-24
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "bind_effect_states",
        sa.Column("operation_id", sa.Text(), primary_key=True),
        sa.Column("authorization_id", sa.Text(), nullable=False, unique=True),
        sa.Column("consumption_id", sa.Text(), nullable=False, unique=True),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("record_hash", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "state IN ('IN_FLIGHT','EFFECT_UNKNOWN','CONFIRMED_EFFECT','CONFIRMED_NO_EFFECT')",
            name="ck_bind_effect_states_state",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_bind_effect_states_revision"),
    )
    op.create_index(
        "ix_bind_effect_states_state",
        "bind_effect_states",
        ["state"],
    )


def downgrade() -> None:
    op.drop_index("ix_bind_effect_states_state", table_name="bind_effect_states")
    op.drop_table("bind_effect_states")
