# app/api/http/supervisor_explore.py
"""
Supervisor Explore API Module - Partially Refactored to use Repository Pattern

This module handles supervisor browsing and search operations.

REFACTORED:
- get_supervisor_details() uses supervisor_repository.get_with_user()
  and supervisor_repository.get_domains/get_industries()

NOT REFACTORED (complex relevance scoring logic):
- explore_supervisors() - keeps direct SQLAlchemy for relevance scoring
  The repository search() method doesn't support relevance scoring which
  is critical for this endpoint's UX.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase_auth import get_current_user
from app.db import get_db
from app.models.group import InviteStatusEnum
from app.models.user import User
from app.repositories import (
    request_repository,
    student_repository,
    supervisor_repository,
)
from app.models.request import Request
from app.schemas.invite_schema import RequestSummaryItem
from app.schemas.supervisor_explore_schema import (
    DomainInfo,
    IndustryInfo,
    PaginatedSupervisorResponse,
    SupervisorBasicInfo,
    SupervisorDetailedInfo,
)

router = APIRouter(tags=["supervisor-explore"])


# Department alias mapping for flexible department filtering
DEPARTMENT_ALIASES = {
    "se": "Software Engineering",
    "software engineering": "Software Engineering",
    "cs": "Computer Science",
    "computer science": "Computer Science",
    "ee": "Electrical Engineering",
    "electrical engineering": "Electrical Engineering",
    "me": "Mechanical Engineering",
    "mechanical engineering": "Mechanical Engineering",
    "ce": "Civil Engineering",
    "civil engineering": "Civil Engineering",
}


def normalize_department(dept: str) -> str:
    """Normalize department name to handle aliases (e.g., SE -> Software Engineering)"""
    if not dept:
        return dept
    normalized = dept.lower().strip()
    return DEPARTMENT_ALIASES.get(normalized, dept)


@router.get(
    "/supervisors",
    response_model=PaginatedSupervisorResponse,
    summary="Explore Supervisors",
    description="Browse and search all available supervisors with advanced filtering by department, designation, domain expertise, and full-text search capabilities.",
    responses={
        200: {
            "description": "Successfully retrieved paginated list of supervisors",
            "content": {
                "application/json": {
                    "example": {
                        "supervisors": [
                            {
                                "user_id": "550e8400-e29b-41d4-a716-446655440000",
                                "full_name": "Dr. Ahmed Hassan",
                                "email": "ahmed@university.edu",
                                "profile_avatar": None,
                                "department": "Software Engineering",
                                "designation": "Associate Professor",
                                "office": "Building A, Room 301",
                                "capacity_max": 5,
                                "capacity_filled": 3,
                                "available_slots": 2,
                            }
                        ],
                        "total": 42,
                        "page": 1,
                        "per_page": 10,
                        "total_pages": 5,
                        "has_next": True,
                        "has_prev": False,
                    }
                }
            },
        },
        403: {
            "description": "Access denied - only students can access this endpoint",
        },
    },
)
async def explore_supervisors(
    # Query parameters for filtering
    department: Optional[str] = Query(
        None,
        description="Filter by department (e.g., SE, Software Engineering, CS, Computer Science)",
    ),
    designation: Optional[str] = Query(None, description="Filter by designation"),
    domain: Optional[str] = Query(None, description="Filter by domain expertise"),
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
    - Filter by department, designation, domain expertise
    - Search by name or email
    - Combine multiple filters for precise results (intersected filters with AND logic)
    - Paginate through results

    Department aliases supported:
    - SE, Software Engineering → Software Engineering
    - CS, Computer Science → Computer Science
    - EE, Electrical Engineering → Electrical Engineering
    - ME, Mechanical Engineering → Mechanical Engineering
    - CE, Civil Engineering → Civil Engineering

    Only students can access this endpoint.
    """
    # Verify user is a student
    if current_user.role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. This endpoint is only for students.",
        )

    rows, total = await supervisor_repository.search_supervisors_with_scoring(
        db,
        department=department,
        designation=designation,
        domain=domain,
        search=search,
        page=page,
        per_page=per_page,
    )

    # Calculate pagination metadata
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1

    # Convert to response format
    supervisors = []
    for row in rows:
        if len(row) == 3:
            user, supervisor, _ = row  # Unpack user, supervisor, and relevance_score
        else:
            user, supervisor = row  # Unpack just user and supervisor

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
        faculty=supervisors,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )


