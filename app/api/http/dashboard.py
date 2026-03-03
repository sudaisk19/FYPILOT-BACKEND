# app/api/http/dashboard.py

"""
Dashboard API Module

This module provides role-specific dashboard endpoints that return:
1. User profile summary
2. Role-specific data (groups, projects, etc.)
3. Dashboard statistics

Endpoints:
- GET /api/dashboard - Returns role-specific dashboard data
"""

import logging
from typing import Union

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase_auth import get_current_user

# Application imports
from app.db import get_db
from app.models.group import Group
from app.models.student import Student
from app.models.supervisor import Supervisor
from app.models.user import User

# Schema imports
from app.schemas.dashboard_schema import (
    AdminDashboardResponse,
    AdminProfileSummary,
    DashboardStats,
    GroupInfo,
)
from app.schemas.dashboard_schema import GroupMember as GroupMemberSchema
from app.schemas.dashboard_schema import (
    StudentDashboardResponse,
    StudentProfileSummary,
    SupervisorDashboardResponse,
    SupervisorProfileSummary,
)

# Configure logging
logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter(tags=["dashboard"])


async def get_student_dashboard_data(
    user: User, db: AsyncSession
) -> StudentDashboardResponse:
    """Get dashboard data for student users"""
    try:
        # Get student profile
        student_profile = user.student_profile
        if not student_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Student profile not found",
            )

        # Get groups the student is enrolled in
        groups_query = (
            select(Group)
            .options(selectinload(Group.project))
            .join(Group.students)
            .where(Student.user_id == user.user_id)
        )
        groups_result = await db.execute(groups_query)
        groups = groups_result.scalars().all()

        # Format group information
        group_info_list = []
        for group in groups:
            group_info = GroupInfo(
                group_id=group.group_id,
                project_name=group.project.name if group.project else "Unknown Project",
                project_title=getattr(group, "project_title", None),
                status=group.fyp_stage,
                created_at=group.created_at.isoformat(),
                updated_at=getattr(group, "updated_at", group.created_at).isoformat(),
                role="member",  # Students are members of groups
            )
            group_info_list.append(group_info)

        # Calculate statistics
        stats = DashboardStats(
            total_groups=len(group_info_list),
            active_groups=len([g for g in group_info_list if g.status == "active"]),
            pending_tasks=0,  # TODO: Implement task counting
        )

        # Create student profile summary
        student_summary = StudentProfileSummary(
            student_id=student_profile.user_id,
            department=student_profile.department,
            year=getattr(student_profile, "year", None),
            enrollment_date=user.created_at.isoformat(),
            cgpa=getattr(student_profile, "cgpa", None),
            status="active",  # Default status since it's not in the model
        )

        return StudentDashboardResponse(
            student_profile=student_summary, groups=group_info_list, stats=stats
        )

    except Exception as e:
        logger.error(f"Error getting student dashboard data: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get student dashboard data",
        )


