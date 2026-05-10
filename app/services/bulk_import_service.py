# app/services/bulk_import_service.py

"""
Bulk Import Service

Handles the core business logic for bulk user registration:
- File parsing (CSV/Excel)
- Password generation and encryption
- User creation with profiles
- Inline background processing (replaces old cron-based approach)
"""

import csv
import io
import logging
import re
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from cryptography.fernet import Fernet
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.utils import hash_password
from app.core.config import settings
from app.core.departments import normalize_department
from app.models.bulk_import import (
    BulkImportItem,
    BulkImportJob,
    BulkItemStatus,
    BulkJobStatus,
)
from app.models.faculty import Faculty
from app.models.student import Student
from app.models.user import RoleEnum, User

# How many rows to accumulate before flushing as a single batch INSERT.
# Row-by-row sqlite-style inserts are replaced with multi-row INSERT statements.
FAST_BATCH_SIZE = 50

logger = logging.getLogger(__name__)

# Configuration from settings
BATCH_SIZE = settings.bulk_import_batch_size
TEMP_PASSWORD_TTL_HOURS = settings.temp_password_ttl_hours
APP_ENCRYPTION_KEY = settings.app_encryption_key

# Required columns for each role
STUDENT_REQUIRED_COLUMNS = {
    "full_name",
    "email",
    "roll_number",
    "cgpa",
    "fyp_start_semester",
    "fyp_start_year",
    "department",
}
SUPERVISOR_REQUIRED_COLUMNS = {"full_name", "email", "department", "designation"}

# Email validation regex
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


# ─── Batch Insert (Step 3 – Bulk Optimization) ──────────────────────────────


async def batch_insert_users_and_profiles(
    db: AsyncSession,
    user_rows: List[dict],
    student_rows: List[dict],
    faculty_rows: List[dict],
) -> None:
    """
    Insert multiple Users + profiles in a single multi-row INSERT each.

    This replaces the previous N individual db.add() / await db.flush() cycles
    with three bulk INSERT ... ON CONFLICT DO NOTHING statements — one for users,
    one for students, one for faculty — regardless of batch size.

    Args:
        db: Async SQLAlchemy session (still within active transaction)
        user_rows: Dicts of column values for the `users` table
        student_rows: Dicts of column values for the `students` table
        faculty_rows: Dicts of column values for the `faculty` table
    """
    if user_rows:
        stmt = (
            pg_insert(User.__table__)
            .values(user_rows)
            .on_conflict_do_nothing(index_elements=["email"])
        )
        await db.execute(stmt)

    if student_rows:
        stmt = (
            pg_insert(Student.__table__)
            .values(student_rows)
            .on_conflict_do_nothing(index_elements=["roll_number"])
        )
        await db.execute(stmt)

    if faculty_rows:
        stmt = (
            pg_insert(Faculty.__table__)
            .values(faculty_rows)
            .on_conflict_do_nothing(index_elements=["user_id"])
        )
        await db.execute(stmt)


def get_fernet() -> Optional[Fernet]:
    """Get Fernet instance for encryption/decryption."""
    if not APP_ENCRYPTION_KEY:
        logger.warning(
            "APP_ENCRYPTION_KEY not set, temp passwords will not be encrypted"
        )
        return None
    try:
        return Fernet(APP_ENCRYPTION_KEY.encode())
    except Exception as e:
        logger.error(f"Invalid APP_ENCRYPTION_KEY: {e}")
        return None


def generate_temp_password(length: int = 12) -> str:
    """
    Generate a secure temporary password.

    Password will contain:
    - At least 1 uppercase letter
    - At least 1 lowercase letter
    - At least 1 digit
    - Random mix of alphanumeric characters
    """
    # Ensure at least one of each required type
    password_chars = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
    ]

    # Fill the rest with random alphanumeric
    remaining_length = length - len(password_chars)
    alphabet = string.ascii_letters + string.digits
    password_chars.extend(secrets.choice(alphabet) for _ in range(remaining_length))

    # Shuffle to randomize positions
    secrets.SystemRandom().shuffle(password_chars)

    return "".join(password_chars)


