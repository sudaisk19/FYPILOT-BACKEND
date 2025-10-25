# app/api/http/admin_profile.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.supabase_auth import get_current_user
from app.db import get_db
from app.models.admin import Admin
from app.models.user import User
from app.schemas.profile_schema import (
    AdminProfilePatchUpdate,
    AdminProfileResponse,
    AdminProfileUpdate,
    AdminProfileUpdateResponse,
)

router = APIRouter()


@router.get("/profile", response_model=AdminProfileResponse)
async def get_admin_profile(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """
    Get admin profile information.

    Returns combined user and admin data for the authenticated admin.
    Only admins can access this endpoint.
    """
    # Verify user is an admin
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. This endpoint is only for admins.",
        )

    # Fetch user with admin profile
    result = await db.execute(
        select(User)
        .options(selectinload(User.admin_profile))
        .where(User.user_id == current_user.user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # If no admin profile exists, return user data with empty admin fields
    if not user.admin_profile:
        return AdminProfileResponse(
            # User fields
            user_id=user.user_id,
            full_name=user.full_name,
            email=user.email,
            role=user.role,
            profile_avatar=user.profile_avatar,
            created_at=user.created_at,
            updated_at=user.updated_at,
            # Admin fields (empty/default values)
            phone=None,
            profile_pic=None,
        )

    # Build response with combined user and admin data
    return AdminProfileResponse(
        # User fields
        user_id=user.user_id,
        full_name=user.full_name,
        email=user.email,
        role=user.role,
        profile_avatar=user.profile_avatar,
        created_at=user.created_at,
        updated_at=user.updated_at,
        # Admin fields
        phone=user.admin_profile.phone,
        profile_pic=user.admin_profile.profile_pic,
    )


@router.post("/wizard-profile", response_model=AdminProfileUpdateResponse)
async def complete_admin_wizard_profile(
    profile_data: AdminProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Complete admin profile through wizard form.

    Creates or updates both user and admin data in a single atomic transaction.
    Only admins can access this endpoint. All fields are optional for admins.
    """
    # Verify user is an admin
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. This endpoint is only for admins.",
        )

    # Check if admin profile exists, create if it doesn't
    result = await db.execute(
        select(Admin).where(Admin.user_id == current_user.user_id)
    )
    admin_profile = result.scalar_one_or_none()

    # If no admin profile exists, create one
    if not admin_profile:
        admin_profile = Admin(user_id=current_user.user_id)
        db.add(admin_profile)
        await db.flush()  # Get the ID

    # Start transaction
    try:
        # Prepare user updates
        user_updates = {}
        if profile_data.full_name is not None:
            user_updates["full_name"] = profile_data.full_name
        if profile_data.email is not None:
            user_updates["email"] = profile_data.email
        if profile_data.profile_avatar is not None:
            user_updates["profile_avatar"] = profile_data.profile_avatar

        # Update user table if there are changes
        if user_updates:
            user_updates["updated_at"] = func.now()
            await db.execute(
                update(User)
                .where(User.user_id == current_user.user_id)
                .values(**user_updates)
            )

        # Prepare admin updates
        admin_updates = {}
        if profile_data.phone is not None:
            admin_updates["phone"] = profile_data.phone
        if profile_data.profile_pic is not None:
            admin_updates["profile_pic"] = profile_data.profile_pic

        # Update admin table if there are changes
        if admin_updates:
            await db.execute(
                update(Admin)
                .where(Admin.user_id == current_user.user_id)
                .values(**admin_updates)
            )

        # Commit transaction
        await db.commit()

        # Fetch updated data
        result = await db.execute(
            select(User)
            .options(selectinload(User.admin_profile))
            .where(User.user_id == current_user.user_id)
        )
        updated_user = result.scalar_one()

        # Return updated profile with success message
        profile_data = AdminProfileResponse(
            # User fields
            user_id=updated_user.user_id,
            full_name=updated_user.full_name,
            email=updated_user.email,
            role=updated_user.role,
            profile_avatar=updated_user.profile_avatar,
            created_at=updated_user.created_at,
            updated_at=updated_user.updated_at,
            # Admin fields
            phone=updated_user.admin_profile.phone,
            profile_pic=updated_user.admin_profile.profile_pic,
        )

        return AdminProfileUpdateResponse(
            message="Admin profile completed successfully", profile=profile_data
        )

    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to complete profile: {str(e)}",
        )


@router.patch("/profile", response_model=AdminProfileUpdateResponse)
async def update_admin_profile(
    profile_data: AdminProfilePatchUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update existing admin profile information.

    Updates both user and admin data in a single atomic transaction.
    Only admins can access this endpoint. Only updates provided fields.

    Note: All admin fields are mutable and can be updated.
    """
    # Verify user is an admin
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. This endpoint is only for admins.",
        )

    # Check if admin profile exists
    result = await db.execute(
        select(Admin).where(Admin.user_id == current_user.user_id)
    )
    admin_profile = result.scalar_one_or_none()

    if not admin_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Admin profile not found. Please complete the wizard profile first.",
        )

    # Start transaction
    try:
        # Prepare user updates - only include non-empty values
        user_updates = {}
        if profile_data.full_name is not None and profile_data.full_name.strip():
            user_updates["full_name"] = profile_data.full_name.strip()
        if profile_data.email is not None and profile_data.email.strip():
            user_updates["email"] = profile_data.email.strip()
        if (
            profile_data.profile_avatar is not None
            and profile_data.profile_avatar.strip()
        ):
            user_updates["profile_avatar"] = profile_data.profile_avatar.strip()

        # Update user table if there are changes
        if user_updates:
            user_updates["updated_at"] = func.now()
            await db.execute(
                update(User)
                .where(User.user_id == current_user.user_id)
                .values(**user_updates)
            )

        # Prepare admin updates - only include non-empty values
        admin_updates = {}
        if profile_data.phone is not None and profile_data.phone.strip():
            admin_updates["phone"] = profile_data.phone.strip()
        if profile_data.profile_pic is not None and profile_data.profile_pic.strip():
            admin_updates["profile_pic"] = profile_data.profile_pic.strip()

        # Update admin table if there are changes
        if admin_updates:
            await db.execute(
                update(Admin)
                .where(Admin.user_id == current_user.user_id)
                .values(**admin_updates)
            )

        # Commit transaction
        await db.commit()

        # Fetch updated data
        result = await db.execute(
            select(User)
            .options(selectinload(User.admin_profile))
            .where(User.user_id == current_user.user_id)
        )
        updated_user = result.scalar_one()

        # Return updated profile with success message
        profile_data = AdminProfileResponse(
            # User fields
            user_id=updated_user.user_id,
            full_name=updated_user.full_name,
            email=updated_user.email,
            role=updated_user.role,
            profile_avatar=updated_user.profile_avatar,
            created_at=updated_user.created_at,
            updated_at=updated_user.updated_at,
            # Admin fields
            phone=updated_user.admin_profile.phone,
            profile_pic=updated_user.admin_profile.profile_pic,
        )

        return AdminProfileUpdateResponse(
            message="Admin profile updated successfully", profile=profile_data
        )

    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update profile: {str(e)}",
        )
