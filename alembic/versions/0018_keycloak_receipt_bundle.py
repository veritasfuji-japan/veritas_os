"""Store historical Keycloak BindReceipt and Outcome artifacts as one pair."""

from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bind_keycloak_dispatch_intents",
        sa.Column("receipt_bundle", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.execute("LOCK TABLE bind_keycloak_dispatch_intents IN ACCESS EXCLUSIVE MODE")
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM bind_keycloak_dispatch_intents
                WHERE receipt_bundle IS NOT NULL
            ) THEN
                RAISE EXCEPTION 'Cannot remove published Keycloak receipt bundles';
            END IF;
        END $$
    """)
    op.drop_column("bind_keycloak_dispatch_intents", "receipt_bundle")
