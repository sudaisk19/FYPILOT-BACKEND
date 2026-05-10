import logging
import mimetypes
import os
import re
import tempfile
from datetime import datetime
from typing import List, Optional
from urllib.parse import urlparse
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Query,
    Request,
    status,
)
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.auth.supabase_auth import get_current_user
from app.db import get_db, supabase
from app.models.announcement import (
    Announcement,
    AnnouncementFile,
    AnnouncementRoleEnum,
    AnnouncementTarget,
    FileTypeEnum,
)
from app.models.group import Group
from app.models.submission import (
    Submission,
    SubmissionStatusEnum,
    SubmissionTypeEnum,
)
from app.models.user import RoleEnum, User
from app.repositories.announcement_repository import announcement_repository
from app.repositories.group_repository import group_repository
from app.repositories.submission_repository import submission_repository
from app.schemas.submission_schema import (
    AttachmentInfo,
    FileOutput,
    GroupSubmissionsResponse,
    GroupSubmissionStatus,
    PaginatedSubmissionTasksResponse,
    SubmissionAnnouncementResponse,
    SubmissionFileInfo,
    SubmissionTaskInfo,
    SupervisorSubmissionEvaluationResponse,
)
from app.services.storage_service import (
    ANNOUNCEMENTS_BUCKET,
    SUBMISSION_FILES_BUCKET,
    delete_file_from_supabase,
    get_public_file_url,
    upload_file_to_supabase,
)

router = APIRouter(tags=["faculty-submissions"])
logger = logging.getLogger(__name__)


# ─── LOCAL SCHEMAS ────────────────────────────────────────────────────────────


class UpdateSupervisorGradingRequest(BaseModel):
    supervisorMarks: Optional[float] = None
    supervisorFeedback: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)


# ─── HELPERS ──────────────────────────────────────────────────────────────────


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


def _assign_to_label(
    targets: List[AnnouncementTarget], managed_groups: List[Group]
) -> str:
    """Convert announcement targets into a human-readable label or ID."""
    if not targets:
        return "None"

    target_group_ids = {t.group_id for t in targets if t.group_id}
    managed_group_ids = {g.group_id for g in managed_groups}

    # If all managed groups are targeted
    if managed_group_ids and target_group_ids.issuperset(managed_group_ids):
        # Checking superset in case managed groups changed over time, but generally == is safer if sync strictly
        # Let's say if it matches ALL currently managed groups
        if len(managed_group_ids) > 0 and len(target_group_ids) == len(
            managed_group_ids
        ):
            return "All Groups"

    # If a single group is targeted
    if len(target_group_ids) == 1:
        target_id = list(target_group_ids)[0]
        # Find the group object
        group = next((g for g in managed_groups if g.group_id == target_id), None)
        if group:
            if group.project and group.project.name:
                return group.project.name

            fyp_id = group.fyp_id or f"P-{str(group.group_id)[:8]}"
            return f"Group {fyp_id}"

        return str(target_id)

    return "Multiple Groups"  # Fallback


def _build_response(
    announcement: Announcement, managed_groups: List[Group]
) -> SubmissionAnnouncementResponse:
    """Build a uniform response from an Announcement ORM object."""
    return SubmissionAnnouncementResponse(
        id=announcement.announcement_id,
        title=announcement.title,
        description=announcement.description,
        dueDate=announcement.due_at,
        total_marks=(
            float(announcement.total_marks) if announcement.total_marks else None
        ),
        assignTo=_assign_to_label(announcement.targets, managed_groups),
        isSubmission=announcement.is_submission_request,
        files=[
            FileOutput(
                id=f.file_id,
                name=f.file_name,
                url=get_public_file_url(ANNOUNCEMENTS_BUCKET, f.storage_key),
                type=f.file_type.value,
                mimeType=f.mime_type,
                size=f.size_bytes,
            )
            for f in announcement.files
        ],
        createdAt=announcement.created_at,
        updatedAt=announcement.updated_at,
    )


