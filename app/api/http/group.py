# app/api/http/group.py

import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase_auth import get_current_user
from app.core.config import settings
from app.db import get_db
from app.models.domain import Domain
from app.models.group import (
    FYPCycleEnum,
    FYPStageEnum,
    Group,
    GroupInvite,
    GroupMember,
    InviteStatusEnum,
)
from app.models.industry import Industry
from app.models.project import Project, ProjectDomain
from app.models.student import Student
from app.models.supervisor import Supervisor
from app.models.user import User
from app.schemas.group_schema import (
    CreateGroupRequest,
    DeleteGroupResponse,
    DomainInfo,
    GroupMemberInfo,
    GroupProfileResponse,
    GroupProfileUpdateRequest,
    GroupProfileUpdateResponse,
    GroupResponse,
    IndustryInfo,
    InviteRequest,
    MessageResponse,
    ProjectInfo,
    SupervisorInfo,
)
from app.services.mailer import get_mailer

router = APIRouter(prefix="/groups", tags=["groups"])


@router.post("/", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group(
    body: CreateGroupRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 1) You can only be in one group
    already = await db.execute(
        select(GroupMember).where(GroupMember.student_id == current_user.user_id)
    )
    if already.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="You are already in a group"
        )

    # 2) Ensure a Student record exists with required roll_number
    student = (
        (
            await db.execute(
                select(Student).where(Student.user_id == current_user.user_id)
            )
        )
        .scalars()
        .first()
    )
    if not student:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Student profile not found. Please complete your profile first.",
        )
    if not student.roll_number:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Roll number is required. Please complete your student profile first.",
        )

    # 3) Create the Group
    grp = Group(
        name=body.name,
        fyp_stage=FYPStageEnum.ideation,
        fyp_cycle=FYPCycleEnum.fyp1,
        created_at=datetime.utcnow(),
    )
    db.add(grp)
    await db.flush()  # populate grp.group_id

    # 4) Add as first member
    member = GroupMember(
        group_id=grp.group_id,
        student_id=current_user.user_id,
        joined_at=datetime.utcnow(),
    )
    db.add(member)

    # 5) Commit everything
    # 5) Create a Project row associated with this group (defaults)
    project = Project(
        group_id=grp.group_id,
        name=grp.name,
        # project_type will use model default ('capstone') if not provided
    )
    db.add(project)
    await db.flush()  # populate project.project_id

    # 6) Commit everything
    await db.commit()

    return GroupResponse(
        group_id=grp.group_id, name=grp.name, project_id=project.project_id
    )


