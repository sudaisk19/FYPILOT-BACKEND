# tests/unit/test_config.py
"""Tests for application configuration."""


class TestConfigSettings:
    """Verify Settings loads correctly with test env vars."""

    def test_settings_loads(self):
        """Settings should instantiate without errors when env vars are set."""
        from app.core.config import Settings

        # Settings should load from env vars set by conftest mock_settings
        settings = Settings()
        assert settings is not None

    def test_settings_env_is_testing(self):
        """ENV should be 'testing' in test environment."""
        from app.core.config import Settings

        settings = Settings()
        assert settings.ENV == "testing"

    def test_settings_jwt_algorithm_default(self):
        """JWT_ALGORITHM should default to HS256."""
        from app.core.config import Settings

        settings = Settings()
        assert settings.jwt_algorithm == "HS256"

    def test_settings_redis_url_present(self):
        """Redis URL should be configured."""
        from app.core.config import Settings

        settings = Settings()
        assert settings.redis_url is not None
        assert "redis://" in settings.redis_url
