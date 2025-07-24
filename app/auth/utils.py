# app/auth/utils.py

import os
from datetime import datetime, timedelta

import jwt
from fastapi import HTTPException, status
from passlib.context import CryptContext

# Load ENV and JWT settings
ENV = os.getenv("ENV", "production")
JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

# Plaintext in dev for speed, bcrypt in prod for security
pwd_context = CryptContext(
    schemes=["plaintext"] if ENV == "development" else ["bcrypt"], deprecated="auto"
)


def hash_password(pw: str) -> str:
    """Hash or passthrough password depending on ENV."""
    return pwd_context.hash(pw)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext vs. hash (works for both schemes)."""
    return pwd_context.verify(plain, hashed)


def create_access_token(sub: str, expires_delta: timedelta = timedelta(hours=1)) -> str:
    """Generate a JWT with subject `sub` and expiry."""
    payload = {"sub": sub, "exp": datetime.utcnow() + expires_delta}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> str:
    """
    Decode & validate a JWT, returning the subject (user_id).
    Raises HTTPException(401) if invalid or expired.
    """
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id: str = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload missing subject",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user_id
