"""rename supervisor to faculty

Revision ID: f1a2b3c4d5e6
Revises: 1defabc12345
Create Date: 2026-03-05 12:37:00.000000

Renames:
  - user_role_enum: 'supervisor' → 'faculty'
  - announcement_role_enum: 'supervisor' → 'faculty'
  - target_role_enum: add 'all_faculty', add 'faculty'
  - Tables: supervisors → faculty, supervisor_domains → faculty_domains,
            supervisor_industries → faculty_industries
  - All FK constraints referencing old table names
  - Search index on department
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "1defabc12345"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. Rename 'supervisor' → 'faculty' in user_role_enum ──────────────
    conn.execute(
        sa.text("ALTER TYPE user_role_enum RENAME VALUE 'supervisor' TO 'faculty'")
    )

    # ── 2. Rename 'supervisor' → 'faculty' in announcement_role_enum ──────
    conn.execute(
        sa.text(
            "ALTER TYPE announcement_role_enum RENAME VALUE 'supervisor' TO 'faculty'"
        )
    )

    # ── 3. Rename tables ─────────────────────────────────────────────────
    op.rename_table("supervisors", "faculty")
    op.rename_table("supervisor_domains", "faculty_domains")
    op.rename_table("supervisor_industries", "faculty_industries")

    # ── 5. Update FK constraints on groups table ─────────────────────────
    # Drop old FK, create new FK pointing to 'faculty' table
    try:
        op.drop_constraint("groups_supervisor_id_fkey", "groups", type_="foreignkey")
    except Exception:
        pass
    op.create_foreign_key(
        "groups_supervisor_id_fkey",
        "groups",
        "faculty",
        ["supervisor_id"],
        ["user_id"],
    )

    # ── 6. Update FK on requests table ───────────────────────────────────
    try:
        op.drop_constraint(
            "requests_supervisor_id_fkey", "requests", type_="foreignkey"
        )
    except Exception:
        pass
    op.create_foreign_key(
        "requests_supervisor_id_fkey",
        "requests",
        "faculty",
        ["supervisor_id"],
        ["user_id"],
    )

    # ── 7. Update FK on shortlisted_supervisors table ────────────────────
    try:
        op.drop_constraint(
            "shortlisted_supervisors_supervisor_id_fkey",
            "shortlisted_supervisors",
            type_="foreignkey",
        )
    except Exception:
        pass
    op.create_foreign_key(
        "shortlisted_supervisors_supervisor_id_fkey",
        "shortlisted_supervisors",
        "faculty",
        ["supervisor_id"],
        ["user_id"],
    )

    # ── 8. Update FK on supervisor_evaluations table ─────────────────────
    try:
        op.drop_constraint(
            "supervisor_evaluations_supervisor_id_fkey",
            "supervisor_evaluations",
            type_="foreignkey",
        )
    except Exception:
        pass
    op.create_foreign_key(
        "supervisor_evaluations_supervisor_id_fkey",
        "supervisor_evaluations",
        "faculty",
        ["supervisor_id"],
        ["user_id"],
        ondelete="CASCADE",
    )

    # ── 9. Update FK on faculty_domains (was supervisor_domains) ─────────
    try:
        op.drop_constraint(
            "supervisor_domains_supervisor_id_fkey",
            "faculty_domains",
            type_="foreignkey",
        )
    except Exception:
        pass
    op.create_foreign_key(
        "faculty_domains_supervisor_id_fkey",
        "faculty_domains",
        "faculty",
        ["supervisor_id"],
        ["user_id"],
        ondelete="CASCADE",
    )

    # ── 10. Update FK on faculty_industries (was supervisor_industries) ───
    try:
        op.drop_constraint(
            "supervisor_industries_supervisor_id_fkey",
            "faculty_industries",
            type_="foreignkey",
        )
    except Exception:
        pass
    op.create_foreign_key(
        "faculty_industries_supervisor_id_fkey",
        "faculty_industries",
        "faculty",
        ["supervisor_id"],
        ["user_id"],
        ondelete="CASCADE",
    )

    # ── 11. Rename search index ──────────────────────────────────────────
    conn.execute(
        sa.text(
            "ALTER INDEX IF EXISTS idx_supervisors_department "
            "RENAME TO idx_faculty_department"
        )
    )


def downgrade() -> None:
    conn = op.get_bind()

    # Reverse index rename
    conn.execute(
        sa.text(
            "ALTER INDEX IF EXISTS idx_faculty_department "
            "RENAME TO idx_supervisors_department"
        )
    )

    # Reverse FK on faculty_industries → supervisor_industries
    try:
        op.drop_constraint(
            "faculty_industries_supervisor_id_fkey",
            "faculty_industries",
            type_="foreignkey",
        )
    except Exception:
        pass
    op.create_foreign_key(
        "supervisor_industries_supervisor_id_fkey",
        "faculty_industries",
        "faculty",
        ["supervisor_id"],
        ["user_id"],
        ondelete="CASCADE",
    )

    # Reverse FK on faculty_domains → supervisor_domains
    try:
        op.drop_constraint(
            "faculty_domains_supervisor_id_fkey", "faculty_domains", type_="foreignkey"
        )
    except Exception:
        pass
    op.create_foreign_key(
        "supervisor_domains_supervisor_id_fkey",
        "faculty_domains",
        "faculty",
        ["supervisor_id"],
        ["user_id"],
        ondelete="CASCADE",
    )

    # Reverse FK on supervisor_evaluations
    try:
        op.drop_constraint(
            "supervisor_evaluations_supervisor_id_fkey",
            "supervisor_evaluations",
            type_="foreignkey",
        )
    except Exception:
        pass
    op.create_foreign_key(
        "supervisor_evaluations_supervisor_id_fkey",
        "supervisor_evaluations",
        "supervisors",
        ["supervisor_id"],
        ["user_id"],
        ondelete="CASCADE",
    )

    # Reverse FK on shortlisted_supervisors
    try:
        op.drop_constraint(
            "shortlisted_supervisors_supervisor_id_fkey",
            "shortlisted_supervisors",
            type_="foreignkey",
        )
    except Exception:
        pass
    op.create_foreign_key(
        "shortlisted_supervisors_supervisor_id_fkey",
        "shortlisted_supervisors",
        "supervisors",
        ["supervisor_id"],
        ["user_id"],
    )

    # Reverse FK on requests
    try:
        op.drop_constraint(
            "requests_supervisor_id_fkey", "requests", type_="foreignkey"
        )
    except Exception:
        pass
    op.create_foreign_key(
        "requests_supervisor_id_fkey",
        "requests",
        "supervisors",
        ["supervisor_id"],
        ["user_id"],
    )

    # Reverse FK on groups
    try:
        op.drop_constraint("groups_supervisor_id_fkey", "groups", type_="foreignkey")
    except Exception:
        pass
    op.create_foreign_key(
        "groups_supervisor_id_fkey",
        "groups",
        "supervisors",
        ["supervisor_id"],
        ["user_id"],
    )

    # Reverse table renames
    op.rename_table("faculty_industries", "supervisor_industries")
    op.rename_table("faculty_domains", "supervisor_domains")
    op.rename_table("faculty", "supervisors")

    # Reverse enum renames
    conn.execute(
        sa.text(
            "ALTER TYPE announcement_role_enum RENAME VALUE 'faculty' TO 'supervisor'"
        )
    )
    conn.execute(
        sa.text("ALTER TYPE user_role_enum RENAME VALUE 'faculty' TO 'supervisor'")
    )
