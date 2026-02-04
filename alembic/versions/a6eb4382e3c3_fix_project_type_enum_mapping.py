"""fix_project_type_enum_mapping

This migration fixes the SQLAlchemy enum mapping issue for project_type_enum.
The issue is that SQLAlchemy is looking for 'product_and' instead of 'product and research'.

We'll recreate the enum type to ensure proper mapping.

Revision ID: a6eb4382e3c3
Revises: 001
Create Date: 2026-01-26 23:10:49.046675

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a6eb4382e3c3"
down_revision: Union[str, Sequence[str], None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - recreate enum to fix SQLAlchemy mapping issues."""
    # Get connection
    connection = op.get_bind()

    # First, we need to temporarily change the column types to TEXT
    # so we can drop and recreate the enum
    connection.execute(
        sa.text(
            """
        ALTER TABLE projects ALTER COLUMN project_type TYPE TEXT;
        ALTER TABLE supervisors ALTER COLUMN project_type TYPE TEXT;
    """
        )
    )

    # Drop the existing enum type
    connection.execute(sa.text("DROP TYPE IF EXISTS project_type_enum CASCADE;"))

    # Create the new enum type with proper values
    connection.execute(
        sa.text(
            """
        CREATE TYPE project_type_enum AS ENUM ('research', 'product', 'product and research');
    """
        )
    )

    # Convert columns back to use the enum type
    connection.execute(
        sa.text(
            """
        ALTER TABLE projects ALTER COLUMN project_type TYPE project_type_enum USING project_type::project_type_enum;
        ALTER TABLE supervisors ALTER COLUMN project_type TYPE project_type_enum USING project_type::project_type_enum;
    """
        )
    )

    connection.commit()


def downgrade() -> None:
    """Downgrade schema - this is essentially a no-op since we're fixing mapping, not changing data."""
