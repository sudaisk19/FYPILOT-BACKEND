"""
Unit tests for jury-related **services**.
STEP 1 — inventory:

- ``JuryMatchingService`` (``app/services/jury_matching_service.py``):
  ``health_check``, ``get_batch_matches``, ``trigger_reindex``, ``reset_all_jury_data``,
  ``create_assignment_batch``, ``run_assignment_job`` (background; not unit-tested in full),
  ``get_batch_status``, ``get_all_batches``, ``get_all_jury_pairs``, ``get_jury_matches``,
  ``update_assignment_jury``, plus private normalizers / UUID helpers.

- ``jury_matching_repository`` — DB helpers used by the service.

- **Jury evaluations** (letter grades / proposal marks) are persisted via
  ``jury_evaluation_repository`` functions (no separate ``JuryEvaluationService`` class);
  HTTP lives in ``supervisor_fypmilestone.py`` with ``_ensure_active_jury``.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import allure
import pytest
from fastapi import HTTPException

from app.models.jury_assignment import JuryBatchStatusEnum
from app.services.jury_matching_client import JuryMatchingServiceError
from app.services.jury_matching_service import JuryMatchingService

pytestmark = [
    allure.epic("FYPilot Unit Tests"),
    allure.feature("Jury Service"),
]


@pytest.mark.asyncio
@allure.epic("FYPilot Unit Tests")
@allure.feature("Jury Service")
class TestJuryMatchingServiceHealthCheck:
    """``JuryMatchingService.health_check``."""

    @allure.story("Health check calls client")
    @allure.severity(allure.severity_level.CRITICAL)
    async def test_health_check_calls_client(self):
        # ARRANGE
        svc = JuryMatchingService()
        svc._client = MagicMock()
        svc._client.health_check = AsyncMock(return_value=True)
        # ACT
        ok = await svc.health_check()
        # ASSERT
        assert ok is True
        svc._client.health_check.assert_awaited_once()


@pytest.mark.asyncio
@allure.epic("FYPilot Unit Tests")
@allure.feature("Jury Service")
class TestJuryMatchingServiceGetBatchMatches:
    """``JuryMatchingService.get_batch_matches``."""

    @allure.story("Get batch matches success records circuit success")
    @allure.severity(allure.severity_level.MINOR)
    async def test_get_batch_matches_success_records_circuit_success(self):
        # ARRANGE
        svc = JuryMatchingService()
        svc._circuit = MagicMock()
        svc._circuit.check_and_raise = MagicMock()
        svc._circuit.record_success = MagicMock()
        svc._client = MagicMock()
        svc._client.batch_match = AsyncMock(return_value=[{"project_id": str(uuid4())}])
        # ACT
        out = await svc.get_batch_matches(fyp_cycles=["fyp1"])
        # ASSERT
        assert len(out) == 1
        svc._circuit.record_success.assert_called_once()
        svc._client.batch_match.assert_awaited_once_with(
            fyp_cycles=["fyp1"],
            max_groups_per_pair=None,
            min_jury_per_project=None,
        )

    @allure.story("Get batch matches service error records failure")
    @allure.severity(allure.severity_level.MINOR)
    async def test_get_batch_matches_service_error_records_failure(self):
        # ARRANGE
        svc = JuryMatchingService()
        svc._circuit = MagicMock()
        svc._circuit.check_and_raise = MagicMock()
        svc._circuit.record_failure = MagicMock()
        svc._client = MagicMock()
        svc._client.batch_match = AsyncMock(
            side_effect=JuryMatchingServiceError("down", status_code=503)
        )
        # ACT / ASSERT
        with pytest.raises(JuryMatchingServiceError):
            await svc.get_batch_matches()
        svc._circuit.record_failure.assert_called_once()

    @allure.story("Get batch matches circuit open raises before client")
    @allure.severity(allure.severity_level.MINOR)
    async def test_get_batch_matches_circuit_open_raises_before_client(self):
        # ARRANGE
        svc = JuryMatchingService()
        svc._circuit = MagicMock()
        svc._circuit.check_and_raise = MagicMock(
            side_effect=HTTPException(status_code=503, detail="open")
        )
        svc._client = MagicMock()
        svc._client.batch_match = AsyncMock()
        # ACT / ASSERT
        with pytest.raises(HTTPException):
            await svc.get_batch_matches()
        svc._client.batch_match.assert_not_awaited()


@pytest.mark.asyncio
@allure.epic("FYPilot Unit Tests")
@allure.feature("Jury Service")
class TestJuryMatchingServiceTriggerReindex:
    """``JuryMatchingService.trigger_reindex``."""

    @allure.story("Trigger reindex returns client payload")
    @allure.severity(allure.severity_level.MINOR)
    async def test_trigger_reindex_returns_client_payload(self):
        # ARRANGE
        svc = JuryMatchingService()
        svc._circuit = MagicMock()
        svc._circuit.check_and_raise = MagicMock()
        svc._circuit.record_success = MagicMock()
        svc._client = MagicMock()
        svc._client.reindex = AsyncMock(return_value={"status": "started"})
        # ACT
        out = await svc.trigger_reindex()
        # ASSERT
        assert out["status"] == "started"
        svc._client.reindex.assert_awaited_once()


@pytest.mark.asyncio
@allure.epic("FYPilot Unit Tests")
@allure.feature("Jury Service")
class TestJuryMatchingServiceResetAndRepository:
    """``reset_all_jury_data`` + ``update_assignment_jury`` + ``get_jury_matches``."""

    @allure.story("Reset all jury data commits after repository")
    @allure.severity(allure.severity_level.MINOR)
    async def test_reset_all_jury_data_commits_after_repository(self, mock_db_session):
        # ARRANGE
        svc = JuryMatchingService()
        counts = {"deleted_assignments": 1, "deleted_pairs": 1, "deleted_batches": 1}
        # ACT
        with patch(
            "app.services.jury_matching_service.jury_matching_repository.reset_all_jury_data",
            new_callable=AsyncMock,
            return_value=counts,
        ) as m_reset:
            out = await svc.reset_all_jury_data(mock_db_session)
        # ASSERT
        assert out == counts
        m_reset.assert_awaited_once_with(mock_db_session)
        mock_db_session.commit.assert_awaited()

    @allure.story("Update assignment jury returns none when pair missing")
    @allure.severity(allure.severity_level.CRITICAL)
    async def test_update_assignment_jury_returns_none_when_pair_missing(
        self, mock_db_session
    ):
        # ARRANGE
        svc = JuryMatchingService()
        aid, pid = uuid4(), uuid4()
        # ACT
        with patch(
            "app.services.jury_matching_service.jury_matching_repository.get_jury_pair_by_id",
            new_callable=AsyncMock,
            return_value=None,
        ) as m_pair:
            out = await svc.update_assignment_jury(
                mock_db_session, assignment_id=aid, new_pair_id=pid
            )
        # ASSERT
        assert out is None
        m_pair.assert_awaited_once_with(mock_db_session, pid)

    @allure.story("Get jury matches returns none when no latest batch")
    @allure.severity(allure.severity_level.MINOR)
    async def test_get_jury_matches_returns_none_when_no_latest_batch(
        self, mock_db_session
    ):
        # ARRANGE
        svc = JuryMatchingService()
        # ACT
        with patch(
            "app.services.jury_matching_service.jury_matching_repository.get_latest_batch",
            new_callable=AsyncMock,
            return_value=None,
        ) as m_latest:
            out = await svc.get_jury_matches(mock_db_session, batch_id=None)
        # ASSERT
        assert out is None
        m_latest.assert_awaited_once_with(mock_db_session)


@pytest.mark.asyncio
@allure.epic("FYPilot Unit Tests")
@allure.feature("Jury Service")
class TestJuryMatchingServiceCreateAssignmentBatch:
    """``create_assignment_batch`` persists a processing batch."""

    @allure.story("Create assignment batch adds batch and commits")
    @allure.severity(allure.severity_level.CRITICAL)
    async def test_create_assignment_batch_adds_batch_and_commits(
        self, mock_db_session
    ):
        # ARRANGE
        svc = JuryMatchingService()
        cycles = ["fyp1"]
        uid = uuid4()
        # ACT
        batch = await svc.create_assignment_batch(
            mock_db_session, fyp_cycles=cycles, created_by=uid
        )
        # ASSERT
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_awaited()
        mock_db_session.refresh.assert_awaited()
        assert batch.status == JuryBatchStatusEnum.processing
        assert batch.fyp_cycles == cycles


@allure.epic("FYPilot Unit Tests")
@allure.feature("Jury Service")
class TestProposalEvaluationSchemaBoundaries:
    """Pydantic limits for proposal jury marks (no separate jury evaluation service)."""

    @allure.story("Proposal introduction above max rejected by schema")
    @allure.severity(allure.severity_level.NORMAL)
    def test_proposal_introduction_above_max_rejected_by_schema(self):
        # ARRANGE
        from pydantic import ValidationError

        from app.models.jury_evaluation import ProposalStatusEnum
        from app.schemas.jury_evaluation_schema import ProposalEvaluationPayload

        # ACT / ASSERT
        with pytest.raises(ValidationError):
            ProposalEvaluationPayload(
                introduction=2.5,
                literature_review=1.0,
                methodology=1.0,
                planning=1.0,
                system_diagram=1.0,
                project_status=ProposalStatusEnum.accepted,
            )


@allure.epic("FYPilot Unit Tests")
@allure.feature("Jury Service")
class TestJuryMatchingServiceNormalizePayload:
    """``_normalize_ai_payload`` — shape normalization."""

    @allure.story("Normalize ai payload flattens dict assignments")
    @allure.severity(allure.severity_level.MINOR)
    def test_normalize_ai_payload_flattens_dict_assignments(self):
        # ARRANGE
        svc = JuryMatchingService()
        raw = {
            "pairs": [],
            "assignments": [{"project_id": str(uuid4()), "jury_id": "j1"}],
        }
        # ACT
        pairs, assigns = svc._normalize_ai_payload(raw)
        # ASSERT
        assert pairs == []
        assert len(assigns) == 1
        assert "project_id" in assigns[0]