def encrypt_password(password: str) -> Optional[str]:
    """Encrypt a password for storage."""
    fernet = get_fernet()
    if not fernet:
        return None
    return fernet.encrypt(password.encode()).decode()


def decrypt_password(encrypted: str) -> Optional[str]:
    """Decrypt a password for export."""
    if not encrypted:
        return None
    fernet = get_fernet()
    if not fernet:
        return None
    try:
        return fernet.decrypt(encrypted.encode()).decode()
    except Exception as e:
        logger.error(f"Failed to decrypt password: {e}")
        return None


def validate_email(email: str) -> bool:
    """Validate email format."""
    return bool(EMAIL_REGEX.match(email.strip()))


def parse_csv_content(content: bytes) -> tuple[list[dict], Optional[str]]:
    """
    Parse CSV content into list of row dictionaries.

    Returns:
        Tuple of (rows, error_message)
    """
    try:
        # Try to decode as UTF-8, fall back to latin-1
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            text = content.decode("latin-1")

        # Parse CSV
        reader = csv.DictReader(io.StringIO(text))
        rows = []

        for i, row in enumerate(reader):
            # Normalize column names (lowercase, strip whitespace)
            normalized = {
                k.lower().strip().replace(" ", "_"): v.strip()
                for k, v in row.items()
                if k
            }
            normalized["_row_number"] = i + 2  # 1-indexed, accounting for header
            rows.append(normalized)

        return rows, None

    except Exception as e:
        logger.error(f"Failed to parse CSV: {e}")
        return [], str(e)


def parse_excel_content(content: bytes) -> tuple[list[dict], Optional[str]]:
    """
    Parse Excel content into list of row dictionaries.

    Returns:
        Tuple of (rows, error_message)
    """
    try:
        from openpyxl import load_workbook

        workbook = load_workbook(io.BytesIO(content), read_only=True)
        sheet = workbook.active

        rows = []
        headers = []

        for i, row in enumerate(sheet.iter_rows(values_only=True)):
            if i == 0:
                # First row is headers
                headers = [
                    str(cell).lower().strip().replace(" ", "_") if cell else f"col_{j}"
                    for j, cell in enumerate(row)
                ]
                continue

            # Skip empty rows
            if not any(row):
                continue

            row_dict = {}
            for j, cell in enumerate(row):
                if j < len(headers):
                    row_dict[headers[j]] = str(cell).strip() if cell else ""

            row_dict["_row_number"] = i + 1  # 1-indexed
            rows.append(row_dict)

        workbook.close()
        return rows, None

    except Exception as e:
        logger.error(f"Failed to parse Excel: {e}")
        return [], str(e)


