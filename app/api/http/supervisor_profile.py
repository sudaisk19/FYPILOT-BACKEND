# app/api/http/supervisor_profile.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.supabase_auth import get_current_user
from app.db import get_db
from app.models.supervisor import Supervisor
from app.models.user import User
from app.schemas.profile_schema import (
    SupervisorProfilePatchUpdate,
    SupervisorProfileResponse,
    SupervisorProfileUpdate,
    SupervisorProfileUpdateResponse,
)

router = APIRouter()


@router.get("/profile", response_model=SupervisorProfileResponse)
async def get_supervisor_profile(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """
    Get supervisor profile information.

    Returns combined user and supervisor data for the authenticated supervisor.
    Only supervisors can access this endpoint.
    """
    # Verify user is a supervisor
    if current_user.role != "supervisor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. This endpoint is only for supervisors.",
        )

    # Fetch user with supervisor profile
    result = await db.execute(
        select(User)
        .options(selectinload(User.supervisor_profile))
        .where(User.user_id == current_user.user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # If no supervisor profile exists, return user data with empty supervisor fields
    if not user.supervisor_profile:
        return SupervisorProfileResponse(
            # User fields
            user_id=user.user_id,
            full_name=user.full_name,
            email=user.email,
            role=user.role,
            profile_avatar=user.profile_avatar,
            created_at=user.created_at,
            updated_at=user.updated_at,
            # Supervisor fields (empty/default values)
            department=None,
            designation=None,
            office=None,
            requirements=[],
            project_types=[],
            capacity_max=8,  # Default value
            capacity_filled=0,
        )

    # Build response with combined user and supervisor data
    return SupervisorProfileResponse(
        # User fields
        user_id=user.user_id,
        full_name=user.full_name,
        email=user.email,
        role=user.role,
        profile_avatar=user.profile_avatar,
        created_at=user.created_at,
        updated_at=user.updated_at,
        # Supervisor fields
        department=user.supervisor_profile.department,
        designation=user.supervisor_profile.designation,
        office=user.supervisor_profile.office,
        requirements=user.supervisor_profile.requirements or [],
        project_types=user.supervisor_profile.project_types or [],
        capacity_max=user.supervisor_profile.capacity_max,
        capacity_filled=user.supervisor_profile.capacity_filled,
    )


@router.post("/wizard-profile", response_model=SupervisorProfileUpdateResponse)
async def complete_supervisor_wizard_profile(
    profile_data: SupervisorProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Complete supervisor profile through wizard form.

    Creates or updates both user and supervisor data in a single atomic transaction.
    Only supervisors can access this endpoint. Required fields must be provided.
    """
    # Verify user is a supervisor
    if current_user.role != "supervisor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. This endpoint is only for supervisors.",
        )

    # Check if supervisor profile exists, create if it doesn't
    result = await db.execute(
        select(Supervisor).where(Supervisor.user_id == current_user.user_id)
    )
    supervisor_profile = result.scalar_one_or_none()

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

        # Prepare supervisor updates
        supervisor_updates = {}
        if profile_data.department is not None:
            supervisor_updates["department"] = profile_data.department
        if profile_data.designation is not None:
            supervisor_updates["designation"] = profile_data.designation
        if profile_data.office is not None:
            supervisor_updates["office"] = profile_data.office
        if profile_data.requirements is not None:
            supervisor_updates["requirements"] = profile_data.requirements
        if profile_data.project_types is not None:
            supervisor_updates["project_types"] = profile_data.project_types
        if profile_data.capacity_max is not None:
            supervisor_updates["capacity_max"] = profile_data.capacity_max

        # If no supervisor profile exists, create one with the provided data
        if not supervisor_profile:
            # Create new supervisor profile with all provided data
            supervisor_profile = Supervisor(
                user_id=current_user.user_id, **supervisor_updates
            )
            db.add(supervisor_profile)
        else:
            # Update existing supervisor profile if there are changes
            if supervisor_updates:
                await db.execute(
                    update(Supervisor)
                    .where(Supervisor.user_id == current_user.user_id)
                    .values(**supervisor_updates)
                )

        # Commit transaction
        await db.commit()

        # Refresh the supervisor_profile object to get the committed data
        if not supervisor_profile:
            # Fetch the newly created profile
            result = await db.execute(
                select(Supervisor).where(Supervisor.user_id == current_user.user_id)
            )
            supervisor_profile = result.scalar_one_or_none()

        if not supervisor_profile:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Supervisor profile was not created properly. Please try again.",
            )

        # Refresh to get latest user data
        await db.refresh(current_user)

        # Use current_user and supervisor_profile to build response
        updated_user = current_user

        # Return updated profile with success message
        profile_data = SupervisorProfileResponse(
            # User fields
            user_id=updated_user.user_id,
            full_name=updated_user.full_name,
            email=updated_user.email,
            role=updated_user.role,
            profile_avatar=updated_user.profile_avatar,
            created_at=updated_user.created_at,
            updated_at=updated_user.updated_at,
            # Supervisor fields (use the supervisor_profile object directly)
            department=supervisor_profile.department,
            designation=supervisor_profile.designation,
            office=supervisor_profile.office,
            requirements=supervisor_profile.requirements or [],
            project_types=supervisor_profile.project_types or [],
            capacity_max=supervisor_profile.capacity_max,
            capacity_filled=supervisor_profile.capacity_filled,
        )

        return SupervisorProfileUpdateResponse(
            message="Supervisor profile completed successfully", profile=profile_data
        )

    except Exception as e:
        await db.rollback()
        import traceback

        error_detail = f"Failed to complete profile: {str(e)}\n{traceback.format_exc()}"
        print(error_detail)  # Log to console for debugging
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to complete profile: {str(e)}",
        )


@router.patch("/profile", response_model=SupervisorProfileUpdateResponse)
async def update_supervisor_profile(
    profile_data: SupervisorProfilePatchUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update existing supervisor profile information.

    Updates both user and supervisor data in a single atomic transaction.
    Only supervisors can access this endpoint. Only updates provided fields.

    Note: project_types, capacity_max, and capacity_filled cannot be updated via this endpoint as they are immutable.
    """
    # Verify user is a supervisor
    if current_user.role != "supervisor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. This endpoint is only for supervisors.",
        )

    # Check if supervisor profile exists
    result = await db.execute(
        select(Supervisor).where(Supervisor.user_id == current_user.user_id)
    )
    supervisor_profile = result.scalar_one_or_none()

    if not supervisor_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supervisor profile not found. Please complete the wizard profile first.",
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

        # Prepare supervisor updates - only include non-empty values (excluding required fields)
        supervisor_updates = {}
        # Note: project_types, capacity_max, capacity_filled are required and should not be updated via PATCH
        if profile_data.department is not None and profile_data.department.strip():
            supervisor_updates["department"] = profile_data.department.strip()
        if profile_data.designation is not None and profile_data.designation.strip():
            supervisor_updates["designation"] = profile_data.designation.strip()
        if profile_data.office is not None and profile_data.office.strip():
            supervisor_updates["office"] = profile_data.office.strip()
        if profile_data.requirements is not None and profile_data.requirements:
            supervisor_updates["requirements"] = profile_data.requirements

        # Update supervisor table if there are changes
        if supervisor_updates:
            await db.execute(
                update(Supervisor)
                .where(Supervisor.user_id == current_user.user_id)
                .values(**supervisor_updates)
            )

        # Commit transaction
        await db.commit()

        # Fetch updated data
        result = await db.execute(
            select(User)
            .options(selectinload(User.supervisor_profile))
            .where(User.user_id == current_user.user_id)
        )
        updated_user = result.scalar_one()

        # Return updated profile with success message
        profile_data = SupervisorProfileResponse(
            # User fields
            user_id=updated_user.user_id,
            full_name=updated_user.full_name,
            email=updated_user.email,
            role=updated_user.role,
            profile_avatar=updated_user.profile_avatar,
            created_at=updated_user.created_at,
            updated_at=updated_user.updated_at,
            # Supervisor fields
            department=updated_user.supervisor_profile.department,
            designation=updated_user.supervisor_profile.designation,
            office=updated_user.supervisor_profile.office,
            requirements=updated_user.supervisor_profile.requirements or [],
            project_types=updated_user.supervisor_profile.project_types or [],
            capacity_max=updated_user.supervisor_profile.capacity_max,
            capacity_filled=updated_user.supervisor_profile.capacity_filled,
        )

        return SupervisorProfileUpdateResponse(
            message="Supervisor profile updated successfully", profile=profile_data
        )

    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update profile: {str(e)}",
        )
