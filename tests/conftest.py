# tests/conftest.py
"""
Shared test fixtures for the FYPilot backend test suite.

Provides:
  - Async test client via httpx.AsyncClient
  - Sync test client via FastAPI TestClient
  - Mock database sessions
  - Mock Redis cache
  - Common test data factories
"""

import asyncio
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio


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


# ─── Sync Test Client ─────────────────────────────────────
@pytest.fixture
def client():
    """
    Synchronous test client for simple endpoint tests.
    Uses FastAPI's TestClient (backed by requests).
    """
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


# ─── Async Test Client ────────────────────────────────────
@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator:
    """
    Async test client for testing async endpoints.
    Uses httpx.AsyncClient for full async support.
    """
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac


# ─── Mock Database Session ─────────────────────────────────
@pytest.fixture
def mock_db_session():
    """
    Mock async database session.
    Use this to avoid hitting a real database in unit tests.
    """
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    return session


# ─── Mock Redis Cache ─────────────────────────────────────
@pytest.fixture
def mock_cache():
    """Mock the Redis cache service."""
    cache_mock = MagicMock()
    cache_mock.is_available = True
    cache_mock.get = AsyncMock(return_value=None)
    cache_mock.set = AsyncMock(return_value=True)
    cache_mock.delete = AsyncMock(return_value=True)
    cache_mock.connect = AsyncMock(return_value=True)
    cache_mock.disconnect = AsyncMock()
    return cache_mock


# ─── Test Data Helpers ─────────────────────────────────────
@pytest.fixture
def sample_student_data():
    """Sample student data for testing."""
    return {
        "email": "test.student@university.edu",
        "first_name": "Test",
        "last_name": "Student",
        "enrollment_number": "STU-2024-001",
    }


@pytest.fixture
def sample_supervisor_data():
    """Sample supervisor/faculty data for testing."""
    return {
        "email": "test.supervisor@university.edu",
        "first_name": "Test",
        "last_name": "Supervisor",
        "department": "Computer Science",
    }


@pytest.fixture
def auth_headers():
    """
    Generate mock JWT auth headers for protected endpoint tests.
    Returns headers dict with Bearer token.
    """
    import jwt

    payload = {
        "sub": "test-user-id-123",
        "email": "test@university.edu",
        "role": "student",
        "exp": 9999999999,  # Far future
    }
    token = jwt.encode(payload, "test-jwt-secret-key-for-unit-tests", algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_auth_headers():
    """Generate mock JWT auth headers with admin role."""
    import jwt

    payload = {
        "sub": "admin-user-id-456",
        "email": "admin@university.edu",
        "role": "admin",
        "exp": 9999999999,
    }
    token = jwt.encode(payload, "test-jwt-secret-key-for-unit-tests", algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}
