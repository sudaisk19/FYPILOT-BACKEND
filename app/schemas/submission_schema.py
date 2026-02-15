from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.submission import SubmissionStatusEnum, SubmissionTypeEnum


class SubmissionFileResponse(BaseModel):
    file_name: str
    file_url: str

    model_config = ConfigDict(from_attributes=True)


class SubmissionHistoryResponse(BaseModel):
    submission_id: UUID
    title: str
    type: SubmissionTypeEnum
    status: SubmissionStatusEnum
    submitted_at: Optional[datetime]
    supervisor_marks: Optional[float] = Field(
        default=None, description="Marks given by the supervisor"
    )
    files: List[SubmissionFileResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class FileOutput(BaseModel):
    id: UUID
    name: str
    url: str
    type: str
    module: Optional[str] = None
    mimeType: Optional[str] = None
    size: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class AttachmentInfo(BaseModel):
    file_id: UUID
    file_name: str
    storage_key: str
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    file_type: str
    module: Optional[str] = None
    uploaded_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SubmissionTaskInfo(BaseModel):
    submission_id: UUID
    name: str
    description: Optional[str] = None
    created_at: datetime
    due_at: Optional[datetime] = None
    total_points: Optional[float] = None
    assigned_to: Optional[str] = None
    attachments: List[AttachmentInfo] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class PaginatedSubmissionTasksResponse(BaseModel):
    tasks: List[SubmissionTaskInfo]
    total: int
    page: int
    per_page: int
    total_pages: int
    has_next: bool
    has_prev: bool

    model_config = ConfigDict(from_attributes=True)


class GroupSubmissionStatus(BaseModel):
    fyp_id: str
    project_name: str
    status: str

    model_config = ConfigDict(from_attributes=True)


class GroupSubmissionsResponse(BaseModel):
    submissions: List[GroupSubmissionStatus]
    total: int
    page: int
    per_page: int
    total_pages: int
    has_next: bool
    has_prev: bool

    model_config = ConfigDict(from_attributes=True)


class SubmissionAnnouncementResponse(BaseModel):
    id: UUID
    title: str
    description: Optional[str] = None
    dueDate: Optional[datetime] = None
    total_marks: Optional[float] = Field(default=None, description="Total marks")
    assignTo: Optional[str] = None
    isSubmission: bool = False
    files: List[FileOutput] = Field(default_factory=list)
    createdAt: datetime
    updatedAt: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class SubmissionFileInfo(BaseModel):
    fileId: UUID
    fileName: str
    storageKey: str
    mimeType: Optional[str] = None
    sizeBytes: Optional[int] = None
    uploadedAt: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SubmissionEvaluationResponse(BaseModel):
    submissionId: UUID
    title: str
    totalMarks: Optional[float] = None
    supervisorMarks: Optional[float] = None
    adminMarks: Optional[float] = None
    supervisorFeedback: Optional[str] = None
    adminFeedback: Optional[str] = None
    supervisorGradedAt: Optional[datetime] = None
    adminGradedAt: Optional[datetime] = None
    files: List[SubmissionFileInfo] = Field(default_factory=list)
    submittedAt: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class UpdateAdminGradingRequest(BaseModel):
    adminMarks: Optional[float] = None
    adminFeedback: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)


class CreateSubmissionAnnouncementRequest(BaseModel):
    title: str
    description: Optional[str] = None
    assignTo: str
    dueDate: Optional[datetime] = None
    total_marks: Optional[float] = Field(default=None, description="Total marks")
    files: List[FileOutput] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


class EditSubmissionAnnouncementRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    assignTo: Optional[str] = None
    dueDate: Optional[datetime] = None
    total_marks: Optional[float] = Field(default=None, description="Total marks")
    files: Optional[List[FileOutput]] = None

    model_config = ConfigDict(populate_by_name=True)
