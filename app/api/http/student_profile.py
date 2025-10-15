# app/api/http/student_profile.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.supabase_auth import get_current_user
from app.db import get_db
from app.models.student import Student
from app.models.user import User
from app.schemas.profile_schema import (
    StudentProfileResponse,
    StudentProfileUpdate,
    StudentProfileUpdateResponse,
)

router = APIRouter()


@router.get("/profile", response_model=StudentProfileResponse)
async def get_student_profile(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """
    Get student profile information.

    Returns combined user and student data for the authenticated student.
    Only students can access this endpoint.
    """
    # Verify user is a student
    if current_user.role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. This endpoint is only for students.",
        )

    # Fetch user with student profile
    result = await db.execute(
        select(User)
        .options(selectinload(User.student_profile))
        .where(User.user_id == current_user.user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # If no student profile exists, return user data with empty student fields
    if not user.student_profile:
        return StudentProfileResponse(
            # User fields
            user_id=user.user_id,
            full_name=user.full_name,
            email=user.email,
            role=user.role,
            profile_avatar=user.profile_avatar,
            created_at=user.created_at,
            updated_at=user.updated_at,
            # Student fields (empty/default values)
            roll_number="",  # Will be empty string, not None
            department=None,
            cgpa=None,
            interests=[],
            experience=None,
            portfolio_projects=None,
            skills=[],
        )

    # Build response with combined user and student data
    return StudentProfileResponse(
        # User fields
        user_id=user.user_id,
        full_name=user.full_name,
        email=user.email,
        role=user.role,
        profile_avatar=user.profile_avatar,
        created_at=user.created_at,
        updated_at=user.updated_at,
        # Student fields
        roll_number=user.student_profile.roll_number or "",
        department=user.student_profile.department,
        cgpa=user.student_profile.cgpa,
        interests=user.student_profile.interests or [],
        experience=user.student_profile.experience,
        portfolio_projects=user.student_profile.portfolio_projects,
        skills=user.student_profile.skills or [],
    )


@router.patch("/profile", response_model=StudentProfileUpdateResponse)
async def update_student_profile(
    profile_data: StudentProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update student profile information.

    Updates both user and student data in a single atomic transaction.
    Only students can access this endpoint.
    """
    # Verify user is a student
    if current_user.role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. This endpoint is only for students.",
        )

    # Check if student profile exists, create if it doesn't
    result = await db.execute(
        select(Student).where(Student.user_id == current_user.user_id)
    )
    student_profile = result.scalar_one_or_none()

    # If no student profile exists, create one
    if not student_profile:
        student_profile = Student(user_id=current_user.user_id)
        db.add(student_profile)
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
            user_updates["updated_at"] = db.func.now()
            await db.execute(
                update(User)
                .where(User.user_id == current_user.user_id)
                .values(**user_updates)
            )

        # Prepare student updates
        student_updates = {}
        if profile_data.roll_number is not None:
            student_updates["roll_number"] = profile_data.roll_number
        if profile_data.department is not None:
            student_updates["department"] = profile_data.department
        if profile_data.cgpa is not None:
            student_updates["cgpa"] = profile_data.cgpa
        if profile_data.interests is not None:
            student_updates["interests"] = profile_data.interests
        if profile_data.experience is not None:
            student_updates["experience"] = profile_data.experience
        if profile_data.portfolio_projects is not None:
            student_updates["portfolio_projects"] = profile_data.portfolio_projects
        if profile_data.skills is not None:
            student_updates["skills"] = profile_data.skills

        # Update student table if there are changes
        if student_updates:
            await db.execute(
                update(Student)
                .where(Student.user_id == current_user.user_id)
                .values(**student_updates)
            )

        # Commit transaction
        await db.commit()

        # Fetch updated data
        result = await db.execute(
            select(User)
            .options(selectinload(User.student_profile))
            .where(User.user_id == current_user.user_id)
        )
        updated_user = result.scalar_one()

        # Return updated profile with success message
        profile_data = StudentProfileResponse(
            # User fields
            user_id=updated_user.user_id,
            full_name=updated_user.full_name,
            email=updated_user.email,
            role=updated_user.role,
            profile_avatar=updated_user.profile_avatar,
            created_at=updated_user.created_at,
            updated_at=updated_user.updated_at,
            # Student fields
            roll_number=updated_user.student_profile.roll_number,
            department=updated_user.student_profile.department,
            cgpa=updated_user.student_profile.cgpa,
            interests=updated_user.student_profile.interests or [],
            experience=updated_user.student_profile.experience,
            portfolio_projects=updated_user.student_profile.portfolio_projects,
            skills=updated_user.student_profile.skills or [],
        )

        return StudentProfileUpdateResponse(
            message="Student profile updated successfully", profile=profile_data
        )

    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update profile: {str(e)}",
        )
