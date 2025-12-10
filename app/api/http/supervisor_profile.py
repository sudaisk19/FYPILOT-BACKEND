# app/api/http/supervisor_profile.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.supabase_auth import get_current_user
from app.db import get_db
from app.models.domain import Domain
from app.models.industry import Industry
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

    # Fetch user with supervisor profile, domains, and industries
    result = await db.execute(
        select(User)
        .options(
            selectinload(User.supervisor_profile).selectinload(Supervisor.domains),
            selectinload(User.supervisor_profile).selectinload(Supervisor.industries),
        )
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
            project_type=None,
            capacity_max=8,  # Default value
            capacity_filled=0,
            domains=[],
            industries=[],
        )

    # Extract domain and industry details (ID and name)
    domain_details = [
        {"domain_id": domain.domain_id, "name": domain.name}
        for domain in user.supervisor_profile.domains
    ]
    industry_details = [
        {"industry_id": industry.industry_id, "name": industry.name}
        for industry in user.supervisor_profile.industries
    ]

    # Get project type (single value)
    project_type = None
    if user.supervisor_profile.project_type:
        project_type = user.supervisor_profile.project_type

    # Build response with combined user and supervisor data
    return SupervisorProfileResponse(
        user_id=user.user_id,
        full_name=user.full_name,
        email=user.email,
        role=user.role,
        profile_avatar=user.profile_avatar,
        created_at=user.created_at,
        updated_at=user.updated_at,
        department=user.supervisor_profile.department,
        designation=user.supervisor_profile.designation,
        office=user.supervisor_profile.office,
        requirements=user.supervisor_profile.requirements or [],
        project_type=project_type,
        capacity_max=user.supervisor_profile.capacity_max,
        capacity_filled=user.supervisor_profile.capacity_filled,
        domains=domain_details,
        industries=industry_details,
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
        if profile_data.project_type is not None:
            supervisor_updates["project_type"] = profile_data.project_type
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

        # Fetch updated user and supervisor profile with domains and industries
        result = await db.execute(
            select(User)
            .options(
                selectinload(User.supervisor_profile).selectinload(Supervisor.domains),
                selectinload(User.supervisor_profile).selectinload(
                    Supervisor.industries
                ),
            )
            .where(User.user_id == current_user.user_id)
        )
        updated_user = result.scalar_one()

        # Extract domain and industry details (ID and name)
        domain_details = []
        industry_details = []
        if updated_user.supervisor_profile:
            domain_details = [
                {"domain_id": domain.domain_id, "name": domain.name}
                for domain in updated_user.supervisor_profile.domains
            ]
            industry_details = [
                {"industry_id": industry.industry_id, "name": industry.name}
                for industry in updated_user.supervisor_profile.industries
            ]

        # Get project type (single value)
        project_type = None
        if (
            updated_user.supervisor_profile
            and updated_user.supervisor_profile.project_type
        ):
            project_type = updated_user.supervisor_profile.project_type

        # Build response
        profile_data = SupervisorProfileResponse(
            user_id=updated_user.user_id,
            full_name=updated_user.full_name,
            email=updated_user.email,
            role=updated_user.role,
            profile_avatar=updated_user.profile_avatar,
            created_at=updated_user.created_at,
            updated_at=updated_user.updated_at,
            department=(
                updated_user.supervisor_profile.department
                if updated_user.supervisor_profile
                else None
            ),
            designation=(
                updated_user.supervisor_profile.designation
                if updated_user.supervisor_profile
                else None
            ),
            office=(
                updated_user.supervisor_profile.office
                if updated_user.supervisor_profile
                else None
            ),
            requirements=updated_user.supervisor_profile.requirements or [],
            project_type=project_type,
            capacity_max=(
                updated_user.supervisor_profile.capacity_max
                if updated_user.supervisor_profile
                else 8
            ),
            capacity_filled=(
                updated_user.supervisor_profile.capacity_filled
                if updated_user.supervisor_profile
                else 0
            ),
            domains=domain_details,
            industries=industry_details,
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

    Updates user, supervisor data, domains, industries, project type, and capacity in a single atomic transaction.
    Only supervisors can access this endpoint. Only updates provided fields.

    Fields that can be updated:
    - User fields: full_name, email, profile_avatar
    - Supervisor fields: department, designation, office, requirements
    - Preferences: project_type, domains, industries, capacity_max

    Note: capacity_filled is read-only and automatically managed.
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
        # Handle profile_avatar: allow explicit null to clear avatar
        if "profile_avatar" in profile_data.__fields_set__:
            if (
                profile_data.profile_avatar is not None
                and profile_data.profile_avatar.strip()
            ):
                user_updates["profile_avatar"] = profile_data.profile_avatar.strip()
            else:
                # Explicitly set to None to clear avatar
                user_updates["profile_avatar"] = None

        # Update user table if there are changes
        if user_updates:
            user_updates["updated_at"] = func.now()
            await db.execute(
                update(User)
                .where(User.user_id == current_user.user_id)
                .values(**user_updates)
            )

        # Prepare supervisor updates - only include non-empty values
        supervisor_updates = {}

        if profile_data.department is not None and profile_data.department.strip():
            supervisor_updates["department"] = profile_data.department.strip()
        if profile_data.designation is not None and profile_data.designation.strip():
            supervisor_updates["designation"] = profile_data.designation.strip()
        if profile_data.office is not None and profile_data.office.strip():
            supervisor_updates["office"] = profile_data.office.strip()
        if profile_data.requirements is not None and profile_data.requirements:
            supervisor_updates["requirements"] = profile_data.requirements
        if profile_data.capacity_max is not None:
            supervisor_updates["capacity_max"] = profile_data.capacity_max

        # Fetch domains and industries FIRST (before any modifications)
        domains_to_add = []
        if profile_data.domains:
            domain_result = await db.execute(
                select(Domain).where(Domain.domain_id.in_(profile_data.domains))
            )
            domains_to_add = domain_result.scalars().all()

        industries_to_add = []
        if profile_data.industries:
            industry_result = await db.execute(
                select(Industry).where(
                    Industry.industry_id.in_(profile_data.industries)
                )
            )
            industries_to_add = industry_result.scalars().all()

        # Fetch supervisor WITH eager-loaded relationships (like in group profile)
        supervisor_result = await db.execute(
            select(Supervisor)
            .options(
                selectinload(Supervisor.domains),
                selectinload(Supervisor.industries),
            )
            .where(Supervisor.user_id == current_user.user_id)
        )
        supervisor = supervisor_result.scalar_one()

        # Apply supervisor attribute updates
        for key, value in supervisor_updates.items():
            setattr(supervisor, key, value)

        # Handle project_type update
        if profile_data.project_type is not None:
            supervisor.project_type = profile_data.project_type

        # Handle domains update
        if profile_data.domains is not None:
            supervisor.domains.clear()
            supervisor.domains.extend(domains_to_add)

        # Handle industries update
        if profile_data.industries is not None:
            supervisor.industries.clear()
            supervisor.industries.extend(industries_to_add)

        # Commit all changes together
        await db.commit()

        # Fetch updated user and supervisor profile with domains and industries
        result = await db.execute(
            select(User)
            .options(
                selectinload(User.supervisor_profile).selectinload(Supervisor.domains),
                selectinload(User.supervisor_profile).selectinload(
                    Supervisor.industries
                ),
            )
            .where(User.user_id == current_user.user_id)
        )
        updated_user = result.scalar_one()

        # Extract domain and industry details (ID and name)
        domain_details = []
        industry_details = []
        if updated_user.supervisor_profile:
            domain_details = [
                {"domain_id": domain.domain_id, "name": domain.name}
                for domain in updated_user.supervisor_profile.domains
            ]
            industry_details = [
                {"industry_id": industry.industry_id, "name": industry.name}
                for industry in updated_user.supervisor_profile.industries
            ]

        # Get project type (single value)
        project_type = None
        if (
            updated_user.supervisor_profile
            and updated_user.supervisor_profile.project_type
        ):
            project_type = updated_user.supervisor_profile.project_type

        # Build response
        profile_data = SupervisorProfileResponse(
            user_id=updated_user.user_id,
            full_name=updated_user.full_name,
            email=updated_user.email,
            role=updated_user.role,
            profile_avatar=updated_user.profile_avatar,
            created_at=updated_user.created_at,
            updated_at=updated_user.updated_at,
            department=(
                updated_user.supervisor_profile.department
                if updated_user.supervisor_profile
                else None
            ),
            designation=(
                updated_user.supervisor_profile.designation
                if updated_user.supervisor_profile
                else None
            ),
            office=(
                updated_user.supervisor_profile.office
                if updated_user.supervisor_profile
                else None
            ),
            requirements=updated_user.supervisor_profile.requirements or [],
            project_type=project_type,
            capacity_max=(
                updated_user.supervisor_profile.capacity_max
                if updated_user.supervisor_profile
                else 8
            ),
            capacity_filled=(
                updated_user.supervisor_profile.capacity_filled
                if updated_user.supervisor_profile
                else 0
            ),
            domains=domain_details,
            industries=industry_details,
        )

        return SupervisorProfileUpdateResponse(
            message="Supervisor profile updated successfully", profile=profile_data
        )

    except Exception as e:
        await db.rollback()
        import traceback

        error_detail = f"Failed to update profile: {str(e)}\n{traceback.format_exc()}"
        print(error_detail)  # Log to console for debugging
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update profile: {str(e)}",
        )