def validate_row(row: dict, target_role: RoleEnum) -> Optional[str]:
    """
    Validate a single row's data.

    Returns:
        Error message if invalid, None if valid
    """
    # Check required columns based on role
    if target_role == RoleEnum.student:
        required = STUDENT_REQUIRED_COLUMNS
    else:
        required = SUPERVISOR_REQUIRED_COLUMNS

    missing = required - set(row.keys())
    if missing:
        return f"Missing required columns: {', '.join(missing)}"

    # Validate full_name
    full_name = row.get("full_name", "").strip()
    if not full_name:
        return "full_name is required and cannot be empty"

    # Validate email
    email = row.get("email", "").strip()
    if not email:
        return "email is required and cannot be empty"
    if not validate_email(email):
        return f"Invalid email format: {email}"

    # Validate roll_number for students
    if target_role == RoleEnum.student:
        roll_number = row.get("roll_number", "").strip()
        if not roll_number:
            return "roll_number is required for students"

        # Validate fyp_start_semester
        semester = row.get("fyp_start_semester", "").strip()
        if not semester:
            return "fyp_start_semester is required for students"
        if semester.lower() not in ("fall", "spring", "summer"):
            return f"Invalid fyp_start_semester: '{semester}'. Must be Fall, Spring, or Summer"

        # Validate fyp_start_year
        year_str = row.get("fyp_start_year", "").strip()
        if not year_str:
            return "fyp_start_year is required for students"
        try:
            year_val = int(float(year_str))  # handle "2026.0" from Excel
            if year_val < 2000 or year_val > 2100:
                return (
                    f"Invalid fyp_start_year: {year_val}. Must be between 2000 and 2100"
                )
        except (ValueError, TypeError):
            return f"Invalid fyp_start_year: '{year_str}'. Must be a valid year number"

        department = row.get("department", "").strip()
        if not department:
            return "department is required for students"
        try:
            row["department"] = normalize_department(department)
        except ValueError as exc:
            return str(exc)

        cgpa_raw = str(row.get("cgpa", "")).strip()
        if not cgpa_raw:
            return "cgpa is required for students"
        try:
            cgpa_val = float(cgpa_raw)
        except (ValueError, TypeError):
            return f"Invalid cgpa: '{cgpa_raw}'. Must be a number between 0 and 4"
        if cgpa_val < 0.0 or cgpa_val > 4.0:
            return f"Invalid cgpa: {cgpa_val}. Must be between 0 and 4"

    # Validate department and designation for supervisors
    if target_role == RoleEnum.faculty:
        department = row.get("department", "").strip()
        if not department:
            return "department is required for supervisors"
        try:
            row["department"] = normalize_department(department)
        except ValueError as exc:
            return str(exc)
        designation = row.get("designation", "").strip()
        if not designation:
            return "designation is required for supervisors"

    return None


async def create_bulk_import_job(
    db: AsyncSession,
    admin_user_id: UUID,
    target_role: RoleEnum,
    file_content: bytes,
    filename: str,
) -> tuple[Optional[BulkImportJob], Optional[str]]:
    """
    Create a bulk import job from uploaded file.

    Returns:
        Tuple of (job, error_message)
    """
    # Parse file based on extension
    if filename.lower().endswith((".xlsx", ".xls")):
        rows, parse_error = parse_excel_content(file_content)
    elif filename.lower().endswith(".csv"):
        rows, parse_error = parse_csv_content(file_content)
    else:
        return None, "Unsupported file format. Please upload CSV or Excel file."

    if parse_error:
        return None, f"Failed to parse file: {parse_error}"

    if not rows:
        return None, "File contains no data rows"

    # Check required columns exist
    if target_role == RoleEnum.student:
        required = STUDENT_REQUIRED_COLUMNS
    else:
        required = SUPERVISOR_REQUIRED_COLUMNS

    first_row_keys = set(rows[0].keys()) - {"_row_number"}
    missing = required - first_row_keys
    if missing:
        return None, f"Missing required columns: {', '.join(missing)}"

    try:
        # Create job
        job = BulkImportJob(
            created_by=admin_user_id,
            target_role=target_role,
            status=BulkJobStatus.pending,
            total_rows=len(rows),
            processed_rows=0,
            success_count=0,
            failed_count=0,
            skipped_count=0,
        )
        db.add(job)
        await db.flush()  # Get the job ID

        # Create items
        for row in rows:
            row_number = row.pop("_row_number", 0)
            item = BulkImportItem(
                job_id=job.id,
                row_number=row_number,
                payload=row,
                status=BulkItemStatus.pending,
            )
            db.add(item)

        await db.commit()
        await db.refresh(job)
    except IntegrityError as exc:
        await db.rollback()
        logger.exception("Integrity error while persisting bulk import job")
        db_detail = str(getattr(exc, "orig", exc))
        if target_role == RoleEnum.faculty:
            return (
                None,
                "Database integrity error while creating faculty import job. "
                "This is typically a DB constraint mismatch on bulk_import_jobs.target_role. "
                f"Details: {db_detail}",
            )
        return None, f"Database integrity error while creating import job: {db_detail}"
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.exception("Failed to persist bulk import job")
        return (
            None,
            f"Database error while creating import job: {exc.__class__.__name__}: {exc}",
        )

    logger.info(
        f"Created bulk import job {job.id} with {len(rows)} rows for {target_role.value}s"
    )
    return job, None


