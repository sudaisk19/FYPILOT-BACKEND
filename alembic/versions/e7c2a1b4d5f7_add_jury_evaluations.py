"""create jury + proposal evaluation tables

Revision ID: e7c2a1b4d5f7
Revises: d1e2f3a4b5c6
Create Date: 2026-03-13 10:15:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7c2a1b4d5f7"
down_revision: Union[str, Sequence[str], None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

jury_grade_enum = sa.Enum(
    "A+",
    "A",
    "A-",
    "B+",
    "B",
    "B-",
    "C+",
    "C",
    "C-",
    "D+",
    "D",
    "F",
    name="jury_grade_enum",
)

proposal_status_enum = sa.Enum(
    "accepted",
    "accepted_with_changes",
    "rejected",
    name="proposal_status_enum",
)

jury_form_type_enum = sa.Enum("normal", "proposal", name="jury_form_type_enum")


def upgrade() -> None:
    bind = op.get_bind()

    # Ensure enums exist
    jury_grade_enum.create(bind, checkfirst=True)
    proposal_status_enum.create(bind, checkfirst=True)
    jury_form_type_enum.create(bind, checkfirst=True)

    # Extend admin_milestone with jury form selector
    op.add_column(
        "admin_milestone",
        sa.Column("jury_form_type", jury_form_type_enum, nullable=True),
    )

    # Jury evaluations table
    op.create_table(
        "jury_evaluations",
        sa.Column(
            "evaluation_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "group_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("groups.group_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "jury_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("faculty.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "milestone_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("admin_milestone.milestone_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("letter_grade", jury_grade_enum, nullable=False),
        sa.Column("numeric_marks", sa.Numeric(5, 2), nullable=True),
        sa.Column("comments", sa.Text(), nullable=True),
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
            "group_id",
            "jury_id",
            "milestone_id",
            name="uq_jury_evaluation_unique",
        ),
    )
    op.create_index(
        "idx_jury_eval_group",
        "jury_evaluations",
        ["group_id"],
    )
    op.create_index(
        "idx_jury_eval_milestone",
        "jury_evaluations",
        ["milestone_id"],
    )
    op.create_index(
        "idx_jury_eval_jury",
        "jury_evaluations",
        ["jury_id"],
    )

    op.execute(
        """
        CREATE TRIGGER tr_jury_evaluations_updated_at
        BEFORE UPDATE ON jury_evaluations
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """
    )

    # Proposal evaluations table
    op.create_table(
        "proposal_evaluations",
        sa.Column(
            "evaluation_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "group_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("groups.group_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "jury_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("faculty.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "milestone_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("admin_milestone.milestone_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("introduction", sa.Numeric(3, 1), nullable=True),
        sa.Column("literature_review", sa.Numeric(3, 1), nullable=True),
        sa.Column("methodology", sa.Numeric(3, 1), nullable=True),
        sa.Column("planning", sa.Numeric(3, 1), nullable=True),
        sa.Column("system_diagram", sa.Numeric(3, 1), nullable=True),
        sa.Column("total_marks", sa.Numeric(3, 1), nullable=True),
        sa.Column("recommended_changes", sa.Text(), nullable=True),
        sa.Column("project_status", proposal_status_enum, nullable=True),
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
            "group_id",
            "jury_id",
            "milestone_id",
            name="uq_proposal_evaluation_unique",
        ),
    )
    op.create_index(
        "idx_proposal_eval_group",
        "proposal_evaluations",
        ["group_id"],
    )
    op.create_index(
        "idx_proposal_eval_milestone",
        "proposal_evaluations",
        ["milestone_id"],
    )
    op.create_index(
        "idx_proposal_eval_jury",
        "proposal_evaluations",
        ["jury_id"],
    )

    op.execute(
        """
        CREATE TRIGGER tr_proposal_evaluations_updated_at
        BEFORE UPDATE ON proposal_evaluations
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """
    )

    # Proposal evaluation config table + seed row
    op.create_table(
        "proposal_evaluation_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("intro_max", sa.Numeric(3, 1), nullable=False, server_default=sa.text("2")),
        sa.Column(
            "literature_max",
            sa.Numeric(3, 1),
            nullable=False,
            server_default=sa.text("2"),
        ),
        sa.Column(
            "methodology_max",
            sa.Numeric(3, 1),
            nullable=False,
            server_default=sa.text("2"),
        ),
        sa.Column(
            "planning_max",
            sa.Numeric(3, 1),
            nullable=False,
            server_default=sa.text("2"),
        ),
        sa.Column(
            "diagram_max",
            sa.Numeric(3, 1),
            nullable=False,
            server_default=sa.text("2"),
        ),
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
    )

    op.execute(
        """
        INSERT INTO proposal_evaluation_config (id, intro_max, literature_max, methodology_max, planning_max, diagram_max)
        VALUES (1, 2, 2, 2, 2, 2)
        ON CONFLICT (id) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.drop_table("proposal_evaluation_config")

    op.execute(
        "DROP TRIGGER IF EXISTS tr_proposal_evaluations_updated_at ON proposal_evaluations"
    )
    op.drop_index("idx_proposal_eval_jury", table_name="proposal_evaluations")
    op.drop_index("idx_proposal_eval_milestone", table_name="proposal_evaluations")
    op.drop_index("idx_proposal_eval_group", table_name="proposal_evaluations")
    op.drop_table("proposal_evaluations")

    op.execute(
        "DROP TRIGGER IF EXISTS tr_jury_evaluations_updated_at ON jury_evaluations"
    )
    op.drop_index("idx_jury_eval_jury", table_name="jury_evaluations")
    op.drop_index("idx_jury_eval_milestone", table_name="jury_evaluations")
    op.drop_index("idx_jury_eval_group", table_name="jury_evaluations")
    op.drop_table("jury_evaluations")

    op.drop_column("admin_milestone", "jury_form_type")

    # Drop enums last
    proposal_status_enum.drop(op.get_bind(), checkfirst=False)
    jury_grade_enum.drop(op.get_bind(), checkfirst=False)
    jury_form_type_enum.drop(op.get_bind(), checkfirst=False)