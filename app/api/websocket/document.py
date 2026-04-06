"""
WebSocket Document Presence Endpoint
Tracks who is viewing/editing each document tab.

Connection:
    WS ws://host/ws/document/{doc_id}?token=<jwt>

Client → Server messages (JSON):
    { "type": "start_editing" }          -- request exclusive edit lock
    { "type": "stop_editing" }           -- release edit lock
    { "type": "cursor", "position": 145 } -- optional cursor tracking
    { "type": "ping" }

Server → Client broadcasts (JSON):
    { "type": "presence",      "viewers": ["user_id", ...] }
    { "type": "editor_lock",   "locked_by": "user_id", "locked_by_name": "Ali" }
    { "type": "editor_unlock" }
    { "type": "cursor",        "user_id": "...", "position": 145 }
    { "type": "lock_denied",   "locked_by": "user_id", "locked_by_name": "Ali" }
    { "type": "document_restored", "version": <int>, "restored_by": "<user_id>", "restored_by_name": "..." }
    { "type": "error",         "detail": "..." }
"""

import json
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.api.websocket.manager import manager
from app.auth.supabase_auth import get_ws_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/document/{doc_id}")
async def document_presence_websocket(
    doc_id: str,
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token"),
):
    """
    Document presence WebSocket.

    Tracks all users who have the document tab open and manages the soft
    edit lock so only one student can actively edit at a time.
    The edit lock is advisory — the HTTP autosave endpoint still resolves
    true conflicts via optimistic locking (lock_version).
    """
    # ── Auth ─────────────────────────────────────────────────────────────────
    user = await get_ws_user(token)
    if user is None:
        await websocket.accept()
        await websocket.send_json({"type": "error", "detail": "Unauthorized"})
        await websocket.close(code=4001)
        return

    user_id = str(user.user_id)
    user_name = user.full_name or user_id
    room_key = f"doc:{doc_id}"

    # ── Connect ──────────────────────────────────────────────────────────────
    await manager.connect(room_key, user_id, websocket)

    # Send current lock state to the newly connected user
    lock_holder = manager.get_lock_holder(doc_id)
    if lock_holder:
        await websocket.send_json(
            {
                "type": "editor_lock",
                "locked_by": lock_holder,
                "locked_by_name": lock_holder,  # name lookup skipped for simplicity
            }
        )

    # Broadcast updated presence
    await manager.broadcast(
        room_key,
        {"type": "presence", "viewers": manager.get_online_users(room_key)},
    )

    try:
        while True:
            try:
                raw = await websocket.receive_text()
            except (WebSocketDisconnect, RuntimeError):
                break

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "detail": "Invalid JSON"})
                continue

            msg_type = data.get("type")

            # ── Ping ─────────────────────────────────────────────────────
            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            # ── Acquire edit lock ─────────────────────────────────────────
            if msg_type == "start_editing":
                acquired = manager.acquire_lock(doc_id, user_id)
                if acquired:
                    await manager.broadcast(
                        room_key,
                        {
                            "type": "editor_lock",
                            "locked_by": user_id,
                            "locked_by_name": user_name,
                        },
                    )
                else:
                    holder = manager.get_lock_holder(doc_id)
                    await websocket.send_json(
                        {
                            "type": "lock_denied",
                            "locked_by": holder,
                            "locked_by_name": holder,
                        }
                    )
                continue

            # ── Release edit lock ─────────────────────────────────────────
            if msg_type == "stop_editing":
                released = manager.release_lock(doc_id, user_id)
                if released:
                    await manager.broadcast(
                        room_key,
                        {"type": "editor_unlock"},
                    )
                continue

            # ── Cursor position (optional, lightweight) ───────────────────
            if msg_type == "cursor":
                position = data.get("position")
                await manager.broadcast_except(
                    room_key,
                    exclude_user_id=user_id,
                    data={
                        "type": "cursor",
                        "user_id": user_id,
                        "position": position,
                    },
                )
                continue

    finally:
        # Always clean up on disconnect, error, or normal close
        released = manager.release_lock(doc_id, user_id)
        manager.disconnect(room_key, user_id)

        if released:
            await manager.broadcast(room_key, {"type": "editor_unlock"})

        await manager.broadcast(
            room_key,
            {"type": "presence", "viewers": manager.get_online_users(room_key)},
        )