@router.post(
    "/{group_id}/invite", response_model=MessageResponse, status_code=status.HTTP_200_OK
)
async def send_invite(
    group_id: str,
    body: InviteRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Must already be in the group
    is_member = await db.execute(
        select(GroupMember).where(
            GroupMember.group_id == group_id,
            GroupMember.student_id == current_user.user_id,
        )
    )
    if not is_member.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You’re not a member of that group",
        )

    # Lookup invitee user + student record
    q = await db.execute(
        select(User, Student)
        .join(Student, Student.user_id == User.user_id)
        .where(User.email == body.email, User.role == "student")
    )
    row = q.first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="That email isn’t a registered student",
        )
    invitee, student = row

    # Reject if already in a group
    existing_membership = await db.execute(
        select(GroupMember).where(GroupMember.student_id == student.user_id)
    )
    if existing_membership.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="User is already in a group"
        )

    # Check for existing pending invite to this group
    from sqlalchemy import text

    existing_invite_result = await db.execute(
        text(
            "SELECT * FROM group_invites WHERE group_id = :group_id AND invitee_id = :invitee_id AND status = :status"
        ),
        {"group_id": group_id, "invitee_id": student.user_id, "status": "pending"},
    )
    if existing_invite_result.first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This user already has a pending invite to this group",
        )

    # Capacity check (members + pending invites < 3)
    m_count = (
        await db.execute(
            select(func.count())
            .select_from(GroupMember)
            .where(GroupMember.group_id == group_id)
        )
    ).scalar_one()
    # Get pending invites count using raw SQL to avoid enum constraint issues
    pending_result = await db.execute(
        text(
            "SELECT COUNT(*) FROM group_invites WHERE group_id = :group_id AND status = :status"
        ),
        {"group_id": group_id, "status": "pending"},
    )
    pending = pending_result.scalar_one()
    if m_count + pending >= 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Group is full or has 2 pending invites",
        )

    # Create the invite
    token = secrets.token_urlsafe(16)
    invite = GroupInvite(
        group_id=group_id,
        inviter_id=current_user.user_id,
        invitee_id=invitee.user_id,
        token=token,
        status=InviteStatusEnum.pending,
        expires_at=datetime.utcnow() + timedelta(days=7),
    )
    db.add(invite)
    await db.commit()

    # Send the email
    link = f"{settings.frontend_app_url}/groups/{group_id}/invites/{token}/accept"
    html = (
        f"<p>Hi {invitee.full_name},</p>"
        f"<p>{current_user.full_name} invited you to join the group.</p>"
        f"<p><a href='{link}'>Accept invite</a> (expires in 7 days)</p>"
    )
    background_tasks.add_task(
        get_mailer().send, invitee.email, "FYP Group Invitation", html
    )

    return {"message": "Invitation sent; check Ethereal preview URL"}


@router.post(
    "/invites/{token}/accept",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
)
async def accept_invite(
    token: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Fetch & validate
    invite = (
        (await db.execute(select(GroupInvite).where(GroupInvite.token == token)))
        .scalars()
        .first()
    )
    now = datetime.utcnow()
    if (
        not invite
        or invite.status != InviteStatusEnum.pending
        or invite.expires_at < now
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invalid or expired invite"
        )

    # Only the intended recipient
    if invite.invitee_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="This invite isn’t for you"
        )

    # Capacity re-check
    count = (
        await db.execute(
            select(func.count())
            .select_from(GroupMember)
            .where(GroupMember.group_id == invite.group_id)
        )
    ).scalar_one()
    if count >= 3:
        invite.status = InviteStatusEnum.expired
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Group is already full"
        )

    # Ensure Student record exists with required roll_number
    student = (
        (
            await db.execute(
                select(Student).where(Student.user_id == current_user.user_id)
            )
        )
        .scalars()
        .first()
    )
    if not student:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Student profile not found. Please complete your profile first.",
        )
    if not student.roll_number:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Roll number is required. Please complete your student profile first.",
        )

    # Add to members & update
    db.add(
        GroupMember(
            group_id=invite.group_id,
            student_id=current_user.user_id,
            joined_at=datetime.utcnow(),
        )
    )
    invite.status = InviteStatusEnum.accepted

    await db.commit()
    return {"message": "You’ve joined the group!"}


@router.post(
    "/{group_id}/leave", response_model=MessageResponse, status_code=status.HTTP_200_OK
)
async def leave_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Must be a member
    is_member = await db.execute(
        select(GroupMember).where(
            GroupMember.group_id == group_id,
            GroupMember.student_id == current_user.user_id,
        )
    )
    if not is_member.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You’re not a member of that group",
        )

    # Remove membership
    await db.execute(
        delete(GroupMember).where(
            GroupMember.group_id == group_id,
            GroupMember.student_id == current_user.user_id,
        )
    )

    # Student.group_id doesn't exist - membership is handled through GroupMember table
    # No need to clear anything on the Student model

    await db.commit()
    return {"message": "You have left the group."}


