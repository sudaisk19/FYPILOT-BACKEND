"""merge multiple heads

Revision ID: 9eb24e918774
Revises: add_jury_assignment_tables, c5e4d3b2a1f0
Create Date: 2026-03-02 15:36:37.091657

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "9eb24e918774"
down_revision: Union[str, Sequence[str], None] = (
    "add_jury_assignment_tables",
    "c5e4d3b2a1f0",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
