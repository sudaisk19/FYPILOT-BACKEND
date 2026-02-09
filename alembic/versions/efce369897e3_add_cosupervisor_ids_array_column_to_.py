"""Add cosupervisor_ids array column to groups

Revision ID: efce369897e3
Revises: add_bulk_import_tables
Create Date: 2026-02-08 14:04:51.120918

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "efce369897e3"
down_revision: Union[str, Sequence[str], None] = "add_bulk_import_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add cosupervisor_ids array column to groups table."""
    op.add_column(
        "groups",
        sa.Column(
            "cosupervisor_ids",
            ARRAY(UUID(as_uuid=True)),
            nullable=True,
            server_default="{}",
            comment="Array of co-supervisor user IDs",
        ),
    )


def downgrade() -> None:
    """Remove cosupervisor_ids column from groups table."""
    op.drop_column("groups", "cosupervisor_ids")
