"""Add activation and visibility flags to admin milestones

Revision ID: b7f3e4d29ab3
Revises: a1b2c3d4e5f6
Create Date: 2026-02-18 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "b7f3e4d29ab3"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "admin_milestone",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "admin_milestone",
        sa.Column("activated_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "admin_milestone",
        sa.Column(
            "marks_visible_to_students",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    op.execute(
        """
        UPDATE admin_milestone
        SET is_active = TRUE,
            activated_at = COALESCE(activated_at, created_at)
        """
    )

    op.drop_column("admin_milestone", "activity")


def downgrade() -> None:
    op.add_column("admin_milestone", sa.Column("activity", sa.Text(), nullable=True))
    op.drop_column("admin_milestone", "marks_visible_to_students")
    op.drop_column("admin_milestone", "activated_at")
    op.drop_column("admin_milestone", "is_active")
