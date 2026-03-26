"""
Student Documents API
REST endpoints for the Unified Group Documentation Workspace.

Endpoints:
  GET    /students/chat-sessions/{session_id}/documents      - List all tabs in a workspace
  PATCH  /students/documents/{doc_id}/autosave               - Optimistic-lock live draft save
  POST   /students/documents/{doc_id}/versions               - Create an immutable version snapshot
  POST   /students/chat-sessions                             - Create a new workspace
  GET    /students/chat-sessions                             - List workspaces for a group
  POST   /students/chat-sessions/{session_id}/documents      - Link/create a doc in a workspace
  POST   /students/chat-sessions/{session_id}/messages       - Send a chat message (with LLM)
  GET    /students/chat-sessions/{session_id}/messages       - Paginate chat history
"""

import uuid
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase_auth import get_current_user
from app.db import get_db
from app.db.mongo import get_mongo_db
from app.models.user import User
from app.schemas.document_schema import (
    AutosaveRequest,
    AutosaveResponse,
    ChatMessageResponse,
    CreateDocumentRequest,
    CreateVersionRequest,
    CreateWorkspaceRequest,
    DocumentVersionResponse,
    GroupDocumentResponse,
    MessageListResponse,
    SendMessageRequest,
    WorkspaceResponse,
)
from app.services.document_chat_service import document_chat_service
from app.services.document_service import document_service

router = APIRouter()


# ── Workspace (Session) Endpoints ────────────────────────────────────────────