async def process_single_item(
    db: AsyncSession,
    item: BulkImportItem,
    target_role: RoleEnum,
) -> str:
    """
    Process a single bulk import item.

    Returns:
        Status string: 'success', 'failed', or 'skipped'
    """
    payload = item.payload

    # Validate row data
    validation_error = validate_row(payload, target_role)
    if validation_error:
        item.status = BulkItemStatus.failed
        item.error = validation_error
        return "failed"

    email = payload["email"].strip().lower()
    full_name = payload["full_name"].strip()

    # Check if user already exists
    existing_user = await db.execute(select(User).where(User.email == email))
    if existing_user.scalar_one_or_none():
        item.status = BulkItemStatus.skipped
        item.error = "Email already registered"
        return "skipped"

    # Check roll_number uniqueness for students
    if target_role == RoleEnum.student:
        roll_number = payload["roll_number"].strip()
        existing_student = await db.execute(
            select(Student).where(Student.roll_number == roll_number)
        )
        if existing_student.scalar_one_or_none():
            item.status = BulkItemStatus.skipped
            item.error = f"Roll number already exists: {roll_number}"
            return "skipped"

    # Generate temporary password
    temp_password = generate_temp_password()
    password_hash = hash_password(temp_password)

    # Determine role
    role = RoleEnum.student if target_role == RoleEnum.student else RoleEnum.faculty

    # Create user
    user = User(
        full_name=full_name,
        email=email,
        password_hash=password_hash,
        role=role,
    )
    db.add(user)
    await db.flush()  # Get user_id

    # Create profile based on role
    if target_role == RoleEnum.student:
        # Parse fyp_start_year (handle "2026.0" from Excel)
        fyp_year_raw = payload.get("fyp_start_year", "").strip()
        try:
            fyp_year = int(float(fyp_year_raw))
        except (ValueError, TypeError):
            fyp_year = None

        try:
            student_department = normalize_department(payload.get("department", ""))
        except ValueError as exc:
            item.status = BulkItemStatus.failed
            item.error = str(exc)
            return "failed"

        try:
            cgpa_val = round(float(str(payload.get("cgpa", "")).strip()), 2)
        except (ValueError, TypeError):
            item.status = BulkItemStatus.failed
            item.error = "Invalid cgpa (must be a number between 0 and 4)"
            return "failed"
        if cgpa_val < 0.0 or cgpa_val > 4.0:
            item.status = BulkItemStatus.failed
            item.error = "Invalid cgpa (must be between 0 and 4)"
            return "failed"

        student = Student(
            user_id=user.user_id,
            roll_number=payload["roll_number"].strip(),
            department=student_department,
            cgpa=cgpa_val,
            interests=[],
            skills=[],
            skills_levels={},
            fyp_start_semester=payload.get("fyp_start_semester", "").strip().lower()
            or None,
            fyp_start_year=fyp_year,
            is_active=True,
        )
        db.add(student)
    else:
        try:
            faculty_department = normalize_department(payload.get("department", ""))
        except ValueError as exc:
            item.status = BulkItemStatus.failed
            item.error = str(exc)
            return "failed"

        faculty_member = Faculty(
            user_id=user.user_id,
            department=faculty_department,
            designation=payload["designation"].strip(),
            project_type="research",  # Default
            capacity_max=8,
            capacity_filled=0,
            is_supervisor=True,
            is_jury=True,
            is_active=True,
        )
        db.add(faculty_member)

    # Store encrypted temp password
    item.temp_password_enc = encrypt_password(temp_password)
    item.expires_at = datetime.now(timezone.utc) + timedelta(
        hours=TEMP_PASSWORD_TTL_HOURS
    )
    item.created_user_id = user.user_id
    item.status = BulkItemStatus.success
    item.error = None

    return "success"


