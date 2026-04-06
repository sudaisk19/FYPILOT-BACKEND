# app/api/http/supervisor_invites.py
"""
Supervisor Invites Router

This is a THIN router — its only job is:
1. Auth / role guards
2. Delegating to invite_service (which owns all business logic + DB access)
3. HTTP status codes and JSON shaping

NO raw db.execute() or SQLAlchemy queries live here.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase_auth import get_current_user
from app.db import get_db
from app.models.user import User
from app.schemas.invite_schema import (
    AcceptRequestBody,
    PendingInvitesResponse,
    RejectRequestBody,
    SendSupervisorInviteRequest,
    SentRequestsResponse,
    SupervisorRequestDetailResponse,
)
from app.services.invite_service import (
    accept_supervisor_request_svc,
    cancel_invite_svc,
    get_request_details_svc,
    list_pending_invites_svc,
    list_sent_requests_svc,
    reject_supervisor_request_svc,
    send_supervisor_invite_svc,
)

router = APIRouter(prefix="/invites", tags=["supervisor-invites"])


# ──────────────────────────────────────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────────────────────────────────────


def _require_student(user: User) -> None:
    if user.role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students can perform this action",
        )


def _require_supervisor_faculty(user: User) -> None:
    role_val = user.role.value if hasattr(user.role, "value") else user.role
    if role_val != "faculty":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only faculty can perform this action",
        )
    if not user.faculty_profile or not user.faculty_profile.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your faculty account is inactive. Contact an administrator.",
        )
    if not user.faculty_profile.is_supervisor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only faculty with supervisor privileges can perform this action",
        )


def _map_service_error(exc: Exception) -> HTTPException:
    """Map service-layer exceptions to appropriate HTTP responses."""
    msg = str(exc)
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=msg)
    if isinstance(exc, LookupError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
    if isinstance(exc, ValueError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


# ──────────────────────────────────────────────────────────────────────────────
# endpoints
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/groups/{group_id}/supervisor", status_code=status.HTTP_201_CREATED)
async def send_supervisor_invite(
    group_id: UUID,
    body: SendSupervisorInviteRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    _require_student(current_user)
    try:
        return await send_supervisor_invite_svc(
            db,
            current_user,
            group_id,
            body.faculty_id,
            body.role,
            getattr(body, "message", None),
        )
    except Exception as exc:
        raise _map_service_error(exc) from exc


@router.get(
    "/groups/{group_id}/supervisor/requests",
    response_model=SentRequestsResponse,
)
async def list_sent_requests(
    group_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """List all supervisor requests sent by a group (for group members)."""
    _require_student(current_user)
    try:
        return await list_sent_requests_svc(db, current_user, group_id)
    except Exception as exc:
        raise _map_service_error(exc) from exc


@router.get("/supervisor/pending/requests", response_model=PendingInvitesResponse)
async def list_pending_invites_for_supervisor(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    _require_supervisor_faculty(current_user)
    try:
        return await list_pending_invites_svc(db, current_user)
    except Exception as exc:
        raise _map_service_error(exc) from exc


@router.post("/supervisor/{request_id}/accept")
async def accept_supervisor_request(
    request_id: UUID = Path(...),
    body: AcceptRequestBody = AcceptRequestBody(),
    db: Annotated[AsyncSession, Depends(get_db)] = None,
    current_user: Annotated[User, Depends(get_current_user)] = None,
    background_tasks: BackgroundTasks = None,
):
    _require_supervisor_faculty(current_user)
    try:
        return await accept_supervisor_request_svc(
            db, current_user, request_id, background_tasks, feedback=body.feedback
        )
    except Exception as exc:
        raise _map_service_error(exc) from exc


@router.post("/supervisor/{request_id}/reject")
async def reject_invite(
    request_id: UUID = Path(...),
    body: RejectRequestBody = ...,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
    current_user: Annotated[User, Depends(get_current_user)] = None,
    background_tasks: BackgroundTasks = None,
):
    _require_supervisor_faculty(current_user)
    try:
        return await reject_supervisor_request_svc(
            db, current_user, request_id, background_tasks, feedback=body.feedback
        )
    except Exception as exc:
        raise _map_service_error(exc) from exc


@router.delete("/supervisor/{request_id}/cancel")
async def cancel_invite(
    request_id: UUID = Path(...),
    current_user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
):
    """Cancel (permanently delete) a pending supervisor request."""
    _require_student(current_user)
    try:
        return await cancel_invite_svc(db, current_user, request_id)
    except Exception as exc:
        raise _map_service_error(exc) from exc


@router.get(
    "/supervisor/{request_id}/details",
    response_model=SupervisorRequestDetailResponse,
)
async def get_request_details_for_supervisor(
    request_id: UUID = Path(...),
    current_user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
):
    """Get detailed group/project/student information for a supervisor request."""
    _require_supervisor_faculty(current_user)
    try:
        return await get_request_details_svc(db, current_user, request_id)
    except Exception as exc:
        raise _map_service_error(exc) from exc
