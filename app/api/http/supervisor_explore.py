# app/api/http/supervisor_explore.py

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase_auth import get_current_user
from app.db import get_db
from app.models.supervisor import Supervisor
from app.models.user import User
from app.schemas.supervisor_explore_schema import (
    PaginatedSupervisorResponse,
    SupervisorBasicInfo,
    SupervisorDetailedInfo,
)

router = APIRouter(prefix="/explore", tags=["supervisor-explore"])


@router.get("/supervisors", response_model=PaginatedSupervisorResponse)
async def explore_supervisors(
    # Query parameters for filtering
    department: Optional[str] = Query(None, description="Filter by department"),
    designation: Optional[str] = Query(None, description="Filter by designation"),
    project_type: Optional[str] = Query(None, description="Filter by project type"),
    search: Optional[str] = Query(None, description="Search by name or email"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(10, ge=1, le=50, description="Items per page"),
    # Dependencies
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Explore and browse all supervisors with pagination and filtering.

    This endpoint allows students to:
    - Browse all available supervisors
    - Filter by department, designation, project type
    - Search by name or email
    - Paginate through results

    Only students can access this endpoint.
    """
    # Verify user is a student
    if current_user.role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. This endpoint is only for students.",
        )

    # Build base query - join users and supervisors
    query = (
        select(User, Supervisor)
        .join(Supervisor, User.user_id == Supervisor.user_id)
        .where(User.role == "supervisor")
    )

    # Apply filters
    filters = []

    # Department filter
    if department:
        filters.append(Supervisor.department.ilike(f"%{department}%"))

    # Designation filter
    if designation:
        filters.append(Supervisor.designation.ilike(f"%{designation}%"))

    # Project type filter (check if supervisor supports this project type)
    if project_type:
        filters.append(Supervisor.project_types.contains([project_type]))

    # Search filter (name or email)
    if search:
        search_filter = or_(
            User.full_name.ilike(f"%{search}%"), User.email.ilike(f"%{search}%")
        )
        filters.append(search_filter)

    # Apply all filters
    if filters:
        query = query.where(and_(*filters))

    # Get total count for pagination
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    # Calculate pagination
    offset = (page - 1) * per_page
    total_pages = (total + per_page - 1) // per_page

    # Apply pagination
    query = query.offset(offset).limit(per_page)

    # Execute query
    result = await db.execute(query)
    rows = result.all()

    # Convert to response format
    supervisors = []
    for user, supervisor in rows:
        available_slots = supervisor.capacity_max - supervisor.capacity_filled

        supervisors.append(
            SupervisorBasicInfo(
                user_id=user.user_id,
                full_name=user.full_name,
                email=user.email,
                profile_avatar=user.profile_avatar,
                department=supervisor.department,
                designation=supervisor.designation,
                office=supervisor.office,
                capacity_max=supervisor.capacity_max,
                capacity_filled=supervisor.capacity_filled,
                available_slots=available_slots,
            )
        )

    return PaginatedSupervisorResponse(
        supervisors=supervisors,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )


@router.get("/supervisors/{supervisor_id}", response_model=SupervisorDetailedInfo)
async def get_supervisor_details(
    supervisor_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get detailed information about a specific supervisor.

    This endpoint provides comprehensive supervisor information including:
    - Personal details
    - Professional information
    - Supervision capacity and availability
    - Project types and requirements
    - Current supervision load

    Only students can access this endpoint.
    """
    # Verify user is a student
    if current_user.role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. This endpoint is only for students.",
        )

    # Fetch supervisor with user details
    result = await db.execute(
        select(User, Supervisor)
        .join(Supervisor, User.user_id == Supervisor.user_id)
        .where(User.user_id == supervisor_id, User.role == "supervisor")
    )

    row = result.first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Supervisor not found"
        )

    user, supervisor = row

    # Calculate available slots
    available_slots = supervisor.capacity_max - supervisor.capacity_filled

    # Get current groups count (you might want to add this to your database)
    # For now, we'll use capacity_filled as current_groups
    current_groups = supervisor.capacity_filled

    # For total_supervised, you might want to add a field to track historical data
    # For now, we'll use current_groups as a placeholder
    total_supervised = current_groups

    return SupervisorDetailedInfo(
        # User fields
        user_id=user.user_id,
        full_name=user.full_name,
        email=user.email,
        profile_avatar=user.profile_avatar,
        created_at=user.created_at,
        updated_at=user.updated_at,
        # Supervisor fields
        department=supervisor.department,
        designation=supervisor.designation,
        office=supervisor.office,
        requirements=supervisor.requirements or [],
        project_types=supervisor.project_types or [],
        capacity_max=supervisor.capacity_max,
        capacity_filled=supervisor.capacity_filled,
        available_slots=available_slots,
        # Computed fields
        current_groups=current_groups,
        total_supervised=total_supervised,
    )
