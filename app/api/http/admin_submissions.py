import logging
import os
import re
import mimetypes
import tempfile
from datetime import datetime
from typing import List, Optional, Set
from urllib.parse import urlparse
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, StreamingResponse
from starlette.background import BackgroundTask
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.supabase_auth import get_current_user
from app.db import get_db, supabase
from app.models.announcement import (
    Announcement,
    AnnouncementFile,
    AnnouncementRoleEnum,
    AnnouncementTarget,
    FileTypeEnum,
    TargetRoleEnum,
)
from app.models.group import FYPCycleEnum, Group
from app.models.submission import (
    Submission,
    SubmissionFile,
    SubmissionStatusEnum,
    SubmissionTypeEnum,
)
from app.models.user import RoleEnum, User
from app.schemas.submission_schema import (
    AttachmentInfo,
    CreateSubmissionAnnouncementRequest,
    EditSubmissionAnnouncementRequest,
    FileOutput,
    GroupSubmissionsResponse,
    GroupSubmissionStatus,
    PaginatedSubmissionTasksResponse,
    SubmissionAnnouncementResponse,
    SubmissionEvaluationResponse,
    SubmissionFileInfo,
    SubmissionTaskInfo,
    UpdateAdminGradingRequest,
)
from app.services.storage_service import (
    ANNOUNCEMENTS_BUCKET,
    delete_file_from_supabase,
    upload_file_to_supabase,
)

router = APIRouter(prefix="/admin", tags=["admin-submissions"])
logger = logging.getLogger(__name__)

SUBMISSION_FILES_BUCKET = "submission_files"


ASSIGNMENT_LABEL_TO_ROLES = {
    "All Students": (TargetRoleEnum.all_students,),
    "All Supervisors": (TargetRoleEnum.all_supervisors,),
    "FYP-I Students": (TargetRoleEnum.fyp1_students,),
    "FYP-II Students": (TargetRoleEnum.fyp2_students,),
    "Both": (
        TargetRoleEnum.all_students,
        TargetRoleEnum.all_supervisors,
    ),
}

ASSIGN_TO_CHOICES_DESC = (
    "Students, Supervisors, FYP-I Students, FYP-II Students, or Both"
)

INVALID_ASSIGNTO_MESSAGE = (
    f"Invalid assignTo option. Choose from {ASSIGN_TO_CHOICES_DESC}."
)

_ROLE_SET_TO_LABEL = {
    frozenset(roles): label for label, roles in ASSIGNMENT_LABEL_TO_ROLES.items()
}
_ROLE_SET_TO_LABEL[frozenset({TargetRoleEnum.both})] = "Both"


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _safe_filename(name: str) -> str:
    """Sanitize a filename for safe storage."""
    base, ext = os.path.splitext(name)
    safe_base = re.sub(r"[^A-Za-z0-9._-]", "_", base or "file")
    safe_ext = re.sub(r"[^A-Za-z0-9._-]", "_", ext)
    cleaned = f"{safe_base}{safe_ext}" if safe_ext else safe_base
    return cleaned or "file"


def _build_storage_key(user_id: UUID, filename: str) -> str:
    """Build a unique storage key for a file."""
    safe_name = _safe_filename(filename)
    return f"announcements/{uuid4()}-{safe_name}"


def _resolve_submission_storage_key(raw_key: str) -> str:
    """Map stored keys or URLs back to the Supabase object path."""
    if not raw_key:
        return raw_key

    if raw_key.startswith(("http://", "https://")):
        parsed = urlparse(raw_key)
        path = parsed.path
        public_prefix = "/storage/v1/object/public/"
        if public_prefix in path:
            path = path.split(public_prefix, 1)[1]

        bucket_prefix = f"{SUBMISSION_FILES_BUCKET}/"
        if bucket_prefix in path:
            return path.split(bucket_prefix, 1)[1]

        return os.path.basename(path)

    # Handle values that still include bucket prefix
    bucket_prefix = f"{SUBMISSION_FILES_BUCKET}/"
    if raw_key.startswith(bucket_prefix):
        return raw_key[len(bucket_prefix) :]

    return raw_key


def _infer_mime(file_name: str, stored_mime: Optional[str]) -> str:
    """Best-effort MIME detection for download responses."""
    if stored_mime:
        return stored_mime

    guessed, _ = mimetypes.guess_type(file_name)
    return guessed or "application/octet-stream"


