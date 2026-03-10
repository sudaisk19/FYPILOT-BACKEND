# app/api/http/bulk_import.py

"""
User Registration API Endpoints (Admin Only)

Covers both single-user form-based registration and
bulk CSV/Excel import with background processing.
"""

import csv
import io
import logging
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase_auth import get_current_user
from app.core.departments import COMMON_UNIVERSITY_DEPARTMENTS
from app.db import get_db
from app.models.bulk_import import (
    BulkImportItem,
    BulkImportJob,
    BulkItemStatus,
    BulkJobStatus,
)
from app.models.user import User
from app.schemas.bulk_import_schema import (
    BulkImportItemSummary,
    BulkImportJobDetailResponse,
    BulkImportJobListItem,
    BulkImportJobListResponse,
    BulkImportJobStatus,
    BulkImportReportItemDetail,
    BulkImportReportResponse,
    BulkImportUploadResponse,
    DepartmentListResponse,
    CreateStudentRequest,
    CreateSupervisorRequest,
    ProcessorResponse,
    RetryResponse,
    SingleUserResponse,
)
from app.services.bulk_import_service import (
    create_bulk_import_job,
    create_single_student,
    create_single_supervisor,
    get_job_report,
    get_job_results,
    process_job_inline,
    process_pending_items,
    resume_interrupted_job,
    retry_failed_items,
)

logger = logging.getLogger(__name__)

router = APIRouter()


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


# ─── Reference Data ────────────────────────────────────────────


@router.get(
    "/departments",
    response_model=DepartmentListResponse,
    summary="List allowed departments",
    description="Return the canonical list of departments for dropdown population.",
)
async def get_departments(
    current_user: User = Depends(require_admin),
):
    """Expose canonical departments so FE dropdowns stay in sync with backend validation."""

    return DepartmentListResponse(departments=COMMON_UNIVERSITY_DEPARTMENTS)


# ─── Upload + Auto-Process ──────────────────────────────────────


@router.post(
    "",
    response_model=BulkImportUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload bulk import file",
    description="Upload a CSV or Excel file to create multiple student or supervisor accounts. "
    "Processing starts automatically in the background after upload.",
)
async def upload_bulk_import(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="CSV or Excel file with user data"),
    target_role: str = Form(..., description="Target role: 'student' or 'supervisor'"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a CSV/Excel file to create a bulk import job.

    Processing starts automatically in the background — no cron job needed.
    The admin gets an immediate 201 response with the job_id, then can
    poll GET /{job_id} or GET /{job_id}/report for progress and results.

    Required columns for students: full_name, email, roll_number, department,
    fyp_start_semester, fyp_start_year
    Required columns for faculty: full_name, email, department, designation
    Departments must match the predefined dropdown options (case-insensitive).
    """
    # Validate target_role
    try:
        target_role_lower = target_role.lower()
        if target_role_lower not in ("student", "faculty"):
            raise ValueError()
        role_enum = target_role_lower
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="target_role must be 'student' or 'faculty'",
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

    # Create bulk import job (inserts job + items into DB)
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
        f"Admin {current_user.email} created bulk import job {job.id} "
        f"with {job.total_rows} rows — background processing starting"
    )

    # Kick off background processing immediately
    background_tasks.add_task(process_job_inline, job.id)

    return BulkImportUploadResponse(
        job_id=job.id,
        total_rows=job.total_rows,
        status=job.status.value,
        message=f"Job created successfully. {job.total_rows} rows queued — processing started automatically.",
    )


# ─── List Jobs ──────────────────────────────────────────────────


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


# ─── Job Detail (Status + Recent Errors) ────────────────────────


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


# ─── Full Job Report ────────────────────────────────────────────


@router.get(
    "/{job_id}/report",
    response_model=BulkImportReportResponse,
    summary="Get bulk import job report",
    description="Get a full report with breakdowns of created, skipped, failed, and pending items.",
)
async def get_bulk_import_report(
    job_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Get a comprehensive report for a bulk import job.

    Includes:
    - Summary counts (total, success, failed, skipped, pending)
    - List of successfully created users
    - List of skipped items with reason (e.g. "Email already registered")
    - List of failed items with error details
    - List of pending items (if job is still processing or was interrupted)
    """
    report = await get_job_report(db, job_id)

    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bulk import job not found",
        )

    return BulkImportReportResponse(
        job_id=report["job_id"],
        target_role=report["target_role"],
        status=report["status"],
        total_rows=report["total_rows"],
        success_count=report["success_count"],
        failed_count=report["failed_count"],
        skipped_count=report["skipped_count"],
        pending_count=report["pending_count"],
        progress_percent=report["progress_percent"],
        created_at=report["created_at"],
        updated_at=report["updated_at"],
        created_users=[
            BulkImportReportItemDetail(**item) for item in report["created_users"]
        ],
        skipped_items=[
            BulkImportReportItemDetail(**item) for item in report["skipped_items"]
        ],
        failed_items=[
            BulkImportReportItemDetail(**item) for item in report["failed_items"]
        ],
        pending_items=[
            BulkImportReportItemDetail(**item) for item in report["pending_items"]
        ],
    )