@router.delete(
    "/{group_id}", response_model=DeleteGroupResponse, status_code=status.HTTP_200_OK
)
async def delete_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Delete a group and all its associated data.

    This endpoint allows the group creator (first member) to delete the entire group.
    When a group is deleted, the following data is also deleted due to CASCADE:
    - All group members (GroupMember records)
    - All pending group invites (GroupInvite records)
    - All projects associated with the group
    - All proposal documents
    - All shortlisted supervisors

    Only the group creator (first member who joined) can delete the group.
    This prevents accidental deletions by regular members.

    Args:
        group_id (str): UUID of the group to delete
        db (AsyncSession): Database session
        current_user (User): Current authenticated user

    Returns:
        DeleteGroupResponse: Confirmation of deletion with timestamp

    Raises:
        HTTPException(403): User is not authorized to delete this group
        HTTPException(404): Group not found
        HTTPException(500): Database error during deletion
    """
    # Verify user is a student
    if current_user.role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students can delete groups",
        )

    # Check if group exists
    group_result = await db.execute(select(Group).where(Group.group_id == group_id))
    group = group_result.scalars().first()

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found",
        )

    # Check if user is a member of the group
    membership_result = await db.execute(
        select(GroupMember).where(
            GroupMember.group_id == group_id,
            GroupMember.student_id == current_user.user_id,
        )
    )
    membership = membership_result.scalars().first()

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this group",
        )

    # Check if user is the group creator (first member)
    # The creator is the member with the earliest joined_at timestamp
    creator_result = await db.execute(
        select(GroupMember)
        .where(GroupMember.group_id == group_id)
        .order_by(GroupMember.joined_at.asc())
        .limit(1)
    )
    creator = creator_result.scalars().first()

    if not creator or creator.student_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the group creator can delete the group",
        )

    try:
        # Store group info for response before deletion
        group_name = group.name
        deleted_at = datetime.utcnow().isoformat()

        # Delete the group (CASCADE will handle related records)
        await db.execute(delete(Group).where(Group.group_id == group_id))

        # Commit the deletion
        await db.commit()

        return DeleteGroupResponse(
            message=f"Group '{group_name}' has been successfully deleted",
            group_id=group_id,
            deleted_at=deleted_at,
        )

    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete group: {str(e)}",
        )


@router.get(
    "/{group_id}/profile",
    response_model=GroupProfileResponse,
    status_code=status.HTTP_200_OK,
)
async def get_group_profile(
    group_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get comprehensive group profile information.

    Returns detailed information about a group including:
    - Group basic information (name, stage, cycle, etc.)
    - All group members with their details
    - Primary and co-supervisor information
    - Associated project details with domains and industry
    - Count of pending invites

    Only group members can access this endpoint.

    Args:
        group_id (str): UUID of the group
        db (AsyncSession): Database session
        current_user (User): Current authenticated user

    Returns:
        GroupProfileResponse: Comprehensive group profile data

    Raises:
        HTTPException(403): User is not a member of the group
        HTTPException(404): Group not found
        HTTPException(500): Database error
    """
    # Verify user is a student
    if current_user.role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students can access group profiles",
        )

    # Check if group exists and user is a member
    group_result = await db.execute(select(Group).where(Group.group_id == group_id))
    group = group_result.scalars().first()

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found",
        )

    # Check if user is a member of the group
    membership_result = await db.execute(
        select(GroupMember).where(
            GroupMember.group_id == group_id,
            GroupMember.student_id == current_user.user_id,
        )
    )
    membership = membership_result.scalars().first()

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this group",
        )

    try:
        # Get group members with user details
        members_result = await db.execute(
            select(GroupMember, User, Student)
            .join(User, User.user_id == GroupMember.student_id)
            .join(Student, Student.user_id == User.user_id)
            .where(GroupMember.group_id == group_id)
            .order_by(GroupMember.joined_at.asc())
        )
        members_data = members_result.all()

        # Build members list
        members = []
        for member, user, student in members_data:
            members.append(
                GroupMemberInfo(
                    user_id=user.user_id,
                    full_name=user.full_name,
                    avatar_initial=user.full_name[0].upper() if user.full_name else "?",
                    avatar_url=user.profile_avatar,
                    joined_at=member.joined_at,
                )
            )

        # Get supervisor information
        supervisors = {"primary": None, "co_supervisor": None}

        if group.supervisor_id:
            supervisor_result = await db.execute(
                select(Supervisor, User)
                .join(User, User.user_id == Supervisor.user_id)
                .where(Supervisor.user_id == group.supervisor_id)
            )
            supervisor_data = supervisor_result.first()
            if supervisor_data:
                supervisor, supervisor_user = supervisor_data
                supervisors["primary"] = SupervisorInfo(
                    user_id=supervisor_user.user_id,
                    full_name=supervisor_user.full_name,
                    department=supervisor.department,
                    designation=supervisor.designation,
                    email=supervisor_user.email,
                    avatar_url=supervisor_user.profile_avatar,
                )

        if group.cosupervisor_id:
            cosupervisor_result = await db.execute(
                select(Supervisor, User)
                .join(User, User.user_id == Supervisor.user_id)
                .where(Supervisor.user_id == group.cosupervisor_id)
            )
            cosupervisor_data = cosupervisor_result.first()
            if cosupervisor_data:
                cosupervisor, cosupervisor_user = cosupervisor_data
                supervisors["co_supervisor"] = SupervisorInfo(
                    user_id=cosupervisor_user.user_id,
                    full_name=cosupervisor_user.full_name,
                    department=cosupervisor.department,
                    designation=cosupervisor.designation,
                    email=cosupervisor_user.email,
                    avatar_url=cosupervisor_user.profile_avatar,
                )

        # Get project information
        project = None
        try:
            project_result = await db.execute(
                select(Project).where(Project.group_id == group_id)
            )
            project_data = project_result.scalars().first()
        except Exception as e:
            # Handle enum constraint issues by using raw SQL
            if "enum" in str(e).lower() and "project_type" in str(e).lower():
                # Use raw SQL to bypass enum constraint
                from sqlalchemy import text

                raw_result = await db.execute(
                    text(
                        """
                        SELECT project_id, group_id, name, description, objectives, 
                               tech_stack, start_date, end_date, project_type, 
                               industry_id, repo_links, created_at, updated_at
                        FROM projects 
                        WHERE group_id = :group_id
                    """
                    ),
                    {"group_id": group_id},
                )
                raw_data = raw_result.fetchone()
                if raw_data:
                    # Create a mock project object with the raw data
                    class MockProject:
                        def __init__(self, data):
                            self.project_id = data[0]
                            self.group_id = data[1]
                            self.name = data[2]
                            self.description = data[3]
                            self.objectives = data[4]
                            self.tech_stack = data[5]
                            self.start_date = data[6]
                            self.end_date = data[7]
                            self.project_type = data[
                                8
                            ]  # This might be 'product' or other invalid enum
                            self.industry_id = data[9]
                            self.repo_links = data[10]
                            self.created_at = data[11]
                            self.updated_at = data[12]

                    project_data = MockProject(raw_data)
                else:
                    project_data = None
            else:
                raise e

        if project_data:
            # Get project domains
            domains_result = await db.execute(
                select(Domain)
                .join(ProjectDomain, ProjectDomain.domain_id == Domain.domain_id)
                .where(ProjectDomain.project_id == project_data.project_id)
            )
            domains = [
                DomainInfo(domain_id=d.domain_id, name=d.name)
                for d in domains_result.scalars().all()
            ]

            # Get project industry
            industry = None
            if project_data.industry_id:
                industry_result = await db.execute(
                    select(Industry).where(
                        Industry.industry_id == project_data.industry_id
                    )
                )
                industry_data = industry_result.scalars().first()
                if industry_data:
                    industry = IndustryInfo(
                        industry_id=industry_data.industry_id,
                        name=industry_data.name,
                    )

            # Handle project_type - convert to string and validate
            project_type = (
                str(project_data.project_type)
                if project_data.project_type
                else "capstone"
            )

            project = ProjectInfo(
                project_id=project_data.project_id,
                name=project_data.name,
                description=project_data.description,
                objectives=project_data.objectives,
                tech_stack=project_data.tech_stack,
                domains=domains,
                industry=industry,
                start_date=project_data.start_date,
                end_date=project_data.end_date,
                project_type=project_type,
                repo_links=project_data.repo_links,
                updated_at=project_data.updated_at,
            )

        # Get pending invites count using raw SQL to avoid enum constraint issues
        from sqlalchemy import text

        invites_count_result = await db.execute(
            text(
                "SELECT COUNT(*) FROM group_invites WHERE group_id = :group_id AND status = :status"
            ),
            {"group_id": group_id, "status": "pending"},
        )
        pending_count = invites_count_result.scalar_one()

        # Build group basic info
        group_info = {
            "group_id": str(group.group_id),
            "name": group.name,
            "fyp_stage": group.fyp_stage,
            "fyp_cycle": group.fyp_cycle,
            "cohort_year": group.cohort_year,
            "created_at": group.created_at.isoformat(),
            "updated_at": group.updated_at.isoformat(),
        }

        return GroupProfileResponse(
            group=group_info,
            members=members,
            supervisors=supervisors,
            project=project,
            invites={"pending_count": pending_count},
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch group profile: {str(e)}",
        )


