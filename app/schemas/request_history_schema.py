# app/schemas/request_history_schema.py
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field

class RequestHistoryItem(BaseModel):
    history_id: UUID
    request_id: UUID
    action: str = Field(..., description="Type of event (created, updated, feedback, status_change, message)")
    message: str | None = None
    feedback: str | None = None
    created_by: UUID | None = None
    timestamp: datetime

    class Config:
        from_attributes = True

class RequestHistoryListResponse(BaseModel):
    history: list[RequestHistoryItem] = Field(default_factory=list)
