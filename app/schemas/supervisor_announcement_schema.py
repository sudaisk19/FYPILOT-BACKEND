# app/schemas/supervisor_announcement_schema.py
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel

from app.models.announcement import FileTypeEnum


class SupervisorAnnouncementFileResponse(BaseModel):
    file_id: UUID
    file_name: str
    storage_key: str
    file_type: FileTypeEnum
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    is_template: bool = False

    class Config:
        from_attributes = True


class SupervisorAnnouncementTargetResponse(BaseModel):
    group_id: Optional[UUID] = None
    project_name: Optional[str] = None

    class Config:
        from_attributes = True


class SupervisorAnnouncementResponse(BaseModel):
    announcement_id: UUID
    title: str
    description: Optional[str] = None
    assign_to: str  # "all" | group_id | "Multiple Groups"
    created_at: datetime
    updated_at: datetime
    targets: List[SupervisorAnnouncementTargetResponse]
    files: List[SupervisorAnnouncementFileResponse]

    class Config:
        from_attributes = True


class PaginatedSupervisorAnnouncements(BaseModel):
    announcements: List[SupervisorAnnouncementResponse]
    total_items: int
    total_pages: int
    current_page: int
    per_page: int
