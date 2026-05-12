"""
WebSocket Chat Endpoint
Group real-time chat for a workspace session.

Connection:
    WS ws://host/ws/chat/{session_id}?token=<jwt>

Client → Server messages (JSON):
    { "type": "message", "content": "...", "active_document_id": "uuid|null", "model": "gpt-4o",
      "workspace_action": "chat|suggest|improve|modify" }
    { "type": "ping" }

Server → Client broadcasts (JSON):
    { "type": "presence",      "online": ["user_id", ...] }
    { "type": "user_message",  "sender_id": "...", "sender_name": "...", "content": "...", "timestamp": "..." }
    { "type": "llm_status",    "request_id": "...", "phase": "queued|thinking|streaming|complete", "timestamp": "..." }
    { "type": "llm_token",     "request_id": "...", "token": "Hello", "seq": 1 }
    { "type": "llm_done",      "request_id": "...", "message_id": "...", "full_reply": "...",
                               "proposal_id": "...", "proposal_summary": "..." }
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
from app.core.config import settings
from app.db import get_db
from app.db.mongo import get_mongo_db
from app.repositories.chat_session_repository import chat_session_repo
from app.repositories.group_document_repository import group_document_repo
from app.services.chat_llm_errors import format_chat_stream_llm_error
from app.services.chat_sse_hub import publish as sse_publish
from app.services.chat_sse_hub import (
    sse_stream_error,
    sse_stream_status,
)
from app.services.html_plaintext import html_to_plaintext, tip_tap_html_from_content
from app.services.llm import stream_llm
from app.services.prompts import build_document_modify_system_extra
from app.services.workspace_modify_proposal import (
    finalize_modify_mode_reply,
    link_proposal_to_assistant_message,
)

logger = logging.getLogger(__name__)
router = APIRouter()


async def _mirror_ws_payload_to_sse(session_id: str, payload: dict) -> None:
    """Mirror legacy WebSocket payloads to HTTP SSE channel (same room_id as Mongo session)."""
    t = payload.get("type")
    if t == "presence":
        return
    try:
        import time

        ts = time.time()
        if t == "user_message":
            await sse_publish(
                session_id,
                {
                    "type": "chat.message.sent",
                    "sender_id": payload["sender_id"],
                    "sender_name": payload.get("sender_name"),
                    "content": payload.get("content"),
                    "timestamp": ts,
                },
            )
        elif t == "llm_status":
            rid = payload.get("request_id") or ""
            await sse_publish(
                session_id,
                sse_stream_status(rid, payload.get("phase") or "queued"),
            )
        elif t == "llm_token":
            await sse_publish(
                session_id,
                {
                    "type": "chat.stream.token",
                    "request_id": payload.get("request_id"),
                    "token": payload.get("token"),
                    "seq": payload.get("seq"),
                },
            )
        elif t == "llm_error":
            rid = payload.get("request_id") or ""
            detail = str(payload.get("detail") or "")
            err_code = payload.get("error_code")
            await sse_publish(
                session_id,
                sse_stream_error(rid, detail, error_code=err_code),
            )
        elif t == "llm_done":
            full = payload.get("full_reply") or ""
            evt: dict = {
                "type": "chat.stream.end",
                "request_id": payload.get("request_id"),
                "assistant_message_id": payload.get("message_id"),
                "reply_length": len(full),
            }
            if payload.get("proposal_id"):
                evt["proposal_id"] = payload["proposal_id"]
            if payload.get("proposal_summary"):
                evt["proposal_summary"] = payload["proposal_summary"]
            await sse_publish(session_id, evt)
    except Exception:
        logger.debug("SSE mirror from WebSocket chat failed", exc_info=True)


async def _broadcast_chat_ws(room_key: str, session_id: str, payload: dict) -> None:
    await manager.broadcast(room_key, payload)
    await _mirror_ws_payload_to_sse(session_id, payload)


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
                await _broadcast_chat_ws(
                    room_key,
                    session_id,
                    {
                        "type": "user_message",
                        "sender_id": user_id,
                        "sender_name": user_name,
                        "content": content,
                        "timestamp": timestamp,
                    },
                )

                await _broadcast_chat_ws(
                    room_key,
                    session_id,
                    {
                        "type": "llm_status",
                        "request_id": request_id,
                        "phase": "queued",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )

                # 2. Load document context + modify flags
                doc_context = None
                doc_type_str = None
                document_content_str: Optional[str] = None
                doc_html_raw: Optional[str] = None
                baseline_lock_version: Optional[int] = None
                document_loaded = False

                wa = str(data.get("workspace_action") or "chat").strip().lower()
                is_modify = wa == "modify"

                if active_doc_id:
                    try:
                        doc = await group_document_repo.get_by_id(
                            db, UUID(active_doc_id)
                        )
                        if doc:
                            document_loaded = True
                            doc_type_str = doc.doc_type.value if doc.doc_type else None
                            baseline_lock_version = doc.lock_version
                            if doc.content:
                                document_content_str = json.dumps(doc.content, indent=2)
                                doc_context = {
                                    "active_document_id": active_doc_id,
                                    "version_number": doc.lock_version,
                                }
                                hr = tip_tap_html_from_content(doc.content)
                                if hr:
                                    doc_html_raw = hr
                    except Exception as e:
                        logger.warning("Could not load active document: %s", e)

                modify_valid = is_modify and bool(doc_html_raw) and document_loaded

                leading_document_context: Optional[str] = None
                if doc_html_raw and not modify_valid:
                    leading_document_context = html_to_plaintext(doc_html_raw)

                await chat_session_repo.save_message(
                    mongo_db,
                    chat_session_id=session_id,
                    sender_id=user_id,
                    sender_type="student",
                    content=content,
                    doc_context=doc_context,
                    metadata={"workspace_action": wa, "request_id": request_id},
                    request_id=request_id,
                )

                # 3. Build LLM history from recent messages (modify: smaller window)
                _hist_limit = (
                    settings.chat_modify_context_message_limit if modify_valid else 10
                )
                recent = await chat_session_repo.get_recent_messages_for_context(
                    mongo_db, session_id, n=_hist_limit
                )
                history = []
                for msg in recent:
                    role = "assistant" if msg["sender_type"] == "llm" else "user"
                    history.append({"role": role, "content": msg["content"]})

                if is_modify and not modify_valid:
                    err_text = (
                        "[Modify] Open a document tab with readable HTML content "
                        "to use modify mode."
                    )
                    mid = await chat_session_repo.save_message(
                        mongo_db,
                        chat_session_id=session_id,
                        sender_id="llm",
                        sender_type="llm",
                        content=err_text,
                        doc_context=doc_context,
                        metadata={"modify_skipped": True, "model": model_choice},
                        request_id=request_id,
                    )
                    await _broadcast_chat_ws(
                        room_key,
                        session_id,
                        {
                            "type": "llm_status",
                            "request_id": request_id,
                            "phase": "thinking",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                    await _broadcast_chat_ws(
                        room_key,
                        session_id,
                        {
                            "type": "llm_done",
                            "request_id": request_id,
                            "message_id": mid,
                            "full_reply": err_text,
                        },
                    )
                    await _broadcast_chat_ws(
                        room_key,
                        session_id,
                        {
                            "type": "llm_status",
                            "request_id": request_id,
                            "phase": "complete",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                    continue

                # 4. Stream LLM tokens → broadcast each token to ALL in session
                full_reply_parts: list[str] = []
                token_seq = 0
                sent_streaming_status = False
                modify_system_extra = None
                stream_leading = leading_document_context
                if modify_valid:
                    modify_system_extra = build_document_modify_system_extra(
                        doc_html_raw or "",
                        max_html_chars=settings.chat_modify_html_max_chars,
                    )
                    stream_leading = None
                    document_content_str = None

                try:
                    await _broadcast_chat_ws(
                        room_key,
                        session_id,
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
                        system_extra=modify_system_extra,
                        model_choice=model_choice,
                        doc_type=doc_type_str,
                        leading_document_context=stream_leading,
                        history_message_max_chars=(
                            settings.chat_modify_llm_message_max_chars
                            if modify_valid
                            else None
                        ),
                    ):
                        if not sent_streaming_status:
                            sent_streaming_status = True
                            await _broadcast_chat_ws(
                                room_key,
                                session_id,
                                {
                                    "type": "llm_status",
                                    "request_id": request_id,
                                    "phase": "streaming",
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                },
                            )

                        token_seq += 1
                        full_reply_parts.append(token_chunk)
                        await _broadcast_chat_ws(
                            room_key,
                            session_id,
                            {
                                "type": "llm_token",
                                "request_id": request_id,
                                "token": token_chunk,
                                "seq": token_seq,
                            },
                        )
                except Exception as exc:
                    logger.error("LLM streaming error: %s", exc)
                    detail, err_code = format_chat_stream_llm_error(exc)
                    await _broadcast_chat_ws(
                        room_key,
                        session_id,
                        {
                            "type": "llm_error",
                            "request_id": request_id,
                            "detail": detail,
                            "error_code": err_code,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                    continue

                full_reply = "".join(full_reply_parts)

                final_content, assistant_meta, proposal_id = (
                    await finalize_modify_mode_reply(
                        mongo_db,
                        chat_session_id=session_id,
                        user_id=user_id,
                        full_reply=full_reply,
                        is_modify=modify_valid,
                        active_document_id=active_doc_id,
                        baseline_lock_version=baseline_lock_version,
                        doc_context=doc_context,
                        request_id=request_id,
                        model_choice=model_choice,
                    )
                )
                message_id = await chat_session_repo.save_message(
                    mongo_db,
                    chat_session_id=session_id,
                    sender_id="llm",
                    sender_type="llm",
                    content=final_content,
                    doc_context=doc_context,
                    metadata=assistant_meta,
                    request_id=request_id,
                )
                if proposal_id:
                    await link_proposal_to_assistant_message(
                        mongo_db, proposal_id, message_id
                    )

                done_payload: dict = {
                    "type": "llm_done",
                    "request_id": request_id,
                    "message_id": message_id,
                    "full_reply": final_content,
                }
                if proposal_id:
                    done_payload["proposal_id"] = proposal_id
                    if assistant_meta.get("proposal_summary"):
                        done_payload["proposal_summary"] = assistant_meta[
                            "proposal_summary"
                        ]
                await _broadcast_chat_ws(room_key, session_id, done_payload)

                await _broadcast_chat_ws(
                    room_key,
                    session_id,
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
