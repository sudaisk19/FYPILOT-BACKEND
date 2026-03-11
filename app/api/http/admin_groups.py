from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, literal, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload
from sqlalchemy.orm.attributes import flag_modified

from app.auth.supabase_auth import get_current_user
from app.db import get_db
from app.models.faculty import Faculty
from app.models.group import FYPCycleEnum, Group, GroupMember
from app.models.project import Project
from app.models.student import Student
from app.models.user import RoleEnum, User
from app.schemas.admin_groups_schema import (
    AdminGroupMemberInfo,
    AdminGroupProfileResponse,
    CohortCycleUpdateRequest,
    CohortCycleUpdateResponse,
    GroupCardInfo,
    PaginatedGroupResponse,
)
from app.schemas.group_schema import (
    DomainInfo,
    IndustryInfo,
    ProjectInfo,
    SupervisorInfo,
)

router = APIRouter(prefix="/admin", tags=["admin-groups"])


@router.get("/groups", response_model=PaginatedGroupResponse)
async def list_groups(
    batch: Optional[int] = Query(None, description="Cohort year e.g., 2025"),
    cohort: Optional[str] = Query(None, description="Cohort code e.g., F24"),
    cycle: Optional[FYPCycleEnum] = Query(None, description="fyp1 or fyp2"),
    supervisor: Literal["all", "assigned", "unassigned"] = Query(
        "all",
        description="Filter by supervisor assignment status",
    ),
    members: Optional[int] = Query(None, ge=1, le=3, description="Members count 1-3"),
    search: Optional[str] = Query(None, description="Search by project/supervisor"),
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Admin-only
    if current_user.role != RoleEnum.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    # ── 1. Check Redis Cache ──────────────────────────────────────────────
    cache_key = (
        f"admin:groups:{batch}:{cohort}:{cycle}:{supervisor}:{members}:"
        f"{search}:{page}:{per_page}"
    )
    from app.services.cache import cache

    cached = await cache.get_json(cache_key)
    if cached:
        return cached

    sup_user = aliased(User)
    aliased(User)

    # Subquery: members count per group
    member_counts_sq = (
        select(
            GroupMember.group_id.label("group_id"),
            func.count(GroupMember.student_id).label("members_count"),
        )
        .group_by(GroupMember.group_id)
        .subquery()
    )

    # Base query (select only columns we need)
    query = (
        select(
            Group.group_id,
            Group.fyp_cycle,
            Group.fyp_stage,
            Group.cohort,
            func.coalesce(member_counts_sq.c.members_count, 0).label("members_count"),
            Project.name.label("project_name"),
            sup_user.full_name.label("supervisor_name"),
            # For now, just return None or empty string for copuservisor in list view
            # Since it's an array now, we'd need complex aggregation
            literal(None).label("cosupervisor_name"),
        )
        .select_from(Group)
        .outerjoin(member_counts_sq, member_counts_sq.c.group_id == Group.group_id)
        .outerjoin(Project, Project.group_id == Group.group_id)
        .outerjoin(sup_user, sup_user.user_id == Group.supervisor_id)
        # .outerjoin(cosup_user) <--- Removed broken join
        .group_by(
            Group.group_id,
            Project.name,
            Group.cohort,
            sup_user.full_name,
            # cosup_user.full_name, <--- Removed
            member_counts_sq.c.members_count,
        )
    )

    filters = []

    # Batch + cycle
    if batch is not None:
        filters.append(Group.cohort_year == batch)

    if cycle is not None:
        filters.append(Group.fyp_cycle == cycle)

    # Supervisor assignment
    if supervisor == "assigned":
        filters.append(Group.supervisor_id.isnot(None))
    elif supervisor == "unassigned":
        filters.append(Group.supervisor_id.is_(None))

    # Members count
    if members is not None:
        filters.append(func.coalesce(member_counts_sq.c.members_count, 0) == members)

    # Cohort string filter
    if cohort:
        filters.append(func.upper(Group.cohort) == cohort.upper())

    # Search
    if search:
        s = f"%{search}%"
        filters.append(
            or_(
                Project.name.ilike(s),
                sup_user.full_name.ilike(s),
                Group.name.ilike(s),
            )
        )

    if filters:
        query = query.where(and_(*filters))

    # Count (distinct group_id)
    count_query = (
        select(func.count(func.distinct(Group.group_id)))
        .select_from(Group)
        .outerjoin(member_counts_sq, member_counts_sq.c.group_id == Group.group_id)
        .outerjoin(Project, Project.group_id == Group.group_id)
        .outerjoin(sup_user, sup_user.user_id == Group.supervisor_id)
    )
    if filters:
        count_query = count_query.where(and_(*filters))

    total = (await db.execute(count_query)).scalar() or 0

    offset = (page - 1) * per_page
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    query = query.order_by(Group.updated_at.desc()).offset(offset).limit(per_page)
    rows = (await db.execute(query)).all()

    groups_out: List[GroupCardInfo] = []
    for (
        group_id,
        fyp_cycle,
        fyp_stage,
        cohort_value,
        members_count,
        project_name,
        supervisor_name,
        cosupervisor_name,
    ) in rows:

        groups_out.append(
            GroupCardInfo(
                group_id=str(group_id),
                project_name=project_name,
                fyp_cycle=fyp_cycle.value if fyp_cycle else None,
                fyp_stage=fyp_stage,
                cohort=cohort_value,
                members_count=int(members_count or 0),
                supervisor_name=supervisor_name or "Not assigned",
                cosupervisor_name=cosupervisor_name or "Not assigned",
            )
        )

    response = PaginatedGroupResponse(
        groups=groups_out,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )

    # ── Cache Result (TTL 60s) ────────────────────────────────────────────
    await cache.set_json(cache_key, response.model_dump(), ttl_seconds=60)

    return response


# ─────────────────────────────────────────────────────────────────────────────
# BULK UPDATE COHORT CYCLE
# ─────────────────────────────────────────────────────────────────────────────


@router.patch(
    "/groups/cohort/{cohort}/cycle",
    response_model=CohortCycleUpdateResponse,
    summary="Bulk update FYP cycle for a cohort",
)
async def update_cohort_cycle(
    cohort: str,
    payload: CohortCycleUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role != RoleEnum.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    normalized = cohort.upper()

    match_query = select(func.count(Group.group_id)).where(
        func.upper(Group.cohort) == normalized
    )
    total = (await db.execute(match_query)).scalar() or 0

    if total == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No groups found for cohort {normalized}",
        )

    await db.execute(
        update(Group)
        .where(func.upper(Group.cohort) == normalized)
        .values(fyp_cycle=payload.target_cycle, updated_at=datetime.utcnow())
    )

    await db.commit()

    return CohortCycleUpdateResponse(
        message=(
            f"Updated {total} group{'s' if total == 1 else 's'} to {payload.target_cycle.value.upper()}"
        ),
        cohort=normalized,
        target_cycle=payload.target_cycle,
        updated_count=total,
    )


# app/api/http/admin_groups.py


@router.get("/groups/{group_id}", response_model=AdminGroupProfileResponse)
async def get_admin_group_profile(
    group_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Admin-only: Fetches group profile with detailed student academic info."""
    if current_user.role != RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Admin only")

    # 1. Initialize variables early taake 'not defined' error na aaye
    supervisors = {"primary": None, "co_supervisors": []}
    project_info = None
    formatted_members = []

    # 2. Fetch Group with all relationships
    query = (
        select(Group)
        .options(
            selectinload(Group.project).selectinload(Project.domains),
            selectinload(Group.project).selectinload(Project.industry),
            selectinload(Group.members)
            .joinedload(GroupMember.student)
            .joinedload(Student.user),
            selectinload(Group.supervisor).joinedload(Faculty.user),
            selectinload(Group.co_supervisors).joinedload(Faculty.user),
        )
        .where(Group.group_id == group_id)
    )

    result = await db.execute(query)
    group = result.scalars().first()

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # 3. Build detailed members list
    for m in group.members:
        s = m.student
        u = s.user
        formatted_members.append(
            AdminGroupMemberInfo(
                user_id=u.user_id,
                full_name=u.full_name,
                avatar_initial=u.full_name[0].upper() if u.full_name else "?",
                avatar_url=u.profile_avatar,
                joined_at=m.joined_at,
                roll_number=s.roll_number,
                department=s.department or "CS",
                cgpa=s.cgpa or 0.0,
                experience=s.experience,
                skills=s.skills or [],
                portfolio_projects=s.portfolio_projects or [],
            )
        )

    # 4. Format Supervisor details
    if group.supervisor:
        sup_u = group.supervisor.user
        supervisors["primary"] = SupervisorInfo(
            user_id=sup_u.user_id,
            full_name=sup_u.full_name,
            email=sup_u.email,
            designation=group.supervisor.designation,
            department=group.supervisor.department,
            avatar_url=sup_u.profile_avatar,
        )

    # 4b. Format Co-Supervisor details (List)
    if group.co_supervisors:
        for co_sup in group.co_supervisors:
            if co_sup.user:
                co_sup_u = co_sup.user
                supervisors["co_supervisors"].append(
                    SupervisorInfo(
                        user_id=co_sup_u.user_id,
                        full_name=co_sup_u.full_name,
                        email=co_sup_u.email,
                        designation=co_sup.designation,
                        department=co_sup.department,
                        avatar_url=co_sup_u.profile_avatar,
                    )
                )

    # 5. Format Project details
    if group.project:
        p = group.project
        project_info = ProjectInfo(
            project_id=p.project_id,
            fyp_id=p.fyp_id,
            name=p.name,
            description=p.description,
            objectives=p.objectives or [],
            tech_stack=p.tech_stack or [],
            project_type=str(p.project_type),
            repo_links=p.repo_links or [],
            updated_at=p.updated_at,
            domains=[DomainInfo(domain_id=d.domain_id, name=d.name) for d in p.domains],
            industry=(
                IndustryInfo(industry_id=p.industry.industry_id, name=p.industry.name)
                if p.industry
                else None
            ),
        )

    # Ab ye variables 100% defined hain!
    return AdminGroupProfileResponse(
        group={
            "group_id": str(group.group_id),
            "fyp_id": project_info.fyp_id if project_info else None,
            "project_name": project_info.name if project_info else "Unknown Project",
            "fyp_stage": group.fyp_stage,
            "fyp_cycle": group.fyp_cycle.value if group.fyp_cycle else None,
            "cohort_year": group.cohort_year,
        },
        members=formatted_members,
        supervisors=supervisors,
        project=project_info,
        invites={"pending_count": 0, "pending": []},
    )


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN SUPERVISOR ASSIGNMENT - Direct assignment without invite flow
# ─────────────────────────────────────────────────────────────────────────────
from app.schemas.admin_groups_schema import (
    AssignSupervisorRequest,
    AssignSupervisorResponse,
)


@router.post(
    "/groups/{group_id}/assign-supervisor",
    response_model=AssignSupervisorResponse,
    summary="Assign or update primary supervisor",
    description="Admin can assign a new primary supervisor or replace an existing one.",
)
async def assign_supervisor_to_group(
    group_id: UUID,
    body: AssignSupervisorRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Admin-only: Assign or update primary supervisor for a group.

    - Updates group.supervisor_id
    - Manages capacity_filled for both old and new supervisor
    """
    if current_user.role != RoleEnum.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    # 1. Validate group exists
    group_result = await db.execute(
        select(Group)
        .options(selectinload(Group.project))
        .where(Group.group_id == group_id)
    )
    group = group_result.scalars().first()

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # 2. Validate new supervisor exists
    supervisor_result = await db.execute(
        select(Faculty, User)
        .join(User, User.user_id == Faculty.user_id)
        .where(Faculty.user_id == body.supervisor_id)
    )
    row = supervisor_result.first()

    if not row:
        raise HTTPException(status_code=404, detail="Supervisor not found")

    new_supervisor, new_supervisor_user = row
    action = "assigned"

    # 3. Check if this supervisor is already co-supervisor of the same group
    current_cosupervisors = group.cosupervisor_ids or []
    if body.supervisor_id in current_cosupervisors:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This person is already assigned as co-supervisor. Remove them first or choose another supervisor.",
        )

    # 4. Check if assigning same person (no-op)
    if group.supervisor_id == body.supervisor_id:
        return AssignSupervisorResponse(
            message=f"{new_supervisor_user.full_name} is already the supervisor",
            group_id=str(group_id),
            project_name=group.project.name if group.project else "Unknown Project",
            supervisor_id=str(body.supervisor_id),
            supervisor_name=new_supervisor_user.full_name,
            role="supervisor",
        )

    # 5. If replacing existing supervisor, decrement their capacity first
    if group.supervisor_id is not None:
        action = "updated"
        old_supervisor_id = group.supervisor_id

        # Decrement old supervisor's capacity
        await db.execute(
            update(Faculty)
            .where(Faculty.user_id == old_supervisor_id)
            .values(capacity_filled=Faculty.capacity_filled - 1)
        )

    # 6. Check new supervisor's capacity (safe access)
    capacity_filled = (
        new_supervisor.capacity_filled
        if new_supervisor.capacity_filled is not None
        else 0
    )
    capacity_max = (
        new_supervisor.capacity_max if new_supervisor.capacity_max is not None else 5
    )

    if capacity_filled >= capacity_max:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Supervisor has reached maximum capacity ({capacity_max} groups).",
        )

    # 7. Assign new supervisor
    group.supervisor_id = body.supervisor_id
    group.updated_at = datetime.utcnow()

    # Explicitly mark group as modified just in case
    db.add(group)

    # Increment new supervisor's capacity (handle None case)
    await db.execute(
        update(Faculty)
        .where(Faculty.user_id == body.supervisor_id)
        .values(capacity_filled=func.coalesce(Faculty.capacity_filled, 0) + 1)
    )

    await db.commit()

    return AssignSupervisorResponse(
        message=f"Successfully {action} {new_supervisor_user.full_name} as supervisor",
        group_id=str(group_id),
        project_name=group.project.name if group.project else "Unknown Project",
        supervisor_id=str(body.supervisor_id),
        supervisor_name=new_supervisor_user.full_name,
        role="supervisor",
    )


