from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.supabase_auth import get_current_user
from app.db import get_db
from app.models.supervisor import Supervisor
from app.models.user import RoleEnum, User
from app.repositories.supervisor_repository import supervisor_repository
from app.schemas.admin_supervisors_schema import (
    AdminSupervisorProfileOut,
    CapacityUpdateReq,
    PaginatedSupervisorResponse,
    SupervisedProjectInfo,
    SupervisorCardInfo,
    SupervisorDropdownItem,
)
from app.services.cache import cache

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# DROPDOWN ENDPOINT - For searchable select/combobox in assignment forms
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/supervisors/dropdown",
    response_model=list[SupervisorDropdownItem],
    summary="Get supervisors for dropdown selection",
    description="Returns a lightweight list of all supervisors for use in searchable dropdown/combobox. Frontend can filter as user types.",
)
async def get_supervisors_dropdown(
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
    - Admin assigning supervisor to a group
    - Admin assigning co-supervisor to a group
    - Any form that needs supervisor selection

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
    cache_key = f"sup_dropdown:{search.lower().strip()}:{available_only}"
    cached = await cache.get_json(cache_key)
    if cached is not None:
        return cached

    # ── 2. Database Query (with LIMIT) ────────────────────────────────────
    query = (
        select(User, Supervisor)
        .join(Supervisor, User.user_id == Supervisor.user_id)
        .where(User.role == RoleEnum.supervisor)
    )

    filters = []

    # Search filter
    if search:
        s = f"%{search}%"
        filters.append(
            or_(
                User.full_name.ilike(s),
                User.email.ilike(s),
                Supervisor.department.ilike(s),
            )
        )

    # Available only filter
    if available_only:
        filters.append(Supervisor.capacity_filled < Supervisor.capacity_max)

    if filters:
        query = query.where(and_(*filters))

    # Order by name and LIMIT to 15 results for fast response
    query = query.order_by(User.full_name.asc()).limit(15)

    rows = (await db.execute(query)).all()

    # ── 3. Build Response ─────────────────────────────────────────────────
    supervisors = []
    for user, supervisor in rows:
        free_slots = supervisor.capacity_max - supervisor.capacity_filled
        supervisors.append(
            SupervisorDropdownItem(
                user_id=str(user.user_id),
                full_name=user.full_name,
                department=supervisor.department,
                is_available=free_slots > 0,
            )
        )

    # ── 4. Cache in Redis (5 min TTL) ─────────────────────────────────────
    result_dicts = [s.model_dump() for s in supervisors]
    await cache.set_json(cache_key, result_dicts, ttl_seconds=300)

    return supervisors


@router.get("/supervisors", response_model=PaginatedSupervisorResponse)
async def list_supervisors(
    department: Optional[str] = Query(None),
    availability: Literal["all", "available", "full"] = Query("all"),
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
        f"admin:supervisors:{department}:{availability}:" f"{search}:{page}:{per_page}"
    )
    cached = await cache.get_json(cache_key)
    if cached:
        return cached

    # 1. Base Query using your exact models
    query = (
        select(User, Supervisor)
        .join(Supervisor, User.user_id == Supervisor.user_id)
        .options(selectinload(Supervisor.domains))  # Pre-loads domains for the tags
        .where(User.role == RoleEnum.supervisor)
    )

    filters = []
    if department:
        filters.append(Supervisor.department.ilike(f"%{department}%"))

    if availability == "available":
        filters.append(Supervisor.capacity_filled < Supervisor.capacity_max)
    elif availability == "full":
        filters.append(Supervisor.capacity_filled >= Supervisor.capacity_max)

    if search:
        s = f"%{search}%"
        filters.append(
            or_(
                User.full_name.ilike(s),
                User.email.ilike(s),
                Supervisor.department.ilike(s),
            )
        )

    if filters:
        query = query.where(and_(*filters))

    # 2. Count Query (Pagination formula from your Student API)
    count_query = (
        select(func.count(User.user_id))
        .join(Supervisor)
        .where(User.role == RoleEnum.supervisor)
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
    supervisors_out = []
    for user, supervisor in rows:
        free = supervisor.capacity_max - supervisor.capacity_filled
        supervisors_out.append(
            SupervisorCardInfo(
                user_id=str(user.user_id),
                full_name=user.full_name,
                email=user.email,
                department=supervisor.department,
                designation=supervisor.designation,
                domains=[d.name for d in supervisor.domains],
                capacity_max=supervisor.capacity_max,
                capacity_filled=supervisor.capacity_filled,
                free_slots=free,
                status="AVAILABLE" if free > 0 else "FULL",
            )
        )

    response = PaginatedSupervisorResponse(
        supervisors=supervisors_out,
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


@router.get("/supervisors/{supervisor_id}", response_model=AdminSupervisorProfileOut)
async def get_admin_supervisor_profile(
    supervisor_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    user = await supervisor_repository.get_full_profile(db, supervisor_id)
    if not user or not user.supervisor_profile:
        raise HTTPException(status_code=404, detail="Supervisor not found")

    sp = user.supervisor_profile

    # Format Projects list for UI
    projects_data = []
    for group in sp.supervised_groups:
        if group.project:
            projects_data.append(
                SupervisedProjectInfo(
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

    return AdminSupervisorProfileOut(
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
        domains=[d.name for d in sp.domains],
        industries=[i.name for i in sp.industries],
        projects=projects_data,
    )


# 2. UPDATE Capacity (For the 'Save' button in screenshot)
# app/api/http/admin_supervisors.py


@router.patch("/supervisors/{supervisor_id}/capacity")
async def update_supervisor_capacity(
    supervisor_id: UUID,
    data: CapacityUpdateReq,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Admin only")

    # 1. Supervisor ko fetch karein taake current filled capacity pata chale
    user = await supervisor_repository.get_full_profile(db, supervisor_id)
    if not user or not user.supervisor_profile:
        raise HTTPException(status_code=404, detail="Supervisor not found")

    sp = user.supervisor_profile

    # 2. Business Logic: Check if new capacity is enough for already assigned groups
    if data.capacity_max < sp.capacity_filled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot reduce capacity to {data.capacity_max}. Supervisor already has {sp.capacity_filled} assigned groups.",
        )

    # 3. Agar sab theek hai, toh update karein
    await supervisor_repository.update(
        db, supervisor_id, {"capacity_max": data.capacity_max}
    )
    await db.commit()

    return {
        "message": "Capacity updated successfully",
        "new_capacity": data.capacity_max,
    }
