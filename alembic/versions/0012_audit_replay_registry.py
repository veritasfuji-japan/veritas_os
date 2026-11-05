"""Local audit replay observations (not execution authority).

Revision ID: 0012
Revises: 0011

Packet and case metadata are retained atomically. Unique indexes detect
replay only against records that were actually archived in this database.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_packet_inventory",
        sa.Column("packet_id", sa.Text(), primary_key=True),
        sa.Column("profile_sha256", sa.Text(), nullable=False),
        sa.Column("repository_claim", sa.Text(), nullable=False),
        sa.Column("repository_key", sa.Text(), nullable=False),
        sa.Column("source_commit", sa.Text(), nullable=False),
        sa.Column("snapshot_digest", sa.Text(), nullable=False),
        sa.Column("case_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("btrim(packet_id) <> ''", name="audit_packet_id_nonempty"),
        sa.CheckConstraint("repository_key = lower(repository_claim)",
                           name="audit_packet_namespace_lowercase"),
        sa.CheckConstraint("case_count > 0 AND case_count <= 32768",
                           name="audit_packet_bounded_cases"),
        sa.CheckConstraint("profile_sha256 ~ '^[0-9a-f]{64}$'",
                           name="audit_packet_profile_sha"),
        sa.CheckConstraint("snapshot_digest ~ '^[0-9a-f]{64}$'",
                           name="audit_packet_snapshot_sha"),
        sa.CheckConstraint("source_commit ~ '^[0-9a-f]{40}$'",
                           name="audit_packet_source_commit_sha"),
    )
    op.create_table(
        "audit_case_observations",
        sa.Column("record_hash", sa.Text(), primary_key=True),
        sa.Column("packet_id", sa.Text(), nullable=False),
        sa.Column("case_id", sa.Text(), nullable=False),
        sa.Column("repository_key", sa.Text(), nullable=False),
        sa.Column("operation_id", sa.Text(), nullable=False),
        sa.Column("manifest_id", sa.Text(), nullable=False),
        sa.Column("manifest_sha256", sa.Text(), nullable=False),
        sa.Column("record", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["packet_id"], ["audit_packet_inventory.packet_id"],
            name="audit_case_packet_fk", ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("packet_id", "case_id", name="audit_case_unique_local_case"),
        sa.UniqueConstraint("repository_key", "operation_id",
                            name="audit_case_unique_repository_operation"),
        sa.UniqueConstraint("repository_key", "manifest_id",
                            name="audit_case_unique_repository_manifest"),
        sa.UniqueConstraint("manifest_sha256",
                            name="audit_case_unique_global_manifest_bytes"),
        sa.CheckConstraint("record_hash ~ '^[0-9a-f]{64}$'",
                           name="audit_case_record_hash_sha"),
        sa.CheckConstraint("manifest_sha256 ~ '^[0-9a-f]{64}$'",
                           name="audit_case_manifest_hash_sha"),
    )
    op.create_index(
        "ix_audit_case_packet", "audit_case_observations", ["packet_id"],
    )


def downgrade() -> None:
    # Destructive: never downgrade populated production audit history.
    op.drop_index("ix_audit_case_packet", table_name="audit_case_observations")
    op.drop_table("audit_case_observations")
    op.drop_table("audit_packet_inventory")
