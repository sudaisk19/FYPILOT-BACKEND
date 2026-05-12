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
  POST   /students/chat-sessions/{session_id}/documents      - Create a new doc tab in a workspace
  POST   /students/chat-sessions/{session_id}/documents/link - Attach an existing Postgres doc to the workspace
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
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
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
from app.repositories.group_document_repository import group_document_repo
from app.schemas.document_schema import (
    AddDocumentToSessionRequest,
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
    UploadDocumentRequest,
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


def _implicit_empty_content(content: Optional[Dict[str, Any]]) -> bool:
    return content is None or content == {}


def _document_has_editor_body(doc: Any) -> bool:
    """True when live draft has usable HTML/editor payload (upload/autosave), not bare {}."""
    c = doc.content
    if not c or not isinstance(c, dict) or c == {}:
        return False
    html = c.get("html")
    if isinstance(html, str) and html.strip():
        return True
    return any(k not in ("type", "html") for k in c)


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


# ── Document Upload ──────────────────────────────────────────────────────────


# Example usage (curl) — session_id is required (workspace Mongo _id):
# curl -X POST http://localhost:8000/api/students/documents/upload \
#   -H "Authorization: Bearer <token>" \
#   -F "file=@document.pdf" \
#   -F "session_id=<workspace_session_uuid>" \
#   -F "doc_type=proposal" \
#   -F "title=My Document"
#
# Example usage (JavaScript fetch):
# const formData = new FormData();
# formData.append('file', fileInputElement.files[0]);
# formData.append('session_id', workspaceSessionId);  // required
# formData.append('doc_type', 'proposal');
# formData.append('title', 'My Document');
# // optional: formData.append('group_id', groupId);  // must match workspace group if sent
# const response = await fetch(`${baseURL}/api/students/documents/upload`, {
#   method: 'POST',
#   headers: { Authorization: `Bearer ${token}` },
#   body: formData,
# });


@router.post(
    "/students/documents/upload",
    response_model=GroupDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document file and create a new document",
    tags=["student-documents"],
)
async def upload_document(
    file: UploadFile = File(..., description="Document file to upload (PDF, DOCX, TXT, etc.)"),
    session_id: str = Form(
        ...,
        min_length=1,
        description="Chat workspace session id (MongoDB workspace document _id). Required.",
    ),
    doc_type: str = Form(DocTypeEnum.other, description="Document type enum value"),
    title: str = Form(None, description="Document title (defaults to filename)"),
    group_id: str = Form(
        None,
        description="Optional safety check: if provided, must equal the workspace's group_id.",
    ),
    clean: bool = Query(True, description="Use AI to clean PDF formatting (takes 3-5s)"),
    db: AsyncSession = Depends(get_db),
    mongo_db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a document file (PDF, DOCX, TXT, etc.), extract its content,
    and create a new editable GroupDocument scoped to the chat workspace.

    **session_id is required.** The backend resolves `group_id` from the workspace
    record in MongoDB and sets `group_documents.chat_session_id` before insert,
    then links the new document id to the workspace session.

    Raw file bytes are not stored in object storage — HTML lives in `group_documents.content`.
    """
    # 1. Validate file is present and not empty
    if not file or not file.filename:
        raise HTTPException(
            status_code=400,
            detail="No file was uploaded or file is empty"
        )
    
    # 2. Validate file type
    ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt"}
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Supported formats: PDF, DOCX, DOC, TXT. Got: {file_ext or 'unknown'}"
        )
    
    # 3. Max size enforced after reading body (UploadFile.size is often unset)
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB in bytes
    
    # 4. Resolve group from workspace (session_id is required)
    sid = session_id.strip()
    session = await document_chat_service.get_workspace(mongo_db, sid)
    if not session:
        raise HTTPException(status_code=404, detail="Workspace session not found")
    group_id_str = session.get("group_id")
    if not group_id_str:
        raise HTTPException(status_code=404, detail="Workspace not linked to a group")
    try:
        target_group_id = UUID(str(group_id_str))
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid group_id in workspace")

    if group_id is not None and str(group_id).strip():
        try:
            claimed = UUID(str(group_id).strip())
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid group_id format")
        if claimed != target_group_id:
            raise HTTPException(
                status_code=400,
                detail="group_id does not match the workspace's group.",
            )
    
    # 5. Verify user is a member of the group
    if not await _user_is_group_member(db, current_user.user_id, target_group_id):
        raise HTTPException(
            status_code=403,
            detail="You are not a member of this group"
        )
    
    # 6. Generate document title from filename if not provided
    document_title = title if title and title.strip() else file.filename or "Untitled Document"
    document_title = document_title.strip()[:255]  # Truncate to max length

    # 7. Read upload into memory and extract HTML (no object storage)
    temp_path = ""
    try:
        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(
                status_code=400,
                detail="Uploaded file is empty",
            )
        if len(file_bytes) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size is 50MB, got {len(file_bytes) / 1024 / 1024:.1f}MB",
            )

        ext = os.path.splitext(file.filename or "")[1].lower() or ".pdf"
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(file_bytes)
            temp_path = tmp.name

        html_content = await process_document_import_async(temp_path, clean_pdf=clean)
        content_json = {"type": "doc", "html": html_content}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("Error processing uploaded document: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Failed to process document content",
        ) from e
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

    # 8. Create GroupDocument in database
    try:
        doc = await document_service.create_document(
            db=db,
            group_id=target_group_id,
            doc_type=doc_type,
            title=document_title,
            created_by=current_user.user_id,
            chat_session_id=sid,
            content=content_json,
        )
        logger.info(f"Created document {doc.id} from uploaded file")
    except Exception as e:
        logger.error(f"Error creating document: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to create document in database"
        )
    
    # 9. Append document id to Mongo workspace (same session as Postgres chat_session_id)
    try:
        await document_chat_service.link_document_to_session(
            db=mongo_db,
            session_id=sid,
            document_id=str(doc.id),
        )
    except Exception as e:
        logger.warning("Failed to link document to workspace %s: %s", sid, e)

    return GroupDocumentResponse.model_validate(doc)


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
    db: AsyncSession = Depends(get_db),
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
    aligned = await document_chat_service.reconcile_workspace_sessions_document_ids(
        db, mongo_db, [session]
    )
    session = aligned[0]
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
    db: AsyncSession = Depends(get_db),
    mongo_db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user: User = Depends(get_current_user),
):
    sessions = await document_chat_service.list_workspaces(mongo_db, group_id)
    sessions = await document_chat_service.reconcile_workspace_sessions_document_ids(
        db, mongo_db, sessions
    )
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
    aligned = await document_chat_service.reconcile_workspace_sessions_document_ids(
        db, mongo_db, [session]
    )
    session = aligned[0]
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

    If `content` is empty and `blank_tab` is false (legacy clients that POST after
    multipart upload), the handler first tries to return an **existing** tab:
    same `title` with real content, otherwise the newest doc with body created by
    this user in the last few minutes. That avoids 422 and duplicate empty shells.
    Use `blank_tab: true` when intentionally opening a truly empty editor tab.
    """
    # Always use the URL path param as the canonical session_id.
    # Never let body.chat_session_id override it — doing so causes a Postgres/Mongo
    # mismatch where MongoDB has the doc UUID but Postgres can't find the doc on reload.
    session = await document_chat_service.get_workspace(mongo_db, session_id)
    group_id_str = session["group_id"] if session else None
    if not group_id_str:
        raise HTTPException(status_code=404, detail="Workspace session not found.")

    implicit_empty = _implicit_empty_content(body.content)

    if implicit_empty and not body.blank_tab:
        try:
            existing_docs = await document_service.get_workspace_documents(db, session_id)
        except (TimeoutError, asyncio.TimeoutError, SQLAlchemyError):
            existing_docs = []

        title_norm = body.title.strip()

        for doc_row in sorted(existing_docs, key=lambda d: d.created_at, reverse=True):
            if doc_row.title.strip() != title_norm:
                continue
            if _document_has_editor_body(doc_row):
                payload = jsonable_encoder(GroupDocumentResponse.model_validate(doc_row))
                return JSONResponse(status_code=status.HTTP_200_OK, content=payload)

        cutoff = datetime.now(timezone.utc) - timedelta(minutes=3)
        for doc_row in sorted(existing_docs, key=lambda d: d.created_at, reverse=True):
            if doc_row.created_by != current_user.user_id:
                continue
            ca = doc_row.created_at
            if ca.tzinfo is None:
                ca = ca.replace(tzinfo=timezone.utc)
            else:
                ca = ca.astimezone(timezone.utc)
            if ca < cutoff:
                continue
            if _document_has_editor_body(doc_row):
                payload = jsonable_encoder(GroupDocumentResponse.model_validate(doc_row))
                return JSONResponse(status_code=status.HTTP_200_OK, content=payload)

        raise HTTPException(
            status_code=422,
            detail=(
                "Empty document content requires blank_tab=true for a new empty tab, "
                "or pass initial content. After a file upload, use the upload response "
                "or repeat this call with the same title as the uploaded document."
            ),
        )

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
    "/students/chat-sessions/{session_id}/documents/link",
    response_model=GroupDocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="Attach an existing GroupDocument to this workspace",
    tags=["student-documents"],
)
async def link_document_into_workspace(
    session_id: str,
    body: AddDocumentToSessionRequest,
    db: AsyncSession = Depends(get_db),
    mongo_db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    current_user: User = Depends(get_current_user),
):
    """
    Sets `chat_session_id` on an existing Postgres row and adds its id to the
    MongoDB workspace. Use this after uploading a document without a session,
    or to fix duplicate tabs (empty new doc vs uploaded doc with content).
    """
    session = await document_chat_service.get_workspace(mongo_db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Workspace session not found.")
    group_id_str = session.get("group_id")
    if not group_id_str:
        raise HTTPException(
            status_code=404, detail="Workspace is not linked to a group."
        )

    try:
        doc_uuid = UUID(body.document_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid document_id.")

    doc = await require_group_document_for_user(db, doc_uuid, current_user)
    try:
        workspace_group_id = UUID(str(group_id_str))
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid group_id on workspace.")
    if doc.group_id != workspace_group_id:
        raise HTTPException(
            status_code=400,
            detail="Document belongs to a different group than this workspace.",
        )

    updated = await group_document_repo.attach_to_session(
        db,
        doc_id=doc_uuid,
        chat_session_id=session_id,
        updated_by=current_user.user_id,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Document not found.")

    await document_chat_service.link_document_to_session(
        db=mongo_db,
        session_id=session_id,
        document_id=str(doc_uuid),
    )
    await db.commit()
    await db.refresh(updated)
    return GroupDocumentResponse.model_validate(updated)


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
