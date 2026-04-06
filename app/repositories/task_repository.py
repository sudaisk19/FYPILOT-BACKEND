from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.student import Student
from app.models.task import Task, TaskPriorityEnum, TaskStatusEnum
from app.models.task_attachment import TaskAttachment

from .base import BaseRepository


class TaskRepository(BaseRepository[Task]):
    """Data access helpers for `Task` and `TaskAttachment`."""

    def __init__(self) -> None:
        super().__init__(Task)

    async def get_by_id(
        self, db: AsyncSession, task_id: UUID, id_field: Optional[str] = "task_id"
    ) -> Optional[Task]:
        return await super().get_by_id(db, task_id, id_field)

    async def get_with_details(self, db: AsyncSession, task_id: UUID) -> Optional[Task]:
        query = (
            select(Task)
            .options(
                selectinload(Task.attachments),
                selectinload(Task.assignee).selectinload(Student.user),
                selectinload(Task.milestone),
            )
            .where(Task.task_id == task_id)
        )
        result = await db.execute(query)
        return result.unique().scalars().first()

    async def list_by_group(
        self,
        db: AsyncSession,
        group_id: UUID,
        *,
        milestone_id: Optional[UUID] = None,
        backlog_only: bool = False,
        statuses: Optional[Sequence[TaskStatusEnum | str]] = None,
        priorities: Optional[Sequence[TaskPriorityEnum | str]] = None,
        assignee_ids: Optional[Sequence[UUID]] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[Task], int]:
        """Return tasks plus total count for a group with optional filters."""

        conditions = [Task.group_id == group_id]

        if backlog_only:
            conditions.append(Task.milestone_id.is_(None))
        elif milestone_id:
            conditions.append(Task.milestone_id == milestone_id)

        status_values = self._normalize_statuses(statuses)
        if status_values:
            conditions.append(Task.status.in_(status_values))

        priority_values = self._normalize_priorities(priorities)
        if priority_values:
            conditions.append(Task.priority.in_(priority_values))

        if assignee_ids:
            conditions.append(Task.assignee_id.in_(assignee_ids))

        if search:
            conditions.append(Task.title.ilike(f"%{search}%"))

        query = (
            select(Task)
            .options(
                selectinload(Task.attachments),
                selectinload(Task.assignee).selectinload(Student.user),
                selectinload(Task.milestone),
            )
            .where(*conditions)
            .order_by(Task.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(query)
        tasks = list(result.unique().scalars().all())

        total_query = select(func.count()).select_from(Task).where(*conditions)
        total = (await db.execute(total_query)).scalar_one()
        return tasks, total

    async def create_task(self, db: AsyncSession, payload: Dict) -> Task:
        return await super().create(db, payload)

    async def update_task(
        self, db: AsyncSession, task_id: UUID, updates: Dict
    ) -> Optional[Task]:
        task = await self.get_by_id(db, task_id)
        if not task:
            return None
        return await super().update(db, task, updates)

    async def delete_task(self, db: AsyncSession, task_id: UUID) -> bool:
        return await super().delete(db, task_id, "task_id")

    async def unlink_sprint_tasks(self, db: AsyncSession, milestone_id: UUID) -> None:
        from sqlalchemy import update

        await db.execute(
            update(Task)
            .where(Task.milestone_id == milestone_id)
            .values(milestone_id=None)
        )

    async def add_attachment(
        self,
        db: AsyncSession,
        task_id: UUID,
        *,
        file_name: str,
        storage_key: str,
        mime_type: Optional[str] = None,
        size_bytes: Optional[int] = None,
    ) -> TaskAttachment:
        attachment = TaskAttachment(
            task_id=task_id,
            file_name=file_name,
            storage_key=storage_key,
            mime_type=mime_type,
            size_bytes=size_bytes,
        )
        db.add(attachment)
        await db.flush()
        return attachment

    async def list_attachments(
        self, db: AsyncSession, task_id: UUID
    ) -> List[TaskAttachment]:
        query = select(TaskAttachment).where(TaskAttachment.task_id == task_id)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_attachment(
        self, db: AsyncSession, attachment_id: UUID
    ) -> Optional[TaskAttachment]:
        query = select(TaskAttachment).where(
            TaskAttachment.attachment_id == attachment_id
        )
        result = await db.execute(query)
        return result.scalars().first()

    async def remove_attachment(self, db: AsyncSession, attachment_id: UUID) -> bool:
        stmt = delete(TaskAttachment).where(
            TaskAttachment.attachment_id == attachment_id
        )
        result = await db.execute(stmt)
        await db.flush()
        return result.rowcount > 0

    async def get_status_breakdown(
        self, db: AsyncSession, group_id: UUID, milestone_id: Optional[UUID] = None
    ) -> Dict[TaskStatusEnum, int]:
        conditions = [Task.group_id == group_id]
        if milestone_id is not None:
            conditions.append(Task.milestone_id == milestone_id)

        query = (
            select(Task.status, func.count()).where(*conditions).group_by(Task.status)
        )
        result = await db.execute(query)
        rows = result.all()
        return {TaskStatusEnum(status): count for status, count in rows}

    # app/repositories/task_repository.py

    def _normalize_statuses(self, statuses):
        if not statuses:
            return []

        # ✅ Agar statuses sirf aik string hai (e.g. "InProgress"), toh usay list mein wrap karein
        if isinstance(statuses, str):
            statuses = [statuses]

        normalized = []
        for value in statuses:
            try:
                normalized.append(TaskStatusEnum(value))
            except ValueError:
                # Error handle karein agar value galat ho
                continue
        return normalized

    def _normalize_priorities(
        self,  # ✅ 'self' add kiya taake class method ban jaye
        values: Optional[Sequence[TaskPriorityEnum | str]],
    ) -> Optional[List[TaskPriorityEnum]]:
        if not values:
            return None

        # ✅ Single string handling: agar user ne sirf aik priority select ki hai
        if isinstance(values, str):
            values = [values]

        normalized: List[TaskPriorityEnum] = []
        for value in values:
            try:
                if isinstance(value, TaskPriorityEnum):
                    normalized.append(value)
                else:
                    # String ko Enum mein convert karein
                    normalized.append(TaskPriorityEnum(value))
            except ValueError:
                # Agar koi invalid priority string aa jaye toh skip karein
                continue

        return normalized


task_repository = TaskRepository()
