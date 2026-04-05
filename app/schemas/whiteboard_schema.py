"""Pydantic schemas for group Excalidraw whiteboards."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class WhiteboardCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    group_id: UUID


class WhiteboardPatch(BaseModel):
    """Partial update: rename (`title`) and/or Excalidraw scene (`elements`, `app_state`, `files`)."""

    title: Optional[str] = Field(None, min_length=1, max_length=255)
    elements: Optional[List[Any]] = None
    app_state: Optional[Dict[str, Any]] = None
    files: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "WhiteboardPatch":
        if (
            self.title is None
            and self.elements is None
            and self.app_state is None
            and self.files is None
        ):
            raise ValueError(
                "Provide at least one of: title, elements, app_state, files"
            )
        return self


class WhiteboardResponse(BaseModel):
    id: UUID
    group_id: UUID
    created_by: UUID
    created_by_name: str
    title: str
    elements: List[Any]
    app_state: Dict[str, Any]
    files: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    updated_by: Optional[UUID] = None

    model_config = {"from_attributes": True}


class WhiteboardListItem(BaseModel):
    id: UUID
    title: str
    created_by: UUID
    created_by_name: str
    updated_at: datetime

    model_config = {"from_attributes": True}
