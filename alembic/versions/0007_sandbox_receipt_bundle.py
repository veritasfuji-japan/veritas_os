"""Write-once sandbox BindReceipt and OutcomeReceipt pair.

Revision ID: 0007
Revises: 0006
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bind_effect_states", sa.Column("sandbox_receipt_bundle", sa.JSON(), nullable=True))


def downgrade() -> None:
    # Operators must preserve receipts under their retention policy first.
    op.drop_column("bind_effect_states", "sandbox_receipt_bundle")
