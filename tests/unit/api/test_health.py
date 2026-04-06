# tests/unit/api/test_health.py
"""Tests for the /health endpoint."""

import pytest


class TestHealthEndpoint:
    """Health check endpoint tests."""

    def test_health_check_returns_200(self, client):
        """GET /api/health should return 200."""
        response = client.get("/api/health")
        assert response.status_code == 200

    def test_health_check_returns_ok_status(self, client):
        """GET /api/health response should contain status=ok."""
        response = client.get("/api/health")
        data = response.json()
        assert data["status"] == "ok"

    def test_health_check_includes_redis_status(self, client):
        """GET /api/health should report Redis connection status."""
        response = client.get("/api/health")
        data = response.json()
        assert "redis" in data
        assert data["redis"] in ("connected", "disconnected")


class TestHealthEndpointAsync:
    """Async health check tests."""

    @pytest.mark.asyncio
    async def test_health_check_async(self, async_client):
        """Async GET /api/health should return 200."""
        response = await async_client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
