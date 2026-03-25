# app/repositories/submission_repository.py
from __future__ import annotations

from typing import List, Optional, Tuple
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


# Singleton instance
submission_repository = SubmissionRepository()
