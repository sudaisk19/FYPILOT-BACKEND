"""
Student Documents API
REST endpoints for the Unified Group Documentation Workspace.

Endpoints:
  GET    /students/chat-sessions/{session_id}/documents      - List all tabs in a workspace
  PATCH  /students/documents/{doc_id}/autosave               - Optimistic-lock live draft save
   POST   /students/documents/{doc_id}/versions               - Create an immutable version snapshot
  GET    /students/documents/{doc_id}/versions               - List all versions
  GET    /students/documents/{doc_id}/versions/{version_number} - Read-only snapshot (preview)
  POST   /students/documents/{doc_id}/versions/{version_number}/restore - Restore draft from snapshot
  GET    /students/documents/{doc_id}                        - Fetch single document
  PATCH  /students/documents/{doc_id}                        - Rename document
  POST   /students/chat-sessions                             - Create a new workspace
  PATCH  /students/chat-sessions/{session_id}                - Rename workspace
  DELETE /students/chat-sessions/{session_id}                - Delete workspace
  GET    /students/chat-sessions                             - List workspaces for a group
  POST   /students/chat-sessions/{session_id}/documents      - Link/create a doc in a workspace
  POST   /students/chat-sessions/{session_id}/messages       - Send a chat message (with LLM)
  GET    /students/chat-sessions/{session_id}/messages       - Paginate chat history
"""

# --- Manual tests (replace JWT, session_id, group membership as needed) ----------
# export TOKEN="<jwt>"
# export SID="<session_uuid>"
#
# PATCH rename (expect 200 + JSON body, or 403/404/422):
# curl -sS -X PATCH "http://localhost:8000/api/students/chat-sessions/${SID}" \
#   -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
#   -d '{"title":"New workspace title"}' -w "\nHTTP %{http_code}\n"
#
# DELETE soft-delete (expect 204 empty body):
# curl -sS -X DELETE "http://localhost:8000/api/students/chat-sessions/${SID}" \
#   -H "Authorization: Bearer ${TOKEN}" -w "\nHTTP %{http_code}\n" -D -
#
# import httpx
# client = httpx.Client(base_url="http://localhost:8000", headers={"Authorization": "Bearer <jwt>"})
# r = client.patch("/api/students/chat-sessions/<session_id>", json={"title": "New Name"})
# print(r.status_code, r.text)
# r = client.delete("/api/students/chat-sessions/<session_id>")
# print(r.status_code, r.text)
# -------------------------------------------------------------------------------

import asyncio
import logging
import os
import tempfile
import uuid
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from supabase import Client

from app.api.websocket.manager import manager
from app.auth.supabase_auth import get_current_user
from app.db import get_db
from app.db.mongo import get_mongo_db
from app.db.supabase import get_supabase_client
from app.models.announcement import AnnouncementFile
from app.models.group import GroupMember
from app.models.group_document import DocTypeEnum
from app.models.user import User
from app.schemas.document_schema import (
    AutosaveRequest,
    AutosaveResponse,
    ChatMessageResponse,
    CreateDocumentRequest,
    CreateVersionRequest,
    CreateWorkspaceRequest,
    DocumentTypeOptionResponse,
    DocumentVersionResponse,
    GroupDocumentResponse,
    ImportTemplateRequest,
    MessageListResponse,
    RenameDocumentRequest,
    RenameWorkspaceRequest,
    RestoreVersionRequest,
    RestoreVersionResponse,
    SendMessageRequest,
    WorkspaceResponse,
)
from app.services.document_access import require_group_document_for_user
from app.services.document_chat_service import document_chat_service
from app.services.document_service import document_service
from app.services.extract_text import process_document_import_async
from app.services.storage_service import (
    ANNOUNCEMENTS_BUCKET,
    download_file_from_supabase,
)

router = APIRouter()
logger = logging.getLogger(__name__)


DOC_TYPE_METADATA = {
    DocTypeEnum.proposal: {
        "label": "FYP Proposal",
        "description": "Problem statement, objectives, scope, and feasibility.",
    },
    DocTypeEnum.srs: {
        "label": "Software Requirements Specification (SRS)",
        "description": "Functional and non-functional requirements.",
    },
    DocTypeEnum.sds: {
        "label": "Software Design Specification (SDS)",
        "description": "Architecture, components, interfaces, and design details.",
    },
    DocTypeEnum.report_fyp1: {
        "label": "FYP1 Progress Report",
        "description": "Interim report with literature review and planned implementation.",
    },
    DocTypeEnum.report_fyp2: {
        "label": "FYP2 Final Report",
        "description": "Final report with implementation, results, and conclusions.",
    },
    DocTypeEnum.testcases: {
        "label": "Test Cases",
        "description": "Verification scenarios with expected outcomes.",
    },
    DocTypeEnum.other: {
        "label": "Other",
        "description": "General purpose document type.",
    },
}


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
) -> dict:
    """
    Load session, require active + group_id; 403 if user not in group_members.
    """
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


