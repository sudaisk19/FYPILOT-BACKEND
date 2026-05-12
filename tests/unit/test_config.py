import allure

# tests/unit/test_config.py
"""Tests for application configuration."""

pytestmark = [
    allure.epic("FYPilot Unit Tests"),
    allure.feature("Configuration"),
]


@allure.epic("FYPilot Unit Tests")
@allure.feature("Configuration")
class TestConfigSettings:
    """Verify Settings loads correctly with test env vars."""

    @allure.story("Settings loads")
    @allure.severity(allure.severity_level.MINOR)
    def test_settings_loads(self):
        """Settings should instantiate without errors when env vars are set."""
        from app.core.config import Settings

        # Settings should load from env vars set by conftest mock_settings
        settings = Settings()
        assert settings is not None

    @allure.story("Settings env is testing")
    @allure.severity(allure.severity_level.MINOR)
    def test_settings_env_is_testing(self):
        """ENV should be 'testing' in test environment."""
        from app.core.config import Settings

        settings = Settings()
        assert settings.ENV == "testing"

    @allure.story("Settings jwt algorithm default")
    @allure.severity(allure.severity_level.MINOR)
    def test_settings_jwt_algorithm_default(self):
        """JWT_ALGORITHM should default to HS256."""
        from app.core.config import Settings

        settings = Settings()
        assert settings.jwt_algorithm == "HS256"

    @allure.story("Settings redis url present")
    @allure.severity(allure.severity_level.MINOR)
    def test_settings_redis_url_present(self):
        """Redis URL should be configured."""
        from app.core.config import Settings

        settings = Settings()
        assert settings.redis_url is not None
        assert "redis://" in settings.redis_url
