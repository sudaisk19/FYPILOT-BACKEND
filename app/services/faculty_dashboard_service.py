"""Business logic for assembling the faculty dashboard payload."""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.faculty import Faculty
from app.repositories.faculty_dashboard_repository import (
    FacultyDashboardRepository,
)
from app.schemas.dashboard_schema import (
    FacultyDashboardEnvelope,
    FacultyDashboardInsights,
    FacultyTopCards,
    JuryAssignedGroupEntry,
    JuryEvaluationStatusChart,
    JurySection,
    SupervisorCapacityTracker,
    SupervisorGroupOverviewEntry,
    SupervisorPerformanceChart,
    SupervisorPerformancePoint,
    SupervisorRecentSubmission,
    SupervisorSection,
)


class FacultyDashboardService:
    """Coordinates repository queries into a single dashboard payload."""

    def __init__(self, db: AsyncSession) -> None:
        self.repo = FacultyDashboardRepository(db)

    async def get_dashboard_payload(self, faculty: Faculty) -> FacultyDashboardEnvelope:
        top_cards = await self._build_top_cards(faculty)
        supervisor_section = await self._build_supervisor_section(faculty)
        jury_section = await self._build_jury_section(faculty)

        insights = FacultyDashboardInsights(
            top_cards=top_cards,
            supervisor_section=supervisor_section,
            jury_section=jury_section,
        )
        return FacultyDashboardEnvelope(faculty_dashboard=insights)

    async def _build_top_cards(self, faculty: Faculty) -> FacultyTopCards:
        faculty_id = faculty.user_id

        total_supervised = (
            await self.repo.count_supervised_groups(faculty_id)
            if faculty.is_supervisor
            else 0
        )
        total_jury_assigned = (
            await self.repo.count_jury_assigned_groups(faculty_id)
            if faculty.is_jury
            else 0
        )
        avg_supervisor = (
            self._round_marks(await self.repo.average_supervisor_marks(faculty_id))
            if faculty.is_supervisor
            else None
        )
        avg_jury = (
            self._round_marks(await self.repo.average_jury_marks(faculty_id))
            if faculty.is_jury
            else None
        )

        return FacultyTopCards(
            total_supervised_groups=total_supervised,
            total_jury_assigned_groups=total_jury_assigned,
            avg_supervisor_marks=avg_supervisor,
            avg_jury_marks=avg_jury,
        )

    async def _build_supervisor_section(
        self, faculty: Faculty
    ) -> Optional[SupervisorSection]:
        if not (faculty.is_active and faculty.is_supervisor):
            return None

        faculty_id = faculty.user_id
        group_rows = await self.repo.fetch_supervised_group_overview(faculty_id)
        submissions = await self.repo.fetch_recent_submissions(faculty_id)

        groups_overview = [
            SupervisorGroupOverviewEntry(
                group_id=row.group_id,
                project_name=row.project_name,
                fyp_cycle=row.fyp_cycle,
                members=row.members,
                avg_marks=self._round_marks(row.avg_marks),
            )
            for row in group_rows
        ]

        performance_chart = SupervisorPerformanceChart(
            type="bar_chart",
            data=[
                SupervisorPerformancePoint(
                    project_name=row.project_name,
                    avg_marks=self._round_marks(row.avg_marks) or 0.0,
                )
                for row in group_rows
            ],
        )

        recent_submissions = [
            SupervisorRecentSubmission(
                submission_id=row.submission_id,
                project_name=row.project_name,
                title=row.title,
                status=row.status,
                submitted_at=self._format_datetime(row.submitted_at),
            )
            for row in submissions
        ]

        capacity_tracker = SupervisorCapacityTracker(
            capacity_max=faculty.capacity_max,
            capacity_filled=faculty.capacity_filled,
            remaining=max(faculty.capacity_max - faculty.capacity_filled, 0),
        )

        return SupervisorSection(
            groups_overview=groups_overview,
            performance_chart=performance_chart,
            recent_submissions=recent_submissions,
            capacity_tracker=capacity_tracker,
        )

    async def _build_jury_section(self, faculty: Faculty) -> Optional[JurySection]:
        if not (faculty.is_active and faculty.is_jury):
            return None

        faculty_id = faculty.user_id
        assignments = await self.repo.fetch_jury_assignments(faculty_id)
        if not assignments:
            chart = JuryEvaluationStatusChart(type="pie_chart", data={"evaluated": 0, "pending": 0})
            return JurySection(assigned_groups=[], evaluation_status_chart=chart)

        cycle_titles = await self.repo.fetch_active_milestones_by_cycle()

        assigned_groups = [
            JuryAssignedGroupEntry(
                group_id=row.group_id,
                project_name=row.project_name,
                milestone_title=cycle_titles.get(row.fyp_cycle, "Not Set"),
                evaluated=row.evaluated,
            )
            for row in assignments
        ]

        evaluated_count = sum(1 for row in assignments if row.evaluated)
        pending_count = max(len(assignments) - evaluated_count, 0)

        chart = JuryEvaluationStatusChart(
            type="pie_chart",
            data={"evaluated": evaluated_count, "pending": pending_count},
        )

        return JurySection(
            assigned_groups=assigned_groups,
            evaluation_status_chart=chart,
        )

    def _round_marks(self, value: Optional[float]) -> Optional[float]:
        if value is None:
            return None
        return round(value, 1)

    def _format_datetime(self, dt) -> Optional[str]:
        if dt is None:
            return None
        return dt.isoformat()
