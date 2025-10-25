# app/auth/oauth.py

"""
OAuth Configuration Module

This module configures OAuth clients for social authentication providers:
1. Google (OpenID Connect)
2. GitHub (OAuth 2.0)

Key Features:
- Automatic endpoint discovery for Google (OIDC)
- Proper scope configuration for each provider
- Secure credential management
- Email verification support

Configuration is loaded from environment variables via settings module.
"""

import logging
from typing import Any

from authlib.integrations.base_client import OAuthError
from authlib.integrations.starlette_client import OAuth

from app.core.config import settings

# Configure logging
logger = logging.getLogger(__name__)

# Initialize OAuth handler
oauth = OAuth()

# Common OAuth configuration
OAUTH_PROVIDERS = {
    "google": {
        "name": "google",
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration",
        "client_kwargs": {
            "scope": "openid email profile",
            # Uncomment for refresh token support:
            # "prompt": "consent",
            # "access_type": "offline",
        },
        "compliance_fix": None,  # No fixes needed for Google OIDC
    },
    "github": {
        "name": "github",
        "client_id": settings.github_client_id,
        "client_secret": settings.github_client_secret,
        "api_base_url": "https://api.github.com/",
        "access_token_url": "https://github.com/login/oauth/access_token",
        "authorize_url": "https://github.com/login/oauth/authorize",
        "client_kwargs": {
            "scope": "user:email",  # Required for email verification
            # "token_endpoint_auth_method": "client_secret_post",  # Alternative auth method
        },
        "compliance_fix": None,  # No fixes needed for GitHub OAuth2
    },
}


def register_oauth_clients() -> None:
    """
    Register all OAuth clients with proper error handling.

    This function:
    1. Validates required credentials
    2. Registers each provider
    3. Handles registration errors

    Raises:
        ValueError: If required credentials are missing
        OAuthError: If client registration fails
    """
    for provider, config in OAUTH_PROVIDERS.items():
        try:
            # Validate credentials
            if not config["client_id"] or not config["client_secret"]:
                logger.error(f"Missing credentials for {provider} OAuth provider")
                raise ValueError(f"Missing {provider} OAuth credentials")

            # Register OAuth client
            oauth.register(**config)
            logger.info(f"Successfully registered {provider} OAuth client")

        except (ValueError, OAuthError) as e:
            logger.error(f"Failed to register {provider} OAuth client: {str(e)}")
            raise


def get_oauth_client(provider: str) -> Any:
    """
    Safely retrieve configured OAuth client.

    Args:
        provider: Name of the OAuth provider ("google" or "github")

    Returns:
        OAuthClient: Configured OAuth client instance

    Raises:
        ValueError: If provider is not supported
    """
    if provider not in OAUTH_PROVIDERS:
        logger.error(f"Attempted to get unsupported OAuth provider: {provider}")
        raise ValueError(f"Unsupported OAuth provider: {provider}")

    return oauth.create_client(provider)


# Register OAuth clients on module load
try:
    register_oauth_clients()
except Exception as e:
    logger.error(f"OAuth client registration failed: {str(e)}")
    # Allow application to start without OAuth
    # Individual OAuth routes will fail if accessed
