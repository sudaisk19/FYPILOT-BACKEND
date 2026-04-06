"""merge dual heads after jury/proposal fixes

Revision ID: e8824ab04c3b
Revises: 0b8a1c2d3e4f, a2b3c4d5e6f7
Create Date: 2026-03-14 01:16:25.458766

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "e8824ab04c3b"
down_revision: Union[str, Sequence[str], None] = ("0b8a1c2d3e4f", "a2b3c4d5e6f7")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
