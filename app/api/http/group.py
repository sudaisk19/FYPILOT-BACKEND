# app/api/http/group.py

import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase_auth import get_current_user
from app.core.config import settings
from app.db import get_db
from app.models.group import Group, GroupInvite, GroupMember
from app.models.student import Student
from app.models.user import User
from app.schemas.group_schema import (
    CreateGroupRequest,
    GroupResponse,
    InviteRequest,
    MessageResponse,
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
    grp = Group(name=body.name, created_at=datetime.utcnow())
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
    await db.commit()
    return GroupResponse(group_id=grp.group_id, name=grp.name)


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

    # Capacity check (members + pending invites < 3)
    m_count = (
        await db.execute(
            select(func.count())
            .select_from(GroupMember)
            .where(GroupMember.group_id == group_id)
        )
    ).scalar_one()
    pending = (
        await db.execute(
            select(func.count())
            .select_from(GroupInvite)
            .where(GroupInvite.group_id == group_id, GroupInvite.status == "pending")
        )
    ).scalar_one()
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
        status="pending",
        expires_at=datetime.utcnow() + timedelta(days=7),
    )
    db.add(invite)
    await db.commit()

    # Send the email
    link = f"{settings.frontend_url}/groups/{group_id}/invites/{token}/accept"
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
    if not invite or invite.status != "pending" or invite.expires_at < now:
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
        invite.status = "expired"
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
    invite.status = "accepted"

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
