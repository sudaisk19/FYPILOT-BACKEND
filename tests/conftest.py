# tests/conftest.py
"""
Shared test fixtures for the FYPilot backend unit tests (services / config).

Provides mock settings and a mock async SQLAlchemy session for service-layer tests.
"""

import os
from pathlib import Path

# Required before importing ``app.auth.utils`` (import-time JWT guard).
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-key-for-unit-tests")
os.environ.setdefault("ENV", "testing")

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import allure
import pytest


# ─── Event Loop ────────────────────────────────────────────
@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ─── Mock Settings ─────────────────────────────────────────
@pytest.fixture(autouse=True)
def mock_settings(monkeypatch):
    """Ensure env vars are set for tests so Settings() can instantiate."""
    env_vars = {
        "DATABASE_URL": "postgresql://test:test@localhost:5432/testdb",
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_KEY": "test-supabase-key",
        "JWT_SECRET": "test-jwt-secret-key-for-unit-tests",
        "JWT_ALGORITHM": "HS256",
        "SESSION_SECRET": "test-session-secret-key",
        "GOOGLE_CLIENT_ID": "test-google-client-id",
        "GOOGLE_CLIENT_SECRET": "test-google-client-secret",
        "GITHUB_CLIENT_ID": "test-github-client-id",
        "GITHUB_CLIENT_SECRET": "test-github-client-secret",
        "MAILTRAP_SMTP_USER": "test-smtp-user",
        "MAILTRAP_SMTP_PASS": "test-smtp-pass",
        "REDIS_URL": "redis://localhost:6379/0",
        "ENV": "testing",
    }
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)


@pytest.fixture(scope="session", autouse=True)
def write_allure_environment_properties():
    """Write pytest run metadata consumed by Allure report widgets."""
    results_dir = Path("allure-results/pytest")
    results_dir.mkdir(parents=True, exist_ok=True)
    environment_file = results_dir / "environment.properties"
    environment_file.write_text(
        "\n".join(
            [
                "ENVIRONMENT=test",
                "FRAMEWORK=pytest",
                "LANGUAGE=Python",
                "TEST_TYPE=Unit Tests",
                "MODULES=Auth,Student,Faculty,Admin,Jury,Schemas",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


# ─── Mock Database Session ─────────────────────────────────
@pytest.fixture
def mock_db_session():
    """
    Mock async SQLAlchemy session for unit tests.
    Supports: execute, commit, refresh, add, rollback, delete, begin (async context manager).
    """
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.delete = AsyncMock()

    def _begin_factory():
        @asynccontextmanager
        async def _begin() -> AsyncIterator[None]:
            yield None

        return _begin()

    session.begin = MagicMock(side_effect=_begin_factory)
    return session


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Expose test phase reports so fixtures can inspect failure states."""
    outcome = yield
    report = outcome.get_result()
    setattr(item, f"rep_{report.when}", report)


@pytest.fixture(autouse=True)
def attach_failure_diagnostics(request):
    """Attach mock call traces and error details whenever a test fails."""
    yield

    report = getattr(request.node, "rep_call", None)
    if not report or not report.failed:
        return

    allure.attach(
        report.longreprtext,
        name="Error Detail",
        attachment_type=allure.attachment_type.TEXT,
    )

    mock_call_dump = []
    for fixture_name, value in request.node.funcargs.items():
        if isinstance(value, (MagicMock, AsyncMock)):
            mock_call_dump.append(
                {
                    "fixture": fixture_name,
                    "called": value.called,
                    "call_count": value.call_count,
                    "calls": [repr(c) for c in value.mock_calls],
                }
            )

    if mock_call_dump:
        allure.attach(
            str(mock_call_dump),
            name="Mock Calls",
            attachment_type=allure.attachment_type.JSON,
        )
