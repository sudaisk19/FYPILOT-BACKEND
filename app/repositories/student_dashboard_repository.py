# app/repositories/student_dashboard_repository.py
from datetime import datetime
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.announcement import Announcement, AnnouncementTarget
from app.models.faculty import Faculty
from app.models.group import Group, GroupMember
from app.models.group_milestone import GroupMilestone, SprintStatusEnum
from app.models.submission import Submission
from app.models.task import Task, TaskStatusEnum
from app.models.user import User


class StudentDashboardRepository:
    """Repository handling read-heavy queries for the student dashboard."""

    async def get_student_group(
        self, db: AsyncSession, student_id: UUID
    ) -> Optional[Group]:
        stmt = (
            select(Group)
            .join(GroupMember, GroupMember.group_id == Group.group_id)
            .where(GroupMember.student_id == student_id)
            .options(
                selectinload(Group.supervisor).selectinload(Faculty.user),
                selectinload(Group.co_supervisors).selectinload(Faculty.user),
                selectinload(Group.project),
                selectinload(Group.members),
            )
            .limit(1)
        )
        result = await db.execute(stmt)
        return result.scalars().first()

    async def get_group_members_as_users(
        self, db: AsyncSession, member_ids: List[UUID]
    ) -> List[User]:
        if not member_ids:
            return []
        stmt = select(User).where(User.user_id.in_(member_ids))
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def get_upcoming_milestones(
        self, db: AsyncSession, group_id: UUID, now: datetime
    ) -> List[GroupMilestone]:
        stmt = (
            select(GroupMilestone)
            .where(
                GroupMilestone.group_id == group_id,
                GroupMilestone.end_date >= now.date(),
                GroupMilestone.status != SprintStatusEnum.Completed,
            )
            .order_by(GroupMilestone.end_date.asc())
        )
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def get_upcoming_submission_requests(
        self, db: AsyncSession, group_id: UUID, valid_targets: List[str], now: datetime
    ) -> List[Announcement]:
        stmt = (
            select(Announcement)
            .join(
                AnnouncementTarget,
                AnnouncementTarget.announcement_id == Announcement.announcement_id,
            )
            .where(
                Announcement.is_submission_request == True,
                Announcement.due_at >= now,
                or_(
                    AnnouncementTarget.group_id == group_id,
                    AnnouncementTarget.target_role.in_(valid_targets),
                ),
            )
        )
        res = await db.execute(stmt)
        return list(res.scalars().unique().all())

    async def get_task_status_counts(
        self, db: AsyncSession, group_id: UUID
    ) -> List[Tuple[TaskStatusEnum, int]]:
        stmt = (
            select(Task.status, func.count(Task.task_id))
            .where(Task.group_id == group_id)
            .group_by(Task.status)
        )
        res = await db.execute(stmt)
        return list(res.all())

    async def get_submission_trends(
        self, db: AsyncSession, group_id: UUID, start_date: datetime
    ) -> List[Tuple[datetime, int]]:
        stmt = (
            select(
                func.date_trunc("day", Submission.submitted_at).label("sub_date"),
                func.count(Submission.submission_id).label("count"),
            )
            .where(
                Submission.group_id == group_id,
                Submission.submitted_at >= start_date,
            )
            .group_by(func.date_trunc("day", Submission.submitted_at))
            .order_by(func.date_trunc("day", Submission.submitted_at))
        )
        res = await db.execute(stmt)
        return list(res.all())

    async def get_project_velocity_for_daterange(
        self, db: AsyncSession, group_id: UUID, start_date: datetime, end_date: datetime
    ) -> int:
        stmt = select(func.count(Task.task_id)).where(
            Task.group_id == group_id,
            Task.status == TaskStatusEnum.Done,
            Task.updated_at >= start_date,
            Task.updated_at < end_date,
        )
        res = await db.execute(stmt)
        return res.scalar_one() or 0


# Singleton instance
student_dashboard_repository = StudentDashboardRepository()
