"""
Document Schemas
Pydantic models for request validation and response serialisation
across the Unified Group Documentation Module.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.group_document import DocTypeEnum, FilePurposeEnum, SaveTriggerEnum

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


# ── Autosave ─────────────────────────────────────────────────────────────────


class AutosaveRequest(BaseModel):
    content: Dict[str, Any]
    lock_version: int = Field(
        ..., ge=1, description="Expected current lock_version from client."
    )


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


class ChatMessageResponse(BaseModel):
    message_id: Optional[str] = None
    reply: str


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
