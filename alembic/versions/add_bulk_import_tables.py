"""Add bulk import tables

Revision ID: add_bulk_import_tables
Revises:
Create Date: 2026-01-28

Creates the bulk_import_jobs and bulk_import_items tables for
batch user registration functionality.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_bulk_import_tables"
down_revision: Union[str, None] = "a6eb4382e3c3"  # Latest migration
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enums
    bulk_job_status_enum = postgresql.ENUM(
        "pending",
        "processing",
        "done",
        "failed",
        name="bulk_job_status_enum",
        create_type=False,
    )
    bulk_job_status_enum.create(op.get_bind(), checkfirst=True)

    bulk_item_status_enum = postgresql.ENUM(
        "pending",
        "success",
        "failed",
        "skipped",
        name="bulk_item_status_enum",
        create_type=False,
    )
    bulk_item_status_enum.create(op.get_bind(), checkfirst=True)

    target_role_enum = postgresql.ENUM(
        "student",
        "supervisor",
        name="target_role_enum",
        create_type=False,
    )
    target_role_enum.create(op.get_bind(), checkfirst=True)

    # Create bulk_import_jobs table
    op.create_table(
        "bulk_import_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_role",
            sa.Enum(
                "student", "supervisor", name="target_role_enum", create_type=False
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "processing",
                "done",
                "failed",
                name="bulk_job_status_enum",
                create_type=False,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    # Create indexes for bulk_import_jobs
    op.create_index("idx_bulk_jobs_status", "bulk_import_jobs", ["status"])
    op.create_index("idx_bulk_jobs_created_by", "bulk_import_jobs", ["created_by"])

    # Create bulk_import_items table
    op.create_table(
        "bulk_import_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bulk_import_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "success",
                "failed",
                "skipped",
                name="bulk_item_status_enum",
                create_type=False,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("temp_password_enc", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    # Create indexes for bulk_import_items
    op.create_index("idx_bulk_items_job_id", "bulk_import_items", ["job_id"])
    op.create_index(
        "idx_bulk_items_job_status", "bulk_import_items", ["job_id", "status"]
    )
    op.create_index(
        "idx_bulk_items_job_row", "bulk_import_items", ["job_id", "row_number"]
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index("idx_bulk_items_job_row", table_name="bulk_import_items")
    op.drop_index("idx_bulk_items_job_status", table_name="bulk_import_items")
    op.drop_index("idx_bulk_items_job_id", table_name="bulk_import_items")

    op.drop_index("idx_bulk_jobs_created_by", table_name="bulk_import_jobs")
    op.drop_index("idx_bulk_jobs_status", table_name="bulk_import_jobs")

    # Drop tables
    op.drop_table("bulk_import_items")
    op.drop_table("bulk_import_jobs")

    # Drop enums
    op.execute("DROP TYPE IF EXISTS bulk_item_status_enum")
    op.execute("DROP TYPE IF EXISTS bulk_job_status_enum")
    op.execute("DROP TYPE IF EXISTS target_role_enum")
