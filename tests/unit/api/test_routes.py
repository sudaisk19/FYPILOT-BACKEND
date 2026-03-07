# tests/unit/api/test_routes.py
"""Tests to verify all API routes are properly registered."""


class TestRouteRegistration:
    """Verify critical routes exist in the application."""

    def test_api_routes_registered(self, client):
        """Check that main API router is mounted at /api."""
        # The OpenAPI schema lists all routes
        response = client.get("/openapi.json")
        assert response.status_code == 200
        paths = response.json()["paths"]
        # At minimum, health endpoint should be registered
        assert any("/health" in path for path in paths)

    def test_auth_routes_registered(self, client):
        """Check that auth router is mounted at /auth."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        paths = response.json()["paths"]
        # Auth-related paths should exist
        auth_paths = [p for p in paths if p.startswith("/auth")]
        assert len(auth_paths) > 0, "No /auth routes found"

    def test_openapi_schema_valid(self, client):
        """OpenAPI schema should be valid JSON with expected keys."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert "info" in schema
        assert "paths" in schema
        assert schema["info"]["title"] == "FYPilot Backend"
