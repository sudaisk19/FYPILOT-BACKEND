"""Add jury assignment tables

Revision ID: add_jury_assignment_tables
Revises: add_bulk_import_tables
Create Date: 2026-02-18

Creates the jury_assignment_batches and jury_assignments tables
for automated jury assignment functionality (lean schema).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_jury_assignment_tables"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum using raw SQL (avoids SQLAlchemy DDL event conflicts)
    op.execute(
        "CREATE TYPE jury_batch_status_enum AS ENUM "
        "('processing', 'completed', 'failed')"
    )

    # ── Table A: jury_assignment_batches (the container / tracker) ──
    op.create_table(
        "jury_assignment_batches",
        sa.Column(
            "batch_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "processing",
                "completed",
                "failed",
                name="jury_batch_status_enum",
                create_type=False,
            ),
            nullable=False,
            server_default="processing",
        ),
        sa.Column("error_log", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    op.create_index("idx_jury_batches_status", "jury_assignment_batches", ["status"])

    # ── Table B: jury_assignments (the data) ──
    op.create_table(
        "jury_assignments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "batch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jury_assignment_batches.batch_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.project_id"),
            nullable=False,
        ),
        sa.Column(
            "jury_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id"),
            nullable=False,
        ),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
    )

    # Indexes
    op.create_index("idx_jury_assignments_batch_id", "jury_assignments", ["batch_id"])
    op.create_index("idx_jury_assignments_jury_id", "jury_assignments", ["jury_id"])
    op.create_unique_constraint(
        "uq_jury_assignment_project_jury",
        "jury_assignments",
        ["project_id", "jury_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_jury_assignment_project_jury",
        "jury_assignments",
        type_="unique",
    )
    op.drop_index("idx_jury_assignments_jury_id", table_name="jury_assignments")
    op.drop_index("idx_jury_assignments_batch_id", table_name="jury_assignments")
    op.drop_index("idx_jury_batches_status", table_name="jury_assignment_batches")

    op.drop_table("jury_assignments")
    op.drop_table("jury_assignment_batches")

    op.execute("DROP TYPE IF EXISTS jury_batch_status_enum")
