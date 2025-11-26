# app/api/http/supervisor_invites.py
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase_auth import get_current_user
from app.db import get_db
from app.models.domain import Domain
from app.models.group import Group, GroupMember, InviteStatusEnum
from app.models.project import Project, ProjectDomain
from app.models.request import Request, RequestTypeEnum
from app.models.student import Student
from app.models.supervisor import Supervisor
from app.models.user import User
from app.schemas.invite_schema import (
    PendingInviteItem,
    PendingInvitesResponse,
    PortfolioProject,
    ProjectDetail,
    ProjectDomainInfo,
    SendSupervisorInviteRequest,
    SentRequestItem,
    SentRequestsResponse,
    StudentDetail,
    SupervisorRequestDetailResponse,
)

router = APIRouter(prefix="/invites", tags=["supervisor-invites"])


@router.post("/groups/{group_id}/supervisor", status_code=status.HTTP_201_CREATED)
async def send_supervisor_invite(
    group_id: UUID,
    body: SendSupervisorInviteRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # Only students can send, and must be member of the group
    if current_user.role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students can send invites",
        )

    membership = await db.execute(
        select(GroupMember).where(
            GroupMember.group_id == group_id,
            GroupMember.student_id == current_user.user_id,
        )
    )
    if membership.scalars().first() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this group",
        )

    # Validate requested role constraints
    grp = (
        (await db.execute(select(Group).where(Group.group_id == group_id)))
        .scalars()
        .first()
    )
    if not grp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Group not found"
        )

    if body.role == "supervisor" and grp.supervisor_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Group already has a supervisor",
        )
    if body.role == "cosupervisor" and grp.cosupervisor_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Group already has a co-supervisor",
        )

    # Prevent same supervisor from being both primary and co (aligns with DB constraint)
    if body.role == "supervisor" and grp.cosupervisor_id == body.supervisor_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This supervisor is already assigned as co-supervisor. Cannot assign same person as supervisor.",
        )
    if body.role == "cosupervisor" and grp.supervisor_id == body.supervisor_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This supervisor is already assigned as supervisor. Cannot assign same person as co-supervisor.",
        )

    # Check for existing pending request (cancelled requests are deleted, so no need to check for them)
    existing_request = await db.execute(
        select(Request).where(
            Request.group_id == group_id,
            Request.supervisor_id == body.supervisor_id,
            Request.status == InviteStatusEnum.pending,
        )
    )
    if existing_request.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A pending request already exists for this supervisor",
        )

    # Create request in requests table
    if body.role not in ("supervisor", "cosupervisor"):
        raise HTTPException(
            status_code=400, detail="role must be 'supervisor' or 'cosupervisor'"
        )
    request_type = (
        RequestTypeEnum.supervisor
        if body.role == "supervisor"
        else RequestTypeEnum.cosupervisor
    )
    request = Request(
        group_id=group_id,
        supervisor_id=body.supervisor_id,
        request_type=request_type,
        status=InviteStatusEnum.pending,
        message=getattr(body, "message", None),
    )
    db.add(request)
    await db.commit()

    return {
        "message": "Request sent",
        "role": body.role,
        "request_id": str(request.request_id),
    }


