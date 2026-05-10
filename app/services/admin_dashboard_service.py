"""Service helpers for building the admin dashboard payload."""

from datetime import date
from typing import Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.admin_dashboard_repository import AdminDashboardRepository
from app.schemas.dashboard_schema import (
    AdminDashboardEnvelope,
    AdminDashboardInsights,
    AdminTopCards,
    EvaluationStatusSummary,
    MilestoneSummary,
    ProjectsPerCycleChart,
    ProjectsPerCycleEntry,
    StudentsPerTermChart,
    StudentsPerTermPoint,
    SupervisorCapacityUsage,
    SupervisorsPerDepartment,
    SupervisorWorkloadInsights,
    UpcomingMilestones,
)


class AdminDashboardService:
    """Calculates aggregate stats required by the admin dashboard UI."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = AdminDashboardRepository(db)

    async def get_dashboard_payload(self) -> AdminDashboardEnvelope:
        """Build the full dashboard payload in one place."""

        top_cards = await self._build_top_cards()
        supervisors_per_department = await self._build_supervisors_per_department()
        students_per_term = await self._build_students_per_term()
        projects_per_cycle = await self._build_projects_per_cycle()
        capacity_usage = await self._build_supervisor_capacity_usage()
        workload = await self._build_supervisor_workload()
        milestones = await self._build_upcoming_milestones()
        evaluation_status = await self._build_evaluation_status()

        insights = AdminDashboardInsights(
            top_cards=top_cards,
            supervisors_per_department=supervisors_per_department,
            students_per_term=students_per_term,
            projects_per_cycle=projects_per_cycle,
            supervisor_capacity_usage=capacity_usage,
            supervisor_workload_insights=workload,
            upcoming_milestones=milestones,
            evaluation_status=evaluation_status,
        )

        return AdminDashboardEnvelope(admin_dashboard=insights)

    async def _build_top_cards(self) -> AdminTopCards:
        total_users = await self.repo.count_total_users()
        active_students = await self.repo.count_active_students()
        active_supervisors = await self.repo.count_active_supervisors()
        active_projects = await self.repo.count_active_projects()

        return AdminTopCards(
            total_users=total_users,
            active_students=active_students,
            active_supervisors=active_supervisors,
            active_projects=active_projects,
        )

    async def _build_supervisors_per_department(self) -> SupervisorsPerDepartment:
        department_counts = await self.repo.count_supervisors_per_department()

        if not department_counts:
            return SupervisorsPerDepartment(
                title="Supervisors per Department",
                type="bar_chart",
                x_axis=[],
                y_axis=[],
            )

        top_departments = department_counts[:5]
        x_axis = [dept for dept, _ in top_departments]
        y_axis = [count for _, count in top_departments]

        return SupervisorsPerDepartment(
            title="Supervisors per Department",
            type="bar_chart",
            x_axis=x_axis,
            y_axis=y_axis,
        )

    async def _build_students_per_term(self) -> StudentsPerTermChart:
        trend_rows = await self.repo.students_per_start_term()

        points = [
            StudentsPerTermPoint(term=term, count=count) for term, count in trend_rows
        ]

        trend_delta = None
        if len(points) >= 2:
            trend_delta = points[-1].count - points[-2].count

        return StudentsPerTermChart(
            title="Students per Start Term",
            type="line_chart",
            points=points,
            trend_delta=trend_delta,
        )

    async def _build_projects_per_cycle(self) -> ProjectsPerCycleChart:
        cycle_rows = await self.repo.active_projects_per_cycle()

        cycle_map: Dict[str, int] = {"fyp1": 0, "fyp2": 0}
        for cycle, count in cycle_rows:
            cycle_map[cycle.lower()] = count

        entries = [
            ProjectsPerCycleEntry(cycle=cycle, active_projects=count)
            for cycle, count in cycle_map.items()
        ]

        total_active = sum(cycle_map.values())

        return ProjectsPerCycleChart(
            title="Active Projects per Cycle",
            type="bar_chart",
            cycles=entries,
            total_active_projects=total_active,
        )

    async def _build_supervisor_capacity_usage(self) -> SupervisorCapacityUsage:
        total_slots, filled_slots = await self.repo.supervisor_capacity_totals()
        remaining_slots = max(total_slots - filled_slots, 0)

        return SupervisorCapacityUsage(
            title="Supervisor Capacity Usage",
            type="pie_chart",
            total_slots=total_slots,
            filled_slots=filled_slots,
            remaining_slots=remaining_slots,
        )

    async def _build_supervisor_workload(self) -> SupervisorWorkloadInsights:
        workload_rows = await self.repo.fetch_supervisor_workload(limit=10)

        x_axis = [name for name, _ in workload_rows]
        y_axis = [int(count) for _, count in workload_rows]

        return SupervisorWorkloadInsights(
            title="Supervisor Load Distribution",
            type="histogram",
            x_axis=x_axis,
            y_axis=y_axis,
            tooltip="Number of groups per supervisor",
        )

    async def _build_upcoming_milestones(self) -> UpcomingMilestones:
        today = date.today()
        milestones = await self.repo.get_upcoming_milestones(
            today, limit=5, horizon_days=10
        )

        milestone_items = [
            MilestoneSummary(
                milestone=m.title,
                date=m.due_date,
                cycle=(
                    m.fyp_cycle.value
                    if hasattr(m.fyp_cycle, "value")
                    else str(m.fyp_cycle)
                ),
            )
            for m in milestones
        ]

        return UpcomingMilestones(
            title="Upcoming FYP Milestones",
            milestones=milestone_items,
        )

    async def _build_evaluation_status(self) -> EvaluationStatusSummary:
        milestone = await self.repo.get_active_milestone()

        if not milestone:
            return EvaluationStatusSummary(
                title="Evaluation Status",
                type="progress_summary",
                active_milestone=None,
                evaluations_submitted=0,
                evaluations_required=0,
                missing_evaluations=0,
                wbs_failure_count=None,
                percentage_submitted=0.0,
                last_updated=None,
            )

        expected = await self.repo.count_expected_evaluations_for_milestone(milestone)
        submitted, wbs_failures = await self.repo.count_evaluations_for_milestone(
            milestone
        )
        missing = max(expected - submitted, 0)
        percentage = (submitted / expected * 100) if expected else 0.0
        evaluator_value = (milestone.evaluator or "").strip().lower()
        wbs_failure_count = wbs_failures if evaluator_value == "supervisor" else None
        last_updated_field = (
            milestone.updated_at or milestone.activated_at or milestone.created_at
        )
        last_updated = (
            last_updated_field.isoformat() if last_updated_field is not None else None
        )

        return EvaluationStatusSummary(
            title="Evaluation Status",
            type="progress_summary",
            active_milestone=milestone.title,
            evaluations_submitted=submitted,
            evaluations_required=expected,
            missing_evaluations=missing,
            wbs_failure_count=wbs_failure_count,
            percentage_submitted=round(percentage, 2),
            last_updated=last_updated,
        )
