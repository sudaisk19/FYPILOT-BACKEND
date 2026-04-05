"""Postgres persistence for group whiteboards."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.whiteboard import Whiteboard
from app.schemas.whiteboard_schema import WhiteboardListItem


class WhiteboardRepository:
    async def get_group_whiteboards(
        self, db: AsyncSession, group_id: UUID
    ) -> List[WhiteboardListItem]:
        stmt = (
            select(
                Whiteboard.id,
                Whiteboard.title,
                Whiteboard.created_by,
                User.full_name,
                Whiteboard.updated_at,
            )
            .join(User, Whiteboard.created_by == User.user_id)
            .where(
                Whiteboard.group_id == group_id,
                Whiteboard.deleted_at.is_(None),
            )
            .order_by(Whiteboard.updated_at.desc())
        )
        result = await db.execute(stmt)
        rows = result.all()
        return [
            WhiteboardListItem(
                id=r.id,
                title=r.title,
                created_by=r.created_by,
                created_by_name=r.full_name,
                updated_at=r.updated_at,
            )
            for r in rows
        ]

    async def get_whiteboard(
        self, db: AsyncSession, whiteboard_id: UUID
    ) -> Optional[Whiteboard]:
        result = await db.execute(
            select(Whiteboard).where(
                Whiteboard.id == whiteboard_id,
                Whiteboard.deleted_at.is_(None),
            )
        )
        return result.scalars().first()

    async def create_whiteboard(
        self,
        db: AsyncSession,
        group_id: UUID,
        created_by: UUID,
        title: str,
    ) -> Whiteboard:
        wb = Whiteboard(
            group_id=group_id,
            created_by=created_by,
            title=title,
            elements=[],
            app_state={},
            files={},
        )
        db.add(wb)
        await db.commit()
        await db.refresh(wb)
        return wb

    async def patch_whiteboard(
        self,
        db: AsyncSession,
        whiteboard_id: UUID,
        updated_by: UUID,
        patch: Dict[str, Any],
    ) -> Optional[Whiteboard]:
        """Apply partial update from model_dump(exclude_unset=True)."""
        wb = await self.get_whiteboard(db, whiteboard_id)
        if wb is None:
            return None
        now = datetime.now(timezone.utc)
        values: Dict[str, Any] = {
            "updated_by": updated_by,
            "updated_at": now,
        }
        if "title" in patch:
            values["title"] = patch["title"]
        scene_keys = ("elements", "app_state", "files")
        if any(k in patch for k in scene_keys):
            values["elements"] = (
                patch["elements"] if "elements" in patch else wb.elements
            )
            values["app_state"] = (
                patch["app_state"] if "app_state" in patch else wb.app_state
            )
            values["files"] = patch["files"] if "files" in patch else wb.files
        stmt = (
            update(Whiteboard)
            .where(
                Whiteboard.id == whiteboard_id,
                Whiteboard.deleted_at.is_(None),
            )
            .values(**values)
        )
        result = await db.execute(stmt)
        await db.commit()
        if result.rowcount == 0:
            return None
        return await self.get_whiteboard(db, whiteboard_id)

    async def soft_delete_whiteboard(
        self, db: AsyncSession, whiteboard_id: UUID
    ) -> bool:
        stmt = (
            update(Whiteboard)
            .where(
                Whiteboard.id == whiteboard_id,
                Whiteboard.deleted_at.is_(None),
            )
            .values(deleted_at=func.now())
        )
        result = await db.execute(stmt)
        await db.commit()
        return result.rowcount > 0


whiteboard_repo = WhiteboardRepository()