# ─── Download Results CSV ───────────────────────────────────────


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


# ─── Retry Failed Items ────────────────────────────────────────


@router.post(
    "/{job_id}/retry",
    response_model=RetryResponse,
    summary="Retry failed items",
    description="Reset failed items back to pending and restart background processing.",
)
async def retry_job(
    job_id: UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Retry failed items in a bulk import job.

    This resets all items with status='failed' back to 'pending',
    then kicks off background processing again.

    Use this when:
    - Some items failed due to transient errors
    - You've fixed data issues and want to retry
    """
    # Verify job exists
    query = select(BulkImportJob).where(BulkImportJob.id == job_id)
    result = await db.execute(query)
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bulk import job not found",
        )

    # Reset failed items
    items_reset = await retry_failed_items(db, job_id)

    if items_reset == 0:
        return RetryResponse(
            job_id=job_id,
            items_reset=0,
            message="No failed items to retry.",
        )

    # Kick off background processing
    background_tasks.add_task(process_job_inline, job_id)

    return RetryResponse(
        job_id=job_id,
        items_reset=items_reset,
        message=f"{items_reset} failed items reset to pending — reprocessing started.",
    )


# ─── Resume Interrupted Job ────────────────────────────────────


@router.post(
    "/{job_id}/resume",
    response_model=RetryResponse,
    summary="Resume interrupted job",
    description="Resume a job that was interrupted (e.g. server crash, power failure).",
)
async def resume_job(
    job_id: UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Resume a job that was interrupted mid-processing.

    Use this when:
    - Server crashed or restarted during processing
    - Power failure interrupted the job
    - Job is stuck in 'processing' status

    Items that were already successfully processed will NOT be reprocessed.
    Only remaining 'pending' items will be picked up.
    """
    # Verify job exists
    query = select(BulkImportJob).where(BulkImportJob.id == job_id)
    result = await db.execute(query)
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bulk import job not found",
        )

    if job.status == BulkJobStatus.done:
        return RetryResponse(
            job_id=job_id,
            items_reset=0,
            message="Job is already completed. No items to resume.",
        )

    # Resume — count pending items and reset job status
    pending_count = await resume_interrupted_job(db, job_id)

    if pending_count == 0:
        # All items processed, just mark as done
        job.status = BulkJobStatus.done
        await db.commit()
        return RetryResponse(
            job_id=job_id,
            items_reset=0,
            message="All items already processed. Job marked as done.",
        )

    # Kick off background processing
    background_tasks.add_task(process_job_inline, job_id)

    return RetryResponse(
        job_id=job_id,
        items_reset=pending_count,
        message=f"Job resumed — {pending_count} pending items will be processed.",
    )


# ─── Manual Process All Pending (admin trigger) ─────────────────


@router.post(
    "/run-pending",
    response_model=ProcessorResponse,
    summary="Process all pending items",
    description="Admin-only endpoint to manually trigger processing of any pending items across all jobs.",
)
async def run_pending_processor(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Manually process pending bulk import items across all jobs.

    This is a fallback endpoint — normally processing happens automatically
    after upload. Use this if:
    - Background task failed silently
    - Server restarted and you want to process all pending items at once
    - You want to manually trigger processing
    """
    try:
        stats = await process_pending_items(db)

        return ProcessorResponse(
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


# ═══════════════════════════════════════════════════════════════
# SINGLE USER REGISTRATION (Form-based)
# ═══════════════════════════════════════════════════════════════


@router.post(
    "/register/student",
    response_model=SingleUserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a single student",
    description="Admin creates a single student account by filling in the form.",
)
async def register_single_student(
    body: CreateStudentRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Register a single student via form.

    Creates a user + student profile with a generated temp password.
    The admin receives the temp password in the response to share
    with the student.
    """
    try:
        user, temp_password = await create_single_student(
            db=db,
            full_name=body.full_name,
            email=body.email,
            roll_number=body.roll_number,
            fyp_start_semester=body.fyp_start_semester,
            fyp_start_year=body.fyp_start_year,
            department=body.department,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )

    return SingleUserResponse(
        user_id=user.user_id,
        full_name=user.full_name,
        email=user.email,
        role="student",
        temp_password=temp_password,
        message=f"Student {user.full_name} registered successfully.",
    )


@router.post(
    "/register/supervisor",
    response_model=SingleUserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a single supervisor",
    description="Admin creates a single supervisor account by filling in the form.",
)
async def register_single_supervisor(
    body: CreateSupervisorRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Register a single supervisor via form.

    Creates a user + supervisor profile with a generated temp password.
    Auto-sets is_supervisor=True, is_jury=True, is_active=True.
    The admin receives the temp password in the response.
    """
    try:
        user, temp_password = await create_single_supervisor(
            db=db,
            full_name=body.full_name,
            email=body.email,
            department=body.department,
            designation=body.designation,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )

    return SingleUserResponse(
        user_id=user.user_id,
        full_name=user.full_name,
        email=user.email,
        role="faculty",
        temp_password=temp_password,
        message=f"Faculty {user.full_name} registered successfully.",
    )