async def _get_managed_groups(user_id: UUID, db: AsyncSession) -> List[Group]:
    """Fetch all groups managed by the supervisor."""
    return await group_repository.get_groups_by_supervisor(db, user_id)


async def _create_placeholder_submissions_for_groups(
    announcement: Announcement,
    group_ids: List[UUID],
    db: AsyncSession,
):
    """Pre-create pending submission rows for targeted student groups."""
    if not group_ids:
        return

    # Check existing submissions to avoid duplicates
    existing_group_ids = (
        await submission_repository.get_existing_group_ids_for_announcement(
            db, announcement.announcement_id, group_ids
        )
    )

    new_group_ids = [gid for gid in group_ids if gid not in existing_group_ids]

    if not new_group_ids:
        return

    submissions = [
        Submission(
            group_id=gid,
            created_by=announcement.created_by,
            title=announcement.title,
            note=None,
            type=SubmissionTypeEnum.official,
            status=SubmissionStatusEnum.pending,
            linked_announcement_id=announcement.announcement_id,
        )
        for gid in new_group_ids
    ]

    db.add_all(submissions)
    logger.info(
        "Created %d placeholder submission rows for announcement %s",
        len(submissions),
        announcement.announcement_id,
    )


# ─── FILE DOWNLOAD (ANNOUNCEMENT) ─────────────────────────────────────────────


@router.get(
    "/announcement-files/{file_id}/download",
    summary="Download or view an announcement file",
)
async def download_announcement_file(
    file_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Download or view an announcement file for supervisor.
    """
    if current_user.role != RoleEnum.faculty:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Faculty only"
        )

    # Active check
    if not current_user.faculty_profile or not current_user.faculty_profile.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your faculty account is inactive. Contact an administrator.",
        )

    # Check if faculty has supervisor privileges
    if not current_user.faculty_profile.is_supervisor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only faculty with supervisor privileges can access submission files",
        )

    # Fetch file metadata
    file_record = await announcement_repository.get_announcement_file(db, file_id)

    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    announcement = file_record.announcement
    # Minimal access check: Assuming if supervisor can see it, they can download.
    # Sticking to "created by me" for now for management,
    # But if they need to see others, this logic might need expansion.
    # Given the prefix "supervisors/submissions", it implies "My Submissions".
    if announcement.created_by != current_user.user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Download from storage
    try:
        file_content = supabase.storage.from_(ANNOUNCEMENTS_BUCKET).download(
            file_record.storage_key
        )
    except Exception as e:
        raise HTTPException(
            status_code=404, detail=f"File not found or failed to download: {str(e)}"
        )

    # Return as streaming response
    return StreamingResponse(
        iter([file_content]),
        media_type=file_record.mime_type or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{file_record.file_name}"'},
    )


# ─── CREATE TASK ──────────────────────────────────────────────────────────────


@router.post(
    "/submission-create",
    response_model=SubmissionAnnouncementResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a submission task for managed groups",
)
async def create_supervisor_submission_task(
    request: Request,
    title: str = Form(..., description="Details of the submission task"),
    dueDate: str = Form(..., description="Due date in ISO format"),
    group_id: str = Form(
        ..., description="Target Group ID or 'all' to assign task to all managed groups"
    ),
    description: Optional[str] = Form(None, description="Description of the task"),
    total_marks: Optional[float] = Form(
        None, description="Total marks for the submission"
    ),
    file_types: Optional[str] = Form(
        None,
        description="Comma-separated file types for each uploaded file",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Supervisor: Create a new submission request for checking/grading."""
    if current_user.role != RoleEnum.faculty:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Faculty only"
        )

    # Active check
    if not current_user.faculty_profile or not current_user.faculty_profile.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your faculty account is inactive. Contact an administrator.",
        )

    # Check if faculty has supervisor privileges
    if not current_user.faculty_profile.is_supervisor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only faculty with supervisor privileges can create submission tasks",
        )

    # Validate Due Date
    try:
        due_date = datetime.fromisoformat(dueDate.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid dueDate format. Use ISO format.",
        )

    # Resolve Groups
    managed_groups = await _get_managed_groups(current_user.user_id, db)
    if not managed_groups:
        raise HTTPException(
            status_code=404, detail="No groups found for this supervisor."
        )

    target_group_ids: List[UUID] = []
    if group_id == "all":
        target_group_ids = [g.group_id for g in managed_groups]
    else:
        try:
            gid = UUID(group_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid group_id format.")

        # Verify ownership
        matched = [g for g in managed_groups if g.group_id == gid]
        if not matched:
            raise HTTPException(status_code=403, detail="You do not manage this group.")
        target_group_ids = [gid]

    # 1. Create Announcement
    announcement = Announcement(
        created_by=current_user.user_id,
        created_by_role=AnnouncementRoleEnum.supervisor,
        title=title,
        description=description,
        is_submission_request=True,
        due_at=due_date,
        total_marks=total_marks,
    )
    db.add(announcement)
    await db.flush()

    # 2. Create Targets
    for gid in target_group_ids:
        db.add(
            AnnouncementTarget(
                announcement_id=announcement.announcement_id,
                group_id=gid,
                target_role=None,
            )
        )

    # 3. Upload Files
    form = await request.form()
    incoming_files = [
        v
        for k, v in form.multi_items()
        if k == "uploaded_files" and getattr(v, "filename", None)
    ]

    types_list = [t.strip() for t in file_types.split(",")] if file_types else []

    if incoming_files:
        for idx, upload_file in enumerate(incoming_files):
            storage_key = _build_storage_key(current_user.user_id, upload_file.filename)
            size_bytes = await upload_file_to_supabase(
                supabase,
                bucket=ANNOUNCEMENTS_BUCKET,
                storage_key=storage_key,
                upload=upload_file,
            )

            ftype_str = types_list[idx] if idx < len(types_list) else "Document"
            if ftype_str.lower() == "template":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only admins can upload template files",
                )
            ftype = FileTypeEnum.Document

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

    # 4. Create Placeholders
    await _create_placeholder_submissions_for_groups(
        announcement=announcement,
        group_ids=target_group_ids,
        db=db,
    )

    await db.commit()

    # Re-fetch
    announcement = await announcement_repository.get_by_id(
        db, announcement.announcement_id
    )

    return _build_response(announcement, managed_groups)


