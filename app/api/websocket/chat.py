"""
WebSocket Chat Endpoint
Group real-time chat for a workspace session.

Connection:
    WS ws://host/ws/chat/{session_id}?token=<jwt>

Client → Server messages (JSON):
    { "type": "message", "content": "...", "active_document_id": "uuid|null", "model": "gpt-4o" }
    { "type": "ping" }

Server → Client broadcasts (JSON):
    { "type": "presence",      "online": ["user_id", ...] }
    { "type": "user_message",  "sender_id": "...", "sender_name": "...", "content": "...", "timestamp": "..." }
    { "type": "llm_status",    "request_id": "...", "phase": "queued|thinking|streaming|complete", "timestamp": "..." }
    { "type": "llm_token",     "request_id": "...", "token": "Hello", "seq": 1 }
    { "type": "llm_done",      "request_id": "...", "message_id": "...", "full_reply": "..." }
    { "type": "llm_error",     "request_id": "...", "detail": "...", "timestamp": "..." }
    { "type": "error",         "detail": "..." }
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.websocket.manager import manager
from app.auth.supabase_auth import get_ws_user
from app.db import get_db
from app.db.mongo import get_mongo_db
from app.repositories.chat_session_repository import chat_session_repo
from app.repositories.group_document_repository import group_document_repo
from app.services.llm import stream_llm

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/chat/{session_id}")
async def chat_websocket(
    session_id: str,
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token"),
    db: AsyncSession = Depends(get_db),
    mongo_db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """
    Real-time group chat WebSocket.
    All students connected to the same session_id receive each other's messages
    and the LLM reply is streamed token-by-token to all of them simultaneously.
    """
    # ── Auth ─────────────────────────────────────────────────────────────────
    user = await get_ws_user(token)
    if user is None:
        # Must accept before we can send a close frame
        await websocket.accept()
        await websocket.send_json({"type": "error", "detail": "Unauthorized"})
        await websocket.close(code=4001)
        return

    user_id = str(user.user_id)
    user_name = user.full_name or user_id
    room_key = f"chat:{session_id}"

    # ── Connect ──────────────────────────────────────────────────────────────
    await manager.connect(room_key, user_id, websocket)

    # Broadcast updated presence to all in session
    await manager.broadcast(
        room_key,
        {
            "type": "presence",
            "online": manager.get_online_users(room_key),
        },
    )

    try:
        while True:
            try:
                raw = await websocket.receive_text()
            except (WebSocketDisconnect, RuntimeError):
                # RuntimeError is raised by Starlette when the client disconnects abruptly
                break

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "detail": "Invalid JSON"})
                continue

            msg_type = data.get("type", "message")

            # ── Ping / keep-alive ─────────────────────────────────────────
            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            # ── Chat message ─────────────────────────────────────────────
            if msg_type == "message":
                content = data.get("content", "").strip()
                if not content:
                    continue

                active_doc_id: Optional[str] = data.get("active_document_id")
                model_choice: str = data.get("model", "gpt-4o")
                timestamp = datetime.now(timezone.utc).isoformat()
                request_id = str(uuid4())

                # 1. Broadcast the student's own message to all in session
                await manager.broadcast(
                    room_key,
                    {
                        "type": "user_message",
                        "sender_id": user_id,
                        "sender_name": user_name,
                        "content": content,
                        "timestamp": timestamp,
                    },
                )

                await manager.broadcast(
                    room_key,
                    {
                        "type": "llm_status",
                        "request_id": request_id,
                        "phase": "queued",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )

                # 2. Persist to MongoDB
                doc_context = None
                document_content_str = None
                doc_type_str = None

                if active_doc_id:
                    try:
                        doc = await group_document_repo.get_by_id(
                            db, UUID(active_doc_id)
                        )
                        if doc:
                            doc_type_str = doc.doc_type.value if doc.doc_type else None
                            if doc.content:
                                document_content_str = json.dumps(doc.content, indent=2)
                                doc_context = {
                                    "active_document_id": active_doc_id,
                                    "version_number": doc.lock_version,
                                }
                    except Exception as e:
                        logger.warning(f"Could not load active document: {e}")

                await chat_session_repo.save_message(
                    mongo_db,
                    chat_session_id=session_id,
                    sender_id=user_id,
                    sender_type="student",
                    content=content,
                    doc_context=doc_context,
                )

                # 3. Build LLM history from recent messages
                recent = await chat_session_repo.get_recent_messages_for_context(
                    mongo_db, session_id, n=10
                )
                history = []
                for msg in recent:
                    role = "assistant" if msg["sender_type"] == "llm" else "user"
                    history.append({"role": role, "content": msg["content"]})

                # 4. Stream LLM tokens → broadcast each token to ALL in session
                full_reply_parts = []
                token_seq = 0
                sent_streaming_status = False
                try:
                    await manager.broadcast(
                        room_key,
                        {
                            "type": "llm_status",
                            "request_id": request_id,
                            "phase": "thinking",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    )

                    async for token_chunk in stream_llm(
                        history=history,
                        document_content=document_content_str,
                        model_choice=model_choice,
                        doc_type=doc_type_str,
                    ):
                        if not sent_streaming_status:
                            sent_streaming_status = True
                            await manager.broadcast(
                                room_key,
                                {
                                    "type": "llm_status",
                                    "request_id": request_id,
                                    "phase": "streaming",
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                },
                            )

                        token_seq += 1
                        full_reply_parts.append(token_chunk)
                        await manager.broadcast(
                            room_key,
                            {
                                "type": "llm_token",
                                "request_id": request_id,
                                "token": token_chunk,
                                "seq": token_seq,
                            },
                        )
                except Exception as exc:
                    logger.error(f"LLM streaming error: {exc}")
                    await manager.broadcast(
                        room_key,
                        {
                            "type": "llm_error",
                            "request_id": request_id,
                            "detail": str(exc),
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                    continue

                full_reply = "".join(full_reply_parts)

                # 5. Persist LLM reply to MongoDB
                message_id = await chat_session_repo.save_message(
                    mongo_db,
                    chat_session_id=session_id,
                    sender_id="llm",
                    sender_type="llm",
                    content=full_reply,
                    doc_context=doc_context,
                )

                # 6. Notify all that streaming is complete
                await manager.broadcast(
                    room_key,
                    {
                        "type": "llm_done",
                        "request_id": request_id,
                        "message_id": message_id,
                        "full_reply": full_reply,
                    },
                )

                await manager.broadcast(
                    room_key,
                    {
                        "type": "llm_status",
                        "request_id": request_id,
                        "phase": "complete",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )

    finally:
        # Always clean up — runs on disconnect, error, or normal close
        manager.disconnect(room_key, user_id)
        await manager.broadcast(
            room_key,
            {
                "type": "presence",
                "online": manager.get_online_users(room_key),
            },
        )
