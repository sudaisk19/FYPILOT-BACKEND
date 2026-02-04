from typing import Optional, Literal
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from uuid import UUID  

from app.auth.supabase_auth import get_current_user
from app.db import get_db  # <--- THIS FIXES YOUR IMPORT ERROR
from app.models.user import User, RoleEnum
from app.models.supervisor import Supervisor

from app.repositories.supervisor_repository import supervisor_repository
from app.schemas.admin_supervisors_schema import (
    AdminSupervisorProfileOut, 
    SupervisedProjectInfo, 
    CapacityUpdateReq
)

from app.schemas.admin_supervisors_schema import PaginatedSupervisorResponse, SupervisorCardInfo

router = APIRouter()

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

    # 1. Base Query using your exact models
    query = (
        select(User, Supervisor)
        .join(Supervisor, User.user_id == Supervisor.user_id)
        .options(selectinload(Supervisor.domains)) # Pre-loads domains for the tags
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
        filters.append(or_(
            User.full_name.ilike(s),
            User.email.ilike(s),
            Supervisor.department.ilike(s)
        ))

    if filters:
        query = query.where(and_(*filters))

    # 2. Count Query (Pagination formula from your Student API)
    count_query = select(func.count(User.user_id)).join(Supervisor).where(User.role == RoleEnum.supervisor)
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
                status="AVAILABLE" if free > 0 else "FULL"
            )
        )

    return PaginatedSupervisorResponse(
        supervisors=supervisors_out,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )
    
    # 1. GET Individual Profile
@router.get("/supervisors/{supervisor_id}", response_model=AdminSupervisorProfileOut)
async def get_admin_supervisor_profile(
    supervisor_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
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
            projects_data.append(SupervisedProjectInfo(
                project_id=group.project.project_id,
                name=group.project.name,
                description=group.project.description,
                fyp_cycle=group.fyp_cycle,
                fyp_stage=group.fyp_stage,
                domains=[d.name for d in group.project.domains]
            ))

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
        projects=projects_data
    )

# 2. UPDATE Capacity (For the 'Save' button in screenshot)
# app/api/http/admin_supervisors.py

@router.patch("/supervisors/{supervisor_id}/capacity")
async def update_supervisor_capacity(
    supervisor_id: UUID,
    data: CapacityUpdateReq,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
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
            detail=f"Cannot reduce capacity to {data.capacity_max}. Supervisor already has {sp.capacity_filled} assigned groups."
        )

    # 3. Agar sab theek hai, toh update karein
    await supervisor_repository.update(db, supervisor_id, {"capacity_max": data.capacity_max})
    await db.commit()
    
    return {"message": "Capacity updated successfully", "new_capacity": data.capacity_max}