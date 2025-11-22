# app/api/http/supervisor_invites.py
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase_auth import get_current_user
from app.db import get_db
from app.models.group import Group, GroupMember, InviteStatusEnum
from app.models.request import Request, RequestTypeEnum
from app.models.supervisor import Supervisor
from app.models.user import User
from app.schemas.invite_schema import (
    PendingInviteItem,
    PendingInvitesResponse,
    SendSupervisorInviteRequest,
    SentRequestItem,
    SentRequestsResponse,
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
    - Displaying request status (pending, accepted, rejected, cancelled)
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
    # Only show pending, accepted, and rejected requests
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


@router.get("/supervisor/pending", response_model=PendingInvitesResponse)
async def list_pending_invites_for_supervisor(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if current_user.role != "supervisor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only supervisors can view invites",
        )

    # Fetch pending requests for this supervisor
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
        items.append(
            PendingInviteItem(
                invite_id=req.request_id,  # Using request_id as invite_id for compatibility
                group_id=req.group_id,
                group_name=group.name,
                requested_role=req.request_type.value,
                created_at=req.created_at,
            )
        )
    return PendingInvitesResponse(invites=items)


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
    # Mark request accepted
    await db.execute(
        update(Request)
        .where(Request.request_id == request_id)
        .values(
            status=InviteStatusEnum.accepted,
            updated_by=current_user.user_id,
            updated_at=datetime.now(timezone.utc),
        )
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
            status=InviteStatusEnum.rejected,
            updated_by=current_user.user_id,
            updated_at=datetime.now(timezone.utc),
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
