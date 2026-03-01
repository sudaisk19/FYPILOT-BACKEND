from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import db
from app.models.group_milestone import GroupMilestone, SprintStatusEnum

from .base import BaseRepository


class SprintRepository(BaseRepository[GroupMilestone]):
    """Data access helpers for student sprint planning."""

    def __init__(self) -> None:
        super().__init__(GroupMilestone)

    async def get_by_id(
        self, 
        db: AsyncSession, 
        milestone_id: UUID, 
        *args, # Yeh extra arguments ko handle kar lega
        **kwargs
    ) -> Optional[GroupMilestone]:
        # milestone_id hamesha yahan "milestone_id" hi rahega
        return await super().get_by_id(db, milestone_id, "milestone_id")

    async def get_with_tasks(
    self, db: AsyncSession, milestone_id: UUID
) -> Optional[GroupMilestone]:
     from app.models.task import Task
     from app.models.student import Student
     query = (
        select(GroupMilestone)
        .options(
            selectinload(GroupMilestone.tasks).selectinload(Task.attachments), # Deep load attachments
            selectinload(GroupMilestone.tasks).selectinload(Task.assignee).selectinload(Student.user) # Deep load assignee details
        )
        .where(GroupMilestone.milestone_id == milestone_id)
    )
     result = await db.execute(query)
     return result.unique().scalars().first()

    async def list_by_group(
        self,
        db: AsyncSession,
        group_id: UUID,
        *,
        include_tasks: bool = False,
    ) -> List[GroupMilestone]:
        query = select(GroupMilestone).where(GroupMilestone.group_id == group_id)
        if include_tasks:
            query = query.options(selectinload(GroupMilestone.tasks))
        query = query.order_by(GroupMilestone.start_date.nulls_last())

        result = await db.execute(query)
        return list(result.unique().scalars().all())

    async def create_sprint(
        self,
        db: AsyncSession,
        *,
        group_id: UUID,
        title: str,
        sprint_goal: Optional[str],
        start_date: Optional[date],
        end_date: Optional[date],
        status: Optional[SprintStatusEnum] = None,
    ) -> GroupMilestone:
        final_status = status or SprintStatusEnum.planned
        payload = {
            "group_id": group_id,
            "title": title,
            "sprint_goal": sprint_goal,
            "start_date": start_date,
            "end_date": end_date,
            "status": final_status.value if hasattr(final_status, "value") else final_status,
        }
        return await super().create(db, payload)

    async def update_sprint(
        self,
        db: AsyncSession,
        milestone_id: UUID,
        updates: Dict,
    ) -> Optional[GroupMilestone]:
        sprint = await self.get_by_id(db, milestone_id)
        if not sprint:
            return None
        return await super().update(db, sprint, updates)

    async def delete_sprint(self, db: AsyncSession, milestone_id: UUID) -> bool:
        return await super().delete(db, milestone_id, "milestone_id")

    async def get_active_sprint(
        self, db: AsyncSession, group_id: UUID
    ) -> Optional[GroupMilestone]:
        query = select(GroupMilestone).where(
            GroupMilestone.group_id == group_id,
            GroupMilestone.status == SprintStatusEnum.active,
        )
        result = await db.execute(query)
        return result.scalars().first()

    async def task_counts(
        self, db: AsyncSession, milestone_ids: List[UUID]
    ) -> Dict[UUID, Dict[str, int]]:
        if not milestone_ids:
            return {}

        from app.models.task import Task

        query = (
            select(Task.milestone_id, Task.status, func.count())
            .where(Task.milestone_id.in_(milestone_ids))
            .group_by(Task.milestone_id, Task.status)
        )
        result = await db.execute(query)
        stats: Dict[UUID, Dict[str, int]] = {}
        for milestone_id, status, count in result:
            status_key = status.value if hasattr(status, "value") else str(status)
            stats.setdefault(milestone_id, {})[status_key] = count
        return stats


sprint_repository = SprintRepository()
