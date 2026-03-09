# app/api/http/student_profile.py

from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.supabase_auth import get_current_user
from app.db import get_db
from app.models.group import Group, GroupMember
from app.models.student import Student
from app.models.user import User
from app.schemas.profile_schema import (
    GroupInfo,
    GroupMemberInfo,
    StudentProfilePatchUpdate,
    StudentProfileResponse,
    StudentProfileUpdate,
    StudentProfileUpdateResponse,
)

router = APIRouter()


def normalize_skills_levels(
    skills: Optional[List[str]], skills_levels: Optional[Dict[str, int]]
) -> Dict[str, int]:
    """
    Normalize skills_levels to ensure all skills have a level.
    If a skill is in the skills list but not in skills_levels, default to level 1.

    Args:
        skills: List of skill names
        skills_levels: Dictionary mapping skill names to levels (1-5)

    Returns:
        Normalized dictionary with all skills having a level (default 1 if not specified)
    """
    if not skills:
        return skills_levels or {}

    normalized = skills_levels.copy() if skills_levels else {}

    # Ensure all skills have a level (default to 1 if not specified)
    for skill in skills:
        if skill not in normalized:
            normalized[skill] = 1

    return normalized


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

    # Fetch user with student profile and group information
    result = await db.execute(
        select(User)
        .options(
            selectinload(User.student_profile)
            .selectinload(Student.groups)
            .selectinload(Group.project)
        )
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
            skills_levels={},
            # Group information (None since no student profile)
            group=None,
        )

    # Get group information if student is in a group
    group_info = None
    if user.student_profile.groups:
        # Get the first group (assuming student can only be in one group)
        group = user.student_profile.groups[0]

        # Get group members with their details
        members_result = await db.execute(
            select(User, Student)
            .join(Student, User.user_id == Student.user_id)
            .join(GroupMember, Student.user_id == GroupMember.student_id)
            .where(GroupMember.group_id == group.group_id)
        )
        members_data = members_result.all()

        # Build member info list
        members = []
        for member_user, member_student in members_data:
            members.append(
                GroupMemberInfo(
                    user_id=member_user.user_id,
                    full_name=member_user.full_name,
                    email=member_user.email,
                    roll_number=member_student.roll_number,
                )
            )

        # Get supervisor information
        supervisor_name = None
        cosupervisor_name = None

        if group.supervisor_id:
            supervisor_result = await db.execute(
                select(User).where(User.user_id == group.supervisor_id)
            )
            supervisor_user = supervisor_result.scalar_one_or_none()
            if supervisor_user:
                supervisor_name = supervisor_user.full_name

        if group.cosupervisor_id:
            cosupervisor_result = await db.execute(
                select(User).where(User.user_id == group.cosupervisor_id)
            )
            cosupervisor_user = cosupervisor_result.scalar_one_or_none()
            if cosupervisor_user:
                cosupervisor_name = cosupervisor_user.full_name

        # Build group info
        group_info = GroupInfo(
            group_id=group.group_id,
            project_name=(group.project.name if group.project else "Unknown Project"),
            fyp_stage=(
                group.fyp_stage.value
                if hasattr(group.fyp_stage, "value")
                else str(group.fyp_stage)
            ),
            fyp_cycle=(
                group.fyp_cycle.value
                if hasattr(group.fyp_cycle, "value")
                else str(group.fyp_cycle)
            ),
            cohort_year=group.cohort_year,
            max_members=group.max_members,
            supervisor_name=supervisor_name,
            cosupervisor_name=cosupervisor_name,
            members=members,
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
        skills_levels=user.student_profile.skills_levels_normalized,
        # Group information
        group=group_info,
    )