# ─── READ ONE TASK ────────────────────────────────────────────────────────────


@router.get(
    "/submission-details/{announcement_id}",
    response_model=SubmissionAnnouncementResponse,
    summary="Get a single submission task",
)
async def get_supervisor_submission_task(
    announcement_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Supervisor: Get details of a specific submission task."""
    if current_user.role != RoleEnum.faculty:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Faculty only"
        )

    # Active check
    if not current_user.faculty_profile or not current_user.faculty_profile.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your faculty account is inactive. Contact an administrator.",
        )

    # Check if faculty has supervisor privileges
    if not current_user.faculty_profile.is_supervisor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only faculty with supervisor privileges can view submission tasks",
        )

    announcement = await announcement_repository.get_by_id(db, announcement_id)

    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")

    if announcement.created_by != current_user.user_id:
        raise HTTPException(status_code=403, detail="You did not create this task.")

    managed_groups = await _get_managed_groups(current_user.user_id, db)
    return _build_response(announcement, managed_groups)


# ─── UPDATE TASK ──────────────────────────────────────────────────────────────


@router.patch(
    "/submission-update/{announcement_id}",
    response_model=SubmissionAnnouncementResponse,
    summary="Edit a submission task",
)
async def edit_supervisor_submission_task(
    request: Request,
    announcement_id: UUID,
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    group_id: Optional[str] = Form(None, description="Update target group(s)"),
    dueDate: Optional[str] = Form(None),
    total_marks: Optional[str] = Form(None),
    keep_file_ids: Optional[str] = Form(None),
    file_types: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Supervisor: Update an existing submission task."""
    if current_user.role != RoleEnum.faculty:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Faculty only"
        )

    # Active check
    if not current_user.faculty_profile or not current_user.faculty_profile.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your faculty account is inactive. Contact an administrator.",
        )

    # Check if faculty has supervisor privileges
    if not current_user.faculty_profile.is_supervisor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only faculty with supervisor privileges can update submission tasks",
        )

    # Fetch Announcement
    announcement = await announcement_repository.get_by_id(db, announcement_id)

    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")

    if announcement.created_by != current_user.user_id:
        raise HTTPException(status_code=403, detail="You did not create this task.")

    # Parse Fields
    title = title.strip() if title and title.strip() else None
    description = description.strip() if description and description.strip() else None

    # Update Basic Fields
    if title:
        announcement.title = title
    if description:
        announcement.description = description

    if dueDate:
        try:
            announcement.due_at = datetime.fromisoformat(dueDate.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid dueDate format.")

    if total_marks:
        try:
            announcement.total_marks = float(total_marks)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid total_marks value.")

    # Update Targets
    managed_groups = await _get_managed_groups(current_user.user_id, db)

    if group_id:
        # Delete old targets
        await db.execute(
            delete(AnnouncementTarget).where(
                AnnouncementTarget.announcement_id == announcement_id
            )
        )
        # Determine new target IDs
        new_target_ids = []
        if group_id == "all":
            new_target_ids = [g.group_id for g in managed_groups]
        else:
            try:
                gid = UUID(group_id)
                matched = [g for g in managed_groups if g.group_id == gid]
                if not matched:
                    raise HTTPException(
                        status_code=403, detail="You do not manage this group."
                    )
                new_target_ids = [gid]
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid group_id format.")

        # Add new targets
        for gid in new_target_ids:
            db.add(
                AnnouncementTarget(
                    announcement_id=announcement_id,
                    group_id=gid,
                    target_role=None,
                )
            )

        # Add placeholders for new targets (safe due to check in helper)
        await _create_placeholder_submissions_for_groups(
            announcement=announcement,
            group_ids=new_target_ids,
            db=db,
        )

    # Handle Files (Sync)
    if keep_file_ids is not None:
        try:
            keep_ids = {
                UUID(fid.strip()) for fid in keep_file_ids.split(",") if fid.strip()
            }
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid UUID in keep_file_ids")

        for existing_file in list(announcement.files):
            if existing_file.file_id not in keep_ids:
                try:
                    await delete_file_from_supabase(
                        supabase,
                        bucket=ANNOUNCEMENTS_BUCKET,
                        storage_key=existing_file.storage_key,
                    )
                except Exception as e:
                    logger.warning(f"Delete file error: {e}")
                await db.delete(existing_file)

    # Handle New Files
    form = await request.form()
    incoming_files = [
        v
        for k, v in form.multi_items()
        if k == "uploaded_files" and getattr(v, "filename", None)
    ]

    types_list = [t.strip() for t in file_types.split(",")] if file_types else []

    if incoming_files:
        for idx, upload_file in enumerate(incoming_files):
            storage_key = _build_storage_key(current_user.user_id, upload_file.filename)
            size_bytes = await upload_file_to_supabase(
                supabase,
                bucket=ANNOUNCEMENTS_BUCKET,
                storage_key=storage_key,
                upload=upload_file,
            )

            ftype_str = types_list[idx] if idx < len(types_list) else "Document"
            if ftype_str.lower() == "template":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only admins can upload template files",
                )
            ftype = FileTypeEnum.Document

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

    announcement.updated_at = datetime.utcnow()
    await db.commit()

    # Re-fetch
    announcement = await announcement_repository.get_by_id(db, announcement_id)

    return _build_response(announcement, managed_groups)


