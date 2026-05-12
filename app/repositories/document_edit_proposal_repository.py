"""MongoDB persistence for pending AI document edit proposals (modify flow)."""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase

PROPOSAL_STATUS_PENDING = "pending"
PROPOSAL_STATUS_ACCEPTED = "accepted"
PROPOSAL_STATUS_REJECTED = "rejected"
PROPOSAL_STATUS_EXPIRED = "expired"


class DocumentEditProposalRepository:
    COLLECTION = "document_edit_proposals"

    async def ensure_indexes(self, db: AsyncIOMotorDatabase) -> None:
        await db[self.COLLECTION].create_index(
            [("chat_session_id", 1), ("status", 1)],
            name="idx_edit_proposals_session_status",
        )
        await db[self.COLLECTION].create_index(
            [("active_document_id", 1), ("status", 1)],
            name="idx_edit_proposals_doc_status",
        )

    async def create_proposal(
        self,
        db: AsyncIOMotorDatabase,
        *,
        chat_session_id: str,
        active_document_id: str,
        baseline_lock_version: int,
        html_fragment: str,
        summary: str,
        warnings: Optional[List[str]],
        user_id: str,
        request_id: Optional[str] = None,
    ) -> str:
        now = datetime.datetime.utcnow()
        doc: Dict[str, Any] = {
            "chat_session_id": chat_session_id,
            "active_document_id": active_document_id,
            "baseline_lock_version": baseline_lock_version,
            "html_fragment": html_fragment,
            "summary": summary,
            "warnings": warnings or [],
            "user_id": user_id,
            "status": PROPOSAL_STATUS_PENDING,
            "assistant_message_id": None,
            "request_id": request_id,
            "created_at": now,
        }
        res = await db[self.COLLECTION].insert_one(doc)
        return str(res.inserted_id)

    async def set_assistant_message_id(
        self,
        db: AsyncIOMotorDatabase,
        proposal_id: str,
        assistant_message_id: str,
    ) -> bool:
        try:
            oid = ObjectId(proposal_id)
        except InvalidId:
            return False
        r = await db[self.COLLECTION].update_one(
            {"_id": oid},
            {"$set": {"assistant_message_id": assistant_message_id}},
        )
        return r.modified_count > 0

    async def get_by_id(
        self, db: AsyncIOMotorDatabase, proposal_id: str
    ) -> Optional[Dict[str, Any]]:
        try:
            oid = ObjectId(proposal_id)
        except InvalidId:
            return None
        doc = await db[self.COLLECTION].find_one({"_id": oid})
        if doc:
            doc["_id"] = str(doc["_id"])
        return doc

    async def update_status(
        self,
        db: AsyncIOMotorDatabase,
        proposal_id: str,
        status: str,
        *,
        only_if_pending: bool = True,
    ) -> bool:
        try:
            oid = ObjectId(proposal_id)
        except InvalidId:
            return False
        filt: Dict[str, Any] = {"_id": oid}
        if only_if_pending:
            filt["status"] = PROPOSAL_STATUS_PENDING
        now = datetime.datetime.utcnow()
        r = await db[self.COLLECTION].update_one(
            filt,
            {"$set": {"status": status, "resolved_at": now}},
        )
        return r.modified_count > 0

    async def list_pending_for_session(
        self,
        db: AsyncIOMotorDatabase,
        chat_session_id: str,
        active_document_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        q: Dict[str, Any] = {
            "chat_session_id": chat_session_id,
            "status": PROPOSAL_STATUS_PENDING,
        }
        if active_document_id:
            q["active_document_id"] = active_document_id
        cursor = (
            db[self.COLLECTION].find(q).sort("created_at", -1).limit(min(limit, 100))
        )
        rows = await cursor.to_list(length=min(limit, 100))
        for r in rows:
            r["_id"] = str(r["_id"])
        return rows


document_edit_proposal_repo = DocumentEditProposalRepository()
