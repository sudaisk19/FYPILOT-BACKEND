from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.supabase_auth import get_current_user
from app.db import get_db
from app.models.faculty import Faculty
from app.models.user import RoleEnum, User
from app.repositories.supervisor_repository import supervisor_repository
from app.schemas.admin_supervisors_schema import (
    AdminFacultyProfileOut,
    CapacityUpdateReq,
    FacultyCardInfo,
    FacultyDropdownItem,
    PaginatedFacultyResponse,
    SupervisedProjectInfo,
)
from app.services.cache import cache

DEFAULT_SUPERVISOR_CAPACITY = 8

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# DROPDOWN ENDPOINT - For searchable select/combobox in assignment forms
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/faculty/dropdown",
    response_model=list[FacultyDropdownItem],
    summary="Get faculty for dropdown selection",
    description="Returns a lightweight list of all faculty for use in searchable dropdown/combobox. Frontend can filter as user types.",
)
async def get_faculty_dropdown(
    search: Optional[str] = Query(
        None, description="Optional search filter (name, email, department)"
    ),
    available_only: bool = Query(
        False, description="If true, only return supervisors with available slots"
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get all supervisors in a lightweight format for dropdown selection.

    Use cases:
    - Admin assigning faculty as group supervisor
    - Admin assigning faculty as group co-supervisor
    - Any form that needs faculty selection

    The frontend should use this with a searchable select component
    (e.g., React Select, MUI Autocomplete, Ant Design Select).

    Optimizations:
    - Returns max 15 results (frontend should debounce 300ms)
    - Cached in Redis for 5 minutes per search term
    - Uses Trigram GIN index for fast ILIKE matching
    """
    if current_user.role != RoleEnum.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    # If no search term, return empty (search-as-you-type optimization)
    if not search:
        return []

    # ── 1. Check Redis Cache ──────────────────────────────────────────────
    cache_key = f"fac_dropdown:{search.lower().strip()}:{available_only}"
    cached = await cache.get_json(cache_key)
    if cached is not None:
        return cached

    # ── 2. Database Query (with LIMIT) ────────────────────────────────────
    query = (
        select(User, Faculty)
        .join(Faculty, User.user_id == Faculty.user_id)
        .where(
            User.role == RoleEnum.faculty,
            Faculty.is_supervisor == True,
        )
    )

    filters = []

    # Search filter
    if search:
        s = f"%{search}%"
        filters.append(
            or_(
                User.full_name.ilike(s),
                User.email.ilike(s),
                Faculty.department.ilike(s),
            )
        )

    # Available only filter
    if available_only:
        filters.append(Faculty.capacity_filled < Faculty.capacity_max)

    if filters:
        query = query.where(and_(*filters))

    # Order by name and LIMIT to 15 results for fast response
    query = query.order_by(User.full_name.asc()).limit(15)

    rows = (await db.execute(query)).all()

    # ── 3. Build Response ─────────────────────────────────────────────────
    faculty_list = []
    for user, faculty_member in rows:
        free_slots = faculty_member.capacity_max - faculty_member.capacity_filled
        faculty_list.append(
            FacultyDropdownItem(
                user_id=str(user.user_id),
                full_name=user.full_name,
                department=faculty_member.department,
                is_available=free_slots > 0,
            )
        )

    # ── 4. Cache in Redis (5 min TTL) ─────────────────────────────────────────────────────
    result_dicts = [s.model_dump() for s in faculty_list]
    await cache.set_json(cache_key, result_dicts, ttl_seconds=300)

    return faculty_list


@router.get("/faculty", response_model=PaginatedFacultyResponse)
async def list_faculty(
    department: Optional[str] = Query(None),
    availability: Literal["all", "available", "full"] = Query("all"),
    status_filter: Literal["all", "active", "inactive"] = Query("all"),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role != RoleEnum.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    # ── 1. Check Redis Cache ──────────────────────────────────────────────
    cache_key = (
        "admin:faculty:"
        f"{department}:{availability}:{status_filter}:{search}:{page}:{per_page}"
    )
    cached = await cache.get_json(cache_key)
    if cached:
        return cached

    # 1. Base Query using your exact models
    query = (
        select(User, Faculty)
        .join(Faculty, User.user_id == Faculty.user_id)
        .options(selectinload(Faculty.domains))  # Pre-loads domains for the tags
        .where(User.role == RoleEnum.faculty)
    )

    filters = []
    if department:
        filters.append(Faculty.department.ilike(f"%{department}%"))

    if availability == "available":
        filters.append(Faculty.capacity_filled < Faculty.capacity_max)
    elif availability == "full":
        filters.append(Faculty.capacity_filled >= Faculty.capacity_max)

    if status_filter == "active":
        filters.append(Faculty.is_active == True)
    elif status_filter == "inactive":
        filters.append(Faculty.is_active == False)

    if search:
        s = f"%{search}%"
        filters.append(
            or_(
                User.full_name.ilike(s),
                User.email.ilike(s),
                Faculty.department.ilike(s),
            )
        )

    if filters:
        query = query.where(and_(*filters))

    # 2. Count Query (Pagination formula from your Student API)
    count_query = (
        select(func.count(User.user_id))
        .join(Faculty)
        .where(User.role == RoleEnum.faculty)
    )
    if filters:
        count_query = count_query.where(and_(*filters))

    total = (await db.execute(count_query)).scalar() or 0
    offset = (page - 1) * per_page
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1

    # 3. Execution
    query = query.order_by(User.full_name.asc()).offset(offset).limit(per_page)
    rows = (await db.execute(query)).all()

    # 4. Formatting for your Frontend Cards
    faculty_out = []
    for user, faculty_member in rows:
        free = faculty_member.capacity_max - faculty_member.capacity_filled
        faculty_out.append(
            FacultyCardInfo(
                user_id=str(user.user_id),
                full_name=user.full_name,
                email=user.email,
                department=faculty_member.department,
                designation=faculty_member.designation,
                domains=[d.name for d in faculty_member.domains],
                capacity_max=faculty_member.capacity_max,
                capacity_filled=faculty_member.capacity_filled,
                free_slots=free,
                status="AVAILABLE" if free > 0 else "FULL",
                is_supervisor=faculty_member.is_supervisor,
                is_jury=faculty_member.is_jury,
                is_active=faculty_member.is_active,
            )
        )

    response = PaginatedFacultyResponse(
        faculty=faculty_out,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )

    # ── Cache Result (TTL 300s / 5 mins) ──────────────────────────────────
    await cache.set_json(cache_key, response.model_dump(), ttl_seconds=300)

    return response

    # 1. GET Individual Profile


@router.get("/faculty/{faculty_id}", response_model=AdminFacultyProfileOut)
async def get_admin_faculty_profile(
    faculty_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Admin only")

    user = await supervisor_repository.get_full_profile(db, faculty_id)
    if not user or not user.faculty_profile:
        raise HTTPException(status_code=404, detail="Faculty not found")

    sp = user.faculty_profile

    # Format Projects list for UI
    projects_data = []
    for group in sp.supervised_groups:
        if group.project:
            projects_data.append(
                SupervisedProjectInfo(
                    group_id=group.group_id,
                    project_id=group.project.project_id,
                    fyp_id=group.project.fyp_id,
                    name=group.project.name,
                    description=group.project.description,
                    fyp_cycle=group.fyp_cycle,
                    fyp_stage=group.fyp_stage,
                    domains=[d.name for d in group.project.domains],
                )
            )

    # 2. Add Co-Supervised Projects
    if hasattr(sp, "co_supervised_groups"):
        for group in sp.co_supervised_groups:
            if group.project:
                projects_data.append(
                    SupervisedProjectInfo(
                        group_id=group.group_id,
                        project_id=group.project.project_id,
                        fyp_id=group.project.fyp_id,
                        name=f"{group.project.name} (Co-Supervisor)",
                        description=group.project.description,
                        fyp_cycle=(
                            group.fyp_cycle.value if group.fyp_cycle else "Unknown"
                        ),
                        fyp_stage=group.fyp_stage,
                        domains=[d.name for d in group.project.domains],
                    )
                )

    return AdminFacultyProfileOut(
        user_id=user.user_id,
        full_name=user.full_name,
        email=user.email,
        profile_avatar=user.profile_avatar,
        department=sp.department,
        designation=sp.designation,
        office=sp.office,
        requirements=sp.requirements or [],
        project_type=sp.project_type if sp.project_type else None,
        capacity_max=sp.capacity_max,
        capacity_filled=sp.capacity_filled,
        is_supervisor=sp.is_supervisor,
        is_jury=sp.is_jury,
        is_active=sp.is_active,
        domains=[d.name for d in sp.domains],
        industries=[i.name for i in sp.industries],
        projects=projects_data,
    )


# 2. UPDATE Faculty profile (capacity & roles)


@router.patch("/faculty/{faculty_id}/profile-update")
async def update_faculty_profile(
    faculty_id: UUID,
    data: CapacityUpdateReq,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Admin only")

    if (
        data.capacity_max is None
        and data.is_supervisor is None
        and data.is_jury is None
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide at least one field to update.",
        )

    # 1. Fetch faculty to get current filled capacity
    user = await supervisor_repository.get_full_profile(db, faculty_id)
    if not user or not user.faculty_profile:
        raise HTTPException(status_code=404, detail="Faculty not found")

    sp = user.faculty_profile

    # Resolve final flag states so we can enforce business rules
    new_is_supervisor = (
        sp.is_supervisor if data.is_supervisor is None else data.is_supervisor
    )
    new_is_jury = sp.is_jury if data.is_jury is None else data.is_jury
    new_is_active = new_is_supervisor or new_is_jury

    supervisor_flag_changed = (
        data.is_supervisor is not None and data.is_supervisor != sp.is_supervisor
    )

    update_payload: dict[str, object] = {}
    capacity_to_apply: Optional[int] = None
    final_capacity_max = sp.capacity_max

    if data.capacity_max is not None and not new_is_supervisor:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Capacity changes are only allowed while supervision is enabled.",
        )

    if not new_is_supervisor:
        if sp.capacity_filled > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot disable supervision while faculty has assigned groups.",
            )
        capacity_to_apply = 0
    elif supervisor_flag_changed and data.is_supervisor:
        capacity_to_apply = (
            data.capacity_max
            if data.capacity_max is not None
            else DEFAULT_SUPERVISOR_CAPACITY
        )
    elif data.capacity_max is not None:
        capacity_to_apply = data.capacity_max

    if capacity_to_apply is not None:
        if capacity_to_apply < sp.capacity_filled:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Cannot reduce capacity to {capacity_to_apply}. Faculty member already has {sp.capacity_filled} assigned groups."
                ),
            )
        update_payload["capacity_max"] = capacity_to_apply
        final_capacity_max = capacity_to_apply

    if data.is_supervisor is not None:
        update_payload["is_supervisor"] = data.is_supervisor

    if data.is_jury is not None:
        update_payload["is_jury"] = data.is_jury

    if data.is_supervisor is not None or data.is_jury is not None:
        update_payload["is_active"] = new_is_active

    if not update_payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No changes detected in the request payload.",
        )

    # 3. Apply update
    await supervisor_repository.update(db, faculty_id, update_payload)
    await db.commit()

    return {
        "message": "Faculty profile updated successfully",
        "capacity_max": final_capacity_max,
        "capacity_filled": sp.capacity_filled,
        "is_supervisor": new_is_supervisor,
        "is_jury": new_is_jury,
        "is_active": new_is_active,
    }
