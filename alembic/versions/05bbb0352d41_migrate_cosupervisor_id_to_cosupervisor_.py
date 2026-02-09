"""Migrate cosupervisor_id to cosupervisor_ids array and drop old column

Revision ID: 05bbb0352d41
Revises: efce369897e3
Create Date: 2026-02-08 14:06:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "05bbb0352d41"
down_revision: Union[str, Sequence[str], None] = "efce369897e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Migrate existing cosupervisor_id data to cosupervisor_ids array,
    then drop the old cosupervisor_id column.
    """
    # Step 1: Migrate existing data from cosupervisor_id to cosupervisor_ids array
    op.execute(
        """
        UPDATE groups 
        SET cosupervisor_ids = ARRAY[cosupervisor_id]
        WHERE cosupervisor_id IS NOT NULL 
          AND (cosupervisor_ids IS NULL OR cosupervisor_ids = '{}')
    """
    )

    # Step 2: Drop the old cosupervisor_id column
    op.drop_constraint("groups_cosupervisor_id_fkey", "groups", type_="foreignkey")
    op.drop_column("groups", "cosupervisor_id")


def downgrade() -> None:
    """
    Re-add cosupervisor_id column and migrate first element back from array.
    """
    from sqlalchemy.dialects.postgresql import UUID

    # Step 1: Re-add the cosupervisor_id column
    op.add_column(
        "groups", sa.Column("cosupervisor_id", UUID(as_uuid=True), nullable=True)
    )

    # Step 2: Add back the foreign key constraint
    op.create_foreign_key(
        "groups_cosupervisor_id_fkey",
        "groups",
        "supervisors",
        ["cosupervisor_id"],
        ["user_id"],
    )

    # Step 3: Migrate first element from array back to single column
    op.execute(
        """
        UPDATE groups 
        SET cosupervisor_id = cosupervisor_ids[1]
        WHERE cosupervisor_ids IS NOT NULL 
          AND array_length(cosupervisor_ids, 1) > 0
    """
    )
