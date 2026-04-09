"""
WebSocket Connection Manager
Tracks all live WebSocket connections per workspace session and document.

When Redis is connected, ``broadcast`` / ``broadcast_except`` publish JSON envelopes
on channel ``fyp:ws:{room_key}`` so every Uvicorn worker delivers to its local sockets.
``start_redis_ws_subscriber()`` must run at app startup (see ``app.main``).

When Redis is unavailable, delivery is in-process only (single-worker behaviour).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import WebSocket

from app.metrics import decrement_websocket_connections, increment_websocket_connections

logger = logging.getLogger(__name__)

_WS_SUB_TASK: Optional[asyncio.Task] = None


class ConnectionManager:
    """
    Manages WebSocket connections grouped by a room key (session_id or doc_id).

    Structure:
        rooms: { room_key: { user_id: WebSocket } }
    """

    def __init__(self):
        # room_key → { user_id → WebSocket }
        self._rooms: Dict[str, Dict[str, WebSocket]] = {}
        # doc_id → user_id currently holding the edit lock (None if unlocked)
        self._doc_locks: Dict[str, Optional[str]] = {}

    # ── Connection Lifecycle ─────────────────────────────────────────────────

    async def connect(self, room_key: str, user_id: str, ws: WebSocket) -> None:
        """Accept a new WebSocket and register it in the room."""
        await ws.accept()
        if room_key not in self._rooms:
            self._rooms[room_key] = {}
        is_new_connection = user_id not in self._rooms[room_key]
        self._rooms[room_key][user_id] = ws
        if is_new_connection:
            increment_websocket_connections()
        logger.info(f"WS connected: user={user_id} room={room_key}")

    def disconnect(self, room_key: str, user_id: str) -> None:
        """Remove a connection from the room."""
        room = self._rooms.get(room_key, {})
        removed = room.pop(user_id, None)
        if removed is not None:
            decrement_websocket_connections()
        if not room:
            self._rooms.pop(room_key, None)
        logger.info(f"WS disconnected: user={user_id} room={room_key}")

    # ── Broadcast / Send (local process only) ───────────────────────────────

    async def _broadcast_local(self, room_key: str, data: Dict[str, Any]) -> None:
        """Send a JSON payload to ALL connections in a room (this worker only)."""
        room = self._rooms.get(room_key, {})
        dead: List[str] = []
        for uid, ws in list(room.items()):
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(uid)
        for uid in dead:
            self.disconnect(room_key, uid)

    async def _broadcast_except_local(
        self, room_key: str, exclude_user_id: str, data: Dict[str, Any]
    ) -> None:
        """Broadcast to everyone in the room EXCEPT one user (this worker only)."""
        room = self._rooms.get(room_key, {})
        dead: List[str] = []
        for uid, ws in list(room.items()):
            if uid == exclude_user_id:
                continue
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(uid)
        for uid in dead:
            self.disconnect(room_key, uid)

    async def broadcast(self, room_key: str, data: Dict[str, Any]) -> None:
        """Send to all in room; uses Redis fan-out across workers when available."""
        from app.services.cache import cache

        if cache.is_available:
            try:
                channel = f"fyp:ws:{room_key}"
                payload = json.dumps(
                    {"kind": "all", "payload": data},
                    ensure_ascii=False,
                )
                await cache.client.publish(channel, payload)
            except Exception as e:
                logger.warning("Redis WS publish failed, using local delivery: %s", e)
                await self._broadcast_local(room_key, data)
        else:
            await self._broadcast_local(room_key, data)

    async def broadcast_except(
        self, room_key: str, exclude_user_id: str, data: Dict[str, Any]
    ) -> None:
        from app.services.cache import cache

        if cache.is_available:
            try:
                channel = f"fyp:ws:{room_key}"
                payload = json.dumps(
                    {
                        "kind": "except",
                        "exclude": exclude_user_id,
                        "payload": data,
                    },
                    ensure_ascii=False,
                )
                await cache.client.publish(channel, payload)
            except Exception as e:
                logger.warning("Redis WS publish failed, using local delivery: %s", e)
                await self._broadcast_except_local(room_key, exclude_user_id, data)
        else:
            await self._broadcast_except_local(room_key, exclude_user_id, data)

    async def send_to_user(
        self, room_key: str, user_id: str, data: Dict[str, Any]
    ) -> bool:
        """Send a JSON payload to a single user. Returns False if not connected."""
        ws = self._rooms.get(room_key, {}).get(user_id)
        if ws is None:
            return False
        try:
            await ws.send_json(data)
            return True
        except Exception:
            self.disconnect(room_key, user_id)
            return False

    # ── Presence ─────────────────────────────────────────────────────────────

    def get_online_users(self, room_key: str) -> List[str]:
        """Return list of user_ids currently connected to a room."""
        return list(self._rooms.get(room_key, {}).keys())

    def is_connected(self, room_key: str, user_id: str) -> bool:
        return user_id in self._rooms.get(room_key, {})

    # ── Document Edit Locking ─────────────────────────────────────────────────

    def acquire_lock(self, doc_id: str, user_id: str) -> bool:
        """
        Try to acquire an edit lock on a document.
        Returns True if lock was acquired, False if someone else holds it.
        """
        holder = self._doc_locks.get(doc_id)
        if holder is None or holder == user_id:
            self._doc_locks[doc_id] = user_id
            return True
        return False

    def release_lock(self, doc_id: str, user_id: str) -> bool:
        """
        Release the edit lock.
        Returns True if the lock was released.
        """
        if self._doc_locks.get(doc_id) == user_id:
            self._doc_locks.pop(doc_id, None)
            return True
        return False

    def get_lock_holder(self, doc_id: str) -> Optional[str]:
        """Return the user_id holding the lock, or None if unlocked."""
        return self._doc_locks.get(doc_id)

    def force_release_lock(self, doc_id: str) -> None:
        """Release lock regardless of who holds it (e.g., on disconnect)."""
        self._doc_locks.pop(doc_id, None)


manager = ConnectionManager()


async def _redis_ws_listener_loop() -> None:
    from redis.asyncio import Redis

    from app.core.config import settings

    r = Redis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )
    pubsub = r.pubsub()
    try:
        await pubsub.psubscribe("fyp:ws:*")
        logger.info("WebSocket Redis subscriber: psubscribe fyp:ws:*")
        async for message in pubsub.listen():
            if message["type"] != "pmessage":
                continue
            ch = message["channel"]
            raw = message["data"]
            if not isinstance(ch, str) or not ch.startswith("fyp:ws:"):
                continue
            room_key = ch[len("fyp:ws:") :]
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            kind = obj.get("kind")
            if kind == "except":
                await manager._broadcast_except_local(
                    room_key, obj["exclude"], obj["payload"]
                )
            elif kind == "all":
                await manager._broadcast_local(room_key, obj["payload"])
            else:
                await manager._broadcast_local(room_key, obj)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.warning("WebSocket Redis listener stopped: %s", e)
    finally:
        try:
            await pubsub.punsubscribe()
            await pubsub.close()
        except Exception:
            pass
        try:
            await r.close()
        except Exception:
            pass


def start_redis_ws_subscriber() -> None:
    """Fan-in Redis pub/sub messages to local WebSocket connections (multi-worker)."""
    global _WS_SUB_TASK
    if _WS_SUB_TASK is not None and not _WS_SUB_TASK.done():
        return
    from app.services.cache import cache

    if not cache.is_available:
        return
    _WS_SUB_TASK = asyncio.create_task(_redis_ws_listener_loop())
