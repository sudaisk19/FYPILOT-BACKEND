"""Add announcements and submissions tables

Revision ID: add_announcements_submissions
Revises: add_bulk_import_tables
Create Date: 2026-02-09

Creates the announcements, announcement_targets, announcement_files,
submissions, submission_files, and templates tables for the
submission tracking and announcement system.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_announcements_submissions"
down_revision: Union[str, None] = "add_bulk_import_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enums
    announcement_role_enum = postgresql.ENUM(
        "admin",
        "supervisor",
        name="announcement_role_enum",
        create_type=False,
    )
    announcement_role_enum.create(op.get_bind(), checkfirst=True)

    submission_type_enum = postgresql.ENUM(
        "official",
        "unofficial",
        name="submission_type_enum",
        create_type=False,
    )
    submission_type_enum.create(op.get_bind(), checkfirst=True)

    submission_status_enum = postgresql.ENUM(
        "pending",
        "submitted",
        "graded",
        "returned",
        name="submission_status_enum",
        create_type=False,
    )
    submission_status_enum.create(op.get_bind(), checkfirst=True)

    file_type_enum = postgresql.ENUM(
        "Template",
        "Document",
        name="file_type_enum",
        create_type=False,
    )
    file_type_enum.create(op.get_bind(), checkfirst=True)

    announcement_target_role_enum = postgresql.ENUM(
        "all_students",
        "all_supervisors",
        name="target_role_enum",
        create_type=False,
    )
    announcement_target_role_enum.create(op.get_bind(), checkfirst=True)

    # Create announcements table
    op.create_table(
        "announcements",
        sa.Column(
            "announcement_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_by_role",
            postgresql.ENUM(
                "admin", "supervisor", name="announcement_role_enum", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_submission_request", sa.Boolean(), default=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )

    # Create trigger for announcements updated_at
    op.execute(
        """
        CREATE OR REPLACE FUNCTION update_announcements_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
          NEW.updated_at = now();
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_update_announcements_updated_at
        BEFORE UPDATE ON announcements
        FOR EACH ROW
        EXECUTE FUNCTION update_announcements_updated_at();
        """
    )

    # Create announcement_targets table
    op.create_table(
        "announcement_targets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "announcement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("announcements.announcement_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "group_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("groups.group_id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "target_role",
            postgresql.ENUM(
                "all_students",
                "all_supervisors",
                name="target_role_enum",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.CheckConstraint(
            "(group_id IS NOT NULL AND target_role IS NULL) OR (group_id IS NULL AND target_role IS NOT NULL)",
            name="check_target_exclusivity",
        ),
    )

    # Create announcement_files table
    op.create_table(
        "announcement_files",
        sa.Column(
            "file_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "announcement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("announcements.announcement_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column(
            "file_type",
            postgresql.ENUM("Template", "Document", name="file_type_enum", create_type=False),
            default="Document",
        ),
        sa.Column("module", sa.Text(), nullable=True),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )

    # Create templates table
    op.create_table(
        "templates",
        sa.Column(
            "template_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("file_name", sa.Text(), nullable=True),
        sa.Column("storage_key", sa.Text(), nullable=True),
        sa.Column("module", sa.Text(), nullable=True),
        sa.Column(
            "uploaded_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )

    # Create submissions table
    op.create_table(
        "submissions",
        sa.Column(
            "submission_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "group_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("groups.group_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "type",
            postgresql.ENUM(
                "official", "unofficial", name="submission_type_enum", create_type=False
            ),
            nullable=False,
            server_default="unofficial",
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending",
                "submitted",
                "graded",
                "returned",
                name="submission_status_enum",
                create_type=False,
            ),
            server_default="submitted",
        ),
        sa.Column(
            "linked_announcement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("announcements.announcement_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_marks", sa.Numeric(), nullable=True),
        sa.Column("obtained_marks", sa.Numeric(), nullable=True),
        sa.Column(
            "graded_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id"),
            nullable=True,
        ),
        sa.Column("graded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )

    # Create trigger for submissions updated_at
    op.execute(
        """
        CREATE OR REPLACE FUNCTION update_submissions_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
          NEW.updated_at = now();
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_update_submissions_updated_at
        BEFORE UPDATE ON submissions
        FOR EACH ROW
        EXECUTE FUNCTION update_submissions_updated_at();
        """
    )

    # Create submission_files table
    op.create_table(
        "submission_files",
        sa.Column(
            "file_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "submission_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("submissions.submission_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("supervisor_comment", sa.Text(), nullable=True),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table("submission_files")
    op.execute("DROP TRIGGER IF EXISTS trg_update_submissions_updated_at ON submissions")
    op.execute("DROP FUNCTION IF EXISTS update_submissions_updated_at()")
    op.drop_table("submissions")
    op.drop_table("templates")
    op.drop_table("announcement_files")
    op.drop_table("announcement_targets")
    op.execute("DROP TRIGGER IF EXISTS trg_update_announcements_updated_at ON announcements")
    op.execute("DROP FUNCTION IF EXISTS update_announcements_updated_at()")
    op.drop_table("announcements")

    # Drop enums
    announcement_target_role_enum = postgresql.ENUM(
        name="target_role_enum", create_type=False
    )
    announcement_target_role_enum.drop(op.get_bind(), checkfirst=True)

    file_type_enum = postgresql.ENUM(name="file_type_enum", create_type=False)
    file_type_enum.drop(op.get_bind(), checkfirst=True)

    submission_status_enum = postgresql.ENUM(
        name="submission_status_enum", create_type=False
    )
    submission_status_enum.drop(op.get_bind(), checkfirst=True)

    submission_type_enum = postgresql.ENUM(
        name="submission_type_enum", create_type=False
    )
    submission_type_enum.drop(op.get_bind(), checkfirst=True)

    announcement_role_enum = postgresql.ENUM(
        name="announcement_role_enum", create_type=False
    )
    announcement_role_enum.drop(op.get_bind(), checkfirst=True)
