"""Add primary TrustLog logical publication identity columns.

Revision ID: 0009
Revises: 0008

Existing TrustLog rows remain valid because all new columns are nullable.  Only
rows written through the explicit primary-publication API populate these fields.
A unique logical-identity index makes same-identity/different-payload reuse fail
closed while allowing pre-existing rows to remain untouched.
"""

from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "trustlog_entries",
        sa.Column("logical_identity_key", sa.Text(), nullable=True),
    )
    op.add_column(
        "trustlog_entries",
        sa.Column("publication_key", sa.Text(), nullable=True),
    )
    op.add_column(
        "trustlog_entries",
        sa.Column("canonical_payload_hash", sa.Text(), nullable=True),
    )
    op.add_column(
        "trustlog_entries",
        sa.Column("publication_schema_version", sa.Text(), nullable=True),
    )
    op.add_column(
        "trustlog_entries",
        sa.Column("publication_entry_type", sa.Text(), nullable=True),
    )
    op.add_column(
        "trustlog_entries",
        sa.Column("publication_entry_id", sa.Text(), nullable=True),
    )

    op.create_index(
        "uq_trustlog_entries_logical_identity_key",
        "trustlog_entries",
        ["logical_identity_key"],
        unique=True,
    )
    op.create_index(
        "uq_trustlog_entries_publication_key",
        "trustlog_entries",
        ["publication_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_trustlog_entries_publication_key",
        table_name="trustlog_entries",
    )
    op.drop_index(
        "uq_trustlog_entries_logical_identity_key",
        table_name="trustlog_entries",
    )
    op.drop_column("trustlog_entries", "publication_entry_id")
    op.drop_column("trustlog_entries", "publication_entry_type")
    op.drop_column("trustlog_entries", "publication_schema_version")
    op.drop_column("trustlog_entries", "canonical_payload_hash")
    op.drop_column("trustlog_entries", "publication_key")
    op.drop_column("trustlog_entries", "logical_identity_key")
