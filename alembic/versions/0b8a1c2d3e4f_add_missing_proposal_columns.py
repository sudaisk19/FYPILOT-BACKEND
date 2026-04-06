"""add missing columns to proposal evaluations

Revision ID: 0b8a1c2d3e4f
Revises: e7c2a1b4d5f7
Create Date: 2026-03-13 15:45:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0b8a1c2d3e4f"
down_revision: Union[str, Sequence[str], None] = "e7c2a1b4d5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE proposal_evaluations
        ADD COLUMN IF NOT EXISTS deliverables TEXT;
        """
    )

    op.execute(
        """
        ALTER TABLE proposal_evaluations
        ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
        """
    )

    op.execute(
        """
        ALTER TABLE jury_evaluations
        ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
        """
    )

    op.execute(
        """
        ALTER TABLE proposal_evaluation_config
        ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();
        """
    )

    op.execute(
        """
        ALTER TABLE proposal_evaluation_config
        ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
        """
    )

    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_proposal_evaluations_updated_at ON proposal_evaluations;
        """
    )
    op.execute(
        """
        DROP TRIGGER IF EXISTS tr_proposal_evaluations_updated_at ON proposal_evaluations;
        """
    )
    op.execute(
        """
        CREATE TRIGGER tr_proposal_evaluations_updated_at
        BEFORE UPDATE ON proposal_evaluations
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """
    )

    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_jury_evaluations_updated_at ON jury_evaluations;
        """
    )
    op.execute(
        """
        DROP TRIGGER IF EXISTS tr_jury_evaluations_updated_at ON jury_evaluations;
        """
    )
    op.execute(
        """
        CREATE TRIGGER tr_jury_evaluations_updated_at
        BEFORE UPDATE ON jury_evaluations
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """
    )

    op.execute(
        """
        DROP TRIGGER IF EXISTS tr_proposal_eval_config_updated_at ON proposal_evaluation_config;
        """
    )
    op.execute(
        """
        CREATE TRIGGER tr_proposal_eval_config_updated_at
        BEFORE UPDATE ON proposal_evaluation_config
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE proposal_evaluations DROP COLUMN IF EXISTS deliverables;
        """
    )
