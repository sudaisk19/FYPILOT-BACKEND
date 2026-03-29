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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase_auth import get_current_user
from app.db import get_db
from app.models.group import InviteStatusEnum
from app.models.request import Request
from app.models.user import RoleEnum, User
from app.repositories.group_repository import group_repository
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
    if current_user.role != RoleEnum.faculty:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Faculty only",
        )

    # 2. Active check
    if not current_user.faculty_profile or not current_user.faculty_profile.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your faculty account is inactive. Contact an administrator.",
        )

    # 3. Supervisor privilege check
    if (
        not current_user.faculty_profile
        or not current_user.faculty_profile.is_supervisor
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only faculty with supervisor privileges can view their supervised groups",
        )

    # 2. Query groups via repository
    groups = await group_repository.get_supervisor_assigned_groups_directory(
        db, current_user.user_id, search
    )

    # 4. Build response cards
    cards: List[GroupDirectoryCard] = []

    for group in groups:
        group_info = SupervisorGroupInfo(
            group_id=str(group.group_id),
            fyp_id=group.project.fyp_id if group.project else None,
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
    if current_user.role != RoleEnum.faculty:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Faculty only",
        )

    # 2. Active check
    if not current_user.faculty_profile or not current_user.faculty_profile.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your faculty account is inactive. Contact an administrator.",
        )

    # 3. Supervisor privilege check
    if (
        not current_user.faculty_profile
        or not current_user.faculty_profile.is_supervisor
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only faculty with supervisor privileges can access groups dropdown",
        )

    # 2. Query groups via repository
    rows = await group_repository.get_supervisor_assigned_groups_dropdown(
        db, current_user.user_id
    )

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
    if current_user.role != RoleEnum.faculty:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Faculty only",
        )

    # 2. Active check
    if not current_user.faculty_profile or not current_user.faculty_profile.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your faculty account is inactive. Contact an administrator.",
        )

    # 3. Supervisor privilege check
    if not current_user.faculty_profile.is_supervisor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only faculty with supervisor privileges can view group details",
        )

    # 2. Fetch the group with all relationships eager-loaded via repository
    group = await group_repository.get_group_profile_full(db, group_id)

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
        fyp_id=group.project.fyp_id if group.project else None,
        project_name=group.project.name if group.project else "Unknown Project",
        fyp_stage=group.fyp_stage,
        fyp_cycle=group.fyp_cycle.value if group.fyp_cycle else None,
        cohort_year=group.cohort_year,
        supervisor_acceptance_feedback=None,
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

    # 8. Get latest acceptance feedback (if any) for the primary supervisor
    supervisor_acceptance_feedback: Optional[str] = None
    if group.supervisor_id:
        feedback_result = await db.execute(
            select(Request.feedback)
            .where(
                Request.group_id == group.group_id,
                Request.faculty_id == group.supervisor_id,
                Request.status == InviteStatusEnum.accepted,
                Request.feedback.is_not(None),
            )
            .order_by(Request.updated_at.desc())
        )
        supervisor_acceptance_feedback = feedback_result.scalars().first()
        group_info.supervisor_acceptance_feedback = supervisor_acceptance_feedback

    return SupervisorGroupProfileResponse(
        group=group_info,
        project=project_info,
        members=members,
        supervisors=supervisors,
        supervisor_acceptance_feedback=supervisor_acceptance_feedback,
    )
