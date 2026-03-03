"""remove group name

Revision ID: 1defabc12345
Revises: 9eb24e918774
Create Date: 2026-03-02 12:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision = "1defabc12345"
down_revision = "9eb24e918774"
branch_labels = None
depends_on = None


def upgrade() -> None:
    try:
        op.drop_column("groups", "name")
    except Exception:
        pass


def downgrade() -> None:
    try:
        op.add_column("groups", sa.Column("name", sa.String(length=255), nullable=True))
    except Exception:
        pass
