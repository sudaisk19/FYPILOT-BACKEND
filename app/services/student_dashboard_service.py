# app/services/student_dashboard_service.py
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.group import Group
from app.models.task import TaskStatusEnum
from app.repositories.student_dashboard_repository import student_dashboard_repository
from app.schemas.student_dashboard_schema import (
    DashboardGroupMember,
    ProjectVelocityWidget,
    SkillAlignmentScore,
    SkillDomainAlignmentWidget,
    StudentDashboardEnvelope,
    StudentDashboardInsights,
    StudentDashboardProfile,
    StudentTasksOverviewWidget,
    SubmissionTrendsWidget,
    TaskStatusDistribution,
    TrendDataPoint,
    UpcomingDeadlineItem,
    UpcomingDeadlinesWidget,
    VelocityDataPoint,
)


class StudentDashboardService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_dashboard_payload(self, student_id: UUID) -> StudentDashboardEnvelope:
        # 1. Get the student's group
        group = await self._get_student_group(student_id)
        if not group:
            # Return empty/default envelope if no group
            # (In a real app, maybe raise 404, but returning empty allows the UI to render)
            return self._build_empty_envelope()

        group_id = group.group_id
        fyp_cycle = group.fyp_cycle.value

        # 2. Fetch all widgets concurrently (or sequentially if easier)
        profile = await self._get_profile(group)
        deadlines = await self._get_upcoming_deadlines(group_id, fyp_cycle)
        alignment = await self._get_skill_alignment()  # Mocked for now
        tasks = await self._get_tasks_overview(group_id)
        trends = await self._get_submission_trends(group_id)
        velocity = await self._get_project_velocity(group_id)

        # 3. Wrap and return
        return StudentDashboardEnvelope(
            student_dashboard=StudentDashboardInsights(
                profile=profile,
                upcoming_deadlines=UpcomingDeadlinesWidget(deadlines=deadlines),
                skill_alignment=alignment,
                tasks_overview=tasks,
                submission_trends=trends,
                project_velocity=velocity,
            )
        )

    # ──────────────────────────────────────────────────────────────────────────
    # HELPER METHODS
    # ──────────────────────────────────────────────────────────────────────────

    async def _get_student_group(self, student_id: UUID) -> Optional[Group]:
        return await student_dashboard_repository.get_student_group(self.db, student_id)

    def _build_empty_envelope(self) -> StudentDashboardEnvelope:
        return StudentDashboardEnvelope(
            student_dashboard=StudentDashboardInsights(
                profile=StudentDashboardProfile(
                    project_name="No Project Assigned",
                    fyp_cycle="FYP1",
                    fyp_stage="ideation",
                ),
                upcoming_deadlines=UpcomingDeadlinesWidget(deadlines=[]),
                skill_alignment=SkillDomainAlignmentWidget(
                    individual_scores=[], group_scores=[]
                ),
                tasks_overview=StudentTasksOverviewWidget(
                    completion_percentage=0.0,
                    status_distribution=TaskStatusDistribution(
                        not_started=0, in_progress=0, completed=0, blocked=0
                    ),
                ),
                submission_trends=SubmissionTrendsWidget(points=[]),
                project_velocity=ProjectVelocityWidget(points=[]),
            )
        )

    # ──────────────────────────────────────────────────────────────────────────
    # WIDGET QUERIES
    # ──────────────────────────────────────────────────────────────────────────

    async def _get_profile(self, group: Group) -> StudentDashboardProfile:
        project_name = group.project.name if group.project else "No Project Assigned"

        super_name = (
            group.supervisor.user.full_name
            if group.supervisor and group.supervisor.user
            else None
        )
        co_super_names = (
            [cs.user.full_name for cs in group.co_supervisors if cs.user]
            if group.co_supervisors
            else []
        )

        # Get member names directly from users table using a subquery/join in actual DB call,
        # but here we can just query them using the student IDs in group.members
        member_ids = [m.student_id for m in group.members]
        members = []
        if member_ids:
            users = await student_dashboard_repository.get_group_members_as_users(
                self.db, member_ids
            )
            for u in users:
                members.append(
                    DashboardGroupMember(
                        user_id=u.user_id, full_name=u.full_name, role="Student"
                    )
                )

        return StudentDashboardProfile(
            project_name=project_name,
            project_description=group.project.description if group.project else None,
            fyp_cycle=group.fyp_cycle.value.upper(),
            fyp_stage=group.fyp_stage.replace("_", " ").title(),
            supervisor_name=super_name,
            cosupervisor_names=co_super_names,
            group_members=members,
            project_repositories=(group.project.repo_links if group.project else []),
        )

    async def _get_upcoming_deadlines(
        self, group_id: UUID, fyp_cycle: str
    ) -> List[UpcomingDeadlineItem]:
        now = datetime.now(timezone.utc)
        items = []

        # 1. Milestones
        milestones = await student_dashboard_repository.get_upcoming_milestones(
            self.db, group_id, now
        )

        for ms in milestones:
            if ms.end_date:
                days_left = (ms.end_date - now.date()).days
                items.append(
                    UpcomingDeadlineItem(
                        id=ms.milestone_id,
                        title=ms.title,
                        date=ms.end_date.strftime("%d %b %Y"),
                        days_left=days_left,
                        description=ms.sprint_goal or "Complete sprint tasks",
                        type="milestone",
                    )
                )

        # 2. Submission Requests (Admin Announcements)
        # Using the same logic as the admin announcement tab for students
        from app.models.announcement import TargetRoleEnum

        valid_targets = [TargetRoleEnum.all_students.value, TargetRoleEnum.both.value]
        if fyp_cycle.lower() == "fyp1":
            valid_targets.append(TargetRoleEnum.fyp1_students.value)
        elif fyp_cycle.lower() == "fyp2":
            valid_targets.append(TargetRoleEnum.fyp2_students.value)

        announcements = (
            await student_dashboard_repository.get_upcoming_submission_requests(
                self.db, group_id, valid_targets, now
            )
        )

        for ann in announcements:
            if ann.due_at:
                days_left = (ann.due_at - now).days
                items.append(
                    UpcomingDeadlineItem(
                        id=ann.announcement_id,
                        title=ann.title,
                        date=ann.due_at.strftime("%d %b %Y"),
                        days_left=days_left,
                        description=ann.description or "Submit required documents",
                        type="submission_request",
                    )
                )

        # Sort combined by days_left
        items.sort(key=lambda x: x.days_left)

        # Return top 4
        return items[:4]

    async def _get_skill_alignment(self) -> SkillDomainAlignmentWidget:
        # Mocking this out as requested. In the future, this should pull from:
        # 1. Student skills
        # 2. Project domain tags
        return SkillDomainAlignmentWidget(
            individual_scores=[
                SkillAlignmentScore(domain="AI", score=4.5),
                SkillAlignmentScore(domain="Cybersecurity", score=2.0),
                SkillAlignmentScore(domain="Data Science", score=3.8),
                SkillAlignmentScore(domain="ML", score=4.0),
                SkillAlignmentScore(domain="Web Development", score=4.2),
            ],
            group_scores=[
                SkillAlignmentScore(domain="AI", score=4.0),
                SkillAlignmentScore(domain="Web Development", score=3.7),
                SkillAlignmentScore(domain="Data Science", score=3.0),
            ],
        )

    async def _get_tasks_overview(self, group_id: UUID) -> StudentTasksOverviewWidget:
        counts = await student_dashboard_repository.get_task_status_counts(
            self.db, group_id
        )

        total = 0
        done = 0
        dist = {"not_started": 0, "in_progress": 0, "completed": 0, "blocked": 0}

        for status, count in counts:
            total += count
            if status == TaskStatusEnum.ToDo:
                dist["not_started"] = count
            elif status == TaskStatusEnum.InProgress or status == TaskStatusEnum.Review:
                dist["in_progress"] += count
            elif status == TaskStatusEnum.Done:
                dist["completed"] = count
                done = count
            elif status == TaskStatusEnum.Blocked:
                dist["blocked"] = count

        percentage = round((done / total * 100) if total > 0 else 0.0, 1)

        return StudentTasksOverviewWidget(
            completion_percentage=percentage,
            status_distribution=TaskStatusDistribution(
                not_started=dist["not_started"],
                in_progress=dist["in_progress"],
                completed=dist["completed"],
                blocked=dist["blocked"],
            ),
        )

    async def _get_submission_trends(self, group_id: UUID) -> SubmissionTrendsWidget:
        now = datetime.now(timezone.utc)
        thirty_days_ago = now - timedelta(days=30)

        rows = await student_dashboard_repository.get_submission_trends(
            self.db, group_id, thirty_days_ago
        )

        # Fill in missing dates to make the chart smooth
        date_map = {row.sub_date.date(): row.count for row in rows}

        points = []
        # Let's generate a point every 3 days for the UI to be clean (matching the screenshot's ~7 points)
        for i in range(29, -1, -4):
            target_date = (now - timedelta(days=i)).date()
            # Try to find submissions in a 3 day window
            window_count = 0
            for j in range(4):
                d = target_date + timedelta(days=j)
                window_count += date_map.get(d, 0)

            points.append(
                TrendDataPoint(
                    date_label=target_date.strftime("%b %d"), count=window_count
                )
            )

        return SubmissionTrendsWidget(points=points)

    async def _get_project_velocity(self, group_id: UUID) -> ProjectVelocityWidget:
        now = datetime.now(timezone.utc)

        points = []
        for week in range(4, 0, -1):
            start_date = now - timedelta(weeks=week)
            end_date = now - timedelta(weeks=week - 1)

            count = (
                await student_dashboard_repository.get_project_velocity_for_daterange(
                    self.db, group_id, start_date, end_date
                )
            )

            points.append(
                VelocityDataPoint(week_label=f"Week {5 - week}", tasks_completed=count)
            )

        return ProjectVelocityWidget(points=points)
