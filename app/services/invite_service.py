# app/services/invite_service.py
"""
Invite Service

Business logic layer for supervisor invite/request operations.
Delegates all database access exclusively to the repository layer,
enforcing the Repository Pattern.
"""

from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from uuid import UUID

from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain import Domain
from app.models.faculty import Faculty
from app.models.group import Group, GroupMember, InviteStatusEnum
from app.models.project import Project, ProjectDomain, project_type_value
from app.models.request import Request, RequestTypeEnum
from app.models.student import Student
from app.models.user import User
from app.repositories.group_repository import group_repository
from app.repositories.request_repository import request_repository
from app.repositories.supervisor_repository import supervisor_repository
from app.schemas.invite_schema import (
    PendingInviteItem,
    PendingInvitesResponse,
    PortfolioProject,
    ProjectDetail,
    ProjectDomainInfo,
    SentRequestItem,
    SentRequestsResponse,
    StudentDetail,
    SupervisorRequestDetailResponse,
)
from app.services.mailer import (
    send_supervisor_accepted_email,
    send_supervisor_rejected_email,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _extract_role_val(role_attr) -> str:
    return role_attr.value if hasattr(role_attr, "value") else role_attr


# ---------------------------------------------------------------------------
# send invite
# ---------------------------------------------------------------------------


async def send_supervisor_invite_svc(
    db: AsyncSession,
    current_user: User,
    group_id: UUID,
    faculty_id: UUID,
    role: str,
    message: Optional[str],
) -> dict:
    """
    Validate and create a supervisor request from a student group.
    All DB reads go through repositories; write uses repository.create.
    """
    # 1. Membership check
    is_member = await group_repository.check_membership(
        db, group_id, current_user.user_id
    )
    if not is_member:
        raise PermissionError("You are not a member of this group")

    # 2. Load group
    grp = await group_repository.get_by_id(db, group_id)
    if not grp:
        raise LookupError("Group not found")

    # 3. Role constraint checks
    if role == "supervisor" and grp.supervisor_id is not None:
        raise ValueError("Group already has a supervisor")
    if (
        role == "cosupervisor"
        and grp.cosupervisor_ids
        and faculty_id in grp.cosupervisor_ids
    ):
        raise ValueError("This supervisor is already a co-supervisor for this group")
    if (
        role == "supervisor"
        and grp.cosupervisor_ids
        and faculty_id in grp.cosupervisor_ids
    ):
        raise ValueError(
            "This supervisor is already assigned as co-supervisor. "
            "Cannot assign same person as supervisor."
        )
    if role == "cosupervisor" and grp.supervisor_id == faculty_id:
        raise ValueError(
            "This supervisor is already assigned as supervisor. "
            "Cannot assign same person as co-supervisor."
        )

    # 4. Validate target faculty
    faculty_obj = await supervisor_repository.get_by_user_id(db, faculty_id)
    if not faculty_obj:
        raise LookupError("Faculty not found")
    if not faculty_obj.is_supervisor:
        raise PermissionError("This faculty member cannot be selected as a supervisor")

    # 5. Duplicate pending check
    already_pending = await request_repository.exists_pending(db, group_id, faculty_id)
    if already_pending:
        raise ValueError("A pending request already exists for this supervisor")

    # 6. Role enum
    if role not in ("supervisor", "cosupervisor"):
        raise ValueError("role must be 'supervisor' or 'cosupervisor'")
    request_type = (
        RequestTypeEnum.supervisor
        if role == "supervisor"
        else RequestTypeEnum.cosupervisor
    )

    # 7. Create
    req = await request_repository.create(
        db, group_id, faculty_id, request_type, message
    )
    await db.commit()

    return {"message": "Request sent", "role": role, "request_id": str(req.request_id)}


# ---------------------------------------------------------------------------
# list sent requests
# ---------------------------------------------------------------------------


async def list_sent_requests_svc(
    db: AsyncSession,
    current_user: User,
    group_id: UUID,
) -> SentRequestsResponse:
    """
    Return all (non-cancelled) requests sent by `group_id`.
    Membership gate applied here rather than in the router.
    """
    is_member = await group_repository.check_membership(
        db, group_id, current_user.user_id
    )
    if not is_member:
        raise PermissionError("You are not a member of this group")

    rows: List[Tuple[Request, Faculty, User]] = await request_repository.get_by_group(
        db, group_id, exclude_cancelled=True
    )

    items: List[SentRequestItem] = []
    for req, _faculty, user in rows:
        items.append(
            SentRequestItem(
                request_id=req.request_id,
                faculty_id=user.user_id,
                supervisor_name=user.full_name,
                requested_role=req.request_type.value,
                status=req.status.value,
                message=req.message,
                created_at=req.created_at,
                updated_at=req.updated_at,
            )
        )

    return SentRequestsResponse(group_id=group_id, requests=items)


# ---------------------------------------------------------------------------
# list pending invites for supervisor
# ---------------------------------------------------------------------------


async def _fetch_project_for_group(
    db: AsyncSession, group_id: UUID
) -> Tuple[Optional[str], Optional[str], List[str]]:
    """Return (project_name, project_type_str, domain_names) for a group."""
    try:
        result = await db.execute(select(Project).where(Project.group_id == group_id))
        project = result.scalars().first()
        if not project:
            return None, None, []
        project_type = project_type_value(project.project_type)
        domains_res = await db.execute(
            select(Domain)
            .join(ProjectDomain, ProjectDomain.domain_id == Domain.domain_id)
            .where(ProjectDomain.project_id == project.project_id)
        )
        domain_names = [d.name for d in domains_res.scalars().all()]
        return project.name, project_type, domain_names
    except Exception:
        return None, None, []


async def list_pending_invites_svc(
    db: AsyncSession,
    current_user: User,
) -> PendingInvitesResponse:
    """Return all pending requests addressed to `current_user` (a supervisor)."""
    rows: List[Tuple[Request, Group]] = (
        await request_repository.get_pending_for_supervisor(db, current_user.user_id)
    )

    items: List[PendingInviteItem] = []
    for req, group in rows:
        project_name, project_type, project_domains = await _fetch_project_for_group(
            db, req.group_id
        )
        items.append(
            PendingInviteItem(
                request_id=req.request_id,
                group_id=req.group_id,
                requested_role=req.request_type.value,
                created_at=req.created_at,
                project_name=project_name,
                project_type=project_type,
                project_domains=project_domains,
            )
        )

    return PendingInvitesResponse(requests=items)


# ---------------------------------------------------------------------------
# accept
# ---------------------------------------------------------------------------


async def accept_supervisor_request_svc(
    db: AsyncSession,
    current_user: User,
    request_id: UUID,
    background_tasks: BackgroundTasks,
) -> dict:
    """Accept a pending supervisor request; update group + faculty records."""
    req = await request_repository.get_for_supervisor_validation(
        db, request_id, current_user.user_id
    )
    if not req:
        raise LookupError("Request not found or already processed")

    group = await group_repository.get_with_project(db, req.group_id)
    role = (
        "supervisor"
        if req.request_type == RequestTypeEnum.supervisor
        else "cosupervisor"
    )

    if req.request_type == RequestTypeEnum.supervisor:
        # Set supervisor on group
        await group_repository.set_supervisor(db, req.group_id, current_user.user_id)
        # Increment capacity_filled on faculty
        from sqlalchemy import update as sa_update

        await db.execute(
            sa_update(Faculty)
            .where(Faculty.user_id == current_user.user_id)
            .values(capacity_filled=Faculty.capacity_filled + 1)
        )
        # Auto-decline OTHER pending supervisor requests for this group (excluding this one)
        from sqlalchemy import update as sa_update2

        await db.execute(
            sa_update2(Request)
            .where(
                Request.group_id == req.group_id,
                Request.request_type == RequestTypeEnum.supervisor,
                Request.request_id != request_id,
                Request.status == InviteStatusEnum.pending,
            )
            .values(status=InviteStatusEnum.declined, updated_at=datetime.utcnow())
        )

    elif req.request_type == RequestTypeEnum.cosupervisor:
        await group_repository.set_cosupervisor(db, req.group_id, current_user.user_id)

    # Mark accepted
    await request_repository.update_status(db, request_id, InviteStatusEnum.accepted)
    # Record who accepted
    req.updated_by = current_user.user_id
    await db.commit()

    # Email group members
    if group:
        member_rows = await group_repository.get_members_with_users(db, req.group_id)
        for user, _student, _member in member_rows:
            background_tasks.add_task(
                send_supervisor_accepted_email,
                user.email,
                group.project.name if group.project else "Unknown Project",
                current_user.full_name,
                role,
            )

    return {"message": "Request accepted"}


# ---------------------------------------------------------------------------
# reject
# ---------------------------------------------------------------------------


async def reject_supervisor_request_svc(
    db: AsyncSession,
    current_user: User,
    request_id: UUID,
    background_tasks: BackgroundTasks,
) -> dict:
    """Reject (decline) a pending supervisor request."""
    req = await request_repository.get_for_supervisor_validation(
        db, request_id, current_user.user_id
    )
    if not req:
        raise LookupError("Request not found or already processed")

    group = await group_repository.get_with_project(db, req.group_id)
    role = (
        "supervisor"
        if req.request_type == RequestTypeEnum.supervisor
        else "cosupervisor"
    )

    await request_repository.update_status(db, request_id, InviteStatusEnum.declined)
    req.updated_by = current_user.user_id
    await db.commit()

    if group:
        member_rows = await group_repository.get_members_with_users(db, req.group_id)
        for user, _student, _member in member_rows:
            background_tasks.add_task(
                send_supervisor_rejected_email,
                user.email,
                group.project.name if group.project else "Unknown Project",
                current_user.full_name,
                role,
            )

    return {"message": "Request rejected"}


# ---------------------------------------------------------------------------
# cancel
# ---------------------------------------------------------------------------


async def cancel_invite_svc(
    db: AsyncSession,
    current_user: User,
    request_id: UUID,
) -> dict:
    """Student cancels (permanently deletes) a pending request."""
    req = await request_repository.get_by_id(db, request_id)
    if not req or req.status != InviteStatusEnum.pending:
        raise LookupError("Request not found or already processed")

    is_member = await group_repository.check_membership(
        db, req.group_id, current_user.user_id
    )
    if not is_member:
        raise PermissionError("You are not a member of this group")

    await request_repository.delete(db, request_id)
    await db.commit()
    return {"message": "Request cancelled"}


# ---------------------------------------------------------------------------
# get request details for supervisor
# ---------------------------------------------------------------------------


async def get_request_details_svc(
    db: AsyncSession,
    current_user: User,
    request_id: UUID,
) -> SupervisorRequestDetailResponse:
    """Return full group/project/student details for a supervisor request."""
    # Use a direct query scoped to this supervisor (not just pending)
    result = await db.execute(
        select(Request).where(
            Request.request_id == request_id,
            Request.faculty_id == current_user.user_id,
        )
    )
    req = result.scalars().first()
    if not req:
        raise LookupError("Request not found or you don't have access to it")

    expires_at = req.created_at + timedelta(days=7)

    group = await group_repository.get_by_id(db, req.group_id)
    if not group:
        raise LookupError("Group not found")

    # Project info
    project_detail: Optional[ProjectDetail] = None
    project_brief: Optional[str] = None

    try:
        proj_result = await db.execute(
            select(Project).where(Project.group_id == req.group_id)
        )
        project_data = proj_result.scalars().first()
        if project_data:
            domains_res = await db.execute(
                select(Domain)
                .join(ProjectDomain, ProjectDomain.domain_id == Domain.domain_id)
                .where(ProjectDomain.project_id == project_data.project_id)
            )
            domains = [
                ProjectDomainInfo(name=d.name) for d in domains_res.scalars().all()
            ]
            objectives = (
                project_data.objectives
                if isinstance(project_data.objectives, list)
                else []
            )
            tech_stack = (
                project_data.tech_stack
                if isinstance(project_data.tech_stack, list)
                else []
            )
            repo_links = (
                project_data.repo_links
                if isinstance(project_data.repo_links, list)
                else []
            )
            project_brief = project_data.description
            project_detail = ProjectDetail(
                name=project_data.name,
                description=project_data.description,
                objectives=objectives,
                tech_stack=tech_stack,
                project_type=project_type_value(project_data.project_type),
                github_repositories=repo_links,
                domains=domains,
            )
    except Exception:
        pass

    # Members
    members_result = await db.execute(
        select(GroupMember, User, Student)
        .join(User, User.user_id == GroupMember.student_id)
        .join(Student, Student.user_id == User.user_id)
        .where(GroupMember.group_id == req.group_id)
        .order_by(GroupMember.joined_at.asc())
    )
    members_data = members_result.all()

    students = []
    for member, user, student in members_data:
        portfolio_projects = []
        if student.portfolio_projects and isinstance(student.portfolio_projects, list):
            for proj in student.portfolio_projects:
                if isinstance(proj, dict):
                    portfolio_projects.append(
                        PortfolioProject(
                            title=proj.get("title", ""),
                            link=proj.get("link", ""),
                        )
                    )

        students.append(
            StudentDetail(
                user_id=user.user_id,
                name=user.full_name,
                roll_number=student.roll_number,
                department=student.department,
                cgpa=float(student.cgpa) if student.cgpa else None,
                skills=student.skills or [],
                skills_levels=student.skills_levels_normalized,
                interests=student.interests or [],
                experience=student.experience,
                portfolio_projects=portfolio_projects,
            )
        )

    return SupervisorRequestDetailResponse(
        request_id=req.request_id,
        group_id=req.group_id,
        requested_role=req.request_type.value,
        status=req.status.value,
        message=req.message,
        created_at=req.created_at,
        expires_at=expires_at,
        project_brief=project_brief,
        project=project_detail,
        students=students,
    )