def _assign_to_label(targets: List[AnnouncementTarget]) -> Optional[str]:
    """Convert announcement targets into a human-readable label."""
    role_set = frozenset(
        t.target_role for t in targets if t.target_role is not None
    )
    if not role_set:
        return None
    if TargetRoleEnum.both in role_set:
        return "Both"

    mapped = _ROLE_SET_TO_LABEL.get(role_set)
    if mapped:
        return mapped

    # Fallbacks for mixed legacy data
    if TargetRoleEnum.all_students in role_set and TargetRoleEnum.all_supervisors in role_set:
        return "Both"
    if TargetRoleEnum.all_students in role_set:
        return "Students"
    if TargetRoleEnum.all_supervisors in role_set:
        return "All Supervisors"
    if TargetRoleEnum.fyp1_students in role_set:
        return "FYP-I Students"
    if TargetRoleEnum.fyp2_students in role_set:
        return "FYP-II Students"
    return None


def _build_response(announcement: Announcement) -> SubmissionAnnouncementResponse:
    """Build a uniform response from an Announcement ORM object."""
    return SubmissionAnnouncementResponse(
        id=announcement.announcement_id,
        title=announcement.title,
        description=announcement.description,
        dueDate=announcement.due_at,
        total_marks=(
            float(announcement.total_marks) if announcement.total_marks else None
        ),
        assignTo=_assign_to_label(announcement.targets),
        isSubmission=announcement.is_submission_request,
        files=[
            FileOutput(
                id=f.file_id,
                name=f.file_name,
                url=f.storage_key,
                type=f.file_type.value,
                mimeType=f.mime_type,
                size=f.size_bytes,
            )
            for f in announcement.files
        ],
        createdAt=announcement.created_at,
        updatedAt=announcement.updated_at,
    )


def _build_targets(assign_to: str, announcement_id: UUID) -> List[AnnouncementTarget]:
    """Create AnnouncementTarget rows from an assignTo label."""
    roles = ASSIGNMENT_LABEL_TO_ROLES.get(assign_to)
    if not roles:
        raise HTTPException(status_code=400, detail=INVALID_ASSIGNTO_MESSAGE)

    return [
        AnnouncementTarget(
            announcement_id=announcement_id,
            target_role=role,
        )
        for role in roles
    ]


async def _create_placeholder_submissions_for_groups(
    assign_to: str,
    announcement: Announcement,
    db: AsyncSession,
):
    """Pre-create pending submission rows for every targeted student group."""

    # Only proceed for admin-created submission announcements
    if (
        announcement.created_by_role != AnnouncementRoleEnum.admin
        or not announcement.is_submission_request
    ):
        return

    roles = ASSIGNMENT_LABEL_TO_ROLES.get(assign_to)
    if not roles:
        return

    include_all_students = TargetRoleEnum.all_students in roles
    cycle_filters: Set[FYPCycleEnum] = set()
    if TargetRoleEnum.fyp1_students in roles:
        cycle_filters.add(FYPCycleEnum.fyp1)
    if TargetRoleEnum.fyp2_students in roles:
        cycle_filters.add(FYPCycleEnum.fyp2)

    if not include_all_students and not cycle_filters:
        # Target audience does not include student groups (e.g., supervisors only)
        return

    group_stmt = select(Group.group_id)
    if not include_all_students:
        group_stmt = group_stmt.where(Group.fyp_cycle.in_(tuple(cycle_filters)))

    result = await db.execute(group_stmt)
    group_ids = result.scalars().all()

    if not group_ids:
        logger.info(
            "No groups matched assignTo=%s for announcement %s; skipping placeholder submissions",
            assign_to,
            announcement.announcement_id,
        )
        return

    submissions = [
        Submission(
            group_id=group_id,
            created_by=announcement.created_by,
            title=announcement.title,
            note=announcement.description,
            type=SubmissionTypeEnum.official,
            status=SubmissionStatusEnum.pending,
            linked_announcement_id=announcement.announcement_id,
        )
        for group_id in group_ids
    ]

    db.add_all(submissions)
    logger.info(
        "Created %d placeholder submission rows for announcement %s",
        len(submissions),
        announcement.announcement_id,
    )


