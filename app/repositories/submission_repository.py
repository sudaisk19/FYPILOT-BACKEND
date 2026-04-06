# app/repositories/submission_repository.py
from __future__ import annotations

from typing import Any, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.announcement import Announcement
from app.models.group import Group, GroupMember
from app.models.submission import (
    Submission,
    SubmissionTypeEnum,
)
from app.repositories.base import BaseRepository


class SubmissionRepository(BaseRepository[Submission]):

    def __init__(self) -> None:
        super().__init__(Submission)

    # ─── STUDENT GROUP HELPER ─────────────────────────────────────────────────

    async def get_student_group(
        self, db: AsyncSession, student_id: UUID
    ) -> Optional[Group]:
        """Return the group the student belongs to, or None."""
        result = await db.execute(
            select(Group)
            .join(GroupMember, GroupMember.group_id == Group.group_id)
            .where(GroupMember.student_id == student_id)
            .limit(1)
        )
        return result.scalars().first()

    # ─── OFFICIAL SUBMISSIONS ─────────────────────────────────────────────────

    async def list_official_for_student(
        self,
        db: AsyncSession,
        *,
        group_id: UUID,
        page: int,
        per_page: int,
    ) -> Tuple[List[Submission], int]:
        """
        Paginated list of official submissions for a student's group.
        Eagerly loads files (for file_count) and linked_announcement (for due_date, total_marks).
        """
        base_query = (
            select(Submission)
            .options(
                selectinload(Submission.files),
                selectinload(Submission.linked_announcement).selectinload(
                    Announcement.files
                ),
            )
            .where(
                Submission.group_id == group_id,
                Submission.type == SubmissionTypeEnum.official,
            )
        )

        count_query = select(func.count()).select_from(base_query.subquery())
        total_items = (await db.execute(count_query)).scalar_one()

        offset = (page - 1) * per_page
        paginated_query = (
            base_query.order_by(Submission.updated_at.desc())
            .offset(offset)
            .limit(per_page)
        )
        result = await db.execute(paginated_query)
        return list(result.scalars().unique().all()), total_items

    async def get_official_by_id_for_student(
        self,
        db: AsyncSession,
        *,
        submission_id: UUID,
        group_id: UUID,
    ) -> Optional[Submission]:
        """
        Fetch a single official submission by ID, scoped to the student's group.
        Eagerly loads files and linked announcement (with its files for templates).
        """
        result = await db.execute(
            select(Submission)
            .options(
                selectinload(Submission.files),
                selectinload(Submission.linked_announcement).selectinload(
                    Announcement.files
                ),
            )
            .where(
                Submission.submission_id == submission_id,
                Submission.group_id == group_id,
                Submission.type == SubmissionTypeEnum.official,
            )
        )
        return result.scalars().first()

    # ─── UNOFFICIAL SUBMISSIONS ───────────────────────────────────────────────

    async def list_unofficial_for_student(
        self,
        db: AsyncSession,
        *,
        group_id: UUID,
        page: int,
        per_page: int,
    ) -> Tuple[List[Submission], int]:
        """Paginated list of unofficial submissions for a student's group."""
        base_query = (
            select(Submission)
            .options(selectinload(Submission.files))
            .where(
                Submission.group_id == group_id,
                Submission.type == SubmissionTypeEnum.unofficial,
            )
        )

        count_query = select(func.count()).select_from(base_query.subquery())
        total_items = (await db.execute(count_query)).scalar_one()

        offset = (page - 1) * per_page
        result = await db.execute(
            base_query.order_by(Submission.updated_at.desc())
            .offset(offset)
            .limit(per_page)
        )
        return list(result.scalars().unique().all()), total_items

    async def get_unofficial_by_id_for_student(
        self,
        db: AsyncSession,
        *,
        submission_id: UUID,
        group_id: UUID,
    ) -> Optional[Submission]:
        """Fetch a single unofficial submission scoped to the student's group, eagerly loading linked announcement and files."""
        result = await db.execute(
            select(Submission)
            .options(
                selectinload(Submission.files),
                selectinload(Submission.linked_announcement).selectinload(
                    Announcement.files
                ),
            )
            .where(
                Submission.submission_id == submission_id,
                Submission.group_id == group_id,
                Submission.type == SubmissionTypeEnum.unofficial,
            )
        )
        return result.scalars().first()

    async def get_submissions_by_announcement(
        self, db: AsyncSession, announcement_id: UUID
    ) -> List[Submission]:
        """Fetch all submissions for a given announcement."""
        result = await db.execute(
            select(Submission).where(
                Submission.linked_announcement_id == announcement_id
            )
        )
        return list(result.scalars().all())

    async def get_evaluation_details(
        self, db: AsyncSession, submission_id: UUID
    ) -> Optional[Submission]:
        """Fetch full submission details for supervisor evaluation."""
        result = await db.execute(
            select(Submission)
            .options(
                selectinload(Submission.files),
                selectinload(Submission.linked_announcement),
                selectinload(Submission.group),
            )
            .where(Submission.submission_id == submission_id)
        )
        return result.scalars().first()

    async def get_submission_file_details(
        self, db: AsyncSession, submission_id: UUID, file_id: UUID
    ) -> Optional[Any]:
        """Fetch a specific submission file with its loaded submission and group."""
        from app.models.submission import SubmissionFile

        result = await db.execute(
            select(SubmissionFile)
            .join(Submission, SubmissionFile.submission_id == Submission.submission_id)
            .options(
                selectinload(SubmissionFile.submission).selectinload(Submission.group)
            )
            .where(
                SubmissionFile.file_id == file_id,
                SubmissionFile.submission_id == submission_id,
            )
        )
        return result.scalars().first()

    async def get_existing_group_ids_for_announcement(
        self, db: AsyncSession, announcement_id: UUID, group_ids: List[UUID]
    ) -> set[UUID]:
        """Get group IDs that already have a submission for this announcement."""
        result = await db.execute(
            select(Submission.group_id).where(
                Submission.linked_announcement_id == announcement_id,
                Submission.group_id.in_(group_ids),
            )
        )
        return set(result.scalars().all())


# Singleton instance
submission_repository = SubmissionRepository()
