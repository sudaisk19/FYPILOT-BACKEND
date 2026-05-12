# tests/unit/services/test_student_lifecycle.py
"""Unit tests for student lifecycle / deactivation logic (no real database)."""

from unittest.mock import AsyncMock, MagicMock

import allure
import pytest

from app.repositories.student_repository import student_repository

pytestmark = [
    allure.epic("FYPilot Unit Tests"),
    allure.feature("Services"),
]


@pytest.mark.asyncio
@allure.story("Deactivate expired students returns rowcount")
@allure.severity(allure.severity_level.MINOR)
async def test_deactivate_expired_students_returns_rowcount():
    """Repository delegates to SQL UPDATE; assert execute is used and rowcount is returned."""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.rowcount = 5
    mock_db.execute = AsyncMock(return_value=mock_result)

    count = await student_repository.deactivate_expired_students(mock_db)

    assert count == 5
    mock_db.execute.assert_called_once()
    sql_arg = mock_db.execute.call_args[0][0]
    compiled = str(sql_arg)
    assert "UPDATE students" in compiled
    assert "is_active" in compiled
    assert "fyp_start_semester" in compiled


@pytest.mark.asyncio
@allure.story("Deactivate expired students zero updates")
@allure.severity(allure.severity_level.CRITICAL)
async def test_deactivate_expired_students_zero_updates():
    """When no rows match, rowcount should be 0."""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.rowcount = 0
    mock_db.execute = AsyncMock(return_value=mock_result)

    count = await student_repository.deactivate_expired_students(mock_db)

    assert count == 0
