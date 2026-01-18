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
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase_auth import get_current_user
from app.db import get_db
from app.models.domain import Domain
from app.models.supervisor import Supervisor
from app.models.supervisor_domain import SupervisorDomain
from app.models.user import User
from app.repositories import supervisor_repository
from app.schemas.supervisor_explore_schema import (
    DomainInfo,
    IndustryInfo,
    PaginatedSupervisorResponse,
    SupervisorBasicInfo,
    SupervisorDetailedInfo,
)

router = APIRouter(prefix="/explore", tags=["supervisor-explore"])


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

    # Build base query - join users and supervisors
    query = (
        select(User, Supervisor)
        .join(Supervisor, User.user_id == Supervisor.user_id)
        .where(User.role == "supervisor")
    )

    # Collect simple filters (department, designation, search)
    simple_filters = []
    relevance_score = None

    # Department filter with alias support
    if department:
        normalized_dept = normalize_department(department)
        simple_filters.append(Supervisor.department.ilike(f"%{normalized_dept}%"))

    # Designation filter with relevance scoring
    if designation:
        simple_filters.append(Supervisor.designation.ilike(f"%{designation}%"))
        # Create relevance score for designation:
        # 3 = exact match (case-insensitive), 2 = prefix match, 1 = substring match
        relevance_score = case(
            (
                func.lower(Supervisor.designation) == func.lower(designation),
                3,
            ),  # Exact match
            (
                func.lower(Supervisor.designation).startswith(func.lower(designation)),
                2,
            ),  # Prefix match
            else_=1,  # Substring match
        )

    # Search filter (name or email) with relevance scoring
    if search:
        search_filter = or_(
            User.full_name.ilike(f"%{search}%"), User.email.ilike(f"%{search}%")
        )
        simple_filters.append(search_filter)
        # Create relevance score for name/email:
        # 3 = starts with search term, 2 = contains search term, 1 = default
        search_relevance = case(
            (func.lower(User.full_name).startswith(func.lower(search)), 3),
            (func.lower(User.full_name).contains(func.lower(search)), 2),
            else_=1,
        )
        # Combine with designation relevance if both exist
        if relevance_score is not None:
            relevance_score = relevance_score + search_relevance
        else:
            relevance_score = search_relevance

    # Domain filter (intersected with other filters via many-to-many join)
    if domain:
        query = (
            query.join(
                SupervisorDomain, Supervisor.user_id == SupervisorDomain.supervisor_id
            )
            .join(Domain, SupervisorDomain.domain_id == Domain.domain_id)
            .where(Domain.name.ilike(f"%{domain}%"))
        )

    # Apply simple filters (department, designation, search) with AND logic
    if simple_filters:
        query = query.where(and_(*simple_filters))

    # Apply distinct to avoid duplicate rows from many-to-many joins
    query = query.distinct()

    # Add relevance score to query if it exists
    if relevance_score is not None:
        query = query.add_columns(relevance_score.label("relevance_score"))

    # Get total count BEFORE pagination (count filtered results only)
    # Build a count query from the same filtered query
    count_subquery = query.subquery()
    count_query = select(func.count()).select_from(count_subquery)
    total = (await db.execute(count_query)).scalar() or 0

    # Calculate pagination
    offset = (page - 1) * per_page
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1

    # Apply ordering by relevance score (if it exists) before pagination
    if relevance_score is not None:
        query = query.order_by(relevance_score.desc(), User.full_name.asc())
    else:
        # Default ordering by name if no relevance score
        query = query.order_by(User.full_name.asc())

    # Apply pagination
    query = query.offset(offset).limit(per_page)

    # Execute query
    result = await db.execute(query)
    rows = result.all()

    # Convert to response format
    supervisors = []
    for row in rows:
        # Handle both cases: with and without relevance score
        if relevance_score is not None:
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
        supervisors=supervisors,
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
    )
