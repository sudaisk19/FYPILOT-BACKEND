"""Move due_at and total_marks from submissions to announcements

Revision ID: move_due_at_total_marks
Revises: add_announcements_submissions
Create Date: 2026-02-10

Moves due_at and total_marks columns from submissions table to announcements table
since these fields belong to the submission request (announcement), not individual submissions.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "move_due_at_total_marks"
down_revision: Union[str, None] = "add_announcements_submissions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add columns to announcements table
    op.add_column(
        "announcements",
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "announcements",
        sa.Column("total_marks", sa.Numeric(), nullable=True),
    )

    # Remove columns from submissions table
    op.drop_column("submissions", "due_at")
    op.drop_column("submissions", "total_marks")


def downgrade() -> None:
    # Add columns back to submissions table
    op.add_column(
        "submissions",
        sa.Column("total_marks", sa.Numeric(), nullable=True),
    )
    op.add_column(
        "submissions",
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Remove columns from announcements table
    op.drop_column("announcements", "total_marks")
    op.drop_column("announcements", "due_at")
