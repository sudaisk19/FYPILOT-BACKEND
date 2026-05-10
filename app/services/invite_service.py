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
from urllib.parse import urlparse

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


def _portfolio_projects_to_items(raw_portfolio_projects) -> List[PortfolioProject]:
    """Normalize stored portfolio projects into response items."""
    if not raw_portfolio_projects:
        return []

    if isinstance(raw_portfolio_projects, list):
        candidates = raw_portfolio_projects
    elif isinstance(raw_portfolio_projects, dict):
        if "links" in raw_portfolio_projects and isinstance(
            raw_portfolio_projects["links"], list
        ):
            candidates = [{"link": link} for link in raw_portfolio_projects["links"]]
        elif "projects" in raw_portfolio_projects and isinstance(
            raw_portfolio_projects["projects"], list
        ):
            candidates = raw_portfolio_projects["projects"]
        elif "items" in raw_portfolio_projects and isinstance(
            raw_portfolio_projects["items"], list
        ):
            candidates = raw_portfolio_projects["items"]
        if any(
            key in raw_portfolio_projects
            for key in ("title", "name", "link", "url", "repository", "repo_link")
        ):
            candidates = [raw_portfolio_projects]
        elif "links" not in raw_portfolio_projects:
            candidates = raw_portfolio_projects.values()
    else:
        return []

    portfolio_projects: List[PortfolioProject] = []
    for project in candidates:
        if not isinstance(project, dict):
            continue

        title = (
            project.get("title")
            or project.get("name")
            or project.get("project_name")
            or ""
        )
        link = (
            project.get("link")
            or project.get("url")
            or project.get("repository")
            or project.get("repo_link")
            or ""
        )

        title = str(title).strip()
        link = str(link).strip()
        if not title and link:
            parsed = urlparse(link)
            title = parsed.path.rstrip("/").split("/")[-1] if parsed.path else ""
            title = title or parsed.netloc or link
        if title or link:
            portfolio_projects.append(PortfolioProject(title=title, link=link))

    return portfolio_projects


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

    # 6. Role type
    request_type = (
        RequestTypeEnum.supervisor
        if role == "supervisor"
        else RequestTypeEnum.cosupervisor
    )

    # 7. Block only if there's already a pending or accepted request
    existing_pending = await request_repository.exists_pending(db, group_id, faculty_id)
    if existing_pending:
        raise ValueError("A pending request already exists for this supervisor")

    existing_accepted = (
        await request_repository.get_recent_by_group_supervisor_statuses(
            db, group_id, faculty_id, [InviteStatusEnum.accepted]
        )
    )
    if existing_accepted:
        raise ValueError(f"This supervisor has already been accepted as {role}")

    # 8. Always create a new request row (preserves history of all past requests)
    req = await request_repository.create(
        db, group_id, faculty_id, request_type, message=message
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
                feedback=req.feedback,
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
    feedback: Optional[str] = None,
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

    # Mark accepted with optional feedback
    await request_repository.update_status(
        db, request_id, InviteStatusEnum.accepted, feedback=feedback
    )
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
    feedback: str = "",
) -> dict:
    """Reject (decline) a pending supervisor request with mandatory feedback."""
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

    await request_repository.update_status(
        db, request_id, InviteStatusEnum.declined, feedback=feedback
    )
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
        portfolio_projects = _portfolio_projects_to_items(student.portfolio_projects)

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

    # Fetch all requests between this group and supervisor for history
    from sqlalchemy import select as sa_select

    from app.schemas.invite_schema import RequestSummaryItem

    all_requests_result = await db.execute(
        sa_select(Request)
        .where(
            Request.group_id == req.group_id,
            Request.faculty_id == req.faculty_id,
        )
        .order_by(Request.created_at.asc())
    )
    all_requests = all_requests_result.scalars().all()
    request_history = [
        RequestSummaryItem(
            request_id=r.request_id,
            requested_role=r.request_type.value,
            status=r.status.value,
            message=r.message,
            feedback=r.feedback,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in all_requests
    ]

    return SupervisorRequestDetailResponse(
        request_id=req.request_id,
        group_id=req.group_id,
        faculty_id=req.faculty_id,
        status=req.status.value,
        message=req.message,
        feedback=req.feedback,
        created_at=req.created_at,
        expires_at=expires_at,
        project_brief=project_brief,
        project=project_detail,
        students=students,
        request_history=request_history,
    )
