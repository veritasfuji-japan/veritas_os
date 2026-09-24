"""Add immutable effect provenance and sandbox ownership arbitration.

Revision ID: 0010
Revises: 0009

Sandbox ownership and pre-dispatch NO_EFFECT recovery share one durable row so
both operations can compete on the same exact predicate. Existing rows are
classified conservatively as GENERIC_AMBIGUOUS_V1 and receive no ownership cell.
"""

from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bind_effect_states",
        sa.Column("authorization_hash", sa.Text(), nullable=True),
    )
    op.add_column(
        "bind_effect_states",
        sa.Column("consumption_hash", sa.Text(), nullable=True),
    )
    op.add_column(
        "bind_effect_states",
        sa.Column("execution_intent_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "bind_effect_states",
        sa.Column("idempotency_key", sa.Text(), nullable=True),
    )
    op.add_column(
        "bind_effect_states",
        sa.Column("effect_provenance", sa.Text(), nullable=True),
    )
    op.add_column(
        "bind_effect_states",
        sa.Column("ownership_state", sa.Text(), nullable=True),
    )
    op.add_column(
        "bind_effect_states",
        sa.Column("ownership_digest", sa.Text(), nullable=True),
    )
    op.add_column(
        "bind_effect_states",
        sa.Column("ownership_origin_record_hash", sa.Text(), nullable=True),
    )
    op.add_column(
        "bind_effect_states",
        sa.Column("ownership_lineage_digest", sa.Text(), nullable=True),
    )
    op.add_column(
        "bind_effect_states",
        sa.Column("ownership_revision", sa.Integer(), nullable=True),
    )
    op.add_column(
        "bind_effect_states",
        sa.Column("ownership_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "bind_effect_states",
        sa.Column("ownership_record_hash", sa.Text(), nullable=True),
    )

    op.execute(
        """
        UPDATE bind_effect_states
        SET authorization_hash = record->>'authorization_hash',
            consumption_hash = record->>'consumption_hash',
            execution_intent_id = record->>'execution_intent_id',
            idempotency_key = record->>'idempotency_key',
            effect_provenance = COALESCE(
                record->>'effect_provenance',
                'GENERIC_AMBIGUOUS_V1'
            )
        """
    )

    for column in (
        "authorization_hash",
        "consumption_hash",
        "execution_intent_id",
        "idempotency_key",
        "effect_provenance",
    ):
        op.alter_column("bind_effect_states", column, nullable=False)

    op.create_check_constraint(
        "ck_bind_effect_states_effect_provenance",
        "bind_effect_states",
        "effect_provenance IN ('GENERIC_AMBIGUOUS_V1','SANDBOX_PRE_DISPATCH_V1')",
    )
    op.create_check_constraint(
        "ck_bind_effect_states_ownership_state",
        "bind_effect_states",
        "ownership_state IS NULL OR ownership_state IN ('AVAILABLE','CONSUMED','CANCELLED')",
    )
    op.create_check_constraint(
        "ck_bind_effect_states_ownership_revision",
        "bind_effect_states",
        "ownership_revision IS NULL OR ownership_revision >= 1",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_bind_effect_states_ownership_revision",
        "bind_effect_states",
        type_="check",
    )
    op.drop_constraint(
        "ck_bind_effect_states_ownership_state",
        "bind_effect_states",
        type_="check",
    )
    op.drop_constraint(
        "ck_bind_effect_states_effect_provenance",
        "bind_effect_states",
        type_="check",
    )

    for column in (
        "ownership_record_hash",
        "ownership_updated_at",
        "ownership_revision",
        "ownership_lineage_digest",
        "ownership_origin_record_hash",
        "ownership_digest",
        "ownership_state",
        "effect_provenance",
        "idempotency_key",
        "execution_intent_id",
        "consumption_hash",
        "authorization_hash",
    ):
        op.drop_column("bind_effect_states", column)
