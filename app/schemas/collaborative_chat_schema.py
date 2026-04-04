"""Pydantic models for collaborative workspace chat (HTTP + SSE)."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CollaborativeChatPostRequest(BaseModel):
    content: str = Field(..., min_length=1)
    sender_name: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Optional display name; defaults to the authenticated user's full name.",
    )
    active_document_id: Optional[str] = Field(
        None,
        description="Optional open document tab UUID for LLM grounding.",
    )
    model: Optional[str] = Field(
        default="gpt-4o",
        description="Model key: gpt-4o, gpt-4o-mini, deepseek, llama",
    )


class CollaborativeChatPostResponse(BaseModel):
    message_id: str
    request_id: str


class ChatRoomSummaryResponse(BaseModel):
    room_id: str
    group_id: str
    title: str
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    message_count: int = 0
    last_message_preview: Optional[str] = None
    last_sender_name: Optional[str] = None


class ChatHistoryResponse(BaseModel):
    messages: List[Dict[str, Any]]
    has_more: bool