async def update_job_counters(db: AsyncSession, job_id: UUID) -> None:
    """Update job counters by re-counting item statuses from the DB."""
    from sqlalchemy import func

    counts_query = select(
        func.count()
        .filter(BulkImportItem.status == BulkItemStatus.success)
        .label("success"),
        func.count()
        .filter(BulkImportItem.status == BulkItemStatus.failed)
        .label("failed"),
        func.count()
        .filter(BulkImportItem.status == BulkItemStatus.skipped)
        .label("skipped"),
        func.count()
        .filter(BulkImportItem.status != BulkItemStatus.pending)
        .label("processed"),
    ).where(BulkImportItem.job_id == job_id)

    result = await db.execute(counts_query)
    counts = result.one()

    await db.execute(
        update(BulkImportJob)
        .where(BulkImportJob.id == job_id)
        .values(
            success_count=counts.success,
            failed_count=counts.failed,
            skipped_count=counts.skipped,
            processed_rows=counts.processed,
        )
    )


# ─── NEW: Inline Background Processing ─────────────────────────


async def process_job_inline(job_id: UUID) -> None:
    """
    Process ALL pending items for a specific job in-process.

    This is called as a FastAPI BackgroundTask after the upload endpoint
    returns 201 to the admin. It creates its own DB session since
    background tasks run outside the request lifecycle.

    Handles power failure / restart gracefully:
    - Items that were not processed remain in "pending" status
    - The job stays in "processing" status
    - Admin can call the retry endpoint to resume
    """
    from app.db import AsyncSessionLocal

    logger.info(f"Background processing started for job {job_id}")

    async with AsyncSessionLocal() as db:
        try:
            # Load the job
            job_query = select(BulkImportJob).where(BulkImportJob.id == job_id)
            job_result = await db.execute(job_query)
            job = job_result.scalar_one_or_none()

            if not job:
                logger.error(f"Job {job_id} not found for background processing")
                return

            if job.status not in (BulkJobStatus.pending, BulkJobStatus.processing):
                logger.info(f"Job {job_id} already in status {job.status}, skipping")
                return

            # Mark job as processing
            job.status = BulkJobStatus.processing
            await db.commit()

            # Load all pending items for this job
            items_query = (
                select(BulkImportItem)
                .where(
                    BulkImportItem.job_id == job_id,
                    BulkImportItem.status == BulkItemStatus.pending,
                )
                .order_by(BulkImportItem.row_number)
            )
            items_result = await db.execute(items_query)
            items = items_result.scalars().all()

            if not items:
                logger.info(f"No pending items for job {job_id}")
                job.status = BulkJobStatus.done
                await update_job_counters(db, job_id)
                await db.commit()
                return

            # Process each item
            stats = {"processed": 0, "success": 0, "failed": 0, "skipped": 0}

            for item in items:
                try:
                    result = await process_single_item(db, item, job.target_role)
                    stats[result] += 1
                    stats["processed"] += 1
                except Exception as e:
                    logger.error(
                        f"Error processing item {item.id} (row {item.row_number}): {e}"
                    )
                    item.status = BulkItemStatus.failed
                    item.error = str(e)[:500]
                    stats["failed"] += 1
                    stats["processed"] += 1

                # Commit after each item so progress is saved
                # (if power fails, already-processed items don't reprocess)
                await db.commit()

            # Update final job counters and mark as done
            await update_job_counters(db, job_id)

            # Reload job to get updated counters
            await db.refresh(job)
            job.status = BulkJobStatus.done
            await db.commit()

            logger.info(
                f"Job {job_id} completed: {stats['success']} success, "
                f"{stats['failed']} failed, {stats['skipped']} skipped "
                f"out of {stats['processed']} processed"
            )

        except Exception as e:
            logger.error(f"Fatal error processing job {job_id}: {e}")
            try:
                # Try to mark job as failed
                await db.rollback()
                job_query = select(BulkImportJob).where(BulkImportJob.id == job_id)
                job_result = await db.execute(job_query)
                job = job_result.scalar_one_or_none()
                if job:
                    job.status = BulkJobStatus.failed
                    await update_job_counters(db, job_id)
                    await db.commit()
            except Exception as inner_e:
                logger.error(f"Failed to mark job {job_id} as failed: {inner_e}")


