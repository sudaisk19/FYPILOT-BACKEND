"""
Unit tests for ``StudentDashboardService`` (`app.services.student_dashboard_service`).
The student domain exposes one dedicated service class; profile/milestone routes call
repositories directly (those are covered in route tests with repo mocks).

Repository dependency is ``student_dashboard_repository`` — mocked here per user rules.
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import allure
import pytest

from app.models.announcement import TargetRoleEnum
from app.models.group import FYPCycleEnum
from app.repositories.student_dashboard_repository import student_dashboard_repository
from app.services.student_dashboard_service import StudentDashboardService

pytestmark = [
    allure.epic("FYPilot Unit Tests"),
    allure.feature("Student Service"),
]


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.mark.asyncio
@allure.epic("FYPilot Unit Tests")
@allure.feature("Student Service")
class TestStudentDashboardServiceGetDashboardPayload:
    """``StudentDashboardService.get_dashboard_payload``."""

    @allure.story("Get dashboard when no group returns empty envelope")
    @allure.severity(allure.severity_level.CRITICAL)
    async def test_get_dashboard_when_no_group_returns_empty_envelope(self, mock_db):
        # ARRANGE
        with patch.object(
            student_dashboard_repository,
            "get_student_group",
            AsyncMock(return_value=None),
        ) as m_group:
            svc = StudentDashboardService(mock_db)
            # ACT
            envelope = await svc.get_dashboard_payload(uuid4())
        # ASSERT
        assert envelope.student_dashboard.profile.project_name == "No Project Assigned"
        assert envelope.student_dashboard.tasks_overview.completion_percentage == 0.0
        m_group.assert_awaited_once()

    @allure.story("Get dashboard when group exists builds profile and widgets")
    @allure.severity(allure.severity_level.CRITICAL)
    async def test_get_dashboard_when_group_exists_builds_profile_and_widgets(
        self, mock_db
    ):
        # ARRANGE
        gid = uuid4()
        sid = uuid4()

        member = MagicMock()
        member.student_id = sid

        group = MagicMock()
        group.group_id = gid
        group.fyp_cycle = FYPCycleEnum.fyp1
        group.fyp_stage = "ideation"
        group.members = [member]
        group.supervisor = None
        group.co_supervisors = []
        proj = MagicMock()
        proj.name = "Quantum UI"
        proj.description = "Desc"
        proj.repo_links = ["https://github.com/org/repo"]
        group.project = proj

        u = MagicMock()
        u.user_id = sid
        u.full_name = "Member One"

        ms = MagicMock()
        ms.milestone_id = uuid4()
        ms.title = "Sprint 1"
        ms.end_date = date.today() + timedelta(days=5)
        ms.sprint_goal = "Goal"
        ms.status = MagicMock()

        ann = MagicMock()
        ann.announcement_id = uuid4()
        ann.title = "Submit proposal"
        ann.due_at = datetime.now(timezone.utc) + timedelta(days=3)
        ann.description = "Desc"

        m_group = AsyncMock(return_value=group)
        m_tasks = AsyncMock(return_value=[])
        with patch.object(
            student_dashboard_repository,
            "get_student_group",
            m_group,
        ), patch.object(
            student_dashboard_repository,
            "get_group_members_as_users",
            AsyncMock(return_value=[u]),
        ), patch.object(
            student_dashboard_repository,
            "get_upcoming_milestones",
            AsyncMock(return_value=[ms]),
        ), patch.object(
            student_dashboard_repository,
            "get_upcoming_submission_requests",
            AsyncMock(return_value=[ann]),
        ), patch.object(
            student_dashboard_repository,
            "get_task_status_counts",
            m_tasks,
        ), patch.object(
            student_dashboard_repository,
            "get_submission_trends",
            AsyncMock(return_value=[]),
        ), patch.object(
            student_dashboard_repository,
            "get_project_velocity_for_daterange",
            AsyncMock(return_value=0),
        ):
            svc = StudentDashboardService(mock_db)
            # ACT
            envelope = await svc.get_dashboard_payload(sid)
        # ASSERT
        assert envelope.student_dashboard.profile.project_name == "Quantum UI"
        assert len(envelope.student_dashboard.profile.group_members) == 1
        assert len(envelope.student_dashboard.upcoming_deadlines.deadlines) <= 4
        m_group.assert_awaited_once()
        m_tasks.assert_awaited_once()

    @allure.story("Get dashboard when fyp2 passes fyp2 targets for submission requests")
    @allure.severity(allure.severity_level.CRITICAL)
    async def test_get_dashboard_when_fyp2_passes_fyp2_targets_for_submission_requests(
        self, mock_db
    ):
        # ARRANGE — business rule: FYP2 adds ``TargetRoleEnum.fyp2_students`` to filters.
        gid = uuid4()
        sid = uuid4()

        group = MagicMock()
        group.group_id = gid
        group.fyp_cycle = FYPCycleEnum.fyp2
        group.fyp_stage = "implementation"
        group.members = []
        group.supervisor = None
        group.co_supervisors = []
        proj = MagicMock()
        proj.name = "P"
        proj.description = None
        proj.repo_links = []
        group.project = proj

        sub_mock = AsyncMock(return_value=[])

        with patch.object(
            student_dashboard_repository,
            "get_student_group",
            AsyncMock(return_value=group),
        ), patch.object(
            student_dashboard_repository,
            "get_group_members_as_users",
            AsyncMock(return_value=[]),
        ), patch.object(
            student_dashboard_repository,
            "get_upcoming_milestones",
            AsyncMock(return_value=[]),
        ), patch.object(
            student_dashboard_repository,
            "get_upcoming_submission_requests",
            sub_mock,
        ), patch.object(
            student_dashboard_repository,
            "get_task_status_counts",
            AsyncMock(return_value=[]),
        ), patch.object(
            student_dashboard_repository,
            "get_submission_trends",
            AsyncMock(return_value=[]),
        ), patch.object(
            student_dashboard_repository,
            "get_project_velocity_for_daterange",
            AsyncMock(return_value=0),
        ):
            svc = StudentDashboardService(mock_db)
            # ACT
            await svc.get_dashboard_payload(sid)
        # ASSERT
        sub_mock.assert_awaited_once()
        args, _kwargs = sub_mock.await_args
        valid_targets = args[2]
        assert TargetRoleEnum.fyp2_students.value in valid_targets

    @allure.story("Get dashboard when tasks counts mix maps status distribution")
    @allure.severity(allure.severity_level.CRITICAL)
    async def test_get_dashboard_when_tasks_counts_mix_maps_status_distribution(
        self, mock_db
    ):
        # ARRANGE
        from app.models.task import TaskStatusEnum

        gid = uuid4()
        sid = uuid4()

        group = MagicMock()
        group.group_id = gid
        group.fyp_cycle = FYPCycleEnum.fyp1
        group.fyp_stage = "ideation"
        group.members = []
        group.supervisor = None
        group.co_supervisors = []
        proj = MagicMock()
        proj.name = "X"
        proj.description = None
        proj.repo_links = []
        group.project = proj

        counts = [
            (TaskStatusEnum.ToDo, 2),
            (TaskStatusEnum.InProgress, 1),
            (TaskStatusEnum.Done, 4),
            (TaskStatusEnum.Blocked, 1),
        ]

        with patch.object(
            student_dashboard_repository,
            "get_student_group",
            AsyncMock(return_value=group),
        ), patch.object(
            student_dashboard_repository,
            "get_group_members_as_users",
            AsyncMock(return_value=[]),
        ), patch.object(
            student_dashboard_repository,
            "get_upcoming_milestones",
            AsyncMock(return_value=[]),
        ), patch.object(
            student_dashboard_repository,
            "get_upcoming_submission_requests",
            AsyncMock(return_value=[]),
        ), patch.object(
            student_dashboard_repository,
            "get_task_status_counts",
            AsyncMock(return_value=counts),
        ), patch.object(
            student_dashboard_repository,
            "get_submission_trends",
            AsyncMock(return_value=[]),
        ), patch.object(
            student_dashboard_repository,
            "get_project_velocity_for_daterange",
            AsyncMock(return_value=0),
        ):
            svc = StudentDashboardService(mock_db)
            # ACT
            envelope = await svc.get_dashboard_payload(sid)
        # ASSERT
        assert envelope.student_dashboard.tasks_overview.completion_percentage == 50.0
        dist = envelope.student_dashboard.tasks_overview.status_distribution
        assert dist.not_started == 2
        assert dist.completed == 4
