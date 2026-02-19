"""Create supervisor evaluations table

Revision ID: c5e4d3b2a1f0
Revises: b7f3e4d29ab3
Create Date: 2026-02-18 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "c5e4d3b2a1f0"
down_revision = "b7f3e4d29ab3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "supervisor_evaluations",
        sa.Column(
            "evaluation_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "milestone_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("admin_milestone.milestone_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "group_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("groups.group_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "supervisor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("supervisors.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("marks", sa.Numeric(), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("wbs_achieved", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "milestone_id",
            "group_id",
            "supervisor_id",
            name="uq_supervisor_eval_unique",
        ),
    )

    op.create_index(
        "idx_supervisor_eval_milestone",
        "supervisor_evaluations",
        ["milestone_id"],
    )
    op.create_index(
        "idx_supervisor_eval_group",
        "supervisor_evaluations",
        ["group_id"],
    )

    op.execute(
        """
        CREATE TRIGGER tr_supervisor_evaluations_updated_at
        BEFORE UPDATE ON supervisor_evaluations
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS tr_supervisor_evaluations_updated_at ON supervisor_evaluations")
    op.drop_index("idx_supervisor_eval_group", table_name="supervisor_evaluations")
    op.drop_index("idx_supervisor_eval_milestone", table_name="supervisor_evaluations")
    op.drop_table("supervisor_evaluations")