@router.patch(
    "/{group_id}/profile",
    response_model=GroupProfileUpdateResponse,
    status_code=status.HTTP_200_OK,
)
async def update_group_profile(
    group_id: str,
    update_data: GroupProfileUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Update group profile information.

    Allows group members to update:
    - Group basic information (name, stage, cycle, cohort year, supervisors)
    - Project information (name, description, objectives, tech stack, domains, industry, etc.)

    Only group members can update the group profile.

    Args:
        group_id (str): UUID of the group
        update_data (GroupProfileUpdateRequest): Update data for group and/or project
        db (AsyncSession): Database session
        current_user (User): Current authenticated user

    Returns:
        GroupProfileUpdateResponse: Confirmation of update with timestamp

    Raises:
        HTTPException(403): User is not a member of the group
        HTTPException(404): Group not found
        HTTPException(400): Invalid update data
        HTTPException(500): Database error
    """
    # Verify user is a student
    if current_user.role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students can update group profiles",
        )

    # Check if group exists and user is a member
    group_result = await db.execute(select(Group).where(Group.group_id == group_id))
    group = group_result.scalars().first()

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found",
        )

    # Check if user is a member of the group
    membership_result = await db.execute(
        select(GroupMember).where(
            GroupMember.group_id == group_id,
            GroupMember.student_id == current_user.user_id,
        )
    )
    membership = membership_result.scalars().first()

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this group",
        )

    try:
        updated_at = datetime.utcnow()

        # Update group information if provided
        if update_data.group:
            group_updates = {}

            if update_data.group.name is not None:
                group_updates["name"] = update_data.group.name
            if update_data.group.fyp_stage is not None:
                # Cast to proper enum type to avoid database constraint issues
                group_updates["fyp_stage"] = update_data.group.fyp_stage
            if update_data.group.fyp_cycle is not None:
                # Cast to proper enum type to avoid database constraint issues
                group_updates["fyp_cycle"] = update_data.group.fyp_cycle
            if update_data.group.cohort_year is not None:
                group_updates["cohort_year"] = update_data.group.cohort_year
            if update_data.group.supervisor_id is not None:
                group_updates["supervisor_id"] = update_data.group.supervisor_id
            if update_data.group.cosupervisor_id is not None:
                group_updates["cosupervisor_id"] = update_data.group.cosupervisor_id

            if group_updates:
                group_updates["updated_at"] = updated_at

                # Handle special field types before using SQLAlchemy update
                processed_updates = {}
                enum_updates = {}

                for key, value in group_updates.items():
                    if key in ["fyp_stage", "fyp_cycle"]:
                        # Store enum fields for separate handling
                        enum_updates[key] = value
                    else:
                        processed_updates[key] = value

                # Update non-enum fields using SQLAlchemy
                if processed_updates:
                    await db.execute(
                        update(Group)
                        .where(Group.group_id == group_id)
                        .values(**processed_updates)
                    )

                # Handle enum fields separately with raw SQL
                if enum_updates:
                    from sqlalchemy import text

                    for key, value in enum_updates.items():
                        enum_type = (
                            "fyp_stage_enum" if key == "fyp_stage" else "fyp_cycle_enum"
                        )
                        await db.execute(
                            text(
                                f"UPDATE groups SET {key} = :value::{enum_type} WHERE group_id = :group_id"
                            ),
                            {"value": value, "group_id": group_id},
                        )

        # Update project information if provided
        if update_data.project:
            # Check if project exists
            project_result = await db.execute(
                select(Project).where(Project.group_id == group_id)
            )
            project = project_result.scalars().first()

            if not project:
                # Create new project if it doesn't exist
                project = Project(
                    group_id=group_id,
                    name=update_data.project.name or "Untitled Project",
                    project_type=update_data.project.project_type or "capstone",
                )
                db.add(project)
                await db.flush()  # Get the project_id

            # Update project fields
            project_updates = {}

            if update_data.project.name is not None:
                project_updates["name"] = update_data.project.name
            if update_data.project.description is not None:
                project_updates["description"] = update_data.project.description
            if update_data.project.objectives is not None:
                project_updates["objectives"] = update_data.project.objectives
            if update_data.project.tech_stack is not None:
                project_updates["tech_stack"] = update_data.project.tech_stack
            if update_data.project.industry_id is not None:
                project_updates["industry_id"] = update_data.project.industry_id
            if update_data.project.start_date is not None:
                project_updates["start_date"] = update_data.project.start_date
            if update_data.project.end_date is not None:
                project_updates["end_date"] = update_data.project.end_date
            if update_data.project.project_type is not None:
                project_updates["project_type"] = update_data.project.project_type
            if update_data.project.repo_links is not None:
                project_updates["repo_links"] = update_data.project.repo_links

            if project_updates:
                project_updates["updated_at"] = updated_at

                # Handle special field types before using SQLAlchemy update
                processed_updates = {}
                for key, value in project_updates.items():
                    if key in ["objectives", "tech_stack", "repo_links"]:
                        # JSONB fields - SQLAlchemy handles serialization automatically
                        processed_updates[key] = value
                    elif key == "project_type":
                        # For enum fields, we need to use raw SQL with proper casting
                        # We'll handle this separately
                        continue
                    else:
                        processed_updates[key] = value

                # Update non-enum fields using SQLAlchemy (handles JSONB automatically)
                if processed_updates:
                    await db.execute(
                        update(Project)
                        .where(Project.project_id == project.project_id)
                        .values(**processed_updates)
                    )

                # Handle project_type separately with raw SQL if needed
                if "project_type" in project_updates:
                    from sqlalchemy import text

                    await db.execute(
                        text(
                            "UPDATE projects SET project_type = :project_type WHERE project_id = :project_id"
                        ),
                        {
                            "project_type": project_updates["project_type"],
                            "project_id": project.project_id,
                        },
                    )

            # Update project domains if provided
            if update_data.project.domain_ids is not None:
                # Remove existing project domains
                await db.execute(
                    delete(ProjectDomain).where(
                        ProjectDomain.project_id == project.project_id
                    )
                )

                # Add new project domains
                for domain_id in update_data.project.domain_ids:
                    project_domain = ProjectDomain(
                        project_id=project.project_id,
                        domain_id=domain_id,
                    )
                    db.add(project_domain)

        # Commit all changes
        await db.commit()

        return GroupProfileUpdateResponse(
            message="Group profile updated successfully",
            updated_at=updated_at,
        )

    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update group profile: {str(e)}",
        )
