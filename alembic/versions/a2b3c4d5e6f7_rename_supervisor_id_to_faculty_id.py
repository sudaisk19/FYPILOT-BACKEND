"""rename supervisor_id to faculty_id in 4 tables

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-03-05 13:05:00.000000

Renames supervisor_id column to faculty_id in:
  - faculty_domains
  - faculty_industries
  - requests
  - shortlisted_supervisors
"""

from typing import Sequence, Union

from alembic import op

revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. faculty_domains: rename column
    op.alter_column("faculty_domains", "supervisor_id", new_column_name="faculty_id")

    # 2. faculty_industries: rename column
    op.alter_column("faculty_industries", "supervisor_id", new_column_name="faculty_id")

    # 3. requests: rename column
    op.alter_column("requests", "supervisor_id", new_column_name="faculty_id")

    # 4. shortlisted_supervisors: rename column
    op.alter_column(
        "shortlisted_supervisors", "supervisor_id", new_column_name="faculty_id"
    )


def downgrade() -> None:
    op.alter_column(
        "shortlisted_supervisors", "faculty_id", new_column_name="supervisor_id"
    )
    op.alter_column("requests", "faculty_id", new_column_name="supervisor_id")
    op.alter_column("faculty_industries", "faculty_id", new_column_name="supervisor_id")
    op.alter_column("faculty_domains", "faculty_id", new_column_name="supervisor_id")
