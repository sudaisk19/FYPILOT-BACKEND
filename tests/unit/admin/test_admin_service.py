"""
STEP 1 — Admin-related **services** (inventory):
- ``AdminDashboardService`` — ``get_dashboard_payload`` (+ private widget builders)
  ([``app/services/admin_dashboard_service.py``](app/services/admin_dashboard_service.py)).
  Uses ``AdminDashboardRepository``.

- ``bulk_import_service`` — ``create_bulk_import_job``, ``process_single_item``,
  ``create_single_student``, ``create_single_supervisor``, ``batch_insert_*``, …
  ([``app/services/bulk_import_service.py``](app/services/bulk_import_service.py)).

There is no single ``AdminService`` class; HTTP handlers also call repositories directly.

STEP 2 — Tests below mock repositories / DB and assert call behaviour.
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import allure
import pytest

from app.models.bulk_import import BulkItemStatus
from app.models.user import RoleEnum
from app.services import bulk_import_service
from app.services.admin_dashboard_service import AdminDashboardService

pytestmark = [
    allure.epic("FYPilot Unit Tests"),
    allure.feature("Admin Service"),
]


def _exec_scalar(val):
    r = MagicMock()
    r.scalar_one_or_none = MagicMock(return_value=val)
    return r


@pytest.mark.asyncio
@allure.epic("FYPilot Unit Tests")
@allure.feature("Admin Service")
class TestAdminDashboardService:
    """``AdminDashboardService.get_dashboard_payload`` orchestrates the repository."""

    @allure.story("Get dashboard payload calls repo methods and returns envelope")
    @allure.severity(allure.severity_level.CRITICAL)
    async def test_get_dashboard_payload_calls_repo_methods_and_returns_envelope(
        self, mock_db_session
    ):
        # ARRANGE
        mock_repo = MagicMock()
        mock_repo.count_total_users = AsyncMock(return_value=4)
        mock_repo.count_active_students = AsyncMock(return_value=3)
        mock_repo.count_active_supervisors = AsyncMock(return_value=2)
        mock_repo.count_active_projects = AsyncMock(return_value=1)
        mock_repo.count_supervisors_per_department = AsyncMock(
            return_value=[("Computer Science", 2)]
        )
        mock_repo.students_per_start_term = AsyncMock(return_value=[("fall 2025", 5)])
        mock_repo.active_projects_per_cycle = AsyncMock(return_value=[("fyp1", 3)])
        mock_repo.supervisor_capacity_totals = AsyncMock(return_value=(20, 10))
        mock_repo.fetch_supervisor_workload = AsyncMock(
            return_value=[("Dr. A", 2), ("Dr. B", 1)]
        )

        class _M:
            title = "M1"
            due_date = date.today()
            fyp_cycle = MagicMock()
            fyp_cycle.value = "fyp1"

        mock_repo.get_upcoming_milestones = AsyncMock(return_value=[_M()])
        mock_repo.get_active_milestone = AsyncMock(return_value=None)

        with patch(
            "app.services.admin_dashboard_service.AdminDashboardRepository",
            return_value=mock_repo,
        ):
            svc = AdminDashboardService(mock_db_session)
            # ACT
            envelope = await svc.get_dashboard_payload()
        # ASSERT
        mock_repo.count_total_users.assert_awaited_once()
        mock_repo.count_active_students.assert_awaited_once()
        mock_repo.count_supervisors_per_department.assert_awaited_once()
        mock_repo.students_per_start_term.assert_awaited_once()
        mock_repo.active_projects_per_cycle.assert_awaited_once()
        mock_repo.supervisor_capacity_totals.assert_awaited_once()
        mock_repo.fetch_supervisor_workload.assert_awaited_once()
        mock_repo.get_upcoming_milestones.assert_awaited_once()
        mock_repo.get_active_milestone.assert_awaited_once()
        assert envelope.admin_dashboard.top_cards.total_users == 4


@pytest.mark.asyncio
@allure.epic("FYPilot Unit Tests")
@allure.feature("Admin Service")
class TestBulkImportCreateSingleStudent:
    """``bulk_import_service.create_single_student``."""

    @allure.story("Create student success when email and roll available")
    @allure.severity(allure.severity_level.CRITICAL)
    async def test_create_student_success_when_email_and_roll_available(self):
        # ARRANGE
        db = MagicMock()
        db.execute = AsyncMock(
            side_effect=[
                _exec_scalar(None),
                _exec_scalar(None),
            ]
        )
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        with patch.object(bulk_import_service, "hash_password", return_value="h"):
            with patch.object(
                bulk_import_service,
                "generate_temp_password",
                return_value="temp-pass",
            ):
                # ACT
                user, pwd = await bulk_import_service.create_single_student(
                    db,
                    full_name="Student One",
                    email="new.student@uni.edu",
                    roll_number="CS-001",
                    cgpa=3.4,
                    fyp_start_semester="fall",
                    fyp_start_year=2025,
                    department="Computer Science",
                )
        # ASSERT
        assert pwd == "temp-pass"
        assert user.email == "new.student@uni.edu"
        assert user.role == RoleEnum.student
        assert db.execute.await_count == 2
        db.add.assert_called()
        db.flush.assert_awaited_once()
        db.commit.assert_awaited_once()

    @allure.story("Create student duplicate email raises value error")
    @allure.severity(allure.severity_level.CRITICAL)
    async def test_create_student_duplicate_email_raises_value_error(self):
        # ARRANGE
        db = MagicMock()
        db.execute = AsyncMock(return_value=_exec_scalar(object()))
        # ACT / ASSERT
        with pytest.raises(ValueError, match="Email already registered"):
            await bulk_import_service.create_single_student(
                db,
                full_name="X",
                email="dup@uni.edu",
                roll_number="CS-002",
                cgpa=3.0,
                fyp_start_semester="fall",
                fyp_start_year=2025,
                department="Computer Science",
            )


@pytest.mark.asyncio
@allure.epic("FYPilot Unit Tests")
@allure.feature("Admin Service")
class TestBulkImportCreateSingleSupervisor:
    """``bulk_import_service.create_single_supervisor``."""

    @allure.story("Create supervisor duplicate email raises value error")
    @allure.severity(allure.severity_level.CRITICAL)
    async def test_create_supervisor_duplicate_email_raises_value_error(self):
        # ARRANGE
        db = MagicMock()
        db.execute = AsyncMock(return_value=_exec_scalar(object()))
        # ACT / ASSERT
        with pytest.raises(ValueError, match="Email already registered"):
            await bulk_import_service.create_single_supervisor(
                db,
                full_name="Faculty",
                email="dup@uni.edu",
                department="Computer Science",
                designation="Professor",
            )


@pytest.mark.asyncio
@allure.epic("FYPilot Unit Tests")
@allure.feature("Admin Service")
class TestBulkImportProcessSingleItem:
    """``process_single_item`` — duplicate detection yields partial row outcome."""

    @allure.story("Process single item skips when email already registered")
    @allure.severity(allure.severity_level.MINOR)
    async def test_process_single_item_skips_when_email_already_registered(self):
        # ARRANGE
        payload = {
            "full_name": "Jane",
            "email": "jane@uni.edu",
            "roll_number": "R9",
            "cgpa": "3.0",
            "fyp_start_semester": "fall",
            "fyp_start_year": "2025",
            "department": "Computer Science",
        }
        item = MagicMock()
        item.payload = payload
        item.status = None
        item.error = None

        db = MagicMock()
        db.execute = AsyncMock(return_value=_exec_scalar(object()))
        db.add = MagicMock()
        db.flush = AsyncMock()

        # ACT
        status = await bulk_import_service.process_single_item(
            db, item, RoleEnum.student
        )
        # ASSERT
        assert status == "skipped"
        assert item.status == BulkItemStatus.skipped
        assert "Email already registered" in (item.error or "")
        db.add.assert_not_called()


@pytest.mark.asyncio
@allure.epic("FYPilot Unit Tests")
@allure.feature("Admin Service")
class TestAdminDashboardEvaluationBranch:
    """Active milestone branch on ``_build_evaluation_status``."""

    @allure.story("Evaluation status uses repo counts when milestone active")
    @allure.severity(allure.severity_level.MINOR)
    async def test_evaluation_status_uses_repo_counts_when_milestone_active(self):
        # ARRANGE
        mock_repo = MagicMock()
        mock_repo.count_total_users = AsyncMock(return_value=1)
        mock_repo.count_active_students = AsyncMock(return_value=1)
        mock_repo.count_active_supervisors = AsyncMock(return_value=1)
        mock_repo.count_active_projects = AsyncMock(return_value=1)
        mock_repo.count_supervisors_per_department = AsyncMock(return_value=[])
        mock_repo.students_per_start_term = AsyncMock(return_value=[])
        mock_repo.active_projects_per_cycle = AsyncMock(return_value=[])
        mock_repo.supervisor_capacity_totals = AsyncMock(return_value=(0, 0))
        mock_repo.fetch_supervisor_workload = AsyncMock(return_value=[])
        mock_repo.get_upcoming_milestones = AsyncMock(return_value=[])

        ms = MagicMock()
        ms.milestone_id = uuid4()
        ms.title = "Eval milestone"
        ms.evaluator = "supervisor"
        ms.updated_at = None
        ms.activated_at = None
        ms.created_at = None
        mock_repo.get_active_milestone = AsyncMock(return_value=ms)
        mock_repo.count_expected_evaluations_for_milestone = AsyncMock(return_value=10)
        mock_repo.count_evaluations_for_milestone = AsyncMock(return_value=(4, 1))

        with patch(
            "app.services.admin_dashboard_service.AdminDashboardRepository",
            return_value=mock_repo,
        ):
            svc = AdminDashboardService(MagicMock())
            # ACT
            envelope = await svc.get_dashboard_payload()
        # ASSERT
        mock_repo.count_expected_evaluations_for_milestone.assert_awaited_once_with(ms)
        mock_repo.count_evaluations_for_milestone.assert_awaited_once_with(ms)
        assert envelope.admin_dashboard.evaluation_status.evaluations_required == 10
        assert envelope.admin_dashboard.evaluation_status.evaluations_submitted == 4
