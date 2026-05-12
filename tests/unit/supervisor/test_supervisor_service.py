"""
Unit tests for supervisor-facing **services**.
Inventory (STEP 1 — supervisor-related services):
- ``SupervisorRecommendationService`` — ``health_check``, ``recommend_supervisors``,
  ``refresh_supervisor_index``, ``_transform_members``, ``_transform_recommendations``
  (``app/services/supervisor_recommendation_service.py``).
- ``FacultyDashboardService`` — ``get_dashboard_payload`` plus private builders
  (``app/services/faculty_dashboard_service.py``); supervisor UI uses the supervisor
  section when ``faculty.is_supervisor``; jury section when ``faculty.is_jury``.

There is no separate ``SupervisorService``; milestone / submission ownership rules live
in HTTP + repositories (``group_repository``, ``supervisor_evaluation_repository``).
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import allure
import pytest

from app.services.faculty_dashboard_service import FacultyDashboardService
from app.services.supervisor_recommendation_client import (
    SupervisorRecommendationServiceError,
)
from app.services.supervisor_recommendation_service import (
    SupervisorRecommendationService,
)

pytestmark = [
    allure.epic("FYPilot Unit Tests"),
    allure.feature("Faculty Service"),
]


def _make_recommendation_service_with_mocks() -> (
    tuple[SupervisorRecommendationService, dict]
):
    """Build a fresh service instance with injectable mocks (no module singleton)."""
    svc = SupervisorRecommendationService()
    mocks = {
        "circuit": MagicMock(),
        "cache": MagicMock(),
        "dedup": MagicMock(),
        "ai": MagicMock(),
    }
    mocks["circuit"].check_and_raise = MagicMock()
    mocks["circuit"].record_success = MagicMock()
    mocks["circuit"].record_failure = MagicMock()
    mocks["cache"].get = AsyncMock(return_value=None)
    mocks["cache"].set = AsyncMock()
    mocks["dedup"].acquire = AsyncMock(return_value=(True, "lock-key"))
    mocks["dedup"].release = AsyncMock()
    mocks["ai"].health_check = AsyncMock(return_value=True)
    mocks["ai"].get_recommendations = AsyncMock(
        return_value={
            "results": [
                {
                    "name": "Dr. Example",
                    "department": "CS",
                    "score": 0.91,
                    "user_id": str(uuid4()),
                    "domains": [],
                    "requirements": [],
                    "project_type": [],
                    "reason": "match",
                }
            ]
        }
    )
    mocks["ai"].refresh_supervisors = AsyncMock(return_value={"status": "ok"})
    svc._circuit = mocks["circuit"]
    svc._cache = mocks["cache"]
    svc._deduplicator = mocks["dedup"]
    svc._ai_client = mocks["ai"]
    return svc, mocks


@pytest.mark.asyncio
@allure.epic("FYPilot Unit Tests")
@allure.feature("Faculty Service")
class TestSupervisorRecommendationServiceHealthCheck:
    """``SupervisorRecommendationService.health_check``."""

    @allure.story("Health check delegates to ai client")
    @allure.severity(allure.severity_level.CRITICAL)
    async def test_health_check_delegates_to_ai_client(self):
        # ARRANGE
        svc, mocks = _make_recommendation_service_with_mocks()
        mocks["ai"].health_check = AsyncMock(return_value=True)
        # ACT
        out = await svc.health_check()
        # ASSERT
        assert out is True
        mocks["ai"].health_check.assert_awaited_once()


@pytest.mark.asyncio
@allure.epic("FYPilot Unit Tests")
@allure.feature("Faculty Service")
class TestSupervisorRecommendationServiceRecommendSupervisors:
    """``SupervisorRecommendationService.recommend_supervisors``."""

    @allure.story("Recommend supervisors success calls group repo ai and cache set")
    @allure.severity(allure.severity_level.MINOR)
    async def test_recommend_supervisors_success_calls_group_repo_ai_and_cache_set(
        self, mock_db_session
    ):
        # ARRANGE
        svc, mocks = _make_recommendation_service_with_mocks()
        gid = str(uuid4())
        member = MagicMock()
        member.student = MagicMock(
            skills=["Rust"],
            cgpa=3.7,
            portfolio_projects=[{"title": "P1", "tech_stack": ["Go"]}],
        )
        group = MagicMock()
        group.members = [member]
        # ACT
        with patch(
            "app.services.supervisor_recommendation_service.group_repository.get_with_members",
            new_callable=AsyncMock,
            return_value=group,
        ) as m_group:
            recs = await svc.recommend_supervisors(
                mock_db_session,
                group_id=gid,
                idea_domain="ML",
            )
        # ASSERT
        m_group.assert_awaited_once_with(mock_db_session, gid)
        mocks["circuit"].check_and_raise.assert_called_once()
        mocks["circuit"].record_success.assert_called_once()
        mocks["cache"].get.assert_awaited()
        mocks["ai"].get_recommendations.assert_awaited()
        mocks["cache"].set.assert_awaited()
        assert len(recs) == 1
        assert recs[0]["name"] == "Dr. Example"
        assert recs[0]["score"] == 91.0

    @allure.story("Recommend supervisors group not found raises value error")
    @allure.severity(allure.severity_level.NORMAL)
    async def test_recommend_supervisors_group_not_found_raises_value_error(
        self, mock_db_session
    ):
        # ARRANGE
        svc, _ = _make_recommendation_service_with_mocks()
        with patch(
            "app.services.supervisor_recommendation_service.group_repository.get_with_members",
            new_callable=AsyncMock,
            return_value=None,
        ):
            # ACT / ASSERT
            with pytest.raises(ValueError, match="Group not found"):
                await svc.recommend_supervisors(mock_db_session, group_id="missing-id")

    @allure.story("Recommend supervisors cache hit skips ai and group fetch")
    @allure.severity(allure.severity_level.MINOR)
    async def test_recommend_supervisors_cache_hit_skips_ai_and_group_fetch(
        self, mock_db_session
    ):
        # ARRANGE
        svc, mocks = _make_recommendation_service_with_mocks()
        cached = [{"name": "Cached", "score": 50.0, "user_id": "u"}]
        mocks["cache"].get = AsyncMock(return_value=cached)
        # ACT
        with patch(
            "app.services.supervisor_recommendation_service.group_repository.get_with_members",
            new_callable=AsyncMock,
        ) as m_group:
            out = await svc.recommend_supervisors(
                mock_db_session, group_id=str(uuid4())
            )
        # ASSERT
        assert out == cached
        m_group.assert_not_awaited()
        mocks["ai"].get_recommendations.assert_not_awaited()

    @allure.story("Recommend supervisors ai error records failure")
    @allure.severity(allure.severity_level.MINOR)
    async def test_recommend_supervisors_ai_error_records_failure(
        self, mock_db_session
    ):
        # ARRANGE
        svc, mocks = _make_recommendation_service_with_mocks()
        mocks["ai"].get_recommendations = AsyncMock(
            side_effect=SupervisorRecommendationServiceError("boom", status_code=502)
        )
        member = MagicMock()
        member.student = MagicMock(skills=[], cgpa=None, portfolio_projects=None)
        group = MagicMock(members=[member])
        # ACT / ASSERT
        with patch(
            "app.services.supervisor_recommendation_service.group_repository.get_with_members",
            new_callable=AsyncMock,
            return_value=group,
        ):
            with pytest.raises(SupervisorRecommendationServiceError):
                await svc.recommend_supervisors(mock_db_session, group_id=str(uuid4()))
        mocks["circuit"].record_failure.assert_called_once()


@pytest.mark.asyncio
@allure.epic("FYPilot Unit Tests")
@allure.feature("Faculty Service")
class TestSupervisorRecommendationServiceRefreshIndex:
    """``SupervisorRecommendationService.refresh_supervisor_index``."""

    @allure.story("Refresh supervisor index calls client with secret")
    @allure.severity(allure.severity_level.MINOR)
    async def test_refresh_supervisor_index_calls_client_with_secret(self):
        # ARRANGE
        svc, mocks = _make_recommendation_service_with_mocks()
        # ACT
        await svc.refresh_supervisor_index(webhook_secret="sec")
        # ASSERT
        mocks["ai"].refresh_supervisors.assert_awaited_once_with("sec")


@allure.epic("FYPilot Unit Tests")
@allure.feature("Faculty Service")
class TestSupervisorRecommendationServiceTransforms:
    """Pure helpers on ``SupervisorRecommendationService``."""

    @allure.story("Transform recommendations scales fractional score to percent")
    @allure.severity(allure.severity_level.MINOR)
    def test_transform_recommendations_scales_fractional_score_to_percent(self):
        # ARRANGE
        svc, _ = _make_recommendation_service_with_mocks()
        ai = {"results": [{"score": 0.25, "name": "A", "user_id": "x"}]}
        # ACT
        out = svc._transform_recommendations(ai)
        # ASSERT
        assert out[0]["score"] == 25.0

    @allure.story("Transform members maps skills and portfolio")
    @allure.severity(allure.severity_level.MINOR)
    def test_transform_members_maps_skills_and_portfolio(self):
        # ARRANGE
        svc, _ = _make_recommendation_service_with_mocks()
        m = MagicMock()
        m.student = MagicMock(
            skills=["X"],
            cgpa=3.0,
            portfolio_projects=[{"title": "T", "tech_stack": ["Y"]}],
        )
        # ACT
        data = svc._transform_members([m])
        # ASSERT
        assert data[0]["cgpa"] == 3.0
        assert "X" in data[0]["skills"]
        assert "T" in data[0]["past_projects"]


@pytest.mark.asyncio
@allure.epic("FYPilot Unit Tests")
@allure.feature("Faculty Service")
class TestFacultyDashboardServiceSupervisorBranch:
    """``FacultyDashboardService.get_dashboard_payload`` — supervisor-only faculty."""

    @allure.story("Get dashboard payload supervisor calls repo and omits jury section")
    @allure.severity(allure.severity_level.CRITICAL)
    async def test_get_dashboard_payload_supervisor_calls_repo_and_omits_jury_section(
        self, mock_db_session
    ):
        # ARRANGE
        faculty = MagicMock()
        faculty.user_id = uuid4()
        faculty.is_active = True
        faculty.is_supervisor = True
        faculty.is_jury = False
        faculty.capacity_max = 5
        faculty.capacity_filled = 2

        mock_repo = MagicMock()
        mock_repo.count_supervised_groups = AsyncMock(return_value=2)
        mock_repo.count_jury_assigned_groups = AsyncMock(return_value=99)
        mock_repo.average_supervisor_marks = AsyncMock(return_value=7.25)
        mock_repo.average_jury_marks = AsyncMock(return_value=1.0)
        mock_repo.fetch_supervised_group_overview = AsyncMock(return_value=[])
        mock_repo.fetch_recent_submissions = AsyncMock(return_value=[])
        # ACT
        with patch(
            "app.services.faculty_dashboard_service.FacultyDashboardRepository",
            return_value=mock_repo,
        ):
            service = FacultyDashboardService(mock_db_session)
            envelope = await service.get_dashboard_payload(faculty)
        # ASSERT
        mock_repo.count_supervised_groups.assert_awaited_once_with(faculty.user_id)
        mock_repo.count_jury_assigned_groups.assert_not_awaited()
        mock_repo.fetch_supervised_group_overview.assert_awaited_once()
        assert envelope.faculty_dashboard.top_cards.total_supervised_groups == 2
        assert envelope.faculty_dashboard.jury_section is None
        assert envelope.faculty_dashboard.supervisor_section is not None
