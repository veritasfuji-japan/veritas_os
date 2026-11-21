"""Deployment-wide emergency halt and its pending approvals."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deployment_halts",
        sa.Column("deployment_id", sa.Text(), primary_key=True),
        sa.Column("halt_id", sa.Text()),
        sa.Column("halted_at", sa.DateTime(timezone=True)),
        sa.Column("operator", sa.Text()),
        sa.Column("reason", sa.Text()),
        sa.Column("pending", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )

    op.create_table(
        "deployment_resume_receipts",
        sa.Column("deployment_id", sa.Text(), primary_key=True),
        sa.Column("halt_id", sa.Text(), primary_key=True),
        sa.Column("receipt", JSONB(), nullable=False),
        sa.Column("audit_entries", sa.Text(), nullable=False),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_index(
        "ix_deployment_resume_audit_pending",
        "deployment_resume_receipts",
        ["deployment_id", "next_attempt_at", "queued_at"],
        postgresql_where=sa.text("published_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("deployment_resume_receipts")
    op.drop_table("deployment_halts")