# ─── LIST TASKS ───────────────────────────────────────────────────────────────


@router.get("/submission-list", response_model=PaginatedSubmissionTasksResponse)
async def list_supervisor_submission_tasks(
    search: Optional[str] = Query(None, description="Search by title"),
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Supervisor: Fetch all submission tasks created by me."""
    if current_user.role != RoleEnum.faculty:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Faculty only"
        )

    # Active check
    if not current_user.faculty_profile or not current_user.faculty_profile.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your faculty account is inactive. Contact an administrator.",
        )

    # Check if faculty has supervisor privileges
    if not current_user.faculty_profile.is_supervisor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only faculty with supervisor privileges can view submission tasks",
        )

    # Query
    announcements, total = (
        await announcement_repository.list_supervisor_submission_tasks(
            db=db,
            supervisor_id=current_user.user_id,
            page=page,
            per_page=per_page,
            search=search,
        )
    )

    total_pages = (total + per_page - 1) // per_page if total > 0 else 1

    # Helper needed for context
    managed_groups = await _get_managed_groups(current_user.user_id, db)

    items = []
    for a in announcements:
        assign_to = _assign_to_label(a.targets, managed_groups)

        attachments = [
            AttachmentInfo(
                file_id=f.file_id,
                file_name=f.file_name,
                storage_key=f.storage_key,
                mime_type=f.mime_type,
                size_bytes=f.size_bytes,
                file_type=f.file_type.value,
                uploaded_at=f.uploaded_at,
            )
            for f in a.files
        ]

        items.append(
            SubmissionTaskInfo(
                submission_id=a.announcement_id,
                name=a.title,
                description=a.description,
                created_at=a.created_at,
                due_at=a.due_at,
                total_points=(float(a.total_marks) if a.total_marks else None),
                assigned_to=assign_to,
                attachments=attachments,
            )
        )

    return PaginatedSubmissionTasksResponse(
        tasks=items,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )


# ─── LIST STUDENT SUBMISSIONS ─────────────────────────────────────────────────


@router.get(
    "/submission-responses/{announcement_id}",
    response_model=GroupSubmissionsResponse,
)
async def get_submission_responses(
    announcement_id: UUID,
    search: Optional[str] = Query(None, description="Search by project name or FYP ID"),
    status_filter: Optional[str] = Query(
        None, description="Filter by status: submitted, missing, graded, pending"
    ),
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Supervisor: Get all group submissions (responses) for a specific task.
    """
    if current_user.role != RoleEnum.faculty:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Faculty only"
        )

    # Active check
    if not current_user.faculty_profile or not current_user.faculty_profile.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your faculty account is inactive. Contact an administrator.",
        )

    # Check if faculty has supervisor privileges
    if not current_user.faculty_profile.is_supervisor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only faculty with supervisor privileges can view group submissions",
        )

    # Data Fetch: Announcement
    announcement = await announcement_repository.get_by_id(db, announcement_id)

    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")

    if announcement.created_by != current_user.user_id:
        raise HTTPException(status_code=403, detail="You did not create this task.")

    # Get target groups from AnnouncementTargets
    target_group_ids = [t.group_id for t in announcement.targets if t.group_id]

    if not target_group_ids:
        # No targets?
        return GroupSubmissionsResponse(
            submissions=[],
            total=0,
            page=page,
            per_page=per_page,
            total_pages=1,
            has_next=False,
            has_prev=False,
        )

    # Get Groups details
    groups = await group_repository.get_groups_with_project_by_ids(db, target_group_ids)

    # Get Submissions
    submissions_list = await submission_repository.get_submissions_by_announcement(
        db, announcement_id
    )
    submissions_by_group = {sub.group_id: sub for sub in submissions_list}

    # Build Response List
    group_submissions = []

    status_map = {
        SubmissionStatusEnum.submitted: "Submitted",
        SubmissionStatusEnum.graded: "Graded",
        SubmissionStatusEnum.pending: "Pending",
        SubmissionStatusEnum.missing: "Missing",
    }

    for group in groups:
        submission = submissions_by_group.get(group.group_id)
        if submission:
            st_val = status_map.get(submission.status, submission.status.value)
        else:
            st_val = "Missing"

        fyp_id = group.project.fyp_id or f"P-{str(group.project.project_id)[:8]}"
        project_name = group.project.name if group.project else "Unknown Project"

        group_submissions.append(
            GroupSubmissionStatus(
                group_id=group.group_id,
                submission_id=submission.submission_id if submission else None,
                fyp_id=fyp_id,
                project_name=project_name,
                status=st_val,
            )
        )

    # Filtering (In-Memory due to composite nature of display fields vs DB fields)
    filtered = group_submissions
    if search:
        s = search.strip().lower()
        filtered = [
            x for x in filtered if s in x.project_name.lower() or s in x.fyp_id.lower()
        ]

    if status_filter:
        s_low = status_filter.strip().lower()
        filtered = [x for x in filtered if x.status.lower() == s_low]

    # Pagination
    total = len(filtered)
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    offset = (page - 1) * per_page
    paginated = filtered[offset : offset + per_page]

    return GroupSubmissionsResponse(
        submissions=paginated,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )


# ─── EVALUATION (GET) ─────────────────────────────────────────────────────────


@router.get(
    "/submission-evaluation/{submission_id}",
    response_model=SupervisorSubmissionEvaluationResponse,
    summary="Get submission details for evaluation",
)
async def get_submission_evaluation(
    submission_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Supervisor: Get full submission details for grading."""
    if current_user.role != RoleEnum.faculty:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Faculty only"
        )

    # Active check
    if not current_user.faculty_profile or not current_user.faculty_profile.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your faculty account is inactive. Contact an administrator.",
        )

    # Check if faculty has supervisor privileges
    if not current_user.faculty_profile.is_supervisor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only faculty with supervisor privileges can evaluate submissions",
        )

    submission = await submission_repository.get_evaluation_details(db, submission_id)

    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    # Access Check: Does supervisor manage this group?
    # Simple check: User should be supervisor or cosupervisor of group
    group = submission.group
    is_sup = group.supervisor_id == current_user.user_id
    is_cosup = group.cosupervisor_ids and current_user.user_id in group.cosupervisor_ids

    if not (is_sup or is_cosup):
        raise HTTPException(status_code=403, detail="You do not supervise this group.")

    total_marks = None
    if submission.linked_announcement:
        total_marks = (
            float(submission.linked_announcement.total_marks)
            if submission.linked_announcement.total_marks
            else None
        )

    files = [
        SubmissionFileInfo(
            fileId=f.file_id,
            fileName=f.file_name,
            url=get_public_file_url(SUBMISSION_FILES_BUCKET, f.storage_key),
            mimeType=f.mime_type,
            sizeBytes=f.size_bytes,
            supervisorComment=f.supervisor_comment,
            uploadedAt=f.uploaded_at,
        )
        for f in submission.files
    ]

    # Return only supervisor marks (admin marks hidden from supervisor)
    return SupervisorSubmissionEvaluationResponse(
        submissionId=submission.submission_id,
        title=submission.title,
        totalMarks=total_marks,
        note=submission.note,
        supervisorMarks=(
            float(submission.supervisor_marks) if submission.supervisor_marks else None
        ),
        supervisorFeedback=submission.supervisor_feedback,
        supervisorGradedAt=submission.supervisor_graded_at,
        files=files,
        submittedAt=submission.submitted_at,
    )


# ─── EVALUATION (POST) ────────────────────────────────────────────────────────


@router.post(
    "/submission-evaluation-update/{submission_id}",
    response_model=SupervisorSubmissionEvaluationResponse,
    summary="Update supervisor grading",
)
async def update_supervisor_grading(
    submission_id: UUID,
    body: UpdateSupervisorGradingRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Supervisor: Update marks and feedback.
    """
    if current_user.role != RoleEnum.faculty:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Faculty only"
        )

    # Active check
    if not current_user.faculty_profile or not current_user.faculty_profile.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your faculty account is inactive. Contact an administrator.",
        )

    # Check if faculty has supervisor privileges
    if not current_user.faculty_profile.is_supervisor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only faculty with supervisor privileges can update grading",
        )

    submission = await submission_repository.get_evaluation_details(db, submission_id)

    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    # Access Check
    group = submission.group
    is_sup = group.supervisor_id == current_user.user_id
    is_cosup = group.cosupervisor_ids and current_user.user_id in group.cosupervisor_ids
    if not (is_sup or is_cosup):
        raise HTTPException(status_code=403, detail="Access denied.")

    # Update Fields
    if body.supervisorMarks is not None:
        submission.supervisor_marks = body.supervisorMarks
    if body.supervisorFeedback is not None:
        submission.supervisor_feedback = body.supervisorFeedback

    if body.supervisorMarks is not None or body.supervisorFeedback is not None:
        submission.supervisor_graded_at = datetime.utcnow()
        if submission.status == SubmissionStatusEnum.submitted:
            submission.status = SubmissionStatusEnum.graded

    await db.commit()
    await db.refresh(submission)

    total_marks = None
    if submission.linked_announcement:
        total_marks = (
            float(submission.linked_announcement.total_marks)
            if submission.linked_announcement.total_marks
            else None
        )

    files = [
        SubmissionFileInfo(
            fileId=f.file_id,
            fileName=f.file_name,
            url=get_public_file_url(SUBMISSION_FILES_BUCKET, f.storage_key),
            mimeType=f.mime_type,
            sizeBytes=f.size_bytes,
            supervisorComment=f.supervisor_comment,
            uploadedAt=f.uploaded_at,
        )
        for f in submission.files
    ]

    # Return only supervisor marks (admin marks hidden from supervisor)
    return SupervisorSubmissionEvaluationResponse(
        submissionId=submission.submission_id,
        title=submission.title,
        totalMarks=total_marks,
        note=submission.note,
        supervisorMarks=(
            float(submission.supervisor_marks) if submission.supervisor_marks else None
        ),
        supervisorFeedback=submission.supervisor_feedback,
        supervisorGradedAt=submission.supervisor_graded_at,
        files=files,
        submittedAt=submission.submitted_at,
    )