@router.get(
    "/files/{file_id}/download",
    summary="Download or view an announcement file",
)
async def download_announcement_file(
    file_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Download or view an announcement file.
    """
    if current_user.role != RoleEnum.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    # Fetch file metadata
    result = await db.execute(
        select(AnnouncementFile).where(AnnouncementFile.file_id == file_id)
    )
    file_record = result.scalars().first()

    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    # Download from storage
    try:
        file_content = supabase.storage.from_(SUBMISSION_FILES_BUCKET).download(file_record.storage_key)
    except Exception as e:
        raise HTTPException(
            status_code=404,
            detail=f"File not found or failed to download: {str(e)}"
        )

    # Return as streaming response
    return StreamingResponse(
        iter([file_content]),
        media_type=file_record.mime_type or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{file_record.file_name}"'},
    )


# ─── CREATE ───────────────────────────────────────────────────────────────────


@router.post(
    "/submission-tasks",
    response_model=SubmissionAnnouncementResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a submission-request announcement",
)
async def create_submission_announcement(
    request: Request,
    title: str = Form(..., description="Announcement title"),
    assignTo: str = Form(
        ...,
        description=f"Target audience: {ASSIGN_TO_CHOICES_DESC}",
    ),
    description: Optional[str] = Form(None, description="Announcement description"),
    dueDate: str = Form(
        ..., description="Due date in ISO format (YYYY-MM-DDTHH:MM:SSZ)"
    ),
    total_marks: Optional[float] = Form(
        None, description="Total marks for the submission"
    ),
    file_types: Optional[str] = Form(
        None,
        description="Comma-separated file types for each uploaded file (Document or Template). E.g., 'Document,Template,Document'",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Create a new submission-request announcement with optional file uploads.

    Request Body (multipart/form-data):
    - title: **(Required)** Announcement title
    - assignTo: **(Required)** Target audience (Students, Supervisors, FYP1 Students, FYP2 Students, or Both)
    - description: (Optional) Announcement description
    - dueDate: **(Required)** Due date in ISO format (e.g., 2026-02-12T00:00:00Z)
    - total_marks: (Optional) Total marks for the submission
    - uploaded_files: (Optional) Attachment files
    - file_types: (Optional) Comma-separated types for each file: 'Document' or 'Template' (defaults to Document)
    """
    if current_user.role != RoleEnum.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    # Parse due date if provided
    try:
        from datetime import datetime as dt

        due_date = dt.fromisoformat(dueDate.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid dueDate format. Use ISO format: YYYY-MM-DDTHH:MM:SSZ",
        )

    # Create request object
    body = CreateSubmissionAnnouncementRequest(
        title=title,
        description=description,
        assignTo=assignTo,
        dueDate=due_date,
        total_marks=total_marks,
        files=[],
    )

    # 1. Create announcement
    announcement = Announcement(
        created_by=current_user.user_id,
        created_by_role=AnnouncementRoleEnum.admin,
        title=body.title,
        description=body.description,
        is_submission_request=True,
        due_at=body.dueDate,
        total_marks=body.total_marks,
    )
    db.add(announcement)
    await db.flush()  # get announcement_id

    # 2. Create targets
    for target in _build_targets(body.assignTo, announcement.announcement_id):
        db.add(target)

    # 3. Upload new files if provided
    # Extract files manually from form data to avoid 422 when empty string is sent
    form = await request.form()
    incoming_files = [
        v
        for k, v in form.multi_items()
        if k == "uploaded_files" and getattr(v, "filename", None)
    ]
    logger.info(f"Received {len(incoming_files)} files for upload")

    # Parse file_types list
    types_list = [t.strip() for t in file_types.split(",")] if file_types else []
    logger.info(f"File types: {types_list}")

    if incoming_files:
        logger.info(f"Uploading {len(incoming_files)} files to storage...")

        for idx, upload_file in enumerate(incoming_files):
            # Build storage key
            storage_key = _build_storage_key(current_user.user_id, upload_file.filename)

            # Upload to Supabase
            size_bytes = await upload_file_to_supabase(
                supabase,
                bucket=ANNOUNCEMENTS_BUCKET,
                storage_key=storage_key,
                upload=upload_file,
            )
            logger.info(f"Uploaded file: {upload_file.filename} ({size_bytes} bytes) to {storage_key}")

            # Determine file type (default to Document)
            ftype_str = (
                types_list[idx]
                if idx < len(types_list)
                else "Document"
            )
            ftype = (
                FileTypeEnum.Template
                if ftype_str.lower() == "template"
                else FileTypeEnum.Document
            )

            logger.info(f"Saving file to DB: {upload_file.filename} (type={ftype.value})")
            db.add(
                AnnouncementFile(
                    announcement_id=announcement.announcement_id,
                    file_name=upload_file.filename,
                    storage_key=storage_key,
                    mime_type=upload_file.content_type or "application/octet-stream",
                    size_bytes=size_bytes,
                    file_type=ftype,
                )
            )
    else:
        logger.info("No files to upload")

    # 4. Link existing files from body.files (if using pre-uploaded files)
    for f in body.files:
        db.add(
            AnnouncementFile(
                announcement_id=announcement.announcement_id,
                file_name=f.name,
                storage_key=f.url,
                mime_type=f.mimeType,
                size_bytes=f.size,
                file_type=FileTypeEnum(f.type),
            )
        )

    await _create_placeholder_submissions_for_groups(
        assign_to=body.assignTo,
        announcement=announcement,
        db=db,
    )

    await db.commit()

    # 4. Re-fetch with relationships loaded
    result = await db.execute(
        select(Announcement)
        .options(
            selectinload(Announcement.targets),
            selectinload(Announcement.files),
        )
        .where(Announcement.announcement_id == announcement.announcement_id)
    )
    announcement = result.scalars().first()

    return _build_response(announcement)


# ─── GET ONE ──────────────────────────────────────────────────────────────────


@router.get(
    "/submission-tasks/{announcement_id}",
    response_model=SubmissionAnnouncementResponse,
    summary="Get a single submission-request announcement",
)
async def get_submission_announcement(
    announcement_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Get details of a specific submission-request announcement.

    Use this to fetch current values before editing.
    """
    if current_user.role != RoleEnum.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    result = await db.execute(
        select(Announcement)
        .options(
            selectinload(Announcement.targets),
            selectinload(Announcement.files),
        )
        .where(Announcement.announcement_id == announcement_id)
    )
    announcement = result.scalars().first()

    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")

    if not announcement.is_submission_request:
        raise HTTPException(
            status_code=400, detail="This announcement is not a submission request"
        )

    return _build_response(announcement)


# ─── EDIT ─────────────────────────────────────────────────────────────────────


@router.patch(
    "/submission-tasks/{announcement_id}",
    response_model=SubmissionAnnouncementResponse,
    summary="Edit a submission-request announcement",
)
async def edit_submission_announcement(
    request: Request,
    announcement_id: UUID,
    title: Optional[str] = Form(None, description="Announcement title"),
    description: Optional[str] = Form(None, description="Announcement description"),
    assignTo: Optional[str] = Form(
        None,
        description=f"Target audience: {ASSIGN_TO_CHOICES_DESC}",
    ),
    dueDate: Optional[str] = Form(
        None, description="Due date in ISO format (YYYY-MM-DDTHH:MM:SSZ)"
    ),
    total_marks: Optional[str] = Form(
        None, description="Total marks for the submission"
    ),
    keep_file_ids: Optional[str] = Form(
        None, description="Comma-separated file IDs to keep (e.g., 'uuid1,uuid2')"
    ),
    file_types: Optional[str] = Form(
        None,
        description="Comma-separated file types for each uploaded file (Document or Template)",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Update an existing submission-request announcement with optional file uploads.

    Request Body (multipart/form-data):
    - title: (Optional) New announcement title
    - description: (Optional) New announcement description
    - assignTo: (Optional) New target audience (Students, Supervisors, FYP1 Students, FYP2 Students, or Both)
    - dueDate: (Optional) New due date in ISO format (e.g., 2026-02-12T00:00:00Z)
    - total_marks: (Optional) New total marks
    - keep_file_ids: (Optional) Comma-separated UUIDs of files to keep. Files not in this list will be deleted.
    - uploaded_files: (Optional) New files to upload
    - file_types: (Optional) Comma-separated types for each new file: 'Document' or 'Template' (defaults to Document)
    """
    if current_user.role != RoleEnum.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    # Normalize empty strings to None
    title = title.strip() if title and title.strip() else None
    description = description.strip() if description and description.strip() else None
    assignTo = assignTo.strip() if assignTo and assignTo.strip() else None
    dueDate = dueDate.strip() if dueDate and dueDate.strip() else None
    # keep_file_ids: empty string means "delete all files", None means "not provided"
    keep_file_ids_provided = keep_file_ids is not None
    keep_file_ids = (
        keep_file_ids.strip() if keep_file_ids and keep_file_ids.strip() else None
    )
    file_types = file_types.strip() if file_types and file_types.strip() else None

    # Parse total_marks (handle empty strings)
    parsed_total_marks = None
    if total_marks and total_marks.strip():
        try:
            parsed_total_marks = float(total_marks)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid total_marks value")

    # Parse due date if provided
    parsed_due_date = None
    if dueDate:
        try:
            from datetime import datetime as dt

            parsed_due_date = dt.fromisoformat(dueDate.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid dueDate format. Use ISO format: YYYY-MM-DDTHH:MM:SSZ",
            )

    # Parse keep_file_ids
    keep_ids = set()
    if keep_file_ids:
        try:
            keep_ids = {
                UUID(fid.strip()) for fid in keep_file_ids.split(",") if fid.strip()
            }
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid UUID in keep_file_ids")

    # Create request object (only with provided fields)
    body = EditSubmissionAnnouncementRequest(
        title=title,
        description=description,
        assignTo=assignTo,
        dueDate=parsed_due_date,
        total_marks=parsed_total_marks,
        files=None,  # We'll handle file sync separately
    )

    # 1. Fetch existing announcement
    result = await db.execute(
        select(Announcement)
        .options(
            selectinload(Announcement.targets),
            selectinload(Announcement.files),
        )
        .where(Announcement.announcement_id == announcement_id)
    )
    announcement = result.scalars().first()

    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")

    if not announcement.is_submission_request:
        raise HTTPException(
            status_code=400, detail="This announcement is not a submission request"
        )

    # 2. Update scalar fields
    if body.title is not None:
        announcement.title = body.title
    if body.description is not None:
        announcement.description = body.description
    if body.dueDate is not None:
        announcement.due_at = body.dueDate
    if body.total_marks is not None:
        announcement.total_marks = body.total_marks

    # 3. Update targets if assignTo changed
    if body.assignTo is not None:
        # Remove old targets
        await db.execute(
            delete(AnnouncementTarget).where(
                AnnouncementTarget.announcement_id == announcement_id
            )
        )
        # Add new targets
        for target in _build_targets(body.assignTo, announcement_id):
            db.add(target)

    # 4. Sync files based on keep_file_ids
    # IMPORTANT: keep_file_ids controls EXISTING files only
    # - Not provided (None): Keep all existing files
    # - Empty string: Delete all existing files  
    # - Comma-separated UUIDs: Keep only those files, delete others
    # This is independent of NEW files being uploaded via uploaded_files
    if keep_file_ids_provided:  # If keep_file_ids was sent (even empty = delete all)
        logger.info(f"File sync requested with keep_file_ids: {keep_ids if keep_ids else 'DELETE ALL'}")
        # Delete files that are not in the keep list (both from DB and storage)
        for existing_file in list(announcement.files):
            if existing_file.file_id not in keep_ids:
                # Delete from Supabase Storage
                try:
                    await delete_file_from_supabase(
                        supabase,
                        bucket=ANNOUNCEMENTS_BUCKET,
                        storage_key=existing_file.storage_key,
                    )
                    logger.info(
                        f"Deleted file from storage: {existing_file.storage_key}"
                    )
                except Exception as e:
                    # Log error but continue (file might already be deleted from storage)
                    logger.warning(
                        f"Could not delete file from storage {existing_file.storage_key}: {e}"
                    )
                # Delete from database
                await db.delete(existing_file)

    # 5. Upload NEW files if provided
    # Extract files manually from form data to avoid 422 when empty string is sent
    form = await request.form()
    incoming_files = [
        v
        for k, v in form.multi_items()
        if k == "uploaded_files" and getattr(v, "filename", None)
    ]
    logger.info(f"Received {len(incoming_files)} NEW files for upload in PATCH")

    # Parse file_types list (for NEW files only)
    types_list = [t.strip() for t in file_types.split(",")] if file_types else []
    logger.info(f"NEW file types: {types_list}")

    if incoming_files:
        logger.info(f"Uploading {len(incoming_files)} NEW files to storage (PATCH)...")

        for idx, upload_file in enumerate(incoming_files):
            # Build storage key
            storage_key = _build_storage_key(current_user.user_id, upload_file.filename)

            # Upload to Supabase
            size_bytes = await upload_file_to_supabase(
                supabase,
                bucket=ANNOUNCEMENTS_BUCKET,
                storage_key=storage_key,
                upload=upload_file,
            )
            logger.info(f"Uploaded NEW file: {upload_file.filename} ({size_bytes} bytes) to {storage_key}")

            # Determine file type (default to Document)
            ftype_str = (
                types_list[idx]
                if idx < len(types_list)
                else "Document"
            )
            ftype = (
                FileTypeEnum.Template
                if ftype_str.lower() == "template"
                else FileTypeEnum.Document
            )

            logger.info(f"Saving NEW file to DB: {upload_file.filename} (type={ftype.value})")
            db.add(
                AnnouncementFile(
                    announcement_id=announcement_id,
                    file_name=upload_file.filename,
                    storage_key=storage_key,
                    mime_type=upload_file.content_type or "application/octet-stream",
                    size_bytes=size_bytes,
                    file_type=ftype,
                )
            )
    else:
        logger.info("No NEW files to upload (PATCH)")

    announcement.updated_at = datetime.utcnow()
    await db.commit()

    # 5. Re-fetch with relationships
    result = await db.execute(
        select(Announcement)
        .options(
            selectinload(Announcement.targets),
            selectinload(Announcement.files),
        )
        .where(Announcement.announcement_id == announcement_id)
    )
    announcement = result.scalars().first()

    return _build_response(announcement)


# ─── LIST ─────────────────────────────────────────────────────────────────────


@router.get("/submission-tasks", response_model=PaginatedSubmissionTasksResponse)
async def list_official_submission_tasks(
    search: Optional[str] = Query(None, description="Search by submission name"),
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Admin-only: Fetch all submission-request announcements created by admin.


    Returns paginated list of submission requests with:
    - Basic info (title, description, created date)
    - Target audience (Students, Supervisors, FYP1 Students, FYP2 Students, or Both)
    - Attached files (templates, documents)
    """
    if current_user.role != RoleEnum.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    # Base query: Select announcements that are submission requests created by admin
    query = (
        select(Announcement)
        .options(
            selectinload(Announcement.targets),
            selectinload(Announcement.files),
            selectinload(Announcement.creator),
        )
        .where(
            and_(
                Announcement.is_submission_request == True,
                Announcement.created_by_role == AnnouncementRoleEnum.admin,
            )
        )
    )

    filters = []

    # Search filter - search by announcement title or description
    if search:
        s = f"%{search}%"
        filters.append(
            or_(
                Announcement.title.ilike(s),
                Announcement.description.ilike(s),
            )
        )

    if filters:
        query = query.where(and_(*filters))

    # Count total matching announcements
    count_query = select(func.count(Announcement.announcement_id)).where(
        and_(
            Announcement.is_submission_request == True,
            Announcement.created_by_role == AnnouncementRoleEnum.admin,
        )
    )
    if filters:
        count_query = count_query.where(and_(*filters))

    total = (await db.execute(count_query)).scalar() or 0

    # Pagination
    offset = (page - 1) * per_page
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1

    query = (
        query.order_by(Announcement.created_at.desc()).offset(offset).limit(per_page)
    )
    result = await db.execute(query)
    announcements: List[Announcement] = result.scalars().all()

    # Build response
    tasks_out: List[SubmissionTaskInfo] = []

    for announcement in announcements:
        # Determine assigned_to based on targets
        assigned_to = _assign_to_label(announcement.targets)

        # Build attachments list from announcement files
        attachments = [
            AttachmentInfo(
                file_id=file.file_id,
                file_name=file.file_name,
                storage_key=file.storage_key,
                mime_type=file.mime_type,
                size_bytes=file.size_bytes,
                file_type=file.file_type.value,
                uploaded_at=file.uploaded_at,
            )
            for file in announcement.files
        ]

        tasks_out.append(
            SubmissionTaskInfo(
                submission_id=announcement.announcement_id,
                name=announcement.title,
                description=announcement.description,
                created_at=announcement.created_at,
                due_at=announcement.due_at,
                total_points=(
                    float(announcement.total_marks)
                    if announcement.total_marks
                    else None
                ),
                assigned_to=assigned_to,
                attachments=attachments,
            )
        )

    return PaginatedSubmissionTasksResponse(
        tasks=tasks_out,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )


@router.get(
    "/submission-tasks/{announcement_id}/submissions",
    response_model=GroupSubmissionsResponse,
)
async def get_submission_responses(
    announcement_id: UUID,
    search: Optional[str] = Query(None, description="Search by group name or FYP ID"),
    status_filter: Optional[str] = Query(
        None, description="Filter by status: submitted, missing, graded, returned"
    ),
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Admin-only: Get all group submissions (responses) for a specific submission request.

    Returns list of groups with their submission status:
    - Groups that have submitted
    - Groups that are missing submissions
    """
    if current_user.role != RoleEnum.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    # Verify announcement exists and is a submission request
    announcement_result = await db.execute(
        select(Announcement)
        .options(selectinload(Announcement.targets))
        .where(Announcement.announcement_id == announcement_id)
    )
    announcement = announcement_result.scalars().first()

    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")

    if not announcement.is_submission_request:
        raise HTTPException(
            status_code=400, detail="This announcement is not a submission request"
        )

    # Determine which groups should submit based on announcement targets
    target_group_ids: Set[UUID] = set()
    cycle_filters: Set[FYPCycleEnum] = set()
    fetch_all_groups = False

    for target in announcement.targets:
        role = target.target_role
        if role in (TargetRoleEnum.all_students, TargetRoleEnum.both):
            fetch_all_groups = True
            break
        if role == TargetRoleEnum.fyp1_students:
            cycle_filters.add(FYPCycleEnum.fyp1)
        elif role == TargetRoleEnum.fyp2_students:
            cycle_filters.add(FYPCycleEnum.fyp2)
        elif target.group_id:
            target_group_ids.add(target.group_id)

    # Build query for groups with their projects and submissions
    if fetch_all_groups:
        # Get all groups
        groups_query = (
            select(Group)
            .options(
                selectinload(Group.project),
            )
            .where(Group.project.has())  # Only groups with projects
        )
    else:
        # Get specific groups based on provided targets/cycles
        conditions = []
        if target_group_ids:
            conditions.append(Group.group_id.in_(list(target_group_ids)))
        if cycle_filters:
            conditions.append(Group.fyp_cycle.in_(list(cycle_filters)))

        if not conditions:
            # No targets specified, return empty list with pagination
            return GroupSubmissionsResponse(
                submissions=[],
                total=0,
                page=page,
                per_page=per_page,
                total_pages=1,
                has_next=False,
                has_prev=False,
            )

        groups_query = (
            select(Group)
            .options(
                selectinload(Group.project),
            )
            .where(
                and_(
                    or_(*conditions),
                    Group.project.has(),  # Only groups with projects
                )
            )
        )

    groups_result = await db.execute(groups_query)
    groups = groups_result.scalars().all()

    # Get all submissions for this announcement
    submissions_result = await db.execute(
        select(Submission).where(Submission.linked_announcement_id == announcement_id)
    )
    submissions_by_group = {
        sub.group_id: sub for sub in submissions_result.scalars().all()
    }

    # Build response
    group_submissions = []

    for group in groups:
        if not group.project:
            continue

        # Check if group has submitted
        submission = submissions_by_group.get(group.group_id)

        if submission:
            # Map submission status to frontend format
            status_map = {
                SubmissionStatusEnum.submitted: "Submitted",
                SubmissionStatusEnum.graded: "Graded",
                SubmissionStatusEnum.returned: "Returned",
                SubmissionStatusEnum.pending: "Pending",
                SubmissionStatusEnum.missing: "Missing",
            }
            status = status_map.get(submission.status, submission.status.value)
        else:
            status = "Missing"

        # Get project FYP ID and name
        fyp_id = group.project.fyp_id or f"P-{str(group.project.project_id)[:8]}"
        project_name = group.name or group.project.name

        group_submissions.append(
            GroupSubmissionStatus(
                group_id=group.group_id,
                submission_id=submission.submission_id if submission else None,
                fyp_id=fyp_id,
                project_name=project_name,
                status=status,
            )
        )

    # Apply filters
    filtered_submissions = group_submissions

    # Search filter
    if search:
        s = search.strip().lower()
        filtered_submissions = [
            sub
            for sub in filtered_submissions
            if s in sub.project_name.lower() or s in sub.fyp_id.lower()
        ]

    # Status filter
    if status_filter:
        status_lower = status_filter.strip().lower()
        filtered_submissions = [
            sub for sub in filtered_submissions if sub.status.lower() == status_lower
        ]

    # Pagination
    total = len(filtered_submissions)
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    offset = (page - 1) * per_page
    paginated_submissions = filtered_submissions[offset : offset + per_page]

    return GroupSubmissionsResponse(
        submissions=paginated_submissions,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )


# ─── EVALUATION ───────────────────────────────────────────────────────────────


@router.get(
    "/submissions/{submission_id}/evaluation",
    response_model=SubmissionEvaluationResponse,
    summary="Get submission details for evaluation",
)
async def get_submission_evaluation(
    submission_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Admin-only: Get full submission details for evaluation page.

    Returns:
    - All files for the submission
    - Submission title
    - Total marks from announcement
    - Supervisor's marks and feedback (read-only for admin)
    - Admin's marks and feedback (editable)
    """
    if current_user.role != RoleEnum.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    # Fetch submission with all related data
    result = await db.execute(
        select(Submission)
        .options(
            selectinload(Submission.files),
            selectinload(Submission.linked_announcement),
        )
        .where(Submission.submission_id == submission_id)
    )
    submission = result.scalars().first()

    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    # Get total marks from announcement if linked
    total_marks = None
    if submission.linked_announcement:
        total_marks = (
            float(submission.linked_announcement.total_marks)
            if submission.linked_announcement.total_marks
            else None
        )

    # Build file list
    files = [
        SubmissionFileInfo(
            fileId=f.file_id,
            fileName=f.file_name,
            storageKey=f.storage_key,
            mimeType=f.mime_type,
            sizeBytes=f.size_bytes,
            uploadedAt=f.uploaded_at,
        )
        for f in submission.files
    ]

    return SubmissionEvaluationResponse(
        submissionId=submission.submission_id,
        title=submission.title,
        totalMarks=total_marks,
        note=submission.note,
        adminMarks=float(submission.admin_marks) if submission.admin_marks else None,
        adminFeedback=submission.admin_feedback,
        adminGradedAt=submission.admin_graded_at,
        files=files,
        submittedAt=submission.submitted_at,
    )


@router.post(
    "/submissions/{submission_id}/evaluation",
    response_model=SubmissionEvaluationResponse,
    summary="Update admin grading for a submission",
)
async def update_admin_grading(
    submission_id: UUID,
    body: UpdateAdminGradingRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Admin-only: Update admin's marks and feedback for a submission.

    Only updates admin-specific fields:
    - admin_marks
    - admin_feedback
    - admin_graded_at (auto-set to current time)

    Supervisor fields remain read-only.
    """
    if current_user.role != RoleEnum.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    # Fetch submission
    result = await db.execute(
        select(Submission)
        .options(
            selectinload(Submission.files),
            selectinload(Submission.linked_announcement),
        )
        .where(Submission.submission_id == submission_id)
    )
    submission = result.scalars().first()

    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    # Update admin grading fields
    if body.adminMarks is not None:
        submission.admin_marks = body.adminMarks
    if body.adminFeedback is not None:
        submission.admin_feedback = body.adminFeedback

    # Set graded timestamp if marks are being updated
    if body.adminMarks is not None or body.adminFeedback is not None:
        submission.admin_graded_at = datetime.utcnow()

    # Update submission status to graded if it was submitted
    if submission.status == SubmissionStatusEnum.submitted:
        submission.status = SubmissionStatusEnum.graded

    await db.commit()
    await db.refresh(submission)

    # Get total marks from announcement
    total_marks = None
    if submission.linked_announcement:
        total_marks = (
            float(submission.linked_announcement.total_marks)
            if submission.linked_announcement.total_marks
            else None
        )

    # Build file list
    files = [
        SubmissionFileInfo(
            fileId=f.file_id,
            fileName=f.file_name,
            storageKey=f.storage_key,
            mimeType=f.mime_type,
            sizeBytes=f.size_bytes,
            uploadedAt=f.uploaded_at,
        )
        for f in submission.files
    ]

    return SubmissionEvaluationResponse(
        submissionId=submission.submission_id,
        title=submission.title,
        totalMarks=total_marks,
        note=submission.note,
        adminMarks=float(submission.admin_marks) if submission.admin_marks else None,
        adminFeedback=submission.admin_feedback,
        adminGradedAt=submission.admin_graded_at,
        files=files,
        submittedAt=submission.submitted_at,
    )


@router.get(
    "/submissions/{submission_id}/files/{file_id}/download",
    summary="Download or view a submission file",
)
async def download_submission_file(
    submission_id: UUID,
    file_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Admin-only: Download or view a submission file.
    """
    if current_user.role != RoleEnum.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    # Fetch file metadata and verify it belongs to the submission
    result = await db.execute(
        select(SubmissionFile).where(
            and_(
                SubmissionFile.file_id == file_id,
                SubmissionFile.submission_id == submission_id,
            )
        )
    )
    file_record = result.scalars().first()

    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    storage_key = _resolve_submission_storage_key(file_record.storage_key)

    # Download from storage
    try:
        file_content = supabase.storage.from_(SUBMISSION_FILES_BUCKET).download(storage_key)
    except Exception as e:
        raise HTTPException(
            status_code=404,
            detail=f"File not found or failed to download: {str(e)}",
        )

    temp_file = tempfile.NamedTemporaryFile(delete=False)
    temp_file.write(file_content)
    temp_file.flush()
    temp_path = temp_file.name
    temp_file.close()

    background = BackgroundTask(lambda path=temp_path: os.path.exists(path) and os.remove(path))

    media_type = _infer_mime(file_record.file_name, file_record.mime_type)

    return FileResponse(
        temp_path,
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{file_record.file_name}"'},
        background=background,
    )