@router.post(
    "/groups/{group_id}/assign-cosupervisor",
    response_model=AssignSupervisorResponse,
    summary="Add co-supervisor",
    description="Admin can add a co-supervisor to a group.",
)
async def assign_cosupervisor_to_group(
    group_id: UUID,
    body: AssignSupervisorRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Admin-only: Add a co-supervisor to a group.

    - Adds to group.cosupervisor_ids array
    - No capacity changes
    """
    if current_user.role != RoleEnum.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    # 1. Validate group exists
    group_result = await db.execute(
        select(Group)
        .options(selectinload(Group.project))
        .where(Group.group_id == group_id)
    )
    group = group_result.scalars().first()

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # 2. Validate supervisor exists
    supervisor_result = await db.execute(
        select(Faculty, User)
        .join(User, User.user_id == Faculty.user_id)
        .where(Faculty.user_id == body.supervisor_id)
    )
    row = supervisor_result.first()

    if not row:
        raise HTTPException(status_code=404, detail="Supervisor not found")

    new_supervisor, new_supervisor_user = row

    # 3. Check if this person is already the primary supervisor
    if group.supervisor_id == body.supervisor_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This person is already assigned as primary supervisor. Cannot be both.",
        )

    # 4. Initialize cosupervisor_ids array if None
    current_cosupervisors = group.cosupervisor_ids or []

    # 5. Check if already a co-supervisor
    if body.supervisor_id in current_cosupervisors:
        return AssignSupervisorResponse(
            message=f"{new_supervisor_user.full_name} is already a co-supervisor",
            group_id=str(group_id),
            project_name=group.project.name if group.project else "Unknown Project",
            supervisor_id=str(body.supervisor_id),
            supervisor_name=new_supervisor_user.full_name,
            role="cosupervisor",
        )

    # 6. Add to co-supervisors array (no capacity changes)
    # Be explicit with list conversion and flag_modified for ARRAY columns
    new_list = list(current_cosupervisors) + [body.supervisor_id]
    group.cosupervisor_ids = new_list
    group.updated_at = datetime.utcnow()

    flag_modified(group, "cosupervisor_ids")
    db.add(group)

    await db.commit()

    return AssignSupervisorResponse(
        message=f"Successfully added {new_supervisor_user.full_name} as co-supervisor",
        group_id=str(group_id),
        project_name=group.project.name if group.project else "Unknown Project",
        supervisor_id=str(body.supervisor_id),
        supervisor_name=new_supervisor_user.full_name,
        role="cosupervisor",
    )


@router.delete(
    "/groups/{group_id}/remove-supervisor",
    summary="Remove primary supervisor",
    description="Admin can remove the primary supervisor from a group.",
)
async def remove_supervisor_from_group(
    group_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Admin-only: Remove primary supervisor.

    - Clears group.supervisor_id
    - Decrements capacity_filled
    """
    if current_user.role != RoleEnum.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    group_result = await db.execute(select(Group).where(Group.group_id == group_id))
    group = group_result.scalars().first()

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    if group.supervisor_id is None:
        raise HTTPException(status_code=400, detail="Group has no supervisor to remove")

    old_supervisor_id = group.supervisor_id

    # Decrement capacity_filled
    await db.execute(
        update(Faculty)
        .where(Faculty.user_id == old_supervisor_id)
        .values(capacity_filled=Faculty.capacity_filled - 1)
    )

    group.supervisor_id = None
    group.updated_at = datetime.utcnow()

    await db.commit()
    return {
        "message": "Successfully removed supervisor from group",
        "group_id": str(group_id),
    }


@router.delete(
    "/groups/{group_id}/remove-cosupervisor",
    summary="Remove co-supervisor",
    description="Admin can remove a specific co-supervisor from a group.",
)
async def remove_cosupervisor_from_group(
    group_id: UUID,
    supervisor_id: UUID = Query(..., description="UUID of the co-supervisor to remove"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Admin-only: Remove a specific co-supervisor.

    - Removes supervisor_id from cosupervisor_ids array
    - No capacity changes
    """
    if current_user.role != RoleEnum.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    group_result = await db.execute(select(Group).where(Group.group_id == group_id))
    group = group_result.scalars().first()

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    current_cosupervisors = group.cosupervisor_ids or []

    if supervisor_id not in current_cosupervisors:
        raise HTTPException(
            status_code=404,
            detail="This supervisor is not a co-supervisor of this group",
        )

    # Remove from array (no capacity changes)
    new_list = [s for s in current_cosupervisors if s != supervisor_id]
    group.cosupervisor_ids = new_list
    group.updated_at = datetime.utcnow()

    flag_modified(group, "cosupervisor_ids")
    db.add(group)

    await db.commit()
    return {
        "message": "Successfully removed co-supervisor from group",
        "group_id": str(group_id),
        "removed_supervisor_id": str(supervisor_id),
    }
