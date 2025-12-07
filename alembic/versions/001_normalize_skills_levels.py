"""Normalize skills_levels - set default value 1 for all skills

Revision ID: 001
Revises:
Create Date: 2025-12-07

This migration ensures that whenever a student has skills but empty skills_levels,
we populate skills_levels with default value 1 for each skill.
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Upgrade migration:
    - Update all existing students with skills but empty/null skills_levels
    - Set skills_levels to have default value 1 for each skill
    """
    # Get connection
    connection = op.get_bind()

    # SQL to normalize skills_levels
    # For each student with skills, if skills_levels is empty, populate it with skill->1 mapping
    normalize_sql = """
    UPDATE students
    SET skills_levels = (
        SELECT jsonb_object_agg(skill, 1)
        FROM unnest(skills) AS skill
    )
    WHERE skills IS NOT NULL 
      AND skills != ARRAY[]::text[]
      AND (skills_levels IS NULL OR skills_levels = '{}'::jsonb);
    """

    connection.execute(sa.text(normalize_sql))
    connection.commit()


def downgrade() -> None:
    """
    Downgrade migration:
    - Reset skills_levels to empty object for rows we modified
    Note: We can't perfectly reverse this, so we just reset to empty
    """
    connection = op.get_bind()

    # Reset to empty JSONB
    reset_sql = """
    UPDATE students
    SET skills_levels = '{}'::jsonb
    WHERE skills_levels IS NOT NULL;
    """

    connection.execute(sa.text(reset_sql))
    connection.commit()
