"""Persist the recovery inputs for each Keycloak dispatch reservation."""

from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bind_keycloak_dispatch_intents",
        sa.Column(
            "operation_id", sa.Text(),
            sa.ForeignKey("bind_effect_states.operation_id"), primary_key=True,
        ),
        sa.Column("intent", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    op.execute("LOCK TABLE bind_keycloak_dispatch_intents IN ACCESS EXCLUSIVE MODE")
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM bind_keycloak_dispatch_intents) THEN
                RAISE EXCEPTION 'Cannot remove persisted Keycloak dispatch intents';
            END IF;
        END $$
    """)
    op.drop_table("bind_keycloak_dispatch_intents")
