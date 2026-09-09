"""Reserve one sandbox business event across replacement attempts.

Revision ID: 0008
Revises: 0007

The nullable column is intentionally outside the hashed EffectStateRecord JSON.
It is an execution-ownership index, not new evidence.  PostgreSQL uniqueness
arbitrates concurrent replacement attempts.  CONFIRMED_NO_EFFECT transitions
release the reservation; unresolved and confirmed-effect states retain it.
"""

from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bind_effect_states",
        sa.Column("business_event_key", sa.Text(), nullable=True),
    )
    op.create_index(
        "uq_bind_effect_states_business_event_key",
        "bind_effect_states",
        ["business_event_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_bind_effect_states_business_event_key",
        table_name="bind_effect_states",
    )
    op.drop_column("bind_effect_states", "business_event_key")
