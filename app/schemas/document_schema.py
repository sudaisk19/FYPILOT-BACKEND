"""
Document Schemas
Pydantic models for request validation and response serialisation
across the Unified Group Documentation Module.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.group_document import DocTypeEnum, FilePurposeEnum, SaveTriggerEnum
from app.schemas.workspace_chat import WorkspaceAction

# ── Shared ──────────────────────────────────────────────────────────────────


class UUIDStr(BaseModel):
    """Utility mixin — allows UUID fields to be serialised as str."""

    model_config = {"from_attributes": True}


# ── GroupDocument ────────────────────────────────────────────────────────────


class CreateDocumentRequest(BaseModel):
    doc_type: DocTypeEnum
    title: str = Field(..., min_length=1, max_length=255)
    chat_session_id: Optional[str] = None
    content: Optional[Dict[str, Any]] = None
    blank_tab: bool = Field(
        False,
        description=(
            "Set true when intentionally opening a new empty editor tab. "
            "If omitted with empty content, the server may resolve an existing "
            "uploaded document instead of creating another row (see POST handler)."
        ),
    )


class UploadDocumentRequest(BaseModel):
    """Schema for document file upload.

    Note: file is passed as multipart/form-data (not in this schema),
    but doc_type, title, and group_id/session_id are form fields.
    """

    doc_type: DocTypeEnum = Field(default=DocTypeEnum.other)
    title: Optional[str] = Field(None, min_length=1, max_length=255)


class GroupDocumentResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    group_id: UUID
    chat_session_id: Optional[str]
    doc_type: DocTypeEnum
    title: str
    content: Optional[Dict[str, Any]]
    lock_version: int
    is_active: bool
    created_by: Optional[UUID]
    updated_by: Optional[UUID]
    created_at: datetime
    updated_at: datetime

    @field_validator("content", mode="before")
    @classmethod
    def normalize_content(cls, v: Any) -> Any:
        """Accept dict or JSON string (legacy / mis-typed jsonb)."""
        if v is None:
            return None
        if isinstance(v, dict):
            return v
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
            except json.JSONDecodeError:
                return {}
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, str):
                return {"type": "doc", "html": parsed}
            return {}
        return {}


class DocumentTypeOptionResponse(BaseModel):
    value: DocTypeEnum
    label: str
    description: str


# ── Autosave ─────────────────────────────────────────────────────────────────


class AutosaveRequest(BaseModel):
    content: Dict[str, Any]
    lock_version: int = Field(
        ..., ge=1, description="Expected current lock_version from client."
    )


class RenameDocumentRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)


class AutosaveResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    lock_version: int
    updated_at: datetime


# ── Version Snapshots ─────────────────────────────────────────────────────────


class CreateVersionRequest(BaseModel):
    save_trigger: SaveTriggerEnum = SaveTriggerEnum.student


class DocumentVersionResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    document_id: UUID
    version_number: int
    content: str  # Raw JSON string snapshot
    save_trigger: SaveTriggerEnum
    created_by: Optional[UUID]
    created_at: datetime


class RestoreVersionRequest(BaseModel):
    """Restore live draft from a past snapshot (optimistic lock on current draft)."""

    lock_version: int = Field(
        ...,
        ge=1,
        description="Expected current lock_version on group_documents before applying restore.",
    )


class RestoreVersionResponse(BaseModel):
    """New immutable snapshot row plus updated draft version after restore."""

    snapshot: DocumentVersionResponse
    lock_version: int


# ── Chat Workspace (Sessions) ────────────────────────────────────────────────


class CreateWorkspaceRequest(BaseModel):
    group_id: str
    title: str = Field(default="My Workspace", min_length=1, max_length=255)
    document_ids: List[str] = []


class WorkspaceResponse(BaseModel):
    session_id: str
    group_id: str
    title: str
    document_ids: List[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class RenameWorkspaceRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)


class AddDocumentToSessionRequest(BaseModel):
    """Link an existing Postgres document to an existing workspace."""

    document_id: str = Field(
        ..., description="Postgres UUID of the GroupDocument to link."
    )


class ImportTemplateRequest(BaseModel):
    announcement_file_id: UUID = Field(
        ..., description="UUID of the AnnouncementFile (the chosen template)."
    )
    doc_type: DocTypeEnum = Field(..., description="Type of the document to create.")


# ── Chat Messages ─────────────────────────────────────────────────────────────


class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1)
    active_document_id: Optional[str] = Field(
        None,
        description=(
            "UUID of the document tab currently open. "
            "The backend will inject this document's content into the LLM system prompt."
        ),
    )
    model: Optional[str] = Field(
        default="gpt-4o",
        description="The LLM model to use: gpt-4o, gpt-4o-mini, deepseek, llama",
    )
    workspace_action: Optional[WorkspaceAction] = Field(
        default=None,
        description=(
            "modify = JSON html_fragment proposal + pending row; "
            "suggest, improve, or omitted = standard chat reply."
        ),
    )


class ChatMessageResponse(BaseModel):
    message_id: Optional[str] = None
    reply: str
    assistant_message_id: Optional[str] = None
    proposal_id: Optional[str] = None
    proposal_summary: Optional[str] = None


class MessageListResponse(BaseModel):
    messages: List[Dict[str, Any]]
    total: int


# ── Document Files ────────────────────────────────────────────────────────────


class DocumentFileResponse(BaseModel):
    model_config = {"from_attributes": True}

    file_id: UUID
    document_id: UUID
    file_name: str
    storage_key: str
    mime_type: Optional[str]
    size_bytes: Optional[int]
    file_purpose: FilePurposeEnum
    version_number: Optional[int]
    created_at: datetime
