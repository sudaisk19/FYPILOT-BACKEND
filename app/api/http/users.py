# app/api/http/user_me.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase_auth import get_current_user
from app.auth.utils import hash_password, verify_password
from app.db import get_db
from app.models.user import User
from app.schemas.profile_schema import ChangePasswordRequest, ChangePasswordResponse

router = APIRouter(tags=["users"])


@router.patch("/change-password", response_model=ChangePasswordResponse)
async def change_password(
    body: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Change password for any user role (student, supervisor, admin).

    This endpoint is common for all user roles and can be used from any profile page.
    If this is an OAuth-only account (e.g., password_hash == 'oauth'),
    allow setting a password without verifying current_password.
    """
    # Detect OAuth-only marker; adjust to your convention as needed
    if current_user.password_hash != "oauth":
        if not verify_password(body.current_password, current_user.password_hash):
            raise HTTPException(status_code=400, detail="Current password is incorrect")

    current_user.password_hash = hash_password(body.new_password)
    await db.commit()

    return ChangePasswordResponse(message="Password updated successfully")
