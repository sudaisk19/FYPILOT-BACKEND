"""auto-generate group cohort + project FYP IDs

Revision ID: f2a4b6c8d0e1
Revises: e8824ab04c3b
Create Date: 2026-04-01 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2a4b6c8d0e1"
down_revision: Union[str, Sequence[str], None] = "e8824ab04c3b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DROP FUNCTION IF EXISTS public.generate_fyp_id() CASCADE;
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.determine_group_cohort(group_uuid UUID)
        RETURNS TEXT
        LANGUAGE plpgsql
        AS
        $$
        DECLARE
            sem TEXT;
            yr INT;
            prefix CHAR(1);
        BEGIN
            SELECT lower(s.fyp_start_semester), s.fyp_start_year
            INTO sem, yr
            FROM group_members gm
            JOIN students s ON s.user_id = gm.student_id
            WHERE gm.group_id = group_uuid
            ORDER BY gm.joined_at ASC
            LIMIT 1;

            IF sem IS NULL OR yr IS NULL THEN
                RETURN NULL;
            END IF;

            IF sem LIKE 'f%%' THEN
                prefix := 'F';
            ELSE
                prefix := 'S';
            END IF;

            RETURN prefix || RIGHT(yr::TEXT, 2);
        END;
        $$;
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.generate_group_cohort()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        AS
        $$
        DECLARE
            computed TEXT;
        BEGIN
            computed := public.determine_group_cohort(NEW.group_id);
            IF computed IS NOT NULL THEN
                NEW.cohort := computed;
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.refresh_group_cohort_from_members()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        AS
        $$
        DECLARE
            target_group UUID;
            computed TEXT;
        BEGIN
            target_group := COALESCE(NEW.group_id, OLD.group_id);

            IF target_group IS NULL THEN
                RETURN COALESCE(NEW, OLD);
            END IF;

            computed := public.determine_group_cohort(target_group);

            UPDATE groups
            SET cohort = computed
            WHERE group_id = target_group;

            RETURN COALESCE(NEW, OLD);
        END;
        $$;
        """
    )

    op.execute(
        """
        DROP TRIGGER IF EXISTS tr_groups_generate_cohort ON groups;
        CREATE TRIGGER tr_groups_generate_cohort
        BEFORE INSERT OR UPDATE ON groups
        FOR EACH ROW
        EXECUTE FUNCTION public.generate_group_cohort();
        """
    )

    op.execute(
        """
        DROP TRIGGER IF EXISTS tr_group_members_refresh_cohort ON group_members;
        CREATE TRIGGER tr_group_members_refresh_cohort
        AFTER INSERT OR UPDATE OR DELETE ON group_members
        FOR EACH ROW
        EXECUTE FUNCTION public.refresh_group_cohort_from_members();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.set_project_fyp_id()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        AS
        $$
        DECLARE
            prefix TEXT;
            next_seq INT;
        BEGIN
            SELECT COALESCE(g.cohort, public.determine_group_cohort(g.group_id))
            INTO prefix
            FROM groups g
            WHERE g.group_id = NEW.group_id
            FOR UPDATE;

            IF prefix IS NULL THEN
                RAISE EXCEPTION 'Cannot generate FYP ID because cohort metadata is missing for group %', NEW.group_id;
            END IF;

            SELECT COALESCE(
                MAX((regexp_match(fyp_id, '^[FS][0-9]{2}-(\d+)$'))[1]::INT),
                0
            ) + 1
            INTO next_seq
            FROM projects
            WHERE fyp_id LIKE prefix || '-%';

            NEW.fyp_id := prefix || '-' || LPAD(next_seq::TEXT, 2, '0');
            RETURN NEW;
        END;
        $$;
        """
    )

    op.execute(
        """
        DROP TRIGGER IF EXISTS tr_projects_set_fyp_id ON projects;
        CREATE TRIGGER tr_projects_set_fyp_id
        BEFORE INSERT ON projects
        FOR EACH ROW
        WHEN (NEW.fyp_id IS NULL)
        EXECUTE FUNCTION public.set_project_fyp_id();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER IF EXISTS tr_projects_set_fyp_id ON projects;
        DROP FUNCTION IF EXISTS public.set_project_fyp_id();
        DROP TRIGGER IF EXISTS tr_groups_generate_cohort ON groups;
        DROP TRIGGER IF EXISTS tr_group_members_refresh_cohort ON group_members;
        DROP FUNCTION IF EXISTS public.generate_group_cohort();
        DROP FUNCTION IF EXISTS public.refresh_group_cohort_from_members();
        DROP FUNCTION IF EXISTS public.determine_group_cohort(UUID);
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.generate_fyp_id()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        AS
        $$
        DECLARE
            prefix TEXT;
            next_seq INT;
        BEGIN
            SELECT g.cohort
            INTO prefix
            FROM groups g
            WHERE g.group_id = NEW.group_id;

            IF prefix IS NULL THEN
                RAISE EXCEPTION 'Group cohort not set before generating FYP ID';
            END IF;

            SELECT COALESCE(
                MAX((regexp_match(fyp_id, '^[FS][0-9]{2}-(\d+)$'))[1]::INT),
                0
            ) + 1
            INTO next_seq
            FROM projects
            WHERE fyp_id LIKE prefix || '-%';

            NEW.fyp_id := prefix || '-' || LPAD(next_seq::TEXT, 2, '0');
            RETURN NEW;
        END;
        $$;
        """
    )

    op.execute(
        """
        CREATE TRIGGER tr_projects_generate_fyp_id
        BEFORE INSERT ON projects
        FOR EACH ROW
        WHEN (NEW.fyp_id IS NULL)
        EXECUTE FUNCTION public.generate_fyp_id();
        """
    )
