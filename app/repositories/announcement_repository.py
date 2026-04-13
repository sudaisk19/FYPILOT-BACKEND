# app/repositories/announcement_repository.py
from __future__ import annotations

from datetime import datetime
from typing import Iterable, List, Optional, Sequence, Tuple
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.db import supabase
from app.models.announcement import (
    Announcement,
    AnnouncementFile,
    AnnouncementRoleEnum,
    AnnouncementTarget,
    FileTypeEnum,
    TargetRoleEnum,
)
from app.repositories.base import BaseRepository
from app.services.storage_service import delete_file_from_supabase


class AnnouncementRepository(BaseRepository[Announcement]):

    def __init__(self) -> None:
        super().__init__(Announcement)

    # ─── SHARED / ADMIN METHODS ───────────────────────────────────────────────

    async def get_by_id(
        self, db: AsyncSession, announcement_id: UUID
    ) -> Optional[Announcement]:
        result = await db.execute(
            select(Announcement)
            .where(Announcement.announcement_id == announcement_id)
            .options(
                selectinload(Announcement.targets),
                selectinload(Announcement.files),
            )
        )
        return result.scalars().first()

    async def get_paginated(
        self, db: AsyncSession, page: int, size: int
    ) -> Tuple[Sequence[Announcement], int]:
        offset = (page - 1) * size
        base_filters = (
            Announcement.created_by_role == AnnouncementRoleEnum.admin,
            Announcement.is_submission_request == False,  # noqa: E712
        )

        query = (
            select(Announcement)
            .options(
                selectinload(Announcement.targets),
                selectinload(Announcement.files),
            )
            .where(*base_filters)
            .order_by(Announcement.created_at.desc())
            .offset(offset)
            .limit(size)
        )
        rows = (await db.execute(query)).scalars().all()
        total_query = select(func.count(Announcement.announcement_id)).where(
            *base_filters
        )
        total = (await db.execute(total_query)).scalar_one()
        return rows, total

    async def create_announcement(
        self,
        db: AsyncSession,
        *,
        created_by: UUID,
        created_by_role: AnnouncementRoleEnum,
        title: str,
        description: Optional[str],
        target_role: TargetRoleEnum,
        is_submission_request: bool = False,
        targets: Optional[Iterable[UUID | None]] = None,
        files: Optional[
            Iterable[Tuple[str, str, FileTypeEnum, Optional[str], Optional[int]]]
        ] = None,
        due_at: Optional[datetime] = None,
        total_marks: Optional[float] = None,
    ) -> Announcement:
        announcement = Announcement(
            created_by=created_by,
            created_by_role=created_by_role,
            title=title,
            description=description,
            is_submission_request=is_submission_request,
            due_at=due_at,
            total_marks=total_marks,
        )

        target_rows: list[AnnouncementTarget] = []
        if targets:
            target_rows = [
                AnnouncementTarget(group_id=group_id, target_role=target_role)
                for group_id in targets
            ]

        if not target_rows:
            target_rows = [AnnouncementTarget(group_id=None, target_role=target_role)]

        announcement.targets = target_rows

        if files:
            announcement.files = [
                AnnouncementFile(
                    file_name=file_name,
                    storage_key=storage_key,
                    file_type=file_type,
                    mime_type=mime_type,
                    size_bytes=size_bytes,
                )
                for file_name, storage_key, file_type, mime_type, size_bytes in files
            ]

        db.add(announcement)
        await db.flush()
        return announcement

    async def update(
        self,
        db: AsyncSession,
        announcement: Announcement,
        *,
        title: Optional[str] = None,
        description: Optional[str] = None,
        is_submission_request: Optional[bool] = None,
        due_at: Optional[datetime] = None,
        total_marks: Optional[float] = None,
        keep_file_ids: Optional[List[UUID]] = None,
    ) -> Announcement:
        if title is not None:
            announcement.title = title
        if description is not None:
            announcement.description = description
        if is_submission_request is not None:
            announcement.is_submission_request = is_submission_request
        if due_at is not None:
            announcement.due_at = due_at
        if total_marks is not None:
            announcement.total_marks = total_marks
        if keep_file_ids is not None:
            for existing_file in list(announcement.files):
                if existing_file.file_id not in keep_file_ids:
                    try:
                        await delete_file_from_supabase(
                            supabase,
                            bucket="announcement_files",
                            storage_key=existing_file.storage_key,
                        )
                    except Exception as e:
                        print(f"PATCH Storage Error: {e}")
                    await db.delete(existing_file)
        await db.flush()
        return announcement

    async def delete(self, db: AsyncSession, announcement: Announcement) -> None:
        """Delete an announcement and clean up its storage files."""
        if announcement.files:
            for file_record in announcement.files:
                try:
                    await delete_file_from_supabase(
                        supabase,
                        bucket="announcement_files",
                        storage_key=file_record.storage_key,
                    )
                except Exception as e:
                    print(f"Error deleting file from storage: {e}")
        await db.delete(announcement)
        await db.flush()

    # ─── STUDENT ANNOUNCEMENT QUERIES ─────────────────────────────────────────

    async def get_supervisor_announcements_for_student(
        self,
        db: AsyncSession,
        *,
        group_id: UUID,
        page: int,
        per_page: int,
        search: Optional[str] = None,
    ) -> Tuple[List[Announcement], int]:
        """
        Paginated faculty announcements targeted at a specific group_id.
        Used for the student's 'Supervisor Announcements' tab.
        """
        base_query = (
            select(Announcement)
            .join(AnnouncementTarget)
            .options(
                selectinload(Announcement.files),
                selectinload(Announcement.creator),
            )
            .where(
                Announcement.created_by_role == AnnouncementRoleEnum.supervisor,
                Announcement.is_submission_request == False,  # noqa: E712
                AnnouncementTarget.group_id == group_id,
            )
        )

        if search:
            base_query = base_query.where(Announcement.title.ilike(f"%{search}%"))

        count_query = select(func.count()).select_from(base_query.subquery())
        total_items = (await db.execute(count_query)).scalar_one()

        offset = (page - 1) * per_page
        paginated_query = (
            base_query.order_by(Announcement.created_at.desc())
            .offset(offset)
            .limit(per_page)
        )
        result = await db.execute(paginated_query)
        return list(result.scalars().unique().all()), total_items

    async def get_admin_announcements_for_student(
        self,
        db: AsyncSession,
        *,
        target_roles: List[TargetRoleEnum],
        page: int,
        per_page: int,
    ) -> Tuple[List[Announcement], int]:
        """
        Paginated admin announcements filtered by the provided target_roles.
        Used for the student's 'Admin Announcements' tab.
        Caller determines the role list based on the student's fyp cycle.
        """
        base_query = (
            select(Announcement)
            .join(AnnouncementTarget)
            .options(
                selectinload(Announcement.targets),
                selectinload(Announcement.files),
            )
            .where(
                Announcement.created_by_role == AnnouncementRoleEnum.admin,
                Announcement.is_submission_request == False,  # noqa: E712
                AnnouncementTarget.target_role.in_(target_roles),
            )
        )

        count_query = select(func.count()).select_from(base_query.subquery())
        total_items = (await db.execute(count_query)).scalar_one()

        offset = (page - 1) * per_page
        paginated_query = (
            base_query.order_by(Announcement.created_at.desc())
            .offset(offset)
            .limit(per_page)
        )
        result = await db.execute(paginated_query)
        return list(result.scalars().unique().all()), total_items

    async def list_supervisor_submission_tasks(
        self,
        db: AsyncSession,
        supervisor_id: UUID,
        page: int,
        per_page: int,
        search: Optional[str] = None,
    ) -> Tuple[List[Announcement], int]:
        """Fetch all submission tasks created by a specific supervisor."""
        query = (
            select(Announcement)
            .where(
                Announcement.created_by == supervisor_id,
                Announcement.is_submission_request == True,  # noqa: E712
                Announcement.created_by_role
                == dict(AnnouncementRoleEnum.__members__).get(
                    "supervisor", "supervisor"
                ),
            )
            .options(
                selectinload(Announcement.targets),
                selectinload(Announcement.files),
            )
        )
        if search:
            query = query.where(Announcement.title.ilike(f"%{search}%"))

        count_query = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_query)).scalar_one()

        offset = (page - 1) * per_page
        query = (
            query.order_by(Announcement.created_at.desc())
            .offset(offset)
            .limit(per_page)
        )
        rows = await db.execute(query)
        return list(rows.scalars().all()), total

    async def list_admin_submission_tasks(
        self,
        db: AsyncSession,
        page: int,
        per_page: int,
        search: Optional[str] = None,
    ) -> Tuple[List[Announcement], int]:
        """Fetch all submission tasks created by admin."""
        query = (
            select(Announcement)
            .where(
                Announcement.is_submission_request == True,  # noqa: E712
                Announcement.created_by_role == AnnouncementRoleEnum.admin,
            )
            .options(
                selectinload(Announcement.targets),
                selectinload(Announcement.files),
            )
        )
        if search:
            query = query.where(
                (Announcement.title.ilike(f"%{search}%"))
                | (Announcement.description.ilike(f"%{search}%"))
            )

        count_query = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_query)).scalar_one()

        offset = (page - 1) * per_page
        query = (
            query.order_by(Announcement.created_at.desc())
            .offset(offset)
            .limit(per_page)
        )
        rows = await db.execute(query)
        return list(rows.scalars().all()), total

    async def get_announcement_file(
        self, db: AsyncSession, file_id: UUID
    ) -> Optional[AnnouncementFile]:
        """Fetch an announcement file by its ID with announcement loaded."""
        result = await db.execute(
            select(AnnouncementFile)
            .join(
                Announcement,
                AnnouncementFile.announcement_id == Announcement.announcement_id,
            )
            .options(selectinload(AnnouncementFile.announcement))
            .where(AnnouncementFile.file_id == file_id)
        )
        return result.scalars().first()

    async def get_templates_for_student(
        self,
        db: AsyncSession,
        *,
        target_roles: List[TargetRoleEnum],
    ) -> List[AnnouncementFile]:
        """
        Return all AnnouncementFiles tagged as Template that are scoped to the
        student's role / FYP cycle.

        Used by:  GET /api/students/documents/templates
        The result is a flat list ready to render as a template picker.
        """
        result = await db.execute(
            select(AnnouncementFile)
            .join(
                Announcement,
                AnnouncementFile.announcement_id == Announcement.announcement_id,
            )
            .join(
                AnnouncementTarget,
                AnnouncementTarget.announcement_id == Announcement.announcement_id,
            )
            # Use joinedload to avoid follow-up SELECTs that can time out under load.
            .options(joinedload(AnnouncementFile.announcement))
            .where(
                Announcement.created_by_role == AnnouncementRoleEnum.admin,
                AnnouncementFile.file_type == FileTypeEnum.Template,
                AnnouncementTarget.target_role.in_(target_roles),
            )
            .order_by(AnnouncementFile.uploaded_at.desc())
        )
        # Use unique() to deduplicate rows produced by the join
        return list(result.scalars().unique().all())


# Singleton instance for convenience
announcement_repository = AnnouncementRepository()
