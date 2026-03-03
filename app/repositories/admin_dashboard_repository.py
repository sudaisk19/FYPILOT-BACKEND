"""Data-access helpers for the admin dashboard aggregates."""

from datetime import date, timedelta
from typing import List, Sequence, Tuple

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.group import Group, GroupMember
from app.models.milestone import AdminMilestone
from app.models.project import Project
from app.models.student import Student
from app.models.supervisor_evaluation import SupervisorEvaluation
from app.models.supervisor import Supervisor
from app.models.user import User


class AdminDashboardRepository:
    """Encapsulates all SQL used by the admin dashboard service."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def count_total_users(self) -> int:
        return await self._scalar_int(select(func.count(User.user_id)))

    async def count_active_students(self) -> int:
        stmt = select(func.count(Student.user_id)).where(Student.is_active.is_(True))
        return await self._scalar_int(stmt)

    async def count_active_supervisors(self) -> int:
        stmt = select(func.count(Supervisor.user_id)).where(
            Supervisor.is_active.is_(True),
            Supervisor.is_supervisor.is_(True),
        )
        return await self._scalar_int(stmt)

    async def count_active_projects(self) -> int:
        stmt = (
            select(func.count(func.distinct(Project.project_id)))
            .join(Group, Project.group_id == Group.group_id)
            .join(GroupMember, GroupMember.group_id == Group.group_id)
            .join(Student, Student.user_id == GroupMember.student_id)
            .where(Student.is_active.is_(True))
        )
        return await self._scalar_int(stmt)

    async def count_supervisors_per_department(self) -> List[Tuple[str, int]]:
        stmt = (
            select(
                Supervisor.department,
                func.count(Supervisor.user_id).label("supervisor_count"),
            )
            .where(
                Supervisor.is_active.is_(True),
                Supervisor.is_supervisor.is_(True),
            )
            .group_by(Supervisor.department)
            .order_by(
                func.count(Supervisor.user_id).desc(),
                Supervisor.department.asc(),
            )
        )
        result = await self.db.execute(stmt)
        rows = []
        for department, count in result.all():
            label = (department or "Unspecified").strip() or "Unspecified"
            rows.append((label, int(count)))
        return rows

    async def supervisor_capacity_totals(self) -> Tuple[int, int]:
        stmt = select(
            func.coalesce(func.sum(Supervisor.capacity_max), 0),
            func.coalesce(func.sum(Supervisor.capacity_filled), 0),
        ).where(
            Supervisor.is_active.is_(True),
            Supervisor.is_supervisor.is_(True),
        )
        total_max, total_filled = (await self.db.execute(stmt)).one()
        return int(total_max or 0), int(total_filled or 0)

    async def fetch_supervisor_workload(self, limit: int = 10) -> Sequence[Tuple[str, int]]:
        stmt = (
            select(
                User.full_name,
                func.count(Group.group_id).label("group_count"),
            )
            .join(Supervisor, Supervisor.user_id == User.user_id)
            .outerjoin(Group, Group.supervisor_id == Supervisor.user_id)
            .where(
                Supervisor.is_active.is_(True),
                Supervisor.is_supervisor.is_(True),
            )
            .group_by(User.full_name)
            .order_by(func.count(Group.group_id).desc(), User.full_name.asc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return result.all()

    async def students_per_start_term(self) -> List[Tuple[str, int]]:
        semester_order = case(
            (Student.fyp_start_semester == "fall", 1),
            (Student.fyp_start_semester == "spring", 2),
            else_=3,
        )

        stmt = (
            select(
                Student.fyp_start_semester,
                Student.fyp_start_year,
                func.count(Student.user_id).label("student_count"),
            )
            .where(Student.is_active.is_(True))
            .group_by(Student.fyp_start_semester, Student.fyp_start_year)
            .order_by(Student.fyp_start_year.asc(), semester_order.asc())
        )

        result = await self.db.execute(stmt)
        rows: List[Tuple[str, int]] = []
        for semester, year, count in result.all():
            semester_label = (semester or "Unknown").strip().title() or "Unknown"
            year_label = str(year) if year else "Unknown"
            rows.append((f"{semester_label} {year_label}", int(count)))
        return rows

    async def active_projects_per_cycle(self) -> List[Tuple[str, int]]:
        stmt = (
            select(
                Group.fyp_cycle,
                func.count(func.distinct(Project.project_id)).label("project_count"),
            )
            .join(Group, Project.group_id == Group.group_id)
            .join(GroupMember, GroupMember.group_id == Group.group_id)
            .join(Student, Student.user_id == GroupMember.student_id)
            .where(Student.is_active.is_(True))
            .group_by(Group.fyp_cycle)
        )
        result = await self.db.execute(stmt)
        rows: List[Tuple[str, int]] = []
        for cycle, count in result.all():
            cycle_value = cycle.value if hasattr(cycle, "value") else str(cycle)
            cycle_label = (cycle_value or "fyp1").strip().lower()
            rows.append((cycle_label, int(count)))
        if not rows:
            rows = [("fyp1", 0), ("fyp2", 0)]
        return rows

    async def get_active_milestone(self) -> AdminMilestone | None:
        stmt = (
            select(AdminMilestone)
            .where(AdminMilestone.is_active.is_(True))
            .order_by(AdminMilestone.activated_at.desc().nullslast(), AdminMilestone.updated_at.desc())
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalars().first()

    async def count_expected_evaluations_for_milestone(
        self, milestone: AdminMilestone
    ) -> int:
        stmt = (
            select(func.count(func.distinct(Group.group_id)))
            .select_from(Group)
            .join(GroupMember, GroupMember.group_id == Group.group_id)
            .join(Student, Student.user_id == GroupMember.student_id)
            .where(
                Student.is_active.is_(True),
                Group.fyp_cycle == milestone.fyp_cycle,
            )
        )
        return await self._scalar_int(stmt)

    async def count_evaluations_for_milestone(
        self, milestone_id
    ) -> Tuple[int, int]:
        submitted_stmt = select(func.count(func.distinct(SupervisorEvaluation.group_id))).where(
            SupervisorEvaluation.milestone_id == milestone_id
        )
        submitted = await self._scalar_int(submitted_stmt)

        wbs_stmt = select(func.count()).where(
            SupervisorEvaluation.milestone_id == milestone_id,
            SupervisorEvaluation.wbs_achieved.is_(False),
        )
        wbs_failures = await self._scalar_int(wbs_stmt)

        return submitted, wbs_failures

    async def get_upcoming_milestones(
        self, today: date, limit: int = 5, horizon_days: int = 10
    ) -> Sequence[AdminMilestone]:
        end_date = today + timedelta(days=horizon_days)
        stmt = (
            select(AdminMilestone)
            .where(AdminMilestone.due_date.isnot(None))
            .where(AdminMilestone.due_date >= today)
            .where(AdminMilestone.due_date <= end_date)
            .order_by(AdminMilestone.due_date.asc())
            .limit(limit)
        )
        return (await self.db.execute(stmt)).scalars().all()

    async def _scalar_int(self, stmt) -> int:
        value = await self.db.scalar(stmt)
        return int(value or 0)
