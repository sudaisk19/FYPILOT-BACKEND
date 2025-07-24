# app/api/http/group.py

import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
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


@router.post("/", response_model=GroupResponse)
async def create_group(
    body: CreateGroupRequest,
    db: AsyncSession = Depends(get_db),
    current=Depends(get_current_user),
):
    # Users can only be in one group
    existing = await db.execute(
        select(GroupMember).where(GroupMember.student_id == current.user_id)
    )
    if existing.scalars().first():
        raise HTTPException(400, "You are already in a group")

    # Create the group
    grp = Group(name=body.name)
    db.add(grp)
    await db.flush()  # populate grp.group_id

    # Add creator as first member
    db.add(GroupMember(group_id=grp.group_id, student_id=current.user_id))
    # Also update Student.group_id column
    student = (
        (await db.execute(select(Student).where(Student.user_id == current.user_id)))
        .scalars()
        .first()
    )
    if student:
        student.group_id = grp.group_id

    await db.commit()
    return GroupResponse(group_id=grp.group_id, name=grp.name)


@router.post("/{group_id}/invite", response_model=MessageResponse)
async def send_invite(
    group_id: str,
    body: InviteRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current=Depends(get_current_user),
):
    # Inviter must already be in the group
    if not (
        await db.execute(
            select(GroupMember).where(
                GroupMember.group_id == group_id,
                GroupMember.student_id == current.user_id,
            )
        )
    ).scalar_one_or_none():
        raise HTTPException(403, "You’re not a member of that group")

    # Lookup invitee
    q = await db.execute(
        select(User, Student)
        .where(User.email == body.email, User.role == "student")
        .join(Student, Student.user_id == User.user_id)
    )
    row = q.first()
    if not row:
        raise HTTPException(404, "That email isn’t a registered student")
    invitee, student = row

    # Reject if invitee already in any group
    if student.group_id:
        raise HTTPException(400, "User is already in a group")

    # Capacity check: members + pending invites < 3
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
        raise HTTPException(400, "Group is full or has 2 pending invites")

    # Create invite
    token = secrets.token_urlsafe(16)
    invite = GroupInvite(
        group_id=group_id,
        inviter_id=current.user_id,
        invitee_id=invitee.user_id,
        token=token,
        status="pending",
        expires_at=datetime.utcnow() + timedelta(days=7),
    )
    db.add(invite)
    await db.commit()

    # Send email
    link = f"{settings.frontend_url}/groups/{group_id}/invites/{token}/accept"
    html = (
        f"<p>Hi {invitee.full_name},</p>"
        f"<p>{current.full_name} invited you to join the group.</p>"
        f"<p><a href='{link}'>Accept invite</a> (expires in 7 days)</p>"
    )
    background_tasks.add_task(
        get_mailer().send, invitee.email, "FYP Group Invitation", html
    )

    return {"message": "Invitation sent; check Ethereal preview URL"}


@router.post("/invites/{token}/accept", response_model=MessageResponse)
async def accept_invite(
    token: str,
    db: AsyncSession = Depends(get_db),
    current=Depends(get_current_user),
):
    # Fetch & validate invite
    invite = (
        (await db.execute(select(GroupInvite).where(GroupInvite.token == token)))
        .scalars()
        .first()
    )
    now = datetime.utcnow()
    if not invite or invite.status != "pending" or invite.expires_at < now:
        raise HTTPException(404, "Invalid or expired invite")

    # Ensure only intended recipient
    if invite.invitee_id != current.user_id:
        raise HTTPException(403, "This invite isn’t for you")

    # Re-check capacity
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
        raise HTTPException(400, "Group is already full")

    # Add to members & update Student.group_id
    db.add(GroupMember(group_id=invite.group_id, student_id=current.user_id))
    student = (
        (await db.execute(select(Student).where(Student.user_id == current.user_id)))
        .scalars()
        .first()
    )
    if student:
        student.group_id = invite.group_id

    invite.status = "accepted"
    await db.commit()

    return {"message": "You’ve joined the group!"}


@router.post("/{group_id}/leave", response_model=MessageResponse)
async def leave_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
    current=Depends(get_current_user),
):
    # Ensure user is in that group
    if not (
        await db.execute(
            select(GroupMember).where(
                GroupMember.group_id == group_id,
                GroupMember.student_id == current.user_id,
            )
        )
    ).scalar_one_or_none():
        raise HTTPException(403, "You’re not a member of that group")

    # Remove from group_members
    await db.execute(
        delete(GroupMember).where(
            GroupMember.group_id == group_id, GroupMember.student_id == current.user_id
        )
    )

    # Clear Student.group_id
    student = (
        (await db.execute(select(Student).where(Student.user_id == current.user_id)))
        .scalars()
        .first()
    )
    if student:
        student.group_id = None

    await db.commit()
    return {"message": "You have left the group."}
