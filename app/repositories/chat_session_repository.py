"""
Chat Session Repository (MongoDB)
Handles document_chat_sessions and document_chat_messages collections.
Uses the workspace model: one session has_many Postgres document IDs.
"""

import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


class ChatSessionRepository:
    """
    All MongoDB access for the workspace chat feature.
    Collections:
        - document_chat_sessions
        - document_chat_messages
    """

    SESSIONS_COL = "document_chat_sessions"
    MESSAGES_COL = "document_chat_messages"

    async def ensure_indexes(self, db: AsyncIOMotorDatabase) -> None:
        """Idempotent indexes for chat history queries."""
        await db[self.MESSAGES_COL].create_index(
            [("chat_session_id", 1), ("_id", 1)],
            name="idx_chat_messages_session_id",
        )

    # ── Session Operations ──────────────────────────────────────────────────

    async def create_session(
        self,
        db: AsyncIOMotorDatabase,
        session_id: str,
        group_id: str,
        title: str,
        created_by: str,
        document_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Create a new workspace session.
        `session_id` is provided by caller so it can be stored as FK in Postgres.
        """
        now = datetime.datetime.utcnow()
        doc = {
            "_id": session_id,
            "group_id": group_id,
            "title": title,
            "created_by": created_by,
            "document_ids": document_ids or [],
            "is_active": True,
            "tags": [],
            "created_at": now,
            "updated_at": now,
        }
        await db[self.SESSIONS_COL].insert_one(doc)
        return doc

    async def get_session(
        self, db: AsyncIOMotorDatabase, session_id: str
    ) -> Optional[Dict[str, Any]]:
        doc = await db[self.SESSIONS_COL].find_one({"_id": session_id})
        return doc

    async def list_sessions_for_group(
        self, db: AsyncIOMotorDatabase, group_id: str, active_only: bool = True
    ) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {"group_id": group_id}
        if active_only:
            query["is_active"] = True
        cursor = db[self.SESSIONS_COL].find(query).sort("updated_at", -1)
        return await cursor.to_list(length=100)

    async def add_document_to_session(
        self,
        db: AsyncIOMotorDatabase,
        session_id: str,
        document_id: str,
    ) -> None:
        """
        Append a Postgres document UUID to the session's document_ids array.
        Uses $addToSet so duplicates are ignored.
        """
        now = datetime.datetime.utcnow()
        await db[self.SESSIONS_COL].update_one(
            {"_id": session_id},
            {
                "$addToSet": {"document_ids": document_id},
                "$set": {"updated_at": now},
            },
        )

    async def rename_session(
        self, db: AsyncIOMotorDatabase, session_id: str, title: str
    ) -> bool:
        """Rename an active workspace session only (inactive → no-op)."""
        now = datetime.datetime.utcnow()
        result = await db[self.SESSIONS_COL].update_one(
            {"_id": session_id, "is_active": True},
            {"$set": {"title": title, "updated_at": now}},
        )
        return result.modified_count > 0

    async def delete_session(self, db: AsyncIOMotorDatabase, session_id: str) -> bool:
        """Soft-delete an active session (is_active=True → False). Idempotent for already inactive."""
        now = datetime.datetime.utcnow()
        result = await db[self.SESSIONS_COL].update_one(
            {"_id": session_id, "is_active": True},
            {"$set": {"is_active": False, "updated_at": now}},
        )
        return result.modified_count > 0

    # ── Message Operations ──────────────────────────────────────────────────

    async def save_message(
        self,
        db: AsyncIOMotorDatabase,
        chat_session_id: str,
        sender_id: str,
        sender_type: str,  # "student" | "llm" | "system"
        content: str,
        doc_context: Optional[Dict[str, Any]] = None,
        is_complete: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
        sender_name: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> str:
        """Persist a single chat message and return its string ObjectId."""
        doc = {
            "chat_session_id": chat_session_id,
            "sender_id": sender_id,
            "sender_type": sender_type,
            "content": content,
            "is_complete": is_complete,
            # doc_context: { active_document_id, version_number }
            "doc_context": doc_context,
            "read_by": [sender_id] if sender_type == "student" else [],
            "metadata": metadata or {},
            "created_at": datetime.datetime.utcnow(),
        }
        if sender_name:
            doc["sender_name"] = sender_name
        if request_id:
            doc["request_id"] = request_id
        result = await db[self.MESSAGES_COL].insert_one(doc)

        # bump session updated_at
        await db[self.SESSIONS_COL].update_one(
            {"_id": chat_session_id},
            {"$set": {"updated_at": datetime.datetime.utcnow()}},
        )
        return str(result.inserted_id)

    async def count_messages(
        self, db: AsyncIOMotorDatabase, chat_session_id: str
    ) -> int:
        return await db[self.MESSAGES_COL].count_documents(
            {"chat_session_id": chat_session_id}
        )

    async def get_last_message(
        self, db: AsyncIOMotorDatabase, chat_session_id: str
    ) -> Optional[Dict[str, Any]]:
        cursor = (
            db[self.MESSAGES_COL]
            .find({"chat_session_id": chat_session_id})
            .sort("_id", -1)
            .limit(1)
        )
        rows = await cursor.to_list(length=1)
        if not rows:
            return None
        m = rows[0]
        m["_id"] = str(m["_id"])
        return m

    async def get_messages(
        self,
        db: AsyncIOMotorDatabase,
        chat_session_id: str,
        skip: int = 0,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Return paginated messages in chronological order."""
        cursor = (
            db[self.MESSAGES_COL]
            .find({"chat_session_id": chat_session_id})
            .sort("_id", 1)  # ObjectId ascending ≈ insertion order
            .skip(skip)
            .limit(limit)
        )
        results = await cursor.to_list(length=limit)
        for m in results:
            m["_id"] = str(m["_id"])
        return results

    async def get_messages_after(
        self,
        db: AsyncIOMotorDatabase,
        chat_session_id: str,
        after_id: Optional[str],
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Messages strictly after `after_id` (ObjectId string), oldest first.
        If after_id is None, returns the first `limit` messages chronologically.
        """
        q: Dict[str, Any] = {"chat_session_id": chat_session_id}
        if after_id:
            q["_id"] = {"$gt": ObjectId(after_id)}
        cursor = db[self.MESSAGES_COL].find(q).sort("_id", 1).limit(limit)
        results = await cursor.to_list(length=limit)
        for m in results:
            m["_id"] = str(m["_id"])
        return results

    async def get_recent_messages_for_context(
        self,
        db: AsyncIOMotorDatabase,
        chat_session_id: str,
        n: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Return the last N messages for LLM history context,
        returned in chronological order (oldest first).
        """
        cursor = (
            db[self.MESSAGES_COL]
            .find({"chat_session_id": chat_session_id})
            .sort("_id", -1)  # newest first
            .limit(n)
        )
        results = await cursor.to_list(length=n)
        # Reverse to restore chronological order
        results.reverse()
        for m in results:
            m["_id"] = str(m["_id"])
        return results

    async def mark_read(
        self,
        db: AsyncIOMotorDatabase,
        message_id: str,
        user_id: str,
    ) -> None:
        """Mark a message as read by a user."""
        await db[self.MESSAGES_COL].update_one(
            {"_id": ObjectId(message_id)},
            {"$addToSet": {"read_by": user_id}},
        )


chat_session_repo = ChatSessionRepository()
