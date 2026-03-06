"""sync faculty is_active = is_supervisor OR is_jury

Revision ID: d1e2f3a4b5c6
Revises: c5e4d3b2a1f0
Create Date: 2026-03-06

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "d1e2f3a4b5c6"
down_revision = "c5e4d3b2a1f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Sync is_active for all existing faculty records:
    # is_active = is_supervisor OR is_jury
    op.execute(
        """
        UPDATE faculty
        SET is_active = (is_supervisor OR is_jury)
        WHERE is_active != (is_supervisor OR is_jury)
        """
    )


def downgrade() -> None:
    # Revert: set all faculty to active
    op.execute(
        """
        UPDATE faculty
        SET is_active = true
        """
    )
