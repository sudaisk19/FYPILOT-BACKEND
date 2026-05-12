"""Accept / reject / list document edit proposals (modify-mode AI flow)."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase_auth import get_current_user
from app.db import get_db
from app.db.mongo import get_mongo_db
from app.models.user import User
from app.repositories.document_edit_proposal_repository import (
    PROPOSAL_STATUS_ACCEPTED,
    PROPOSAL_STATUS_REJECTED,
    document_edit_proposal_repo,
)
from app.schemas.document_schema import AutosaveRequest, AutosaveResponse
from app.services.document_access import (
    require_group_document_for_user,
    user_is_group_member,
)
from app.services.document_chat_service import document_chat_service
from app.services.document_service import document_service

router = APIRouter()


async def _require_workspace_access(
    db: AsyncSession,
    mongo_db: AsyncIOMotorDatabase,
    session_id: str,
    current_user: User,
) -> Dict[str, Any]:
    session = await document_chat_service.get_workspace(mongo_db, session_id)
    if not session or not session.get("is_active", True):
        raise HTTPException(status_code=404, detail="Workspace not found")
    gid_raw = session.get("group_id")
    if not gid_raw:
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        gid = UUID(str(gid_raw))
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="Workspace not found")
    if not await user_is_group_member(db, current_user.user_id, gid):
        raise HTTPException(
            status_code=403,
            detail="You are not a member of the group that owns this workspace.",
        )
    return session


async def _proposal_or_404(
    mongo_db: AsyncIOMotorDatabase, proposal_id: str
) -> Dict[str, Any]:
    prop = await document_edit_proposal_repo.get_by_id(mongo_db, proposal_id)
    if not prop:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return prop


class PendingProposalItem(BaseModel):
    proposal_id: str
    chat_session_id: str
    active_document_id: str
    baseline_lock_version: int
    summary: str
    html_fragment: str
    warnings: List[str] = []
    user_id: str
    created_at: Optional[datetime] = None
    assistant_message_id: Optional[str] = None


class PendingProposalsResponse(BaseModel):
    proposals: List[PendingProposalItem]


@router.get(
    "/students/document-edit-proposals/pending",
    response_model=PendingProposalsResponse,
    summary="List pending modify proposals for a workspace",
    tags=["student-documents"],
)
async def list_pending_proposals(
    session_id: str = Query(..., description="Workspace (Mongo chat session) id"),
    active_document_id: Optional[str] = Query(
        None, description="Optional filter by Postgres document UUID"
    ),
    db: AsyncSession = Depends(get_db),
    mongo_db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user: User = Depends(get_current_user),
):
    await _require_workspace_access(db, mongo_db, session_id, current_user)
    raw = await document_edit_proposal_repo.list_pending_for_session(
        mongo_db, session_id, active_document_id=active_document_id
    )
    items: List[PendingProposalItem] = []
    for r in raw:
        items.append(
            PendingProposalItem(
                proposal_id=r["_id"],
                chat_session_id=str(r["chat_session_id"]),
                active_document_id=str(r["active_document_id"]),
                baseline_lock_version=int(r["baseline_lock_version"]),
                summary=str(r.get("summary") or ""),
                html_fragment=str(r.get("html_fragment") or ""),
                warnings=[str(w) for w in (r.get("warnings") or [])],
                user_id=str(r.get("user_id") or ""),
                created_at=r.get("created_at"),
                assistant_message_id=(
                    str(r["assistant_message_id"])
                    if r.get("assistant_message_id")
                    else None
                ),
            )
        )
    return PendingProposalsResponse(proposals=items)


@router.post(
    "/students/document-edit-proposals/{proposal_id}/reject",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Reject a pending proposal (no Postgres write)",
    tags=["student-documents"],
)
async def reject_proposal(
    proposal_id: str,
    db: AsyncSession = Depends(get_db),
    mongo_db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user: User = Depends(get_current_user),
):
    prop = await _proposal_or_404(mongo_db, proposal_id)
    doc_uuid = UUID(str(prop["active_document_id"]))
    await require_group_document_for_user(db, doc_uuid, current_user)
    await _require_workspace_access(
        db, mongo_db, str(prop["chat_session_id"]), current_user
    )
    ok = await document_edit_proposal_repo.update_status(
        mongo_db, proposal_id, PROPOSAL_STATUS_REJECTED, only_if_pending=True
    )
    if not ok:
        raise HTTPException(
            status_code=409, detail="Proposal is not pending or does not exist."
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/students/document-edit-proposals/{proposal_id}/apply",
    response_model=AutosaveResponse,
    summary="Autosave merged content and mark proposal accepted",
    tags=["student-documents"],
)
async def apply_proposal(
    proposal_id: str,
    body: AutosaveRequest,
    db: AsyncSession = Depends(get_db),
    mongo_db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user: User = Depends(get_current_user),
):
    prop = await _proposal_or_404(mongo_db, proposal_id)
    if prop.get("status") != "pending":
        raise HTTPException(status_code=409, detail="Proposal is not pending.")
    doc_uuid = UUID(str(prop["active_document_id"]))
    await require_group_document_for_user(db, doc_uuid, current_user)
    await _require_workspace_access(
        db, mongo_db, str(prop["chat_session_id"]), current_user
    )

    doc = await document_service.autosave_document(
        db=db,
        doc_id=doc_uuid,
        content=body.content,
        expected_lock_version=body.lock_version,
        updated_by=current_user.user_id,
    )
    accepted = await document_edit_proposal_repo.update_status(
        mongo_db, proposal_id, PROPOSAL_STATUS_ACCEPTED, only_if_pending=True
    )
    if not accepted:
        raise HTTPException(
            status_code=409,
            detail="Proposal was resolved by another request; document may have saved.",
        )
    return AutosaveResponse.model_validate(doc)