@router.post(
    "/students/chat-sessions",
    response_model=WorkspaceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new document workspace",
    tags=["student-documents"],
)
async def create_workspace(
    body: CreateWorkspaceRequest,
    mongo_db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a new MongoDB workspace session.
    Optionally pre-links existing Postgres document IDs.
    """
    session_id = str(uuid.uuid4())
    session = await document_chat_service.create_workspace(
        db=mongo_db,
        session_id=session_id,
        group_id=body.group_id,
        title=body.title,
        created_by=str(current_user.user_id),
        document_ids=body.document_ids,
    )
    return WorkspaceResponse(
        session_id=session["_id"],
        group_id=session["group_id"],
        title=session["title"],
        document_ids=session["document_ids"],
        is_active=session["is_active"],
        created_at=session["created_at"],
        updated_at=session["updated_at"],
    )


@router.get(
    "/students/chat-sessions",
    response_model=List[WorkspaceResponse],
    summary="List all workspaces for the current user's group",
    tags=["student-documents"],
)
async def list_workspaces(
    group_id: str = Query(..., description="Postgres group UUID"),
    mongo_db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user: User = Depends(get_current_user),
):
    sessions = await document_chat_service.list_workspaces(mongo_db, group_id)
    return [
        WorkspaceResponse(
            session_id=s["_id"],
            group_id=s["group_id"],
            title=s["title"],
            document_ids=s.get("document_ids", []),
            is_active=s["is_active"],
            created_at=s["created_at"],
            updated_at=s["updated_at"],
        )
        for s in sessions
    ]


# ── Document-in-Workspace Endpoints ──────────────────────────────────────────


@router.get(
    "/students/chat-sessions/{session_id}/documents",
    response_model=List[GroupDocumentResponse],
    summary="Fetch all document tabs in a workspace",
    tags=["student-documents"],
)
async def list_workspace_documents(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns an array of all GroupDocuments linked to this workspace.
    Used by the frontend to populate editor tabs on load.
    """
    docs = await document_service.get_workspace_documents(db, session_id)
    return [GroupDocumentResponse.model_validate(d) for d in docs]


@router.post(
    "/students/chat-sessions/{session_id}/documents",
    response_model=GroupDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new document inside a workspace",
    tags=["student-documents"],
)
async def create_document_in_workspace(
    session_id: str,
    body: CreateDocumentRequest,
    db: AsyncSession = Depends(get_db),
    mongo_db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user: User = Depends(get_current_user),
):
    """
    Creates a new Postgres GroupDocument with chat_session_id set,
    then appends its UUID to the MongoDB session's document_ids array.
    """
    # body.chat_session_id may be provided; if not, use the path param
    effective_session_id = body.chat_session_id or session_id

    # Derive group_id from the user's group — we need it stored on the doc
    # For now the caller sets it via the URL; we extract from the Mongo session
    session = await document_chat_service.get_workspace(mongo_db, session_id)
    group_id_str = session["group_id"] if session else None
    if not group_id_str:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Workspace session not found.")

    doc = await document_service.create_document(
        db=db,
        group_id=UUID(group_id_str),
        doc_type=body.doc_type,
        title=body.title,
        created_by=current_user.user_id,
        chat_session_id=effective_session_id,
        content=body.content,
    )

    # Link the new doc to the Mongo session
    await document_chat_service.link_document_to_session(
        db=mongo_db,
        session_id=session_id,
        document_id=str(doc.id),
    )

    return GroupDocumentResponse.model_validate(doc)


# ── Document Autosave & Versioning ────────────────────────────────────────────


@router.patch(
    "/students/documents/{doc_id}/autosave",
    response_model=AutosaveResponse,
    summary="Autosave the live draft (optimistic locking)",
    tags=["student-documents"],
)
async def autosave_document(
    doc_id: UUID,
    body: AutosaveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Saves the live draft content.
    Returns HTTP 409 Conflict if another writer has already incremented lock_version.
    Does NOT create a version snapshot row.
    """
    doc = await document_service.autosave_document(
        db=db,
        doc_id=doc_id,
        content=body.content,
        expected_lock_version=body.lock_version,
        updated_by=current_user.user_id,
    )
    return AutosaveResponse.model_validate(doc)


@router.post(
    "/students/documents/{doc_id}/versions",
    response_model=DocumentVersionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an immutable version snapshot",
    tags=["student-documents"],
)
async def create_version(
    doc_id: UUID,
    body: CreateVersionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Reads the current live content and inserts a new immutable row
    in document_versions (the 'snapshot' — NOT the autosave path).
    Triggered by: manual save, accepted AI edit, or PDF export.
    """
    snapshot = await document_service.create_version_snapshot(
        db=db,
        doc_id=doc_id,
        save_trigger=body.save_trigger,
        created_by=current_user.user_id,
    )
    return DocumentVersionResponse.model_validate(snapshot)


@router.get(
    "/students/documents/{doc_id}/versions",
    response_model=List[DocumentVersionResponse],
    summary="List all version snapshots for a document",
    tags=["student-documents"],
)
async def list_versions(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    versions = await document_service.list_versions(db, doc_id)
    return [DocumentVersionResponse.model_validate(v) for v in versions]


# ── Chat Messages ─────────────────────────────────────────────────────────────


@router.post(
    "/students/chat-sessions/{session_id}/messages",
    response_model=ChatMessageResponse,
    summary="Send a message and receive an AI reply",
    tags=["student-documents"],
)
async def send_message(
    session_id: str,
    body: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
    mongo_db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user: User = Depends(get_current_user),
):
    """
    Persists the student message, queries GPT-4o with the active document's
    content injected as context, persists the AI reply, and returns it.
    """
    reply = await document_chat_service.send_message_with_llm(
        pg_db=db,
        mongo_db=mongo_db,
        chat_session_id=session_id,
        sender_id=str(current_user.user_id),
        content=body.content,
        active_document_id=body.active_document_id,
    )
    return ChatMessageResponse(reply=reply)


@router.get(
    "/students/chat-sessions/{session_id}/messages",
    response_model=MessageListResponse,
    summary="Paginate chat history for a workspace",
    tags=["student-documents"],
)
async def get_messages(
    session_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    mongo_db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user: User = Depends(get_current_user),
):
    messages = await document_chat_service.get_messages(
        mongo_db=mongo_db,
        chat_session_id=session_id,
        skip=skip,
        limit=limit,
    )
    return MessageListResponse(messages=messages, total=len(messages))
