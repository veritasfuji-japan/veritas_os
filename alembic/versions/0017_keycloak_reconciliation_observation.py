"""Archive the first positive Keycloak reconciliation observation."""

from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bind_keycloak_dispatch_intents",
        sa.Column("reconciliation_observation", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.execute("LOCK TABLE bind_keycloak_dispatch_intents IN ACCESS EXCLUSIVE MODE")
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM bind_keycloak_dispatch_intents
                WHERE reconciliation_observation IS NOT NULL
            ) THEN
                RAISE EXCEPTION 'Cannot remove archived Keycloak reconciliation observations';
            END IF;
        END $$
    """)
    op.drop_column("bind_keycloak_dispatch_intents", "reconciliation_observation")
