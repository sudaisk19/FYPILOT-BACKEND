"""Data access helpers powering the faculty dashboard widgets."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.group import Group, GroupMember
from app.models.jury_assignment import JuryAssignment
from app.models.jury_evaluation import JuryEvaluation
from app.models.jury_pair import JuryPair
from app.models.milestone import AdminMilestone
from app.models.project import Project
from app.models.student import Student
from app.models.submission import Submission
from app.models.supervisor_evaluation import SupervisorEvaluation
from app.models.user import User


@dataclass
class SupervisorGroupRow:
    group_id: UUID
    project_name: str
    fyp_cycle: str
    members: List[str]
    avg_marks: Optional[float]  # Most recent submission supervisor marks
    eval_avg_marks: Optional[float]  # Supervisor evaluation average for bar chart


@dataclass
class SupervisorSubmissionRow:
    submission_id: UUID
    project_name: str
    title: str
    status: str
    submitted_at: Optional[datetime]


@dataclass
class JuryAssignmentRow:
    group_id: UUID
    project_name: str
    fyp_cycle: str
    evaluated: bool


class FacultyDashboardRepository:
    """Encapsulates SQL used by the faculty dashboard service."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def count_supervised_groups(self, faculty_id: UUID) -> int:
        stmt = select(func.count(Group.group_id)).where(
            Group.supervisor_id == faculty_id
        )
        return await self._scalar_int(stmt)

    async def average_supervisor_marks(self, faculty_id: UUID) -> Optional[float]:
        # Use only supervisor evaluation records (milestone-based grading).
        eval_stmt = select(func.avg(SupervisorEvaluation.marks)).where(
            SupervisorEvaluation.supervisor_id == faculty_id
        )
        eval_value = await self.db.scalar(eval_stmt)
        return self._to_float(eval_value)

    async def count_jury_assigned_groups(self, faculty_id: UUID) -> int:
        stmt = (
            select(func.count(func.distinct(Group.group_id)))
            .select_from(JuryAssignment)
            .join(JuryPair, JuryAssignment.pair_id == JuryPair.jury_id)
            .join(Project, JuryAssignment.project_id == Project.project_id)
            .join(Group, Project.group_id == Group.group_id)
            .where(
                or_(
                    JuryPair.faculty_1_id == faculty_id,
                    JuryPair.faculty_2_id == faculty_id,
                )
            )
        )
        return await self._scalar_int(stmt)

    async def average_jury_marks(self, faculty_id: UUID) -> Optional[float]:
        stmt = select(func.avg(JuryEvaluation.numeric_marks)).where(
            JuryEvaluation.jury_id == faculty_id
        )
        value = await self.db.scalar(stmt)
        return self._to_float(value)

    async def fetch_supervised_group_overview(
        self, faculty_id: UUID, limit: int = 6
    ) -> List[SupervisorGroupRow]:
        member_names = func.array_agg(func.distinct(User.full_name)).label(
            "member_names"
        )
        sort_ts = func.coalesce(Project.updated_at, Group.updated_at).label("sort_ts")

        # Subquery to get the most recent submission for each group
        most_recent_submission = (
            select(
                Submission.group_id,
                Submission.submission_id,
                Submission.supervisor_marks,
            )
            .distinct(Submission.group_id)
            .order_by(Submission.group_id, Submission.submitted_at.desc().nullslast())
        ).subquery()

        stmt = (
            select(
                Group.group_id,
                Project.name.label("project_name"),
                Group.fyp_cycle,
                member_names,
                most_recent_submission.c.supervisor_marks.label("submission_marks"),
                func.avg(SupervisorEvaluation.marks).label("eval_avg"),
                sort_ts,
            )
            .select_from(Group)
            .join(GroupMember, GroupMember.group_id == Group.group_id)
            .join(Student, Student.user_id == GroupMember.student_id)
            .join(User, User.user_id == Student.user_id)
            .outerjoin(Project, Project.group_id == Group.group_id)
            .outerjoin(
                most_recent_submission,
                most_recent_submission.c.group_id == Group.group_id,
            )
            .outerjoin(
                SupervisorEvaluation,
                (SupervisorEvaluation.group_id == Group.group_id)
                & (SupervisorEvaluation.supervisor_id == faculty_id),
            )
            .where(Group.supervisor_id == faculty_id)
            .group_by(
                Group.group_id,
                Project.name,
                Group.fyp_cycle,
                sort_ts,
                most_recent_submission.c.supervisor_marks,
            )
            .order_by(sort_ts.desc().nullslast())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        rows: List[SupervisorGroupRow] = []
        for (
            group_id,
            project_name,
            fyp_cycle,
            members,
            submission_marks,
            eval_avg,
            _,
        ) in result.all():
            rows.append(
                SupervisorGroupRow(
                    group_id=group_id,
                    project_name=(project_name or "Untitled Project"),
                    fyp_cycle=self._cycle_value(fyp_cycle),
                    members=list(members or []),
                    avg_marks=self._to_float(submission_marks),
                    eval_avg_marks=self._to_float(eval_avg),
                )
            )
        return rows

    async def fetch_recent_submissions(
        self, faculty_id: UUID, limit: int = 5
    ) -> List[SupervisorSubmissionRow]:
        stmt = (
            select(
                Submission.submission_id,
                Project.name.label("project_name"),
                Submission.title,
                Submission.status,
                Submission.submitted_at,
                Submission.updated_at,
            )
            .join(Group, Submission.group_id == Group.group_id)
            .outerjoin(Project, Project.group_id == Group.group_id)
            .where(Group.supervisor_id == faculty_id)
            .order_by(
                Submission.submitted_at.desc().nullslast(),
                Submission.updated_at.desc(),
            )
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        rows: List[SupervisorSubmissionRow] = []
        for submission_id, project_name, title, status, submitted_at, _ in result.all():
            rows.append(
                SupervisorSubmissionRow(
                    submission_id=submission_id,
                    project_name=(project_name or "Untitled Project"),
                    title=title,
                    status=str(status),
                    submitted_at=submitted_at,
                )
            )
        return rows

    async def fetch_jury_assignments(
        self, faculty_id: UUID, limit: int = 6
    ) -> List[JuryAssignmentRow]:
        stmt = (
            select(
                Group.group_id,
                Project.name.label("project_name"),
                Group.fyp_cycle,
                func.bool_or(JuryEvaluation.evaluation_id.isnot(None)).label(
                    "evaluated"
                ),
            )
            .select_from(JuryAssignment)
            .join(JuryPair, JuryAssignment.pair_id == JuryPair.jury_id)
            .join(Project, JuryAssignment.project_id == Project.project_id)
            .join(Group, Project.group_id == Group.group_id)
            .outerjoin(
                JuryEvaluation,
                (JuryEvaluation.group_id == Group.group_id)
                & (JuryEvaluation.jury_id == faculty_id),
            )
            .where(
                or_(
                    JuryPair.faculty_1_id == faculty_id,
                    JuryPair.faculty_2_id == faculty_id,
                )
            )
            .group_by(Group.group_id, Project.name, Group.fyp_cycle)
            .order_by(func.max(Project.updated_at).desc().nullslast())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        rows: List[JuryAssignmentRow] = []
        for group_id, project_name, fyp_cycle, evaluated in result.all():
            rows.append(
                JuryAssignmentRow(
                    group_id=group_id,
                    project_name=(project_name or "Untitled Project"),
                    fyp_cycle=self._cycle_value(fyp_cycle),
                    evaluated=bool(evaluated),
                )
            )
        return rows

    async def fetch_active_milestones_by_cycle(self) -> Dict[str, str]:
        stmt = (
            select(AdminMilestone.fyp_cycle, AdminMilestone.title)
            .where(AdminMilestone.is_active.is_(True))
            .order_by(AdminMilestone.activated_at.desc().nullslast())
        )
        result = await self.db.execute(stmt)
        mapping: Dict[str, str] = {}
        for fyp_cycle, title in result.all():
            cycle_key = self._cycle_value(fyp_cycle)
            if cycle_key not in mapping:
                mapping[cycle_key] = title
        return mapping

    async def _scalar_int(self, stmt) -> int:
        value = await self.db.scalar(stmt)
        return int(value or 0)

    def _to_float(self, value: Optional[Decimal]) -> Optional[float]:
        if value is None:
            return None
        return float(value)

    def _cycle_value(self, cycle) -> str:
        if hasattr(cycle, "value"):
            return str(cycle.value)
        return str(cycle or "fyp1").lower()
