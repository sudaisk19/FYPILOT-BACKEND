"""Add pg_trgm extension and search indexes

Revision ID: a1b2c3d4e5f6
Revises: 05bbb0352d41
Create Date: 2026-02-10 00:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "05bbb0352d41"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Enable pg_trgm extension for fuzzy search
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # 2. Add GIN Index on users.full_name for fast ILIKE search
    # Using 'gin_trgm_ops' operator class
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_full_name_trgm ON users USING gin (full_name gin_trgm_ops)"
    )

    # 3. Add B-Tree Index on supervisors.department for exact/prefix match
    op.create_index("idx_supervisors_department", "supervisors", ["department"])


def downgrade() -> None:
    # 1. Drop indexes
    op.drop_index("idx_supervisors_department", table_name="supervisors")
    op.execute("DROP INDEX IF EXISTS idx_users_full_name_trgm")

    # 2. Drop extension (Optional - usually keep extensions but strict downgrade removes it)
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