@router.post("/wizard-profile", response_model=StudentProfileUpdateResponse)
async def complete_student_wizard_profile(
    profile_data: StudentProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Complete student profile through wizard form.

    Creates or updates both user and student data in a single atomic transaction.
    Only students can access this endpoint. Required fields must be provided.
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

        # Prepare student updates - only include non-empty values
        student_updates = {}
        if profile_data.roll_number is not None and profile_data.roll_number.strip():
            student_updates["roll_number"] = profile_data.roll_number.strip()
        if profile_data.cgpa is not None:
            student_updates["cgpa"] = profile_data.cgpa
        if profile_data.interests is not None and profile_data.interests:
            student_updates["interests"] = profile_data.interests
        if profile_data.experience is not None and profile_data.experience.strip():
            student_updates["experience"] = profile_data.experience.strip()
        if (
            profile_data.portfolio_projects is not None
            and profile_data.portfolio_projects
        ):
            student_updates["portfolio_projects"] = profile_data.portfolio_projects
        if profile_data.skills is not None and profile_data.skills:
            student_updates["skills"] = profile_data.skills

        # Handle skills_levels - normalize to ensure all skills have a level
        if profile_data.skills is not None or profile_data.skills_levels is not None:
            # Get current skills if updating, or use provided skills
            current_skills = (
                profile_data.skills
                if profile_data.skills is not None
                else (student_profile.skills if student_profile else [])
            )
            # Normalize skills_levels to include all skills with default level 1
            normalized_levels = normalize_skills_levels(
                current_skills, profile_data.skills_levels
            )
            student_updates["skills_levels"] = normalized_levels

        # If no student profile exists, create one with the required data
        if not student_profile:
            # Validate that roll_number is provided for new profiles
            if not profile_data.roll_number or not profile_data.roll_number.strip():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Roll number is required for creating a student profile.",
                )

            # Create new student profile with all provided data
            student_profile = Student(user_id=current_user.user_id, **student_updates)
            # Normalize skills_levels before saving to ensure all skills have default level 1
            student_profile.normalize_skills_levels_for_save()
            db.add(student_profile)
        else:
            # Update existing student profile if there are changes
            if student_updates:
                # Ensure skills_levels is normalized before updating
                if "skills" in student_updates or "skills_levels" in student_updates:
                    # Create temporary object to normalize
                    temp_student = Student()
                    temp_student.skills = student_updates.get(
                        "skills", student_profile.skills
                    )
                    temp_student.skills_levels = student_updates.get(
                        "skills_levels", student_profile.skills_levels
                    )
                    temp_student.normalize_skills_levels_for_save()
                    student_updates["skills_levels"] = temp_student.skills_levels

                await db.execute(
                    update(Student)
                    .where(Student.user_id == current_user.user_id)
                    .values(**student_updates)
                )

        # Commit transaction
        await db.commit()

        # Refresh the student_profile object to get the committed data
        if not student_profile:
            # Fetch the newly created profile
            result = await db.execute(
                select(Student).where(Student.user_id == current_user.user_id)
            )
            student_profile = result.scalar_one_or_none()

        if not student_profile:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Student profile was not created properly. Please try again.",
            )

        # Refresh to get latest user data
        await db.refresh(current_user)

        # Use current_user and student_profile to build response
        updated_user = current_user

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
            # Student fields (use the student_profile object directly)
            roll_number=student_profile.roll_number,
            department=student_profile.department,
            cgpa=student_profile.cgpa,
            interests=student_profile.interests or [],
            experience=student_profile.experience,
            portfolio_projects=student_profile.portfolio_projects,
            skills=student_profile.skills or [],
            skills_levels=student_profile.skills_levels or {},
            # Group information (will be None for new profiles)
            group=None,
        )

        return StudentProfileUpdateResponse(
            message="Student profile completed successfully", profile=profile_data
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


@router.patch("/profile", response_model=StudentProfileUpdateResponse)
async def update_student_profile(
    profile_data: StudentProfilePatchUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update existing student profile information.

    Updates both user and student data in a single atomic transaction.
    Only students can access this endpoint. Only updates provided fields.

    Note: roll_number cannot be updated via this endpoint as it's immutable.
    """
    # Verify user is a student
    if current_user.role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. This endpoint is only for students.",
        )

    # Check if student profile exists
    result = await db.execute(
        select(Student).where(Student.user_id == current_user.user_id)
    )
    student_profile = result.scalar_one_or_none()

    if not student_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student profile not found. Please complete the wizard profile first.",
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

        # Prepare student updates - only include non-empty values (excluding required fields)
        student_updates = {}
        # Note: roll_number is required and should not be updated via PATCH
        if profile_data.cgpa is not None:
            student_updates["cgpa"] = profile_data.cgpa
        if profile_data.interests is not None and profile_data.interests:
            student_updates["interests"] = profile_data.interests
        if profile_data.experience is not None and profile_data.experience.strip():
            student_updates["experience"] = profile_data.experience.strip()
        if (
            profile_data.portfolio_projects is not None
            and profile_data.portfolio_projects
        ):
            student_updates["portfolio_projects"] = profile_data.portfolio_projects
        if profile_data.skills is not None and profile_data.skills:
            student_updates["skills"] = profile_data.skills

        # Handle skills_levels - normalize to ensure all skills have a level
        if profile_data.skills is not None or profile_data.skills_levels is not None:
            # Get current skills if updating, or use existing skills
            current_skills = (
                profile_data.skills
                if profile_data.skills is not None
                else student_profile.skills
            )
            # If skills_levels is provided, use it; otherwise keep existing or normalize
            if profile_data.skills_levels is not None:
                normalized_levels = normalize_skills_levels(
                    current_skills, profile_data.skills_levels
                )
            else:
                # If only skills are updated, normalize existing skills_levels with new skills
                normalized_levels = normalize_skills_levels(
                    current_skills, student_profile.skills_levels
                )
            student_updates["skills_levels"] = normalized_levels

        # Update student table if there are changes
        if student_updates:
            # Ensure skills_levels is normalized before updating
            if "skills" in student_updates or "skills_levels" in student_updates:
                # Create temporary object to normalize
                temp_student = Student()
                temp_student.skills = student_updates.get(
                    "skills", student_profile.skills
                )
                temp_student.skills_levels = student_updates.get(
                    "skills_levels", student_profile.skills_levels
                )
                temp_student.normalize_skills_levels_for_save()
                student_updates["skills_levels"] = temp_student.skills_levels

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
            skills_levels=updated_user.student_profile.skills_levels_normalized,
            # Group information (will be None if not in a group)
            group=None,
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