@router.get(
    "/students/document-types",
    response_model=List[DocumentTypeOptionResponse],
    summary="Get available document types for dropdowns",
    tags=["student-documents"],
)
async def list_document_types(
    current_user: User = Depends(get_current_user),
):
    """
    Return all allowed DocTypeEnum values with frontend-friendly labels.
    """
    _ = current_user  # enforce authenticated access
    options: List[DocumentTypeOptionResponse] = []
    for doc_type in DocTypeEnum:
        metadata = DOC_TYPE_METADATA.get(
            doc_type,
            {
                "label": doc_type.value.replace("_", " ").title(),
                "description": "General purpose document type.",
            },
        )
        options.append(
            DocumentTypeOptionResponse(
                value=doc_type,
                label=metadata["label"],
                description=metadata["description"],
            )
        )
    return options


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


@router.patch(
    "/students/chat-sessions/{session_id}",
    response_model=WorkspaceResponse,
    summary="Rename a workspace",
    tags=["student-documents"],
)
async def rename_workspace(
    session_id: str,
    body: RenameWorkspaceRequest,
    db: AsyncSession = Depends(get_db),
    mongo_db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user: User = Depends(get_current_user),
):
    await _require_active_workspace_group_access(db, mongo_db, session_id, current_user)
    title = body.title.strip()
    if not title:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Title must not be empty",
        )
    if len(title) > 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Title must be at most 100 characters",
        )

    success = await document_chat_service.rename_workspace(mongo_db, session_id, title)
    if not success:
        raise HTTPException(status_code=404, detail="Workspace not found")

    session = await document_chat_service.get_workspace(mongo_db, session_id)
    return WorkspaceResponse(
        session_id=session["_id"],
        group_id=session["group_id"],
        title=session["title"],
        document_ids=session.get("document_ids", []),
        is_active=session.get("is_active", True),
        created_at=session.get("created_at"),
        updated_at=session.get("updated_at"),
    )


@router.delete(
    "/students/chat-sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a workspace",
    tags=["student-documents"],
)
async def delete_workspace(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    mongo_db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user: User = Depends(get_current_user),
):
    """
    Soft-delete MongoDB workspace (is_active=false). Postgres GroupDocuments unchanged.
    """
    await _require_active_workspace_group_access(db, mongo_db, session_id, current_user)
    success = await document_chat_service.delete_workspace(mongo_db, session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return None


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
    try:
        docs = await document_service.get_workspace_documents(db, session_id)
    except (TimeoutError, asyncio.TimeoutError, SQLAlchemyError) as exc:
        logger.exception(
            "Workspace documents query failed for session %s: %s", session_id, exc
        )
        # Return an empty list so the UI does not crash on non-array responses.
        return []
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
    # Always use the URL path param as the canonical session_id.
    # Never let body.chat_session_id override it — doing so causes a Postgres/Mongo
    # mismatch where MongoDB has the doc UUID but Postgres can't find the doc on reload.
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
        chat_session_id=session_id,  # <-- always the URL path param
        content=body.content,
    )

    # Link the new doc to the Mongo session
    await document_chat_service.link_document_to_session(
        db=mongo_db,
        session_id=session_id,
        document_id=str(doc.id),
    )

    return GroupDocumentResponse.model_validate(doc)


