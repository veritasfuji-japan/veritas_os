"""Atomically retain sandbox reconciliation evidence beside its effect state.

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bind_effect_states", sa.Column("reconciliation_archive", sa.JSON(), nullable=True))


def downgrade() -> None:
    # Archival data must be exported before an operator chooses this downgrade.
    op.drop_column("bind_effect_states", "reconciliation_archive")
