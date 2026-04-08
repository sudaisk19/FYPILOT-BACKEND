# app/auth/utils.py

"""
Authentication utility functions for the FYPILOT application.
This module handles password hashing, JWT token creation/validation,
and other security-related functionality.

Key Features:
- Password hashing using bcrypt (plaintext in development)
- JWT token generation and validation
- Role-based token payloads
- Secure error handling
"""

import os
from datetime import datetime, timedelta
from typing import Dict, Literal, Optional

import jwt
from fastapi import HTTPException, status
from passlib.context import CryptContext
from pydantic import BaseModel

# Environment and JWT Configuration
ENV = str(os.getenv("ENV", "production")).lower()
JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

# Validate JWT configuration
if not JWT_SECRET and ENV not in ("development", "dev"):
    raise ValueError("JWT_SECRET must be set in production environment")

# Role type for type safety
Role = Literal["student", "faculty", "admin"]

# Password hashing configuration
# - Development: plaintext only (easy local testing).
# - Production: bcrypt first (default for new hashes), and plaintext so legacy
#   accounts created in dev still verify after switching ENV to production.
pwd_context = CryptContext(
    schemes=["plaintext"] if ENV in ("development", "dev") else ["bcrypt", "plaintext"],
    deprecated="auto",
    bcrypt__rounds=12,
)


class TokenPayload(BaseModel):
    """Schema for JWT token payload validation."""

    sub: str  # user_id
    role: Role
    exp: datetime
    iat: datetime


def hash_password(password: str) -> str:
    """
    Hash a password using the configured hashing algorithm.

    Args:
        password (str): Plain text password to hash

    Returns:
        str: Hashed password string

    Note:
        Uses bcrypt in production, plaintext in development
    """
    if not password:
        raise ValueError("Password cannot be empty")
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its hash.

    Args:
        plain_password (str): Plain text password to verify
        hashed_password (str): Hashed password to verify against

    Returns:
        bool: True if password matches, False otherwise

    Raises:
        ValueError: If either password is empty
    """
    if not plain_password or not hashed_password:
        raise ValueError("Password and hash must not be empty")
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    sub: str, role: Role, expires_delta: Optional[timedelta] = None
) -> str:
    """
    Generate a JWT access token.

    Args:
        sub (str): Subject (user_id) for the token
        role (Role): User role (student/supervisor/admin)
        expires_delta (Optional[timedelta]): Token expiration time
            Defaults to 6 hours in dev, 1 hour in production if not specified

    Returns:
        str: Encoded JWT token

    Raises:
        ValueError: If subject or role is invalid
    """
    if not sub or not role:
        raise ValueError("Subject and role are required")

    # Default expiration: 6 hours in dev, 1 hour in production
    if expires_delta is None:
        expires_delta = (
            timedelta(hours=6) if ENV in ("development", "dev") else timedelta(hours=1)
        )

    payload = {
        "sub": str(sub),  # Ensure UUID is converted to string
        "role": role,
        "exp": datetime.utcnow() + expires_delta,
        "iat": datetime.utcnow(),
    }

    # Validate payload against schema
    TokenPayload(**payload)

    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Dict:
    """
    Decode and validate a JWT token.

    Args:
        token (str): JWT token to decode and validate

    Returns:
        Dict: Validated token payload

    Raises:
        HTTPException(401): If token is invalid, expired, or malformed
    """
    try:
        # Decode and verify the token
        payload = jwt.decode(
            token, JWT_SECRET, algorithms=[JWT_ALGORITHM], options={"verify_exp": True}
        )

        # Validate payload structure
        validated_payload = TokenPayload(**payload)

        return validated_payload.model_dump()

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )
