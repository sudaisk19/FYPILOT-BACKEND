from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ─── File schemas for create/edit ──────────────────────────────────────────────

class FileInput(BaseModel):
    """File info sent by frontend when creating/editing an announcement"""

    id: Optional[UUID] = Field(None, description="Existing file ID (present when keeping a file during edit)")
    name: str
    url: str  # storage URL / storage_key
    type: Literal["Template", "Document"] = "Document"
    module: Optional[str] = None
    mimeType: Optional[str] = None
    size: Optional[int] = None


class FileOutput(BaseModel):
    """File info returned to frontend"""

    id: UUID
    name: str
    url: str
    type: str
    module: Optional[str] = None
    mimeType: Optional[str] = None
    size: Optional[int] = None

    class Config:
        from_attributes = True


# ─── Create / Edit request & response ─────────────────────────────────────────

class CreateSubmissionAnnouncementRequest(BaseModel):
    title: str
    description: Optional[str] = None
    dueDate: Optional[datetime] = None
    total_marks: Optional[float] = None
    assignTo: Literal["Students", "Supervisors", "Both"]
    isSubmission: bool = True
    files: List[FileInput] = Field(default_factory=list)


class EditSubmissionAnnouncementRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    dueDate: Optional[datetime] = None
    total_marks: Optional[float] = None
    assignTo: Optional[Literal["Students", "Supervisors", "Both"]] = None
    isSubmission: bool = True
    files: Optional[List[FileInput]] = None


class SubmissionAnnouncementResponse(BaseModel):
    id: UUID
    title: str
    description: Optional[str] = None
    dueDate: Optional[datetime] = None
    total_marks: Optional[float] = None
    assignTo: Optional[str] = None
    isSubmission: bool = True
    files: List[FileOutput] = Field(default_factory=list)
    createdAt: datetime
    updatedAt: datetime

    class Config:
        from_attributes = True


# ─── Existing schemas ─────────────────────────────────────────────────────────

class AttachmentInfo(BaseModel):
    """File attachment info for announcements"""

    file_id: UUID
    file_name: str
    storage_key: str
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    file_type: str  # "Template" or "Document"
    module: Optional[str] = None
    uploaded_at: datetime

    class Config:
        from_attributes = True


class SubmissionTaskInfo(BaseModel):
    """Individual submission task card for the list view"""

    submission_id: UUID = Field(..., description="Announcement ID that is a submission request")
    name: str = Field(..., description="Title of the submission")
    description: Optional[str] = Field(None, description="Description/note")
    created_at: datetime
    due_at: Optional[datetime] = None
    total_points: Optional[float] = Field(None, description="Total marks for this submission")
    assigned_to: Optional[str] = Field(
        None, description="Target audience (e.g., 'All Students', 'All Supervisors', 'Specific Group')"
    )
    attachments: List[AttachmentInfo] = Field(default_factory=list)

    class Config:
        from_attributes = True


class PaginatedSubmissionTasksResponse(BaseModel):
    """Paginated response for submission tasks"""

    tasks: List[SubmissionTaskInfo]
    total: int
    page: int
    per_page: int
    total_pages: int
    has_next: bool
    has_prev: bool

    class Config:
        from_attributes = True


class GroupSubmissionStatus(BaseModel):
    """Individual group's submission status for a submission request"""

    fyp_id: str = Field(..., description="Project FYP ID")
    project_name: str = Field(..., description="Group/Project name")
    status: str = Field(..., description="Submission status: Submitted, Missing, Graded, Returned")

    class Config:
        from_attributes = True


class GroupSubmissionsResponse(BaseModel):
    """Response containing all group submissions for a submission request"""

    submissions: List[GroupSubmissionStatus]
    total: int
    page: int
    per_page: int
    total_pages: int
    has_next: bool
    has_prev: bool

    class Config:
        from_attributes = True


# ─── Evaluation schemas ────────────────────────────────────────────────────────

class SubmissionFileInfo(BaseModel):
    """File info for submission evaluation"""
    
    fileId: UUID
    fileName: str
    storageKey: str
    mimeType: Optional[str] = None
    sizeBytes: Optional[int] = None
    uploadedAt: datetime
    
    class Config:
        from_attributes = True


class SubmissionEvaluationResponse(BaseModel):
    """Full submission details for evaluation page"""
    
    submissionId: UUID
    title: str
    totalMarks: Optional[float] = Field(None, description="Total marks from announcement")
    supervisorMarks: Optional[float] = Field(None, description="Marks given by supervisor (read-only for admin)")
    adminMarks: Optional[float] = Field(None, description="Marks given by admin (editable)")
    supervisorFeedback: Optional[str] = Field(None, description="Feedback from supervisor (read-only for admin)")
    adminFeedback: Optional[str] = Field(None, description="Feedback from admin (editable)")
    supervisorGradedAt: Optional[datetime] = None
    adminGradedAt: Optional[datetime] = None
    files: List[SubmissionFileInfo] = Field(default_factory=list)
    submittedAt: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class UpdateAdminGradingRequest(BaseModel):
    """Request to update admin grading for a submission"""
    
    adminMarks: Optional[float] = Field(None, description="Admin's marks for the submission")
    adminFeedback: Optional[str] = Field(None, description="Admin's feedback/comments")