async def get_supervisor_dashboard_data(
    user: User, db: AsyncSession
) -> SupervisorDashboardResponse:
    """Get dashboard data for supervisor users"""
    try:
        # Get supervisor profile
        supervisor_profile = user.supervisor_profile
        if not supervisor_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Supervisor profile not found",
            )

        # Get groups managed by the supervisor
        groups_query = (
            select(Group)
            .options(selectinload(Group.project))
            .where(Group.supervisor_id == user.user_id)
        )
        groups_result = await db.execute(groups_query)
        groups = groups_result.scalars().all()

        # Format group information with member details
        group_info_list = []
        for group in groups:
            # Get group members
            members_query = (
                select(Student)
                .join(Group.students)
                .where(Group.group_id == group.group_id)
            )
            members_result = await db.execute(members_query)
            members = members_result.scalars().all()

            # Format members
            member_list = []
            for member in members:
                member_info = GroupMemberSchema(
                    user_id=member.user_id,
                    full_name=member.user.full_name,
                    email=member.user.email,
                    role="student",
                )
                member_list.append(member_info)

            group_info = GroupInfo(
                group_id=group.group_id,
                project_name=group.project.name if group.project else "Unknown Project",
                project_title=getattr(group, "project_title", None),
                status=group.fyp_stage,
                created_at=group.created_at.isoformat(),
                updated_at=getattr(group, "updated_at", group.created_at).isoformat(),
                members_count=len(member_list),
                members=member_list,
            )
            group_info_list.append(group_info)

        # Calculate statistics
        total_students = sum(len(g.members) for g in group_info_list)
        stats = DashboardStats(
            total_groups=len(group_info_list),
            active_groups=len([g for g in group_info_list if g.status == "active"]),
            total_students=total_students,
        )

        # Create supervisor profile summary
        supervisor_summary = SupervisorProfileSummary(
            supervisor_id=supervisor_profile.user_id,
            department=supervisor_profile.department,
            expertise=getattr(supervisor_profile, "expertise", []),
            max_groups=supervisor_profile.capacity_max,
            current_groups=len(group_info_list),
            status="active",  # Default status since it's not in the model
        )

        return SupervisorDashboardResponse(
            supervisor_profile=supervisor_summary,
            managed_groups=group_info_list,
            stats=stats,
        )

    except Exception as e:
        logger.error(f"Error getting supervisor dashboard data: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get supervisor dashboard data",
        )


async def get_admin_dashboard_data(
    user: User, db: AsyncSession
) -> AdminDashboardResponse:
    """Get dashboard data for admin users"""
    try:
        # Get admin profile
        admin_profile = user.admin_profile
        if not admin_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Admin profile not found"
            )

        # Get overall statistics
        total_students = await db.scalar(select(func.count(Student.user_id)))
        await db.scalar(select(func.count(Supervisor.user_id)))
        total_groups = await db.scalar(select(func.count(Group.group_id)))
        active_groups = await db.scalar(
            select(func.count(Group.group_id)).where(
                Group.fyp_stage == "implementation"
            )
        )

        stats = DashboardStats(
            total_groups=total_groups or 0,
            active_groups=active_groups or 0,
            total_students=total_students or 0,
        )

        # Create admin profile summary
        admin_summary = AdminProfileSummary(
            admin_id=admin_profile.user_id,
            department=getattr(admin_profile, "department", None),
            permissions=getattr(admin_profile, "permissions", ["all"]),
            status="active",  # Default status since it's not in the model
        )

        return AdminDashboardResponse(admin_profile=admin_summary, stats=stats)

    except Exception as e:
        logger.error(f"Error getting admin dashboard data: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get admin dashboard data",
        )


@router.get("/dashboard")
async def get_dashboard(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> Union[
    StudentDashboardResponse, SupervisorDashboardResponse, AdminDashboardResponse
]:
    """
    Get role-specific dashboard data.

    This endpoint returns different data based on the user's role:
    - Students: Student profile, enrolled groups, and statistics
    - Supervisors: Supervisor profile, managed groups, and statistics
    - Admins: Admin profile and system-wide statistics

    Args:
        current_user (User): Current authenticated user
        db (AsyncSession): Database session

    Returns:
        DashboardResponse: Role-specific dashboard data

    Raises:
        HTTPException(404): Profile not found
        HTTPException(500): Database error
    """
    try:
        # Handle role value for both enum and string types
        role = (
            current_user.role.value
            if hasattr(current_user.role, "value")
            else current_user.role
        )

        logger.info(
            f"Getting dashboard data for user: {current_user.email} with role: {role}"
        )

        if role == "student":
            return await get_student_dashboard_data(current_user, db)
        elif role == "supervisor":
            return await get_supervisor_dashboard_data(current_user, db)
        elif role == "admin":
            return await get_admin_dashboard_data(current_user, db)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported role: {role}",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in dashboard endpoint: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get dashboard data",
        )
