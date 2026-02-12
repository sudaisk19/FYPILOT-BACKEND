# app/repositories/announcement_repository.py
from __future__ import annotations

from typing import Iterable, Optional, Sequence, Tuple
from datetime import datetime
from uuid import UUID

from app.db import supabase 
from app.services.storage_service import delete_file_from_supabase

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.announcement import (
    Announcement,
    AnnouncementFile,
    AnnouncementTarget,
    AnnouncementRoleEnum,
    FileTypeEnum,
    TargetRoleEnum,
)
from app.repositories.base import BaseRepository


class AnnouncementRepository(BaseRepository[Announcement]):

    def __init__(self) -> None:
        super().__init__(Announcement)
    
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
        query = (
            select(Announcement)
            .options(
                selectinload(Announcement.targets),
                selectinload(Announcement.files),
            )
            .order_by(Announcement.created_at.desc())
            .offset(offset)
            .limit(size)
        )
        rows = (await db.execute(query)).scalars().all()
        total = (await db.execute(select(func.count(Announcement.announcement_id)))).scalar_one()
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
        files: Optional[Iterable[Tuple[str, str, FileTypeEnum, Optional[str], Optional[int], Optional[str]]]] = None,
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
            target_rows = [
                AnnouncementTarget(group_id=None, target_role=target_role)
            ]

        announcement.targets = target_rows

        if files:
            announcement.files = [
                AnnouncementFile(
                    file_name=file_name,
                    storage_key=storage_key,
                    file_type=file_type,
                    mime_type=mime_type,
                    size_bytes=size_bytes,
                    module=module,
                )
                for file_name, storage_key, file_type, mime_type, size_bytes, module in files
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
        await db.flush()
        return announcement

    async def delete(self, db: AsyncSession, announcement: Announcement) -> None:
    # 1. Pehle Storage saaf karein (Database se mitaane se pehle)
    # Agar announcement mein files hain, toh unpar loop chalayein
     if announcement.files:
        for file_record in announcement.files:
            try:
                # Supabase Storage cleanup logic
                await delete_file_from_supabase(
                    supabase, 
                    bucket="announcement_files",
                    storage_key=file_record.storage_key
                )
            except Exception as e:
                # Agar cloud se delete na bhi ho, toh log karein taake DB delete na ruke
                print(f"Error deleting file from storage: {e}")

    # 2. Ab Database se mitaayein
    # Kyunki aapne model mein cascade="all, delete-orphan" lagaya hai,
    # toh targets aur file ki database rows khud hi mita di jayengi.
     await db.delete(announcement)
     await db.flush()

# Singleton instance for convenience
announcement_repository = AnnouncementRepository()


