"""
Collaborative workspace chat — HTTP + SSE (async LLM via background workers).

Routes are mounted under the main API prefix, e.g. /api/chat/rooms/...
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase_auth import get_current_user, get_ws_user
from app.db import get_db
from app.db.mongo import get_mongo_db, mongo_db
from app.models.group import GroupMember
from app.models.user import User
from app.repositories.chat_session_repository import chat_session_repo
from app.schemas.collaborative_chat_schema import (
    ChatHistoryResponse,
    ChatRoomSummaryResponse,
    CollaborativeChatPostRequest,
    CollaborativeChatPostResponse,
)
from app.services.chat_sse_hub import (
    format_sse_data,
    publish,
    register,
    sse_stream_status,
    unregister,
)
from app.services.collaborative_chat_worker import enqueue_chat_job, rate_limit_allow
from app.services.document_chat_service import document_chat_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["collaborative-chat"])


def _message_with_role(m: Dict[str, Any]) -> Dict[str, Any]:
    """Add `role` for UI layers that map assistant/user; `sender_type` remains the source of truth."""
    out = dict(m)
    st = m.get("sender_type")
    if st == "llm":
        out["role"] = "assistant"
    elif st == "system":
        out["role"] = "system"
    else:
        out["role"] = "user"
    return out


async def _user_is_group_member(
    db: AsyncSession, user_id: UUID, group_id: UUID
) -> bool:
    stmt = select(GroupMember).where(
        GroupMember.group_id == group_id,
        GroupMember.student_id == user_id,
    )
    result = await db.execute(stmt)
    return result.scalars().first() is not None


async def _require_active_workspace_group_access(
    db: AsyncSession,
    mongo_db: AsyncIOMotorDatabase,
    session_id: str,
    current_user: User,
) -> Dict[str, Any]:
    session = await document_chat_service.get_workspace(mongo_db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if not session.get("is_active", True):
        raise HTTPException(status_code=404, detail="Workspace not found")
    gid_raw = session.get("group_id")
    if not gid_raw:
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        gid = UUID(str(gid_raw))
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="Workspace not found")
    if not await _user_is_group_member(db, current_user.user_id, gid):
        raise HTTPException(
            status_code=403,
            detail="You are not a member of the group that owns this workspace.",
        )
    return session


@router.get("/rooms", response_model=List[ChatRoomSummaryResponse])
async def list_chat_rooms(
    group_id: UUID = Query(..., description="Postgres group UUID"),
    db: AsyncSession = Depends(get_db),
    mongo_db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user: User = Depends(get_current_user),
):
    if not await _user_is_group_member(db, current_user.user_id, group_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this group.",
        )
    sessions = await document_chat_service.list_workspaces(
        mongo_db, str(group_id), active_only=True
    )
    out: List[ChatRoomSummaryResponse] = []
    for sess in sessions:
        rid = str(sess["_id"])
        cnt = await chat_session_repo.count_messages(mongo_db, rid)
        last = await chat_session_repo.get_last_message(mongo_db, rid)
        preview = None
        last_sender = None
        if last:
            preview = (last.get("content") or "")[:200] or None
            last_sender = last.get("sender_name")
        out.append(
            ChatRoomSummaryResponse(
                room_id=rid,
                group_id=str(group_id),
                title=sess.get("title") or "",
                is_active=bool(sess.get("is_active", True)),
                created_at=sess.get("created_at"),
                updated_at=sess.get("updated_at"),
                message_count=cnt,
                last_message_preview=preview,
                last_sender_name=last_sender,
            )
        )
    return out


@router.get("/rooms/{room_id}/messages", response_model=ChatHistoryResponse)
async def get_room_messages(
    room_id: str,
    after_id: Optional[str] = Query(
        None,
        description="Return messages strictly after this MongoDB ObjectId (cursor).",
    ),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    mongo_db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user: User = Depends(get_current_user),
):
    await _require_active_workspace_group_access(db, mongo_db, room_id, current_user)
    messages = await chat_session_repo.get_messages_after(
        mongo_db, room_id, after_id, limit
    )
    has_more = len(messages) == limit
    return ChatHistoryResponse(
        messages=[_message_with_role(m) for m in messages],
        has_more=has_more,
    )


@router.post(
    "/rooms/{room_id}/messages",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CollaborativeChatPostResponse,
)
async def post_room_message(
    room_id: str,
    body: CollaborativeChatPostRequest,
    db: AsyncSession = Depends(get_db),
    mongo_db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user: User = Depends(get_current_user),
):
    await _require_active_workspace_group_access(db, mongo_db, room_id, current_user)
    uid = str(current_user.user_id)
    if not await rate_limit_allow(uid, room_id):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded for chat. Try again shortly.",
        )

    request_id = str(uuid4())
    sender_name = (
        (body.sender_name.strip() if body.sender_name else None)
        or current_user.full_name
        or uid
    )
    workspace_action = body.workspace_action.value if body.workspace_action else "chat"

    user_message_id = await chat_session_repo.save_message(
        mongo_db,
        chat_session_id=room_id,
        sender_id=uid,
        sender_type="student",
        content=body.content,
        doc_context=(
            {
                "active_document_id": body.active_document_id,
                "version_number": None,
            }
            if body.active_document_id
            else None
        ),
        sender_name=sender_name,
        request_id=request_id,
        metadata={
            "request_id": request_id,
            "workspace_action": workspace_action,
        },
    )

    await publish(
        room_id,
        {
            "type": "chat.message.sent",
            "sender_id": uid,
            "sender_name": sender_name,
            "content": body.content,
            "message_id": user_message_id,
            "request_id": request_id,
            "timestamp": time.time(),
        },
    )
    await publish(room_id, sse_stream_status(request_id, "queued"))

    await enqueue_chat_job(
        {
            "room_id": room_id,
            "request_id": request_id,
            "user_id": uid,
            "user_message_id": user_message_id,
            "model": body.model or "gpt-4o",
            "active_document_id": body.active_document_id,
            "workspace_action": workspace_action,
        }
    )

    return CollaborativeChatPostResponse(
        message_id=user_message_id,
        request_id=request_id,
    )


@router.get("/stream")
async def stream_chat_events(
    room_id: str = Query(..., description="Workspace session id (Mongo _id)"),
    token: str = Query(..., description="JWT (same as WebSocket ?token=)"),
):
    user = await get_ws_user(token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    from app.db import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await _require_active_workspace_group_access(db, mongo_db, room_id, user)

    async def event_generator():
        q = await register(room_id)
        try:
            yield format_sse_data(
                {
                    "type": "chat.stream.connected",
                    "room_id": room_id,
                    "timestamp": time.time(),
                }
            )
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield format_sse_data(event)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            await unregister(room_id, q)

    # CORSMiddleware merges Access-Control-*; these keys do not replace allow_origins.
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
