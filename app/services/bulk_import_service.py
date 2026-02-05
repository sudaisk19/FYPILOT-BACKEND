# app/services/bulk_import_service.py

"""
Bulk Import Service

Handles the core business logic for bulk user registration:
- File parsing (CSV/Excel)
- Password generation and encryption
- User creation with profiles
- Batch processing for cron jobs
"""

import csv
import io
import logging
import re
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from cryptography.fernet import Fernet
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.utils import hash_password
from app.core.config import settings
from app.models.bulk_import import (
    BulkImportItem,
    BulkImportJob,
    BulkItemStatus,
    BulkJobStatus,
    TargetRoleEnum,
)
from app.models.student import Student
from app.models.supervisor import Supervisor
from app.models.user import RoleEnum, User

logger = logging.getLogger(__name__)

# Configuration from settings
BATCH_SIZE = settings.bulk_import_batch_size
TEMP_PASSWORD_TTL_HOURS = settings.temp_password_ttl_hours
APP_ENCRYPTION_KEY = settings.app_encryption_key

# Required columns for each role
STUDENT_REQUIRED_COLUMNS = {"full_name", "email", "roll_number"}
SUPERVISOR_REQUIRED_COLUMNS = {"full_name", "email"}

# Email validation regex
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


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


def validate_row(row: dict, target_role: TargetRoleEnum) -> Optional[str]:
    """
    Validate a single row's data.

    Returns:
        Error message if invalid, None if valid
    """
    # Check required columns based on role
    if target_role == TargetRoleEnum.student:
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
    if target_role == TargetRoleEnum.student:
        roll_number = row.get("roll_number", "").strip()
        if not roll_number:
            return "roll_number is required for students"

    return None


async def create_bulk_import_job(
    db: AsyncSession,
    admin_user_id: UUID,
    target_role: TargetRoleEnum,
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
    if target_role == TargetRoleEnum.student:
        required = STUDENT_REQUIRED_COLUMNS
    else:
        required = SUPERVISOR_REQUIRED_COLUMNS

    first_row_keys = set(rows[0].keys()) - {"_row_number"}
    missing = required - first_row_keys
    if missing:
        return None, f"Missing required columns: {', '.join(missing)}"

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

    logger.info(
        f"Created bulk import job {job.id} with {len(rows)} rows for {target_role.value}s"
    )
    return job, None


async def process_pending_items(db: AsyncSession, batch_size: int = BATCH_SIZE) -> dict:
    """
    Process a batch of pending bulk import items.

    Uses SELECT FOR UPDATE SKIP LOCKED to prevent concurrent processing.

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
    # Join with job to get target_role
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
        await update_job_counters(db, job_id, stats)

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


async def process_single_item(
    db: AsyncSession,
    item: BulkImportItem,
    target_role: TargetRoleEnum,
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
    if target_role == TargetRoleEnum.student:
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
    role = (
        RoleEnum.student
        if target_role == TargetRoleEnum.student
        else RoleEnum.supervisor
    )

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
    if target_role == TargetRoleEnum.student:
        student = Student(
            user_id=user.user_id,
            roll_number=payload["roll_number"].strip(),
            department=payload.get("department", "").strip() or None,
            cgpa=None,
            interests=[],
            skills=[],
            skills_levels={},
        )
        db.add(student)
    else:
        supervisor = Supervisor(
            user_id=user.user_id,
            department=payload.get("department", "").strip() or None,
            designation=payload.get("designation", "").strip() or None,
            project_type="research",  # Default
            capacity_max=8,
            capacity_filled=0,
        )
        db.add(supervisor)

    # Store encrypted temp password
    item.temp_password_enc = encrypt_password(temp_password)
    item.expires_at = datetime.now(timezone.utc) + timedelta(
        hours=TEMP_PASSWORD_TTL_HOURS
    )
    item.created_user_id = user.user_id
    item.status = BulkItemStatus.success
    item.error = None

    return "success"


async def update_job_counters(db: AsyncSession, job_id: UUID, stats: dict) -> None:
    """Update job counters based on processed items."""
    # Get current counts from items
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
                "department": payload.get("department", ""),
                "status": item.status.value if item.status else "",
                "error": item.error or "",
                "user_id": str(item.created_user_id) if item.created_user_id else "",
                "temp_password": temp_password or "",
            }
        )

    return results
