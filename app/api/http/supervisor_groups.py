# app/api/http/supervisor_groups.py
"""
Supervisor Groups API

Provides endpoints for supervisors to:
  1. View all their assigned groups as directory cards.
  2. View a single group's full profile by group_id.
"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.types import Text as SQLText

from app.auth.supabase_auth import get_current_user
from app.db import get_db
from app.models.group import Group, GroupMember
from app.models.project import Project
from app.models.student import Student
from app.models.supervisor import Supervisor
from app.models.user import RoleEnum, User
from app.schemas.supervisor_groups_schema import (
    DomainInfo,
    GroupDirectoryCard,
    GroupProfileGroupInfo,
    GroupProfileMember,
    GroupProfileProject,
    GroupProfileSupervisor,
    IndustryInfo,
    RepoLink,
    SupervisorGroupDropdownItem,
    SupervisorGroupDropdownResponse,
    SupervisorGroupInfo,
    SupervisorGroupMember,
    SupervisorGroupProfileResponse,
    SupervisorGroupProject,
    SupervisorGroupsDirectoryResponse,
)

router = APIRouter(prefix="/supervisors", tags=["supervisor-groups"])


# ─────────────────────────────────────────────────────────────────────────────
# Helper: normalize JSONB tech_stack to a flat list of strings
# ─────────────────────────────────────────────────────────────────────────────
def _normalize_tech_stack(raw) -> List[str]:
    """Convert JSONB tech_stack (list or dict) into a flat string list."""
    if isinstance(raw, list):
        return [str(t) for t in raw]
    if isinstance(raw, dict):
        out: List[str] = []
        for v in raw.values():
            if isinstance(v, list):
                out.extend(str(t) for t in v)
        return out
    return []


# ─────────────────────────────────────────────────────────────────────────────
# 1. Directory listing — GET /supervisors/my-groups
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/my-groups",
    response_model=SupervisorGroupsDirectoryResponse,
    summary="Get supervisor's assigned groups",
    description=(
        "Returns all groups assigned to the logged-in supervisor as directory cards. "
        "Supports optional search across project name, tech stack, and member names."
    ),
)
async def get_supervisor_groups(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    search: Optional[str] = Query(
        None,
        min_length=1,
        max_length=100,
        description="Search across project name, tech stack, and member names",
    ),
):
    """
    Supervisor-only: Fetch all groups where this supervisor is the primary supervisor.
    Optionally filter by a search term.
    """

    # 1. Role check
    if current_user.role != RoleEnum.supervisor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only supervisors can access this endpoint",
        )

    # 2. Query groups with members + project eager-loaded
    query = (
        select(Group)
        .options(
            selectinload(Group.members)
            .joinedload(GroupMember.student)
            .joinedload(Student.user),
            selectinload(Group.project),
        )
        .outerjoin(Project, Project.group_id == Group.group_id)
        .where(Group.supervisor_id == current_user.user_id)
    )

    # 3. Apply search filter if provided
    if search:
        s = f"%{search.strip()}%"

        # Subquery: does any member's name match?
        member_name_exists = (
            select(GroupMember.group_id)
            .join(Student, Student.user_id == GroupMember.student_id)
            .join(User, User.user_id == Student.user_id)
            .where(
                GroupMember.group_id == Group.group_id,
                User.full_name.ilike(s),
            )
            .correlate(Group)
            .exists()
        )

        query = query.where(
            or_(
                Project.name.ilike(s),
                Project.tech_stack.cast(SQLText).ilike(s),
                member_name_exists,
            )
        )

    query = query.order_by(Group.updated_at.desc())

    result = await db.execute(query)
    groups = result.scalars().unique().all()

    # 4. Build response cards
    cards: List[GroupDirectoryCard] = []

    for group in groups:
        group_info = SupervisorGroupInfo(
            group_id=str(group.group_id),
            project_name=group.project.name if group.project else "Unknown Project",
            fyp_stage=group.fyp_stage,
            fyp_cycle=group.fyp_cycle.value if group.fyp_cycle else None,
            cohort_year=group.cohort_year,
        )

        members: List[SupervisorGroupMember] = []
        for m in group.members:
            student = m.student
            user = student.user if student else None
            if user:
                members.append(
                    SupervisorGroupMember(
                        student_id=str(student.user_id),
                        full_name=user.full_name,
                    )
                )

        project_info = None
        if group.project:
            p = group.project
            project_info = SupervisorGroupProject(
                project_id=str(p.project_id),
                fyp_id=p.fyp_id,
                name=p.name,
                description=p.description,
                project_type=str(p.project_type) if p.project_type else None,
                tech_stack=_normalize_tech_stack(p.tech_stack),
            )

        cards.append(
            GroupDirectoryCard(
                group=group_info,
                members=members,
                project=project_info,
            )
        )

    return SupervisorGroupsDirectoryResponse(group_directory=cards)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Dropdown listing — GET /supervisors/my-groups/dropdown
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/my-groups/dropdown",
    response_model=SupervisorGroupDropdownResponse,
    summary="Get simple list of supervisor's groups for dropdowns",
    description="Returns a lightweight list of groups (id and name) where the user is a primary or co-supervisor.",
)
async def get_supervisor_groups_dropdown(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Supervisor-only: Fetch lightweight list of groups for dropdowns.
    """
    # 1. Role check
    if current_user.role != RoleEnum.supervisor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only supervisors can access this endpoint",
        )

    # 2. Query groups
    # We include groups where user is primary supervisor OR is in co-supervisors list
    query = (
        select(Group.group_id, Project.name.label("name"))
        .outerjoin(Project, Project.group_id == Group.group_id)
        .where(
            or_(
                Group.supervisor_id == current_user.user_id,
                Group.cosupervisor_ids.contains([current_user.user_id]),
            )
        )
        .order_by(Project.name.asc())
    )

    result = await db.execute(query)
    rows = result.all()

    # 3. Build response
    items = [
        SupervisorGroupDropdownItem(
            group_id=str(row.group_id),
            project_name=row.name or "Unknown Project",
        )
        for row in rows
    ]

    # Append "All Groups" option at the end
    items.append(
        SupervisorGroupDropdownItem(
            group_id="all",
            project_name="All Groups",
        )
    )

    return SupervisorGroupDropdownResponse(groups=items)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Group profile detail — GET /supervisors/my-groups/{group_id}
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/my-groups/{group_id}",
    response_model=SupervisorGroupProfileResponse,
    summary="Get detailed group profile",
    description=(
        "Returns the full profile for a single group assigned to the supervisor, "
        "including members, project details (domains, industry, objectives, repo links), "
        "and supervisor/co-supervisor information."
    ),
)
async def get_supervisor_group_profile(
    group_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Supervisor-only: Fetch full profile of a group by its ID.

    Returns:
    - Group metadata
    - Full project details (domains, industry, objectives, tech_stack, repo_links)
    - Members with email
    - Primary & co-supervisors
    """

    # 1. Role check
    if current_user.role != RoleEnum.supervisor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only supervisors can access this endpoint",
        )

    # 2. Fetch the group with all relationships eager-loaded
    query = (
        select(Group)
        .options(
            # Members → student → user
            selectinload(Group.members)
            .joinedload(GroupMember.student)
            .joinedload(Student.user),
            # Project → domains + industry
            selectinload(Group.project).selectinload(Project.domains),
            selectinload(Group.project).selectinload(Project.industry),
            # Primary supervisor → user
            selectinload(Group.supervisor).joinedload(Supervisor.user),
            # Co-supervisors → user
            selectinload(Group.co_supervisors).joinedload(Supervisor.user),
        )
        .where(Group.group_id == group_id)
    )

    result = await db.execute(query)
    group = result.scalars().first()

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found",
        )

    # 3. Verify supervisor is assigned to this group (primary or co-supervisor)
    is_primary = group.supervisor_id == current_user.user_id
    is_co = group.cosupervisor_ids and current_user.user_id in group.cosupervisor_ids
    if not is_primary and not is_co:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not assigned to this group",
        )

    # 4. Build group info
    group_info = GroupProfileGroupInfo(
        group_id=str(group.group_id),
        project_name=group.project.name if group.project else "Unknown Project",
        fyp_stage=group.fyp_stage,
        fyp_cycle=group.fyp_cycle.value if group.fyp_cycle else None,
        cohort_year=group.cohort_year,
    )

    # 5. Build members list
    members: List[GroupProfileMember] = []
    for m in group.members:
        student = m.student
        user = student.user if student else None
        if user:
            members.append(
                GroupProfileMember(
                    student_id=str(student.user_id),
                    full_name=user.full_name,
                    email=user.email,
                )
            )

    # 6. Build project details
    project_info = None
    if group.project:
        p = group.project

        domains = [
            DomainInfo(domain_id=str(d.domain_id), name=d.name)
            for d in (p.domains or [])
        ]

        industry = None
        if p.industry:
            industry = IndustryInfo(
                industry_id=str(p.industry.industry_id),
                name=p.industry.name,
            )

        # Normalize repo_links from JSONB
        repo_links: List[RepoLink] = []
        for link in p.repo_links or []:
            if isinstance(link, dict):
                repo_links.append(
                    RepoLink(label=link.get("label"), url=link.get("url", ""))
                )
            elif isinstance(link, str):
                repo_links.append(RepoLink(url=link))

        project_info = GroupProfileProject(
            project_id=str(p.project_id),
            name=p.name,
            description=p.description,
            project_type=str(p.project_type) if p.project_type else None,
            domains=domains,
            industry=industry,
            objectives=p.objectives or [],
            tech_stack=_normalize_tech_stack(p.tech_stack),
            repo_links=repo_links,
            last_updated=p.updated_at,
        )

    # 7. Build supervisors list
    supervisors: List[GroupProfileSupervisor] = []

    if group.supervisor and group.supervisor.user:
        sup_user = group.supervisor.user
        supervisors.append(
            GroupProfileSupervisor(
                user_id=str(sup_user.user_id),
                name=sup_user.full_name,
                email=sup_user.email,
                type="primary",
            )
        )

    if group.co_supervisors:
        for co_sup in group.co_supervisors:
            if co_sup.user:
                supervisors.append(
                    GroupProfileSupervisor(
                        user_id=str(co_sup.user.user_id),
                        name=co_sup.user.full_name,
                        email=co_sup.user.email,
                        type="co_supervisor",
                    )
                )

    return SupervisorGroupProfileResponse(
        group=group_info,
        project=project_info,
        members=members,
        supervisors=supervisors,
    )