@router.post(
    "/students/chat-sessions/{session_id}/import-template",
    response_model=GroupDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Import an admin template into the workspace",
    tags=["student-documents"],
)
async def import_template(
    session_id: str,
    body: ImportTemplateRequest,
    clean: bool = Query(
        True, description="Use AI to clean PDF formatting (takes 3-5s)"
    ),
    db: AsyncSession = Depends(get_db),
    mongo_db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user: User = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
):
    """
    Downloads an admin template from Supabase Storage, extracts/cleans its text,
    and intelligently creates an editable GroupDocument inside the chat workspace.
    """
    # 1. Fetch the workspace to ensure it exists and get group_id
    session = await document_chat_service.get_workspace(mongo_db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Workspace session not found.")
    group_id_str = session["group_id"]
    if not group_id_str:
        raise HTTPException(
            status_code=404, detail="Workspace is not linked to a group."
        )

    # 2. Fetch the announcement file record from Postgres
    stmt = select(AnnouncementFile).where(
        AnnouncementFile.file_id == body.announcement_file_id
    )
    result = await db.execute(stmt)
    ann_file = result.scalar_one_or_none()

    if not ann_file:
        raise HTTPException(status_code=404, detail="Template file not found.")

    # 3. Download the file from Supabase
    file_bytes = await download_file_from_supabase(
        client=supabase, bucket=ANNOUNCEMENTS_BUCKET, storage_key=ann_file.storage_key
    )

    # 4. Write to temp file and parse text
    ext = os.path.splitext(ann_file.file_name)[1].lower() or ".pdf"
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(file_bytes)
            temp_path = tmp.name

        # 5. Extract (and conditionally AI-clean) the text
        html_content = await process_document_import_async(temp_path, clean_pdf=clean)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

    # 6. Format structure for TipTap and create document
    content_json = {"type": "doc", "html": html_content}

    doc = await document_service.create_document(
        db=db,
        group_id=UUID(group_id_str),
        doc_type=body.doc_type,
        title=f"Imported: {ann_file.file_name}",
        created_by=current_user.user_id,
        chat_session_id=session_id,
        content=content_json,
    )

    # 7. Link the new doc to the Mongo session
    await document_chat_service.link_document_to_session(
        db=mongo_db,
        session_id=session_id,
        document_id=str(doc.id),
    )

    return GroupDocumentResponse.model_validate(doc)


# ── Document Autosave & Versioning ────────────────────────────────────────────


@router.get(
    "/students/documents/{doc_id}",
    response_model=GroupDocumentResponse,
    summary="Fetch a single document",
    tags=["student-documents"],
)
async def get_single_document(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = await document_service.get_document(db, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return GroupDocumentResponse.model_validate(doc)


@router.patch(
    "/students/documents/{doc_id}",
    response_model=GroupDocumentResponse,
    summary="Rename a document",
    tags=["student-documents"],
)
async def rename_document(
    doc_id: UUID,
    body: RenameDocumentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Rename a generic document. Does not check optimism lock logic, just renames.
    """
    doc = await document_service.rename_document(
        db, doc_id, body.title, current_user.user_id
    )
    return GroupDocumentResponse.model_validate(doc)


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


@router.get(
    "/students/documents/{doc_id}/versions/{version_number}",
    response_model=DocumentVersionResponse,
    summary="Get a single version snapshot (read-only preview)",
    tags=["student-documents"],
)
async def get_version(
    doc_id: UUID,
    version_number: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await require_group_document_for_user(db, doc_id, current_user)
    snap = await document_service.get_version_snapshot(db, doc_id, version_number)
    if snap is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Version not found",
        )
    return DocumentVersionResponse.model_validate(snap)


@router.post(
    "/students/documents/{doc_id}/versions/{version_number}/restore",
    response_model=RestoreVersionResponse,
    summary="Restore live draft from a past version snapshot",
    tags=["student-documents"],
)
async def restore_document_version(
    doc_id: UUID,
    version_number: int,
    body: RestoreVersionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await require_group_document_for_user(db, doc_id, current_user)
    doc, snapshot = await document_service.restore_document_to_version(
        db,
        doc_id,
        version_number,
        body.lock_version,
        current_user.user_id,
    )
    room_key = f"doc:{doc_id}"
    await manager.broadcast(
        room_key,
        {
            "type": "document_restored",
            "version": version_number,
            "restored_by": str(current_user.user_id),
            "restored_by_name": current_user.full_name or str(current_user.user_id),
        },
    )
    return RestoreVersionResponse(
        snapshot=DocumentVersionResponse.model_validate(snapshot),
        lock_version=doc.lock_version,
    )


# ── Chat Messages ─────────────────────────────────────────────────────────────


@router.get(
    "/students/chat-sessions/models",
    response_model=List[str],
    summary="List available AI models for the chat workspace",
    tags=["student-documents"],
)
async def list_available_models(
    current_user: User = Depends(get_current_user),
):
    """
    Returns the array of available AI model keys the frontend can send
    in the SendMessageRequest `model` field.
    """
    return ["gpt-4o", "gpt-4o-mini", "deepseek", "llama"]


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
    Persists the student message, queries the selected AI model with the active
    document's content injected as context, persists the AI reply, and returns it.
    """
    reply = await document_chat_service.send_message_with_llm(
        pg_db=db,
        mongo_db=mongo_db,
        chat_session_id=session_id,
        sender_id=str(current_user.user_id),
        content=body.content,
        active_document_id=body.active_document_id,
        model_choice=body.model or "gpt-4o",
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
