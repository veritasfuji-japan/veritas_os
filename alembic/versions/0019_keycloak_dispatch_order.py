"""Distinguish Keycloak reservation and terminal decisions in Bind ordering."""

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

_TABLE = "bind_sandbox_dispatch_order"
_CONSTRAINT = "ck_bind_sandbox_dispatch_resolution"
_SANDBOX = "resolution IN ('REVOKED_BEFORE_DISPATCH', 'DISPATCH_ALREADY_COMMITTED')"
_KEYCLOAK = """resolution IN (
    'KEYCLOAK_RESERVED', 'KEYCLOAK_REVOKED_BEFORE_DISPATCH', 'KEYCLOAK_DISPATCH_ALREADY_COMMITTED'
)"""


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(_CONSTRAINT, _TABLE, f"{_SANDBOX} OR {_KEYCLOAK}")


def downgrade() -> None:
    op.execute("LOCK TABLE public.bind_sandbox_dispatch_order IN ACCESS EXCLUSIVE MODE")
    op.execute(
        """DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM public.bind_sandbox_dispatch_order
                WHERE resolution IN (
                    'KEYCLOAK_RESERVED', 'KEYCLOAK_REVOKED_BEFORE_DISPATCH', 'KEYCLOAK_DISPATCH_ALREADY_COMMITTED'
                )
            ) THEN
                RAISE EXCEPTION 'Cannot downgrade 0019 with Keycloak dispatch ordering history';
            END IF;
        END
        $$"""
    )
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(_CONSTRAINT, _TABLE, _SANDBOX)
