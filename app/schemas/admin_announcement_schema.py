from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel

from app.models.announcement import FileTypeEnum, TargetRoleEnum


class TargetResponse(BaseModel):
    group_id: Optional[UUID] = None
    target_role: Optional[TargetRoleEnum] = None

    class Config:
        from_attributes = True


class FileResponse(BaseModel):
    file_id: UUID
    file_name: str
    storage_key: str
    file_type: FileTypeEnum
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    is_template: bool = False

    class Config:
        from_attributes = True


class AnnouncementResponse(BaseModel):
    announcement_id: UUID
    title: str
    description: Optional[str]
    is_submission_request: bool
    total_marks: Optional[float] = None
    created_at: datetime
    updated_at: datetime
    targets: List[TargetResponse]
    files: List[FileResponse]

    class Config:
        from_attributes = True


class PaginatedAnnouncements(BaseModel):
    announcements: List[AnnouncementResponse]
    total_items: int
    total_pages: int
    current_page: int
    per_page: int

    class Config:
        from_attributes = True

class AnnouncementCreate(BaseModel):
    title: str
    description: Optional[str] = None
    target_type: str # "all_students", "all_supervisors", "both", "specific_group"
    group_id: Optional[UUID] = None


class AnnouncementPatch(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    target_type: Optional[TargetRoleEnum] = None
    file_ids_to_delete: Optional[List[str]] = None
    due_at: Optional[datetime] = None
    total_marks: Optional[float] = None