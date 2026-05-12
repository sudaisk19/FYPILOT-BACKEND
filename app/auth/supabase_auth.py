# app/auth/supabase_auth.py

"""
Authentication and Authorization System for FYPILOT Backend

This module provides the core authentication and authorization functionality:
1. JWT token validation and user authentication
2. Role-based access control (RBAC)
3. User session management
4. Security middleware

Key Components:
- get_current_user: Main authentication dependency
- get_current_active_user: Ensures user account is active
- require_roles: Role-based access control decorator
"""

import logging  # For error and security logging

# Standard library imports
from typing import Annotated  # For type hints and annotations
from uuid import UUID  # For user ID validation

# FastAPI imports
from fastapi import Depends  # For dependency injection
from fastapi import HTTPException  # For HTTP error responses
from fastapi import Request  # For request context
from fastapi import status  # HTTP status codes

# Database imports
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession  # For async database operations
from sqlalchemy.orm import selectinload  # For database queries

# Application imports
from app.auth.utils import decode_access_token  # JWT validation
from app.db import get_db  # Database session
from app.models.user import User  # User model

# Configure logging for authentication events and errors
logger = logging.getLogger(__name__)

# Configure OAuth2 password bearer scheme for JWT token extraction
# This defines how tokens are extracted from incoming requests
# - tokenUrl: Endpoint where clients can obtain tokens
# - scheme_name: Name of the auth scheme in OpenAPI docs
# - description: Human-readable description for API documentation
# Simple Bearer token scheme for JWT extraction
from fastapi.security import HTTPBearer

oauth2_scheme = HTTPBearer(
    scheme_name="Bearer", description="Bearer token authentication using JWT"
)


def _is_db_capacity_error(exc: BaseException) -> bool:
    """Pool exhaustion / Supabase session limits — must not be reported as 401."""
    text = f"{type(exc).__name__}: {exc}".lower()
    markers = (
        "emaxconn",
        "max clients",
        "too many connections",
        "could not obtain",
        "pool_timeout",
        "connection timed out",
        "timeout waiting",
    )
    return any(m in text for m in markers)


async def get_current_user(
    request: Request,
    token: Annotated[HTTPBearer, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """
    FastAPI dependency for authenticating and retrieving the current user.

    Args:
        request: FastAPI request object for context and logging
        token: JWT from Authorization header
        db: Database session

    Returns:
        User: Authenticated user model instance

    Raises:
        HTTPException(401): Invalid token or user not found
        HTTPException(503): Database pool / capacity (retry)
        HTTPException(500): Other database error
    """
    token_str = token.credentials

    try:
        claims = decode_access_token(token_str)
    except HTTPException:
        raise

    try:
        user_id = UUID(claims["sub"])
        role = claims.get("role")
    except (ValueError, KeyError) as e:
        logger.error("Invalid token payload: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token format",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        result = await db.execute(
            select(User)
            .options(
                selectinload(User.student_profile),
                selectinload(User.faculty_profile),
                selectinload(User.admin_profile),
            )
            .where(User.user_id == user_id)
            .where(User.role == role)
        )
        user = result.scalars().first()
    except SQLAlchemyError as e:
        logger.error("Database error in get_current_user: %s", e)
        if _is_db_capacity_error(e):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database temporarily unavailable; please retry shortly.",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        )
    except Exception as e:
        if _is_db_capacity_error(e):
            logger.error("DB capacity error in get_current_user: %s", e)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database temporarily unavailable; please retry shortly.",
            )
        logger.exception("Unexpected error in get_current_user")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service error",
        )

    if not user:
        logger.warning("User not found or role mismatch: %s", user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or role mismatch",
            headers={"WWW-Authenticate": "Bearer"},
        )

    request.state.user = user
    request.state.user_id = str(user_id)
    request.state.role = role

    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """
    Dependency that ensures the user is active.

    Args:
        current_user: User from get_current_user dependency

    Returns:
        User: Verified active user

    Raises:
        HTTPException(403): Inactive user account
    """
    if not getattr(current_user, "is_active", True):  # Default to active if not set
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user account"
        )
    return current_user


def require_roles(*allowed_roles: str):
    """
    Creates a dependency that checks if the user has one of the allowed roles.

    Args:
        *allowed_roles: Variable list of allowed role names

    Returns:
        Callable: Dependency function that checks user role

    Example:
        @app.get("/admin")
        async def admin_route(user: User = Depends(require_roles("admin"))):
            return {"message": "Admin only"}
    """

    async def role_checker(
        user: Annotated[User, Depends(get_current_active_user)],
    ) -> User:
        if user.role not in allowed_roles:
            logger.warning(
                f"Unauthorized role access attempt: {user.role} "
                f"tried to access {allowed_roles} protected route"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role {user.role} not authorized",
            )
        return user

    return role_checker


async def get_ws_user(token_str: str) -> User | None:
    """
    Authenticate a WebSocket connection from a raw JWT string.

    Used in WebSocket endpoints where the token is passed as a query parameter
    (since WebSockets cannot carry custom HTTP headers).

    Args:
        token_str: Raw JWT string from the `?token=` query param

    Returns:
        User if valid, None if invalid/expired
    """
    from app.db import AsyncSessionLocal

    try:
        claims = decode_access_token(token_str)
        user_id = UUID(claims["sub"])
        role = claims.get("role")
    except Exception as e:
        logger.warning(f"WebSocket auth failed (token decode): {e}")
        return None

    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(User)
                .options(
                    selectinload(User.student_profile),
                    selectinload(User.faculty_profile),
                )
                .where(User.user_id == user_id)
                .where(User.role == role)
            )
            return result.scalars().first()
    except SQLAlchemyError as e:
        logger.error(f"WebSocket auth DB error: {e}")
        return None
