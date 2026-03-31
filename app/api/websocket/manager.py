"""
WebSocket Connection Manager
Tracks all live WebSocket connections per workspace session and document.
In-memory only — suitable for single-process deployments (single uvicorn worker).
For multi-worker deployments, replace with a Redis Pub/Sub backend.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)


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
        self._rooms[room_key][user_id] = ws
        logger.info(f"WS connected: user={user_id} room={room_key}")

    def disconnect(self, room_key: str, user_id: str) -> None:
        """Remove a connection from the room."""
        room = self._rooms.get(room_key, {})
        room.pop(user_id, None)
        if not room:
            self._rooms.pop(room_key, None)
        logger.info(f"WS disconnected: user={user_id} room={room_key}")

    # ── Broadcast / Send ─────────────────────────────────────────────────────

    async def broadcast(self, room_key: str, data: Dict[str, Any]) -> None:
        """Send a JSON payload to ALL connections in a room."""
        room = self._rooms.get(room_key, {})
        dead: List[str] = []
        for uid, ws in list(room.items()):
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(uid)
        for uid in dead:
            self.disconnect(room_key, uid)

    async def broadcast_except(
        self, room_key: str, exclude_user_id: str, data: Dict[str, Any]
    ) -> None:
        """Broadcast to everyone in the room EXCEPT one user."""
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


# Singleton — shared across all request handlers
manager = ConnectionManager()
