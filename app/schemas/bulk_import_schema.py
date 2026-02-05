# app/schemas/bulk_import_schema.py

"""
Pydantic schemas for bulk import API endpoints.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

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


# === Cron Processor Schemas ===


class CronProcessorResponse(BaseModel):
    """Response from the cron processor endpoint."""

    processed: int
    success: int
    failed: int
    skipped: int
    jobs_completed: list[UUID] = []
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