# ─── Retry / Resume Processing ─────────────────────────────────


async def retry_failed_items(db: AsyncSession, job_id: UUID) -> int:
    """
    Reset failed items back to pending so they can be reprocessed.

    Returns:
        Number of items reset to pending
    """
    # Reset failed items to pending
    result = await db.execute(
        update(BulkImportItem)
        .where(
            BulkImportItem.job_id == job_id,
            BulkImportItem.status == BulkItemStatus.failed,
        )
        .values(status=BulkItemStatus.pending, error=None)
    )
    items_reset = result.rowcount

    if items_reset > 0:
        # Reset job status so it can be reprocessed
        await db.execute(
            update(BulkImportJob)
            .where(BulkImportJob.id == job_id)
            .values(status=BulkJobStatus.pending)
        )
        await update_job_counters(db, job_id)

    await db.commit()
    return items_reset


async def resume_interrupted_job(db: AsyncSession, job_id: UUID) -> int:
    """
    Resume a job that was interrupted (e.g., power failure).
    Only resets the job status — pending items are already pending.

    Returns:
        Number of pending items remaining
    """
    from sqlalchemy import func

    # Count pending items
    count_query = (
        select(func.count())
        .select_from(BulkImportItem)
        .where(
            BulkImportItem.job_id == job_id,
            BulkImportItem.status == BulkItemStatus.pending,
        )
    )
    result = await db.execute(count_query)
    pending_count = result.scalar_one()

    if pending_count > 0:
        # Reset job status to pending so background processing picks it up
        await db.execute(
            update(BulkImportJob)
            .where(BulkImportJob.id == job_id)
            .values(status=BulkJobStatus.pending)
        )
        await db.commit()

    return pending_count


# ─── Process pending items (manual trigger / retry) ─────────────