@router.get(
    "/groups/{group_id}/supervisor/requests", response_model=SentRequestsResponse
)
async def list_sent_requests(
    group_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    List all supervisor requests sent by a group.

    This endpoint allows students (group members) to see all requests their group
    has sent to supervisors, including their status. This is useful for:
    - Checking if a request already exists for a supervisor
    - Getting the request_id to cancel a request
    - Toggling button text between "Send Request" and "Cancel Request"
    - Displaying request status (pending, accepted, declined, cancelled)
    """
    # Only students can view sent requests
    if current_user.role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students can view sent requests",
        )

    # Check membership
    membership = await db.execute(
        select(GroupMember).where(
            GroupMember.group_id == group_id,
            GroupMember.student_id == current_user.user_id,
        )
    )
    if membership.scalars().first() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this group",
        )

    # Fetch all requests sent by this group (excluding cancelled - they're deleted)
    # Only show pending, accepted, and declined requests
    requests_result = await db.execute(
        select(Request, Supervisor, User)
        .join(Supervisor, Supervisor.user_id == Request.supervisor_id)
        .join(User, User.user_id == Supervisor.user_id)
        .where(
            Request.group_id == group_id,
            Request.status
            != InviteStatusEnum.cancelled,  # Exclude cancelled (though they should be deleted)
        )
        .order_by(Request.created_at.desc())
    )
    rows = requests_result.all()

    items: list[SentRequestItem] = []
    for req, supervisor, user in rows:
        items.append(
            SentRequestItem(
                request_id=req.request_id,
                supervisor_id=user.user_id,
                supervisor_name=user.full_name,
                requested_role=req.request_type.value,
                status=req.status.value,
                message=req.message,
                created_at=req.created_at,
                updated_at=req.updated_at,
            )
        )

    return SentRequestsResponse(group_id=group_id, requests=items)


@router.get("/supervisor/pending/requests", response_model=PendingInvitesResponse)
async def list_pending_invites_for_supervisor(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if current_user.role != "supervisor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only supervisors can view invites",
        )

    # Fetch pending requests for this supervisor with group info
    requests_result = await db.execute(
        select(Request, Group)
        .join(Group, Group.group_id == Request.group_id)
        .where(
            Request.supervisor_id == current_user.user_id,
            Request.status == InviteStatusEnum.pending,
        )
        .order_by(Request.created_at.desc())
    )
    rows = requests_result.all()

    items: list[PendingInviteItem] = []
    for req, group in rows:
        # Fetch project information for this group
        project_name = None
        project_type = None
        project_domains = []

        try:
            project_result = await db.execute(
                select(Project).where(Project.group_id == req.group_id)
            )
            project = project_result.scalars().first()

            if project:
                project_name = project.name
                project_type = (
                    str(project.project_type) if project.project_type else None
                )

                # Fetch project domains
                domains_result = await db.execute(
                    select(Domain)
                    .join(ProjectDomain, ProjectDomain.domain_id == Domain.domain_id)
                    .where(ProjectDomain.project_id == project.project_id)
                )
                project_domains = [d.name for d in domains_result.scalars().all()]
        except Exception:
            # Handle potential enum issues with raw SQL
            from sqlalchemy import text

            try:
                raw_project = await db.execute(
                    text(
                        """
                        SELECT project_id, name, project_type
                        FROM projects 
                        WHERE group_id = :group_id
                    """
                    ),
                    {"group_id": req.group_id},
                )
                raw_data = raw_project.fetchone()
                if raw_data:
                    project_name = raw_data[1]
                    project_type = str(raw_data[2]) if raw_data[2] else None

                    # Fetch domains using project_id
                    if raw_data[0]:
                        raw_domains = await db.execute(
                            text(
                                """
                                SELECT d.name 
                                FROM domains d
                                JOIN project_domains pd ON d.domain_id = pd.domain_id
                                WHERE pd.project_id = :project_id
                            """
                            ),
                            {"project_id": raw_data[0]},
                        )
                        project_domains = [row[0] for row in raw_domains.fetchall()]
            except Exception:
                # If project fetch fails, continue with None values
                pass

        items.append(
            PendingInviteItem(
                request_id=req.request_id,
                group_id=req.group_id,
                group_name=group.name,
                requested_role=req.request_type.value,
                created_at=req.created_at,
                project_name=project_name,
                project_type=project_type,
                project_domains=project_domains,
            )
        )
    return PendingInvitesResponse(requests=items)


@router.post("/supervisor/{request_id}/accept")
async def accept_invite(
    request_id: UUID = Path(...),
    current_user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
):
    if current_user.role != "supervisor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only supervisors can accept invites",
        )
    # Load request
    request_result = await db.execute(
        select(Request).where(Request.request_id == request_id)
    )
    req = request_result.scalars().first()
    if not req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Request not found"
        )
    if req.supervisor_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not your request"
        )
    if req.status != InviteStatusEnum.pending:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Request already processed"
        )
    # Check if supervisor is already assigned to the other role (aligns with DB constraint)
    grp = (
        (await db.execute(select(Group).where(Group.group_id == req.group_id)))
        .scalars()
        .first()
    )
    if not grp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Group not found"
        )
    if (
        req.request_type == RequestTypeEnum.supervisor
        and grp.cosupervisor_id == current_user.user_id
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You are already assigned as cosupervisor. Cannot be both supervisor and cosupervisor.",
        )
    if (
        req.request_type == RequestTypeEnum.cosupervisor
        and grp.supervisor_id == current_user.user_id
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You are already assigned as supervisor. Cannot be both supervisor and cosupervisor.",
        )
    # Update group record based on role
    if req.request_type == RequestTypeEnum.supervisor:
        await db.execute(
            update(Group)
            .where(Group.group_id == req.group_id)
            .values(supervisor_id=current_user.user_id)
        )
        # Increment supervisor capacity_filled
        from app.models.supervisor import Supervisor

        await db.execute(
            update(Supervisor)
            .where(Supervisor.user_id == current_user.user_id)
            .values(capacity_filled=Supervisor.capacity_filled + 1)
        )
    else:
        await db.execute(
            update(Group)
            .where(Group.group_id == req.group_id)
            .values(cosupervisor_id=current_user.user_id)
        )
    # Mark request accepted - use raw SQL to completely bypass any caching
    await db.execute(
        text(
            """
            UPDATE requests 
            SET status = 'accepted'::invite_status_enum,
                updated_at = :updated_at,
                updated_by = :updated_by
            WHERE request_id = :request_id
        """
        ),
        {
            "updated_at": datetime.utcnow(),
            "updated_by": current_user.user_id,
            "request_id": request_id,
        },
    )
    await db.commit()
    return {"message": "Request accepted", "role": req.request_type.value}


@router.post("/supervisor/{request_id}/reject")
async def reject_invite(
    request_id: UUID = Path(...),
    current_user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
):
    if current_user.role != "supervisor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only supervisors can reject invites",
        )

    # Load and update request
    request_result = await db.execute(
        select(Request).where(
            Request.request_id == request_id,
            Request.supervisor_id == current_user.user_id,
            Request.status == InviteStatusEnum.pending,
        )
    )
    req = request_result.scalars().first()

    if not req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found or already processed",
        )

    await db.execute(
        update(Request)
        .where(Request.request_id == request_id)
        .values(
            status=InviteStatusEnum.declined,
            updated_by=current_user.user_id,
            updated_at=datetime.utcnow(),
        )
    )
    await db.commit()

    return {"message": "Request rejected"}


@router.delete("/supervisor/{request_id}/cancel")
async def cancel_invite(
    request_id: UUID = Path(...),
    current_user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
):
    """
    Cancel (delete) a pending supervisor request.

    This endpoint completely removes the request from the requests table.
    After cancellation, the request will no longer appear in any lists,
    and the student can send a new request to the same supervisor.
    """
    # Fetch request
    req = (
        (await db.execute(select(Request).where(Request.request_id == request_id)))
        .scalars()
        .first()
    )
    if not req or req.status != InviteStatusEnum.pending:
        raise HTTPException(404, detail="Request not found or already processed")
    # Confirm student is a member of that group
    from app.models.group import GroupMember

    is_member = (
        (
            await db.execute(
                select(GroupMember).where(
                    GroupMember.group_id == req.group_id,
                    GroupMember.student_id == current_user.user_id,
                )
            )
        )
        .scalars()
        .first()
    )
    if not is_member:
        raise HTTPException(403, detail="You are not a member of this group")

    # Delete the request completely (not just update status)
    from sqlalchemy import delete

    await db.execute(delete(Request).where(Request.request_id == request_id))
    await db.commit()
    return {"message": "Request cancelled"}


@router.get(
    "/supervisor/{request_id}/details",
    response_model=SupervisorRequestDetailResponse,
)
async def get_request_details_for_supervisor(
    request_id: UUID = Path(...),
    current_user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
):
    """
    Get detailed group information for a supervisor request.

    This endpoint allows supervisors to view comprehensive information about
    a group that has sent them a request, including:
    - Request details (status, message, dates)
    - Project information (name, description, objectives, tech stack, domains)
    - All group members with their academic and professional details
    - Student skills, interests, experience, and portfolio projects

    Only supervisors can access this endpoint, and only for requests sent to them.
    """
    if current_user.role != "supervisor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only supervisors can view request details",
        )

    # Fetch the request and verify it belongs to this supervisor
    request_result = await db.execute(
        select(Request).where(
            Request.request_id == request_id,
            Request.supervisor_id == current_user.user_id,
        )
    )
    req = request_result.scalars().first()

    if not req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found or you don't have access to it",
        )

    # Calculate expires_at (7 days from created_at)
    from datetime import timedelta

    expires_at = req.created_at + timedelta(days=7)

    # Fetch group information
    group_result = await db.execute(select(Group).where(Group.group_id == req.group_id))
    group = group_result.scalars().first()

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Group not found"
        )

    # Fetch project information
    project_data = None
    project_detail = None
    project_brief = None

    try:
        project_result = await db.execute(
            select(Project).where(Project.group_id == req.group_id)
        )
        project_data = project_result.scalars().first()
    except Exception:
        # Handle potential enum issues
        from sqlalchemy import text

        raw_result = await db.execute(
            text(
                """
                SELECT project_id, name, description, objectives, tech_stack,
                       project_type, repo_links
                FROM projects 
                WHERE group_id = :group_id
            """
            ),
            {"group_id": req.group_id},
        )
        raw_data = raw_result.fetchone()
        if raw_data:
            # Create a simple object for project data
            class SimpleProject:
                def __init__(self, data):
                    self.project_id = data[0]
                    self.name = data[1]
                    self.description = data[2]
                    self.objectives = data[3]
                    self.tech_stack = data[4]
                    self.project_type = data[5]
                    self.repo_links = data[6]

            project_data = SimpleProject(raw_data)

    if project_data:
        # Get project domains
        domains_result = await db.execute(
            select(Domain)
            .join(ProjectDomain, ProjectDomain.domain_id == Domain.domain_id)
            .where(ProjectDomain.project_id == project_data.project_id)
        )
        domains = [
            ProjectDomainInfo(name=d.name) for d in domains_result.scalars().all()
        ]

        # Extract data safely
        objectives = (
            project_data.objectives if isinstance(project_data.objectives, list) else []
        )
        tech_stack = (
            project_data.tech_stack if isinstance(project_data.tech_stack, list) else []
        )
        repo_links = (
            project_data.repo_links if isinstance(project_data.repo_links, list) else []
        )
        project_type = (
            str(project_data.project_type) if project_data.project_type else None
        )

        project_brief = project_data.description
        project_detail = ProjectDetail(
            name=project_data.name,
            description=project_data.description,
            objectives=objectives,
            tech_stack=tech_stack,
            project_type=project_type,
            github_repositories=repo_links,
            domains=domains,
        )

    # Fetch all group members with their student and user details
    members_result = await db.execute(
        select(GroupMember, User, Student)
        .join(User, User.user_id == GroupMember.student_id)
        .join(Student, Student.user_id == User.user_id)
        .where(GroupMember.group_id == req.group_id)
        .order_by(GroupMember.joined_at.asc())
    )
    members_data = members_result.all()

    # Build students list with detailed information
    students = []
    for member, user, student in members_data:
        # Parse portfolio_projects if it exists
        portfolio_projects = []
        if student.portfolio_projects:
            if isinstance(student.portfolio_projects, list):
                for proj in student.portfolio_projects:
                    if isinstance(proj, dict):
                        portfolio_projects.append(
                            PortfolioProject(
                                title=proj.get("title", ""),
                                link=proj.get("link", ""),
                            )
                        )

        # Get skills_levels from JSONB field
        # skills_levels is a JSONB dict mapping skill names to levels (1-5)
        # Fill missing skills with default level 1
        skills_levels = student.skills_levels if student.skills_levels else {}
        if student.skills:
            for skill in student.skills:
                if skill not in skills_levels:
                    skills_levels[skill] = 1  # Default level for missing skills

        students.append(
            StudentDetail(
                user_id=user.user_id,
                name=user.full_name,
                roll_number=student.roll_number,
                department=student.department,
                cgpa=float(student.cgpa) if student.cgpa else None,
                skills=student.skills or [],
                skills_levels=skills_levels,
                interests=student.interests or [],
                experience=student.experience,
                portfolio_projects=portfolio_projects,
            )
        )

    return SupervisorRequestDetailResponse(
        request_id=req.request_id,
        group_id=req.group_id,
        supervisor_id=req.supervisor_id,
        status=req.status.value,
        message=req.message,
        created_at=req.created_at,
        expires_at=expires_at,
        project_brief=project_brief,
        project=project_detail,
        students=students,
    )