@router.get(
    "/supervisors/{supervisor_id}",
    response_model=SupervisorDetailedInfo,
    summary="Get Supervisor Details",
    description="Retrieve comprehensive information about a specific supervisor including personal details, professional information, capacity, domains and industries of expertise.",
    responses={
        200: {
            "description": "Supervisor details retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "user_id": "550e8400-e29b-41d4-a716-446655440000",
                        "full_name": "Dr. Ahmed Hassan",
                        "email": "ahmed.hassan@university.edu",
                        "profile_avatar": "https://example.com/avatar.jpg",
                        "created_at": "2024-01-15T10:00:00Z",
                        "updated_at": "2024-12-08T14:30:00Z",
                        "department": "Software Engineering",
                        "designation": "Associate Professor",
                        "office": "Building A, Room 301",
                        "requirements": ["Good communication", "Research experience"],
                        "project_types": ["product and research"],
                        "capacity_max": 5,
                        "capacity_filled": 3,
                        "available_slots": 2,
                        "domains": [
                            {
                                "domain_id": "550e8400-e29b-41d4-a716-446655440001",
                                "name": "Artificial Intelligence",
                            },
                            {
                                "domain_id": "550e8400-e29b-41d4-a716-446655440002",
                                "name": "Machine Learning",
                            },
                        ],
                        "industries": [
                            {
                                "industry_id": "550e8400-e29b-41d4-a716-446655440010",
                                "name": "Technology",
                            },
                            {
                                "industry_id": "550e8400-e29b-41d4-a716-446655440011",
                                "name": "Finance",
                            },
                        ],
                        "current_groups": 3,
                        "total_supervised": 12,
                    }
                }
            },
        },
        403: {
            "description": "Access denied - only students can access this endpoint",
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "error": {
                            "code": 403,
                            "type": "HTTPException",
                            "message": "Access denied. This endpoint is only for students.",
                        },
                    }
                }
            },
        },
        404: {
            "description": "Supervisor not found",
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "error": {
                            "code": 404,
                            "type": "HTTPException",
                            "message": "Supervisor not found",
                        },
                    }
                }
            },
        },
    },
)
async def get_supervisor_details(
    supervisor_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get detailed information about a specific supervisor.

    This endpoint provides comprehensive supervisor information including:
    - Personal details (name, email, avatar, created/updated timestamps)
    - Professional information (department, designation, office location)
    - Supervision capacity and availability (max capacity, currently filled, available slots)
    - Project type preferences (research, product, or product and research)
    - Requirements and qualifications
    - Domains and industries of expertise (with IDs for filtering/linking)
    - Current supervision load and historical statistics

    **Authentication:** Only authenticated students can access this endpoint.

    **Parameters:**
    - `supervisor_id` (path): UUID of the supervisor to retrieve

    **Returns:** Detailed supervisor information with all related expertise areas and capacity metrics.
    """
    # Verify user is a student
    if current_user.role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. This endpoint is only for students.",
        )

    # Fetch supervisor with user details using repository
    row = await supervisor_repository.get_with_user(db, supervisor_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Supervisor not found"
        )

    user, supervisor = row

    # Fetch domains and industries using repository
    domains_list = await supervisor_repository.get_domains(db, supervisor_id)
    industries_list = await supervisor_repository.get_industries(db, supervisor_id)

    # Calculate available slots
    available_slots = supervisor.capacity_max - supervisor.capacity_filled

    # Get project type (single value) - convert to list for response
    project_types = []
    if supervisor.project_type:
        project_types = [supervisor.project_type]

    # Get current groups count (you might want to add this to your database)
    # For now, we'll use capacity_filled as current_groups
    current_groups = supervisor.capacity_filled

    # For total_supervised, you might want to add a field to track historical data
    # For now, we'll use current_groups as a placeholder
    total_supervised = current_groups

    # Extract domains with id and name using repository data
    domains = [
        DomainInfo(domain_id=domain.domain_id, name=domain.name)
        for domain in domains_list
    ]

    # Extract industries with id and name using repository data
    industries = [
        IndustryInfo(industry_id=industry.industry_id, name=industry.name)
        for industry in industries_list
    ]

    # --- Request history logic for students ---
    request_history = None
    if current_user.role == "student":
        # Get the student's group (assume first group if multiple)
        student = await student_repository.get_with_groups(db, current_user.user_id)
        group = None
        if student and student.groups:
            group = student.groups[0]
        if group:
            # Fetch the most recent request with status in (pending, feedback, declined)
            statuses = [
                InviteStatusEnum.pending,
                InviteStatusEnum.feedback,
                InviteStatusEnum.declined,
            ]
            req = await request_repository.get_recent_by_group_supervisor_statuses(
                db, group.group_id, supervisor_id, statuses
            )
            if req:
                # Fetch all requests between this group and supervisor
                from sqlalchemy import select as sa_select

                all_requests_result = await db.execute(
                    sa_select(Request)
                    .where(
                        Request.group_id == group.group_id,
                        Request.faculty_id == supervisor_id,
                    )
                    .order_by(Request.created_at.asc())
                )
                all_requests = all_requests_result.scalars().all()
                request_history = [
                    RequestSummaryItem(
                        request_id=r.request_id,
                        status=r.status.value,
                        message=r.message,
                        feedback=r.feedback,
                        created_at=r.created_at,
                        updated_at=r.updated_at,
                    )
                    for r in all_requests
                ]

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
        project_types=project_types,
        capacity_max=supervisor.capacity_max,
        capacity_filled=supervisor.capacity_filled,
        available_slots=available_slots,
        # Expertise and preferences
        domains=domains,
        industries=industries,
        # Computed fields
        current_groups=current_groups,
        total_supervised=total_supervised,
        # Add request_history as an extra attribute (will require schema update)
        request_history=request_history,
    )
