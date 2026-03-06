# app/schemas/student_announcement_schema.py
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel

from app.models.announcement import FileTypeEnum


class StudentAnnouncementFileResponse(BaseModel):
    file_id: UUID
    file_name: str
    storage_key: str
    file_type: FileTypeEnum
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None

    class Config:
        from_attributes = True


class StudentAnnouncementResponse(BaseModel):
    announcement_id: UUID
    title: str
    description: Optional[str] = None
    supervisor_name: Optional[str] = None  # Populated for supervisor-tab announcements
    created_at: datetime
    updated_at: datetime
    files: List[StudentAnnouncementFileResponse]

    class Config:
        from_attributes = True


class PaginatedStudentAnnouncements(BaseModel):
    announcements: List[StudentAnnouncementResponse]
    total_items: int
    total_pages: int
    current_page: int
    per_page: int