async def process_pending_items(db: AsyncSession, batch_size: int = BATCH_SIZE) -> dict:
    """
    Process a batch of pending bulk import items.

    Uses SELECT FOR UPDATE SKIP LOCKED to prevent concurrent processing.
    This is used by the manual retry/trigger endpoint.

    Returns:
        Dict with processing statistics
    """
    stats = {
        "processed": 0,
        "success": 0,
        "failed": 0,
        "skipped": 0,
        "jobs_completed": [],
    }

    # Get pending items with row-level locking
    query = (
        select(BulkImportItem)
        .join(BulkImportJob)
        .where(
            BulkImportItem.status == BulkItemStatus.pending,
            BulkImportJob.status.in_([BulkJobStatus.pending, BulkJobStatus.processing]),
        )
        .order_by(BulkImportItem.job_id, BulkImportItem.row_number)
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )

    result = await db.execute(query)
    items = result.scalars().all()

    if not items:
        logger.info("No pending items to process")
        return stats

    # Update jobs to processing status
    job_ids = set(item.job_id for item in items)
    await db.execute(
        update(BulkImportJob)
        .where(
            BulkImportJob.id.in_(job_ids), BulkImportJob.status == BulkJobStatus.pending
        )
        .values(status=BulkJobStatus.processing)
    )

    # Load jobs for target_role lookup
    jobs_query = select(BulkImportJob).where(BulkImportJob.id.in_(job_ids))
    jobs_result = await db.execute(jobs_query)
    jobs_map = {job.id: job for job in jobs_result.scalars().all()}

    # Process each item
    for item in items:
        job = jobs_map.get(item.job_id)
        if not job:
            continue

        try:
            result = await process_single_item(db, item, job.target_role)
            stats[result] += 1
            stats["processed"] += 1
        except Exception as e:
            logger.error(f"Error processing item {item.id}: {e}")
            item.status = BulkItemStatus.failed
            item.error = str(e)[:500]
            stats["failed"] += 1
            stats["processed"] += 1

    # Update job counters
    for job_id in job_ids:
        await update_job_counters(db, job_id)

    await db.commit()

    # Check for completed jobs
    for job_id in job_ids:
        job_query = select(BulkImportJob).where(BulkImportJob.id == job_id)
        job_result = await db.execute(job_query)
        job = job_result.scalar_one_or_none()
        if job and job.processed_rows >= job.total_rows:
            job.status = BulkJobStatus.done
            stats["jobs_completed"].append(job_id)

    await db.commit()

    logger.info(
        f"Processed {stats['processed']} items: {stats['success']} success, "
        f"{stats['failed']} failed, {stats['skipped']} skipped"
    )

    return stats


# ─── Job Report ─────────────────────────────────────────────────


async def get_job_report(db: AsyncSession, job_id: UUID) -> Optional[dict]:
    """
    Generate a full report for a bulk import job.

    Returns a dict with summary counts and detailed breakdowns of
    created, skipped, failed, and pending items.
    """
    # Load job
    job_query = select(BulkImportJob).where(BulkImportJob.id == job_id)
    job_result = await db.execute(job_query)
    job = job_result.scalar_one_or_none()

    if not job:
        return None

    # Load all items
    items_query = (
        select(BulkImportItem)
        .where(BulkImportItem.job_id == job_id)
        .order_by(BulkImportItem.row_number)
    )
    items_result = await db.execute(items_query)
    items = items_result.scalars().all()

    # Categorize items
    created_users = []
    skipped_items = []
    failed_items = []
    pending_items = []

    for item in items:
        payload = item.payload
        detail = {
            "row_number": item.row_number,
            "full_name": payload.get("full_name", ""),
            "email": payload.get("email", ""),
            "roll_number": payload.get("roll_number"),
            "status": item.status.value if item.status else "unknown",
            "error": item.error,
            "user_id": item.created_user_id,
        }

        if item.status == BulkItemStatus.success:
            created_users.append(detail)
        elif item.status == BulkItemStatus.skipped:
            skipped_items.append(detail)
        elif item.status == BulkItemStatus.failed:
            failed_items.append(detail)
        elif item.status == BulkItemStatus.pending:
            pending_items.append(detail)

    # Calculate progress
    progress_percent = (
        (job.processed_rows / job.total_rows * 100) if job.total_rows > 0 else 0
    )

    return {
        "job_id": job.id,
        "target_role": job.target_role.value,
        "status": job.status.value,
        "total_rows": job.total_rows,
        "success_count": len(created_users),
        "failed_count": len(failed_items),
        "skipped_count": len(skipped_items),
        "pending_count": len(pending_items),
        "progress_percent": round(progress_percent, 1),
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "created_users": created_users,
        "skipped_items": skipped_items,
        "failed_items": failed_items,
        "pending_items": pending_items,
    }


