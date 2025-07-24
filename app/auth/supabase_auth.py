# app/auth/supabase_auth.py

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.utils import decode_access_token
from app.db import get_db
from app.models.user import User

# Point OAuth2PasswordBearer at your new password‑flow login URL
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)
) -> User:
    """
    Dependency that:
      1. Extracts & decodes the JWT from the Authorization header
      2. Looks up the corresponding User in the database
      3. Raises 401 if anything goes wrong
      4. Returns the User model instance
    """
    # 1) Decode the token, get the user_id (subject)
    user_id = decode_access_token(token)

    # 2) Fetch the user from the database
    result = await db.execute(select(User).where(User.user_id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user