# ─── SUBMISSION FILE DOWNLOAD ─────────────────────────────────────────────────


@router.get(
    "/submission-files/{submission_id}/{file_id}/download",
    summary="Download or view a submission file",
)
async def download_submission_file(
    submission_id: UUID,
    file_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Supervisor: Download or view a submission file from a student.
    """
    if current_user.role != RoleEnum.faculty:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Faculty only"
        )

    # Active check
    if not current_user.faculty_profile or not current_user.faculty_profile.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your faculty account is inactive. Contact an administrator.",
        )

    # Check if faculty has supervisor privileges
    if not current_user.faculty_profile.is_supervisor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only faculty with supervisor privileges can access submission files",
        )

    # Fetch file record and check access
    file_record = await submission_repository.get_submission_file_details(
        db, submission_id, file_id
    )

    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    submission = file_record.submission
    group = submission.group
    is_sup = group.supervisor_id == current_user.user_id
    is_cosup = group.cosupervisor_ids and current_user.user_id in group.cosupervisor_ids
    if not (is_sup or is_cosup):
        raise HTTPException(status_code=403, detail="Access denied.")

    storage_key = _resolve_submission_storage_key(file_record.storage_key)

    try:
        file_content = supabase.storage.from_(SUBMISSION_FILES_BUCKET).download(
            storage_key
        )
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

    background = BackgroundTask(
        lambda path=temp_path: os.path.exists(path) and os.remove(path)
    )
    media_type = _infer_mime(file_record.file_name, file_record.mime_type)

    return FileResponse(
        temp_path,
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{file_record.file_name}"'},
        background=background,
    )