async def get_job_results(
    db: AsyncSession,
    job_id: UUID,
) -> list[dict]:
    """
    Get all results for a job, decrypting passwords where not expired.

    Returns:
        List of result dictionaries for CSV export
    """
    query = (
        select(BulkImportItem)
        .where(BulkImportItem.job_id == job_id)
        .order_by(BulkImportItem.row_number)
    )

    result = await db.execute(query)
    items = result.scalars().all()

    results = []
    now = datetime.now(timezone.utc)

    for item in items:
        payload = item.payload

        # Decrypt password only if not expired
        temp_password = None
        if item.temp_password_enc and item.expires_at:
            if item.expires_at > now:
                temp_password = decrypt_password(item.temp_password_enc)

        results.append(
            {
                "row_number": item.row_number,
                "full_name": payload.get("full_name", ""),
                "email": payload.get("email", ""),
                "roll_number": payload.get("roll_number", ""),
                "cgpa": payload.get("cgpa", ""),
                "department": payload.get("department", ""),
                "status": item.status.value if item.status else "",
                "error": item.error or "",
                "user_id": str(item.created_user_id) if item.created_user_id else "",
                "temp_password": temp_password or "",
            }
        )

    return results


# ─── Single User Registration ──────────────────────────────────


async def create_single_student(
    db: AsyncSession,
    full_name: str,
    email: str,
    roll_number: str,
    cgpa: float,
    fyp_start_semester: str,
    fyp_start_year: int,
    department: str,
) -> tuple[User, str]:
    """
    Create a single student user with profile.

    Returns:
        Tuple of (created_user, plaintext_temp_password)

    Raises:
        ValueError if email or roll_number already exists
    """
    email = email.strip().lower()

    # Check email uniqueness
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        raise ValueError(f"Email already registered: {email}")

    # Check roll_number uniqueness
    existing_roll = await db.execute(
        select(Student).where(Student.roll_number == roll_number.strip())
    )
    if existing_roll.scalar_one_or_none():
        raise ValueError(f"Roll number already exists: {roll_number}")

    normalized_department = normalize_department(department)

    # Generate temp password
    temp_password = generate_temp_password()
    password_hash = hash_password(temp_password)

    # Create user
    user = User(
        full_name=full_name.strip(),
        email=email,
        password_hash=password_hash,
        role=RoleEnum.student,
    )
    db.add(user)
    await db.flush()

    # Create student profile
    student = Student(
        user_id=user.user_id,
        roll_number=roll_number.strip(),
        department=normalized_department,
        cgpa=round(cgpa, 2),
        interests=[],
        skills=[],
        skills_levels={},
        fyp_start_semester=fyp_start_semester.strip().lower(),
        fyp_start_year=fyp_start_year,
        is_active=True,
    )
    db.add(student)
    await db.commit()
    await db.refresh(user)

    logger.info(f"Created single student: {email} ({user.user_id})")
    return user, temp_password


async def create_single_supervisor(
    db: AsyncSession,
    full_name: str,
    email: str,
    department: str,
    designation: str,
) -> tuple[User, str]:
    """
    Create a single supervisor user with profile.
    Auto-sets is_supervisor=True, is_jury=True, is_active=True.

    Returns:
        Tuple of (created_user, plaintext_temp_password)

    Raises:
        ValueError if email already exists
    """
    email = email.strip().lower()

    # Check email uniqueness
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        raise ValueError(f"Email already registered: {email}")

    normalized_department = normalize_department(department)

    # Generate temp password
    temp_password = generate_temp_password()
    password_hash = hash_password(temp_password)

    # Create user
    user = User(
        full_name=full_name.strip(),
        email=email,
        password_hash=password_hash,
        role=RoleEnum.faculty,
    )
    db.add(user)
    await db.flush()

    # Create faculty profile
    faculty_member = Faculty(
        user_id=user.user_id,
        department=normalized_department,
        designation=designation.strip(),
        project_type="research",
        capacity_max=8,
        capacity_filled=0,
        is_supervisor=True,
        is_jury=True,
        is_active=True,
    )
    db.add(faculty_member)
    await db.commit()
    await db.refresh(user)

    logger.info(f"Created single faculty member: {email} ({user.user_id})")
    return user, temp_password
