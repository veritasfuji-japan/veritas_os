"""Order local sandbox authorization revocation against dispatch commitment."""

from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bind_sandbox_dispatch_order",
        sa.Column("authorization_id", sa.Text(), primary_key=True),
        sa.Column("resolution", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "resolution IN ('REVOKED_BEFORE_DISPATCH', 'DISPATCH_ALREADY_COMMITTED')",
            name="ck_bind_sandbox_dispatch_resolution",
        ),
    )
    # Older workers recorded durable dispatch using the effect state alone.
    op.execute(
        """INSERT INTO bind_sandbox_dispatch_order (authorization_id, resolution)
           SELECT DISTINCT authorization_id, 'DISPATCH_ALREADY_COMMITTED'
           FROM bind_effect_states
           WHERE effect_provenance = 'SANDBOX_PRE_DISPATCH_V1'
             AND state <> 'IN_FLIGHT'
             AND coalesce(record->>'reason_code', '') <> 'SANDBOX_RECOVERY_PRE_DISPATCH_CONFIRMED_NO_EFFECT'"""
    )


def downgrade() -> None:
    # Keep the check and drop atomic with respect to revocation writers.
    op.execute("LOCK TABLE bind_sandbox_dispatch_order IN ACCESS EXCLUSIVE MODE")
    op.execute(
        """DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM bind_sandbox_dispatch_order
                WHERE resolution = 'REVOKED_BEFORE_DISPATCH'
            ) THEN
                RAISE EXCEPTION 'Cannot downgrade 0014 with committed sandbox authorization revocations';
            END IF;
        END
        $$"""
    )
    op.drop_table("bind_sandbox_dispatch_order")
