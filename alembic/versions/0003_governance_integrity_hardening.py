"""governance datastore integrity hardening

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-18
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_governance_policies_policy_revision_positive",
        "governance_policies",
        sa.text("policy_revision > 0"),
    )
    op.create_index(
        "uq_governance_policies_policy_revision",
        "governance_policies",
        ["policy_revision"],
        unique=True,
    )
    op.create_check_constraint(
        "ck_governance_approvals_reviewer_non_empty",
        "governance_approvals",
        sa.text("btrim(reviewer) <> ''"),
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_governance_approvals_reviewer_non_empty",
        "governance_approvals",
        type_="check",
    )
    op.drop_index(
        "uq_governance_policies_policy_revision",
        table_name="governance_policies",
    )
    op.drop_constraint(
        "ck_governance_policies_policy_revision_positive",
        "governance_policies",
        type_="check",
    )
