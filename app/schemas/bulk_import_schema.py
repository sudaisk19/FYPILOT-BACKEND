# app/schemas/bulk_import_schema.py

"""
Pydantic schemas for user registration API endpoints (single + bulk).
"""

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

# === Single User Registration Schemas ===


class CreateStudentRequest(BaseModel):
    """Request body for admin to register a single student."""

    full_name: str = Field(..., min_length=1, max_length=200)
    email: EmailStr
    roll_number: str = Field(..., min_length=1, max_length=50)
    fyp_start_semester: Literal["fall", "spring", "summer"]
    fyp_start_year: int = Field(..., ge=2000, le=2100)
    department: Optional[str] = None


class CreateSupervisorRequest(BaseModel):
    """Request body for admin to register a single supervisor."""

    full_name: str = Field(..., min_length=1, max_length=200)
    email: EmailStr
    department: str = Field(..., min_length=1, max_length=200)
    designation: str = Field(..., min_length=1, max_length=200)


class SingleUserResponse(BaseModel):
    """Response after creating a single user."""

    user_id: UUID
    full_name: str
    email: str
    role: str
    temp_password: str
    message: str


# === Enums (mirrors model enums) ===


class BulkJobStatusEnum(str):
    pending = "pending"
    processing = "processing"
    done = "done"
    failed = "failed"


class BulkItemStatusEnum(str):
    pending = "pending"
    success = "success"
    failed = "failed"
    skipped = "skipped"


# === Request Schemas ===


class BulkImportUploadResponse(BaseModel):
    """Response after uploading a bulk import file."""

    job_id: UUID
    total_rows: int
    status: str
    message: str

    class Config:
        from_attributes = True


# === Job Status Schemas ===


class BulkImportJobStatus(BaseModel):
    """Status of a bulk import job."""

    id: UUID
    target_role: str
    status: str
    total_rows: int
    processed_rows: int
    success_count: int
    failed_count: int
    skipped_count: int
    created_at: datetime
    updated_at: datetime

    # Computed fields
    progress_percent: float = Field(default=0.0)

    class Config:
        from_attributes = True


class BulkImportItemSummary(BaseModel):
    """Summary of a single import item for status display."""

    row_number: int
    email: Optional[str] = None
    full_name: Optional[str] = None
    status: str
    error: Optional[str] = None

    class Config:
        from_attributes = True


class BulkImportJobDetailResponse(BaseModel):
    """Detailed job status with recent errors."""

    job: BulkImportJobStatus
    recent_errors: list[BulkImportItemSummary] = []

    class Config:
        from_attributes = True


# === Results CSV Row Schema ===


class BulkImportResultRow(BaseModel):
    """Schema for a single row in the results CSV export."""

    row_number: int
    full_name: str
    email: str
    roll_number: Optional[str] = None  # For students
    department: Optional[str] = None
    status: str
    error: Optional[str] = None
    user_id: Optional[UUID] = None
    temp_password: Optional[str] = None  # Only if not expired

    class Config:
        from_attributes = True


# === Processor Response (replaces old CronProcessorResponse) ===


class ProcessorResponse(BaseModel):
    """Response from the processor endpoint (retry / manual trigger)."""

    processed: int
    success: int
    failed: int
    skipped: int
    jobs_completed: list[UUID] = []
    message: str


# === Job Report Schema ===


class BulkImportReportItemDetail(BaseModel):
    """Detail of a single item in the report."""

    row_number: int
    full_name: str
    email: str
    roll_number: Optional[str] = None
    status: str
    error: Optional[str] = None
    user_id: Optional[UUID] = None


class BulkImportReportResponse(BaseModel):
    """
    Full report for a completed (or in-progress) bulk import job.

    Shows summary counts + detailed breakdowns of created, skipped, and failed items.
    """

    job_id: UUID
    target_role: str
    status: str

    # Summary counts
    total_rows: int
    success_count: int
    failed_count: int
    skipped_count: int
    pending_count: int
    progress_percent: float

    created_at: datetime
    updated_at: datetime

    # Detailed breakdowns
    created_users: list[BulkImportReportItemDetail] = []
    skipped_items: list[BulkImportReportItemDetail] = []
    failed_items: list[BulkImportReportItemDetail] = []
    pending_items: list[BulkImportReportItemDetail] = []

    class Config:
        from_attributes = True


# === Retry Response Schema ===


class RetryResponse(BaseModel):
    """Response from the retry endpoint."""

    job_id: UUID
    items_reset: int
    message: str


# === Job List Schema ===


class BulkImportJobListItem(BaseModel):
    """Minimal job info for list display."""

    id: UUID
    target_role: str
    status: str
    total_rows: int
    processed_rows: int
    success_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class BulkImportJobListResponse(BaseModel):
    """Paginated list of bulk import jobs."""

    jobs: list[BulkImportJobListItem]
    total: int
    page: int
    page_size: int
