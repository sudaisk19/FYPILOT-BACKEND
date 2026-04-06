# app/api/http/profile_status.py

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.supabase_auth import get_current_user
from app.db import get_db
from app.models.user import User

router = APIRouter(prefix="/profile", tags=["profile-status"])


@router.get("/status")
async def get_profile_completion_status(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """
    Check if user has completed their role-specific profile.

    Returns profile completion status and guidance for next steps.
    This endpoint is useful for:
    - Determining if user should see wizard form or dashboard
    - Checking profile completion status in frontend
    - Redirecting users to appropriate pages
    """

    # Eagerly load the appropriate profile based on user role
    if current_user.role == "student":
        result = await db.execute(
            select(User)
            .options(selectinload(User.student_profile))
            .where(User.user_id == current_user.user_id)
        )
        user = result.scalar_one_or_none()
        has_profile = user.student_profile is not None

        # Check if profile has any meaningful data
        profile_completed = False
        if has_profile:
            student = user.student_profile
            # Consider profile "completed" if at least roll_number and department are filled
            profile_completed = bool(student.roll_number and student.department)

    elif current_user.role == "faculty":
        result = await db.execute(
            select(User)
            .options(selectinload(User.faculty_profile))
            .where(User.user_id == current_user.user_id)
        )
        user = result.scalar_one_or_none()
        has_profile = user.faculty_profile is not None

        # Check if profile has any meaningful data
        profile_completed = False
        if has_profile:
            supervisor = user.faculty_profile
            # Consider profile "completed" if at least department and designation are filled
            profile_completed = bool(supervisor.department and supervisor.designation)

    elif current_user.role == "admin":
        result = await db.execute(
            select(User)
            .options(selectinload(User.admin_profile))
            .where(User.user_id == current_user.user_id)
        )
        user = result.scalar_one_or_none()
        has_profile = user.admin_profile is not None

        # For admins, profile is considered complete if it exists
        # (admin profiles are simpler, just phone and profile_pic)
        profile_completed = has_profile

    else:
        has_profile = False
        profile_completed = False

    # Determine next step
    if not has_profile:
        next_step = "wizard"
        message = (
            f"Please complete your {current_user.role} profile to access all features."
        )
    elif not profile_completed:
        next_step = "wizard"
        message = f"Your {current_user.role} profile is incomplete. Please fill in the required fields."
    else:
        next_step = "dashboard"
        message = f"Your {current_user.role} profile is complete. Welcome!"

    return {
        "user_id": current_user.user_id,
        "role": current_user.role,
        "has_profile": has_profile,
        "profile_completed": profile_completed,
        "next_step": next_step,
        "message": message,
        "profile_endpoint": f"/api/{current_user.role}s/profile",
    }
