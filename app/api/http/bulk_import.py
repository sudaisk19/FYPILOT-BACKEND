# app/api/http/bulk_import.py

"""
Bulk Import API Endpoints

Admin-only endpoints for bulk user registration via CSV/Excel upload.
"""

import csv
import io
import logging
from typing import Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase_auth import get_current_user
from app.core.config import settings
from app.db import get_db
from app.models.bulk_import import (
    BulkImportItem,
    BulkImportJob,
    BulkItemStatus,
    TargetRoleEnum,
)
from app.models.user import User
from app.schemas.bulk_import_schema import (
    BulkImportItemSummary,
    BulkImportJobDetailResponse,
    BulkImportJobListItem,
    BulkImportJobListResponse,
    BulkImportJobStatus,
    BulkImportUploadResponse,
    CronProcessorResponse,
)
from app.services.bulk_import_service import (
    create_bulk_import_job,
    get_job_results,
    process_pending_items,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Cron token for GitHub Actions authentication
CRON_TOKEN = settings.cron_token


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Dependency to ensure user is an admin."""
    role = (
        current_user.role.value
        if hasattr(current_user.role, "value")
        else current_user.role
    )
    if role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


def verify_cron_token(x_cron_token: Optional[str] = Header(None)) -> bool:
    """Verify the cron token for cron processor endpoint."""
    if not CRON_TOKEN:
        logger.warning("CRON_TOKEN not configured, cron endpoint disabled")
        return False
    return x_cron_token == CRON_TOKEN


@router.post(
    "",
    response_model=BulkImportUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload bulk import file",
    description="Upload a CSV or Excel file to create multiple student or supervisor accounts.",
)
async def upload_bulk_import(
    file: UploadFile = File(..., description="CSV or Excel file with user data"),
    target_role: str = Form(..., description="Target role: 'student' or 'supervisor'"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a CSV/Excel file to create a bulk import job.

    The job will be processed in batches by the cron processor.

    Required columns for students: full_name, email, roll_number
    Required columns for supervisors: full_name, email
    Optional columns: department, designation (supervisor only)
    """
    # Validate target_role
    try:
        role_enum = TargetRoleEnum(target_role.lower())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="target_role must be 'student' or 'supervisor'",
        )

    # Validate file
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File name is required",
        )

    # Check file extension
    filename_lower = file.filename.lower()
    if not (
        filename_lower.endswith(".csv") or filename_lower.endswith((".xlsx", ".xls"))
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be CSV or Excel format",
        )

    # Read file content
    try:
        content = await file.read()
    except Exception as e:
        logger.error(f"Failed to read uploaded file: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to read uploaded file",
        )

    # Create bulk import job
    job, error = await create_bulk_import_job(
        db=db,
        admin_user_id=current_user.user_id,
        target_role=role_enum,
        file_content=content,
        filename=file.filename,
    )

    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )

    logger.info(
        f"Admin {current_user.email} created bulk import job {job.id} with {job.total_rows} rows"
    )

    return BulkImportUploadResponse(
        job_id=job.id,
        total_rows=job.total_rows,
        status=job.status.value,
        message=f"Job created successfully. {job.total_rows} rows queued for processing.",
    )


@router.get(
    "",
    response_model=BulkImportJobListResponse,
    summary="List bulk import jobs",
    description="Get a paginated list of bulk import jobs.",
)
async def list_bulk_import_jobs(
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all bulk import jobs with pagination."""
    offset = (page - 1) * page_size

    # Get total count
    count_query = select(func.count()).select_from(BulkImportJob)
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Get jobs
    query = (
        select(BulkImportJob)
        .order_by(BulkImportJob.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(query)
    jobs = result.scalars().all()

    return BulkImportJobListResponse(
        jobs=[
            BulkImportJobListItem(
                id=job.id,
                target_role=job.target_role.value,
                status=job.status.value,
                total_rows=job.total_rows,
                processed_rows=job.processed_rows,
                success_count=job.success_count,
                created_at=job.created_at,
            )
            for job in jobs
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{job_id}",
    response_model=BulkImportJobDetailResponse,
    summary="Get bulk import job status",
    description="Get detailed status of a specific bulk import job.",
)
async def get_bulk_import_job(
    job_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed status of a bulk import job including recent errors."""
    # Get job
    query = select(BulkImportJob).where(BulkImportJob.id == job_id)
    result = await db.execute(query)
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bulk import job not found",
        )

    # Get recent errors (last 10)
    errors_query = (
        select(BulkImportItem)
        .where(
            BulkImportItem.job_id == job_id,
            BulkImportItem.status.in_([BulkItemStatus.failed, BulkItemStatus.skipped]),
        )
        .order_by(BulkImportItem.row_number)
        .limit(10)
    )
    errors_result = await db.execute(errors_query)
    error_items = errors_result.scalars().all()

    # Calculate progress percentage
    progress_percent = (
        (job.processed_rows / job.total_rows * 100) if job.total_rows > 0 else 0
    )

    return BulkImportJobDetailResponse(
        job=BulkImportJobStatus(
            id=job.id,
            target_role=job.target_role.value,
            status=job.status.value,
            total_rows=job.total_rows,
            processed_rows=job.processed_rows,
            success_count=job.success_count,
            failed_count=job.failed_count,
            skipped_count=job.skipped_count,
            created_at=job.created_at,
            updated_at=job.updated_at,
            progress_percent=round(progress_percent, 1),
        ),
        recent_errors=[
            BulkImportItemSummary(
                row_number=item.row_number,
                email=item.payload.get("email"),
                full_name=item.payload.get("full_name"),
                status=item.status.value,
                error=item.error,
            )
            for item in error_items
        ],
    )


@router.get(
    "/{job_id}/results.csv",
    summary="Download results CSV",
    description="Download results as CSV file including credentials (if not expired).",
)
async def download_results_csv(
    job_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Download bulk import results as CSV file."""
    # Verify job exists
    query = select(BulkImportJob).where(BulkImportJob.id == job_id)
    result = await db.execute(query)
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bulk import job not found",
        )

    # Get results
    results = await get_job_results(db, job_id)

    # Generate CSV
    output = io.StringIO()
    fieldnames = [
        "row_number",
        "full_name",
        "email",
        "roll_number",
        "department",
        "status",
        "error",
        "user_id",
        "temp_password",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(results)

    # Return as streaming response
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="bulk_import_{job_id}_results.csv"',
        },
    )


@router.post(
    "/run-pending",
    response_model=CronProcessorResponse,
    summary="Process pending bulk import items",
    description="Cron endpoint to process pending bulk import items in batches.",
)
async def run_pending_processor(
    x_cron_token: Optional[str] = Header(None),
    current_user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Process pending bulk import items.

    This endpoint can be called by:
    1. GitHub Actions cron with X-CRON-TOKEN header
    2. Admin user with valid auth token

    Processes items in batches to avoid timeouts.
    """
    # Verify authorization
    is_cron = verify_cron_token(x_cron_token)
    is_admin = False

    if current_user:
        role = (
            current_user.role.value
            if hasattr(current_user.role, "value")
            else current_user.role
        )
        is_admin = role == "admin"

    if not is_cron and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access or valid cron token required",
        )

    # Process pending items
    try:
        stats = await process_pending_items(db)

        return CronProcessorResponse(
            processed=stats["processed"],
            success=stats["success"],
            failed=stats["failed"],
            skipped=stats["skipped"],
            jobs_completed=stats["jobs_completed"],
            message=f"Processed {stats['processed']} items successfully",
        )
    except Exception as e:
        logger.error(f"Error in bulk import processor: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Processing error: {str(e)}",
        )
