"""governance policy persistence tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-18
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "governance_policies",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("policy_version", sa.Text, nullable=False),
        sa.Column(
            "policy_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("digest", sa.Text, nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_by", sa.Text, nullable=False),
        sa.Column("is_current", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("policy_revision", sa.BigInteger, nullable=False, server_default=sa.text("1")),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_governance_policies_updated_at",
        "governance_policies",
        ["updated_at"],
    )
    op.create_index(
        "ix_governance_policies_payload_gin",
        "governance_policies",
        ["policy_payload"],
        postgresql_using="gin",
    )
    op.create_index(
        "uq_governance_policies_single_current",
        "governance_policies",
        ["is_current"],
        unique=True,
        postgresql_where=sa.text("is_current = true"),
    )

    op.create_table(
        "governance_policy_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "event_order",
            sa.BigInteger,
            sa.Identity(always=False),
            nullable=False,
            unique=True,
        ),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column(
            "previous_policy_id",
            sa.BigInteger,
            sa.ForeignKey("governance_policies.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "new_policy_id",
            sa.BigInteger,
            sa.ForeignKey("governance_policies.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("previous_digest", sa.Text, nullable=False, server_default=""),
        sa.Column("new_digest", sa.Text, nullable=False, server_default=""),
        sa.Column("proposer", sa.Text, nullable=False),
        sa.Column("changed_by", sa.Text, nullable=False),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("reason", sa.Text, nullable=False, server_default=""),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_governance_policy_events_changed_at",
        "governance_policy_events",
        ["changed_at"],
    )
    op.create_index(
        "ix_governance_policy_events_event_type",
        "governance_policy_events",
        ["event_type"],
    )

    op.create_table(
        "governance_approvals",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "event_id",
            sa.BigInteger,
            sa.ForeignKey("governance_policy_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reviewer", sa.Text, nullable=False),
        sa.Column("signature", sa.Text, nullable=False, server_default=""),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("event_id", "reviewer", name="uq_governance_approvals_event_reviewer"),
    )
    op.create_index(
        "uq_governance_approvals_event_signature_non_empty",
        "governance_approvals",
        ["event_id", "signature"],
        unique=True,
        postgresql_where=sa.text("signature <> ''"),
    )
    op.create_index(
        "ix_governance_approvals_event_id",
        "governance_approvals",
        ["event_id"],
    )


def downgrade() -> None:
    op.drop_table("governance_approvals")
    op.drop_table("governance_policy_events")
    op.drop_index("uq_governance_policies_single_current", table_name="governance_policies")
    op.drop_table("governance_policies")
