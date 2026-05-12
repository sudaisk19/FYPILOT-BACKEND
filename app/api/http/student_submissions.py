# app/api/http/student_submissions.py
"""
Student Submissions API — Official Tab

Endpoints (read + student-upload only, no grading):
  GET    /students/submissions/official                          — paginated list
  GET    /students/submissions/official/{submission_id}          — full detail
  PATCH  /students/submissions/official/{submission_id}          — submit / re-submit
  DELETE /students/submissions/official/{submission_id}/files/{file_id} — remove one file
"""

import os
import re
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase_auth import get_current_user
from app.db import get_db, supabase
from app.models.announcement import AnnouncementRoleEnum, FileTypeEnum
from app.models.submission import SubmissionStatusEnum
from app.models.user import RoleEnum, User
from app.repositories.submission_repository import submission_repository
from app.schemas.submission_schema import (
    PaginatedStudentOfficialSubmissions,
    PaginatedStudentUnofficialSubmissions,
    StudentAnnouncementTemplateFile,
    StudentOfficialSubmissionDetail,
    StudentOfficialSubmissionListItem,
    StudentSubmissionFileResponse,
    StudentUnofficialSubmissionDetail,
)
from app.services.storage_service import (
    ANNOUNCEMENTS_BUCKET,
    delete_file_from_supabase,
    get_public_file_url,
    upload_file_to_supabase,
)

router = APIRouter(tags=["student-submissions"])

SUBMISSION_FILES_BUCKET = "submission_files"


# ─── HELPERS ──────────────────────────────────────────────────────────────────


def _safe_filename(name: str) -> str:
    base, ext = os.path.splitext(name)
    safe_base = re.sub(r"[^A-Za-z0-9._-]", "_", base or "file")
    safe_ext = re.sub(r"[^A-Za-z0-9._-]", "_", ext)
    cleaned = f"{safe_base}{safe_ext}" if safe_ext else safe_base
    return cleaned or "file"


def _build_storage_key(user_id: UUID, filename: str) -> str:
    return f"{uuid4()}_{_safe_filename(filename)}"


# ─── GET LIST ─────────────────────────────────────────────────────────────────


@router.get("/official", response_model=PaginatedStudentOfficialSubmissions)
async def list_official_submissions(
    page: int = Query(1, ge=1, description="Page number starting from 1"),
    per_page: int = Query(10, ge=1, le=50, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Student: List all official submissions for my group."""
    if current_user.role != RoleEnum.student:
        raise HTTPException(status_code=403, detail="Student only")

    group = await submission_repository.get_student_group(db, current_user.user_id)
    if not group:
        return PaginatedStudentOfficialSubmissions(
            submissions=[],
            total_items=0,
            total_pages=1,
            current_page=page,
            per_page=per_page,
        )

    submissions, total_items = await submission_repository.list_official_for_student(
        db,
        group_id=group.group_id,
        page=page,
        per_page=per_page,
    )

    total_pages = (total_items + per_page - 1) // per_page if total_items > 0 else 1

    items = [
        StudentOfficialSubmissionListItem(
            submission_id=s.submission_id,
            title=s.title,
            status=s.status,
            due_date=s.linked_announcement.due_at if s.linked_announcement else None,
            total_marks=(
                float(s.linked_announcement.total_marks)
                if s.linked_announcement and s.linked_announcement.total_marks
                else None
            ),
            file_count=len(s.files),
            created_by_role=(
                AnnouncementRoleEnum.normalize(s.linked_announcement.created_by_role)
                if s.linked_announcement
                else None
            ),
        )
        for s in submissions
    ]

    return PaginatedStudentOfficialSubmissions(
        submissions=items,
        total_items=total_items,
        total_pages=total_pages,
        current_page=page,
        per_page=per_page,
    )


# ─── GET BY ID ────────────────────────────────────────────────────────────────


@router.get("/official/{submission_id}", response_model=StudentOfficialSubmissionDetail)
async def get_official_submission(
    submission_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Student: Get full details of one official submission (includes files + feedback)."""
    if current_user.role != RoleEnum.student:
        raise HTTPException(status_code=403, detail="Student only")

    group = await submission_repository.get_student_group(db, current_user.user_id)
    if not group:
        raise HTTPException(status_code=404, detail="You are not part of any group")

    submission = await submission_repository.get_official_by_id_for_student(
        db,
        submission_id=submission_id,
        group_id=group.group_id,
    )
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    announcement = submission.linked_announcement

    # Template files — files attached to the original announcement (e.g. submission templates)
    template_files = []
    if announcement and announcement.files:
        template_files = [
            StudentAnnouncementTemplateFile(
                file_id=f.file_id,
                file_name=f.file_name,
                url=get_public_file_url(ANNOUNCEMENTS_BUCKET, f.storage_key),
                storage_key=f.storage_key,
                mime_type=f.mime_type,
                size_bytes=f.size_bytes,
            )
            for f in announcement.files
            if f.file_type == FileTypeEnum.Template
        ]

    # Student-uploaded files
    uploaded_files = []
    for f in submission.files:
        url = None
        if f.storage_key:
            try:
                url = supabase.storage.from_(SUBMISSION_FILES_BUCKET).get_public_url(
                    f.storage_key
                )
            except Exception:
                pass

        uploaded_files.append(
            StudentSubmissionFileResponse(
                file_id=f.file_id,
                file_name=f.file_name,
                url=url,
                storage_key=f.storage_key,
                mime_type=f.mime_type,
                size_bytes=f.size_bytes,
                uploaded_at=f.uploaded_at,
            )
        )

    # Full announcement details for the new field
    from app.schemas.student_announcement_schema import (
        StudentAnnouncementFileResponse,
        StudentAnnouncementResponse,
    )

    announcement_response = None
    if announcement:
        announcement_response = StudentAnnouncementResponse(
            announcement_id=announcement.announcement_id,
            title=announcement.title,
            description=announcement.description,
            supervisor_name=None,  # Populate if available
            created_at=announcement.created_at,
            updated_at=announcement.updated_at,
            files=[
                StudentAnnouncementFileResponse(
                    file_id=f.file_id,
                    file_name=f.file_name,
                    url=get_public_file_url(ANNOUNCEMENTS_BUCKET, f.storage_key),
                    storage_key=f.storage_key,
                    file_type=f.file_type,
                    mime_type=f.mime_type,
                    size_bytes=f.size_bytes,
                )
                for f in announcement.files
            ],
        )

    return StudentOfficialSubmissionDetail(
        submission_id=submission.submission_id,
        title=submission.title,
        note=submission.note,
        status=submission.status,
        isLate=bool(
            announcement
            and announcement.due_at
            and submission.submitted_at
            and submission.submitted_at > announcement.due_at
        ),
        submitted_at=submission.submitted_at,
        updated_at=submission.updated_at,
        due_date=announcement.due_at if announcement else None,
        total_marks=(
            float(announcement.total_marks)
            if announcement and announcement.total_marks
            else None
        ),
        announcement_description=announcement.description if announcement else None,
        template_files=template_files,
        supervisor_feedback=submission.supervisor_feedback,
        admin_feedback=submission.admin_feedback,
        files=uploaded_files,
        announcement=announcement_response,
    )


# ─── PATCH (SUBMIT / RE-SUBMIT) ───────────────────────────────────────────────


@router.patch(
    "/official/{submission_id}", response_model=StudentOfficialSubmissionDetail
)
async def submit_official_submission(
    submission_id: UUID,
    note: Optional[str] = Form(
        None, description="Optional note/comment for the submission"
    ),
    keep_file_ids: Optional[str] = Form(
        None,
        description=(
            "Comma-separated file_ids of EXISTING files to keep. "
            "Any existing file NOT listed here will be removed. "
            "Omit this field entirely to keep all existing files."
        ),
    ),
    files: List[UploadFile] = File(
        default=[],
        description="New files to upload and attach to this submission",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Student: Submit or re-submit work for an official submission.

    How it works:
    - Upload your files via the 'files' field (multipart)
    - Optionally pass keep_file_ids to control which previously uploaded files to keep
    - Sets submission status → submitted
    """
    if current_user.role != RoleEnum.student:
        raise HTTPException(status_code=403, detail="Student only")

    group = await submission_repository.get_student_group(db, current_user.user_id)
    if not group:
        raise HTTPException(status_code=404, detail="You are not part of any group")

    submission = await submission_repository.get_official_by_id_for_student(
        db,
        submission_id=submission_id,
        group_id=group.group_id,
    )
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    # Update note
    if note is not None:
        submission.note = note.strip() or None

    # Remove files not in keep_file_ids (if the field was provided)
    if keep_file_ids is not None:
        try:
            keep_ids = {
                UUID(fid.strip()) for fid in keep_file_ids.split(",") if fid.strip()
            }
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid UUID in keep_file_ids")

        for existing_file in list(submission.files):
            if existing_file.file_id not in keep_ids:
                try:
                    await delete_file_from_supabase(
                        supabase,
                        bucket=SUBMISSION_FILES_BUCKET,
                        storage_key=existing_file.storage_key,
                    )
                except Exception:
                    pass
                await db.delete(existing_file)

    # Upload new files
    from app.models.submission import SubmissionFile

    for upload in files:
        if not upload.filename:
            continue
        storage_key = _build_storage_key(current_user.user_id, upload.filename)
        size_bytes = await upload_file_to_supabase(
            supabase,
            bucket=SUBMISSION_FILES_BUCKET,
            storage_key=storage_key,
            upload=upload,
        )
        db.add(
            SubmissionFile(
                submission_id=submission_id,
                file_name=upload.filename,
                storage_key=storage_key,
                mime_type=upload.content_type or "application/octet-stream",
                size_bytes=size_bytes,
            )
        )

    # Mark as submitted
    submission.status = SubmissionStatusEnum.submitted
    submission.submitted_at = datetime.now(timezone.utc)

    await db.commit()

    # Re-fetch with updated state
    submission = await submission_repository.get_official_by_id_for_student(
        db,
        submission_id=submission_id,
        group_id=group.group_id,
    )

    announcement = submission.linked_announcement

    template_files = [
        StudentAnnouncementTemplateFile(
            file_id=f.file_id,
            file_name=f.file_name,
            url=get_public_file_url(ANNOUNCEMENTS_BUCKET, f.storage_key),
            storage_key=f.storage_key,
            mime_type=f.mime_type,
            size_bytes=f.size_bytes,
        )
        for f in (announcement.files if announcement and announcement.files else [])
        if f.file_type == FileTypeEnum.Template
    ]

    uploaded_files = []
    for f in submission.files:
        url = None
        if f.storage_key:
            try:
                url = supabase.storage.from_(SUBMISSION_FILES_BUCKET).get_public_url(
                    f.storage_key
                )
            except Exception:
                pass

        uploaded_files.append(
            StudentSubmissionFileResponse(
                file_id=f.file_id,
                file_name=f.file_name,
                url=url,
                storage_key=f.storage_key,
                mime_type=f.mime_type,
                size_bytes=f.size_bytes,
                uploaded_at=f.uploaded_at,
            )
        )

    return StudentOfficialSubmissionDetail(
        submission_id=submission.submission_id,
        title=submission.title,
        note=submission.note,
        status=submission.status,
        isLate=bool(
            announcement
            and announcement.due_at
            and submission.submitted_at
            and submission.submitted_at > announcement.due_at
        ),
        submitted_at=submission.submitted_at,
        updated_at=submission.updated_at,
        due_date=announcement.due_at if announcement else None,
        total_marks=(
            float(announcement.total_marks)
            if announcement and announcement.total_marks
            else None
        ),
        announcement_description=announcement.description if announcement else None,
        template_files=template_files,
        supervisor_feedback=submission.supervisor_feedback,
        admin_feedback=submission.admin_feedback,
        files=uploaded_files,
    )


# ─── UNOFFICIAL SUBMISSIONS: LIST ─────────────────────────────────────────────


@router.get("/unofficial", response_model=PaginatedStudentUnofficialSubmissions)
async def list_unofficial_submissions(
    page: int = Query(1, ge=1, description="Page number starting from 1"),
    per_page: int = Query(10, ge=1, le=50, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Student: List all unofficial submissions created by my group."""
    if current_user.role != RoleEnum.student:
        raise HTTPException(status_code=403, detail="Student only")

    group = await submission_repository.get_student_group(db, current_user.user_id)
    if not group:
        return PaginatedStudentUnofficialSubmissions(
            submissions=[],
            total_items=0,
            total_pages=1,
            current_page=page,
            per_page=per_page,
        )

    submissions, total_items = await submission_repository.list_unofficial_for_student(
        db,
        group_id=group.group_id,
        page=page,
        per_page=per_page,
    )

    total_pages = (total_items + per_page - 1) // per_page if total_items > 0 else 1

    from app.schemas.submission_schema import StudentUnofficialSubmissionListItem

    items = [
        StudentUnofficialSubmissionListItem(
            submission_id=s.submission_id,
            title=s.title,
            status=s.status,
            file_count=len(s.files),
            submitted_at=s.submitted_at or s.updated_at,
        )
        for s in submissions
    ]

    from app.schemas.submission_schema import PaginatedStudentUnofficialSubmissions

    return PaginatedStudentUnofficialSubmissions(
        submissions=items,
        total_items=total_items,
        total_pages=total_pages,
        current_page=page,
        per_page=per_page,
    )


# ─── UNOFFICIAL SUBMISSIONS: GET DETAIL ───────────────────────────────────────


@router.get(
    "/unofficial/{submission_id}", response_model=StudentUnofficialSubmissionDetail
)
async def get_unofficial_submission(
    submission_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Student: View details of an unofficial submission."""
    if current_user.role != RoleEnum.student:
        raise HTTPException(status_code=403, detail="Student only")

    group = await submission_repository.get_student_group(db, current_user.user_id)
    if not group:
        raise HTTPException(status_code=404, detail="You are not part of any group")

    submission = await submission_repository.get_unofficial_by_id_for_student(
        db,
        submission_id=submission_id,
        group_id=group.group_id,
    )
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    from app.schemas.submission_schema import StudentUnofficialSubmissionDetail

    announcement = submission.linked_announcement

    uploaded_files = []
    for f in submission.files:
        url = None
        if f.storage_key:
            try:
                url = supabase.storage.from_(SUBMISSION_FILES_BUCKET).get_public_url(
                    f.storage_key
                )
            except Exception:
                pass

        uploaded_files.append(
            StudentSubmissionFileResponse(
                file_id=f.file_id,
                file_name=f.file_name,
                url=url,
                storage_key=f.storage_key,
                mime_type=f.mime_type,
                size_bytes=f.size_bytes,
                uploaded_at=f.uploaded_at,
            )
        )

    # Full announcement details for the new field
    from app.schemas.student_announcement_schema import (
        StudentAnnouncementFileResponse,
        StudentAnnouncementResponse,
    )

    announcement_response = None
    if announcement:
        announcement_response = StudentAnnouncementResponse(
            announcement_id=announcement.announcement_id,
            title=announcement.title,
            description=announcement.description,
            supervisor_name=None,  # Populate if available
            created_at=announcement.created_at,
            updated_at=announcement.updated_at,
            files=[
                StudentAnnouncementFileResponse(
                    file_id=f.file_id,
                    file_name=f.file_name,
                    url=get_public_file_url(ANNOUNCEMENTS_BUCKET, f.storage_key),
                    storage_key=f.storage_key,
                    file_type=f.file_type,
                    mime_type=f.mime_type,
                    size_bytes=f.size_bytes,
                )
                for f in announcement.files
            ],
        )

    return StudentUnofficialSubmissionDetail(
        submission_id=submission.submission_id,
        title=submission.title,
        note=submission.note,
        status=submission.status,
        submitted_at=submission.submitted_at or submission.updated_at,
        updated_at=submission.updated_at,
        supervisor_feedback=submission.supervisor_feedback,
        files=uploaded_files,
        announcement=announcement_response,
    )


# ─── UNOFFICIAL SUBMISSIONS: CREATE (POST) ────────────────────────────────────


@router.post(
    "/unofficial",
    response_model=StudentUnofficialSubmissionDetail,
    status_code=status.HTTP_201_CREATED,
)
async def create_unofficial_submission(
    title: str = Form(..., description="Title of the unofficial submission"),
    note: Optional[str] = Form(None, description="Optional note/comment"),
    files: List[UploadFile] = File(
        default=[], description="Files to upload and attach"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Student: Create a new unofficial submission."""
    if current_user.role != RoleEnum.student:
        raise HTTPException(status_code=403, detail="Student only")

    group = await submission_repository.get_student_group(db, current_user.user_id)
    if not group:
        raise HTTPException(status_code=404, detail="You are not part of any group")

    from app.models.submission import Submission, SubmissionTypeEnum

    # Create submission record
    new_sub = Submission(
        group_id=group.group_id,
        created_by=current_user.user_id,
        title=title.strip(),
        note=note.strip() if note else None,
        type=SubmissionTypeEnum.unofficial,
        status=SubmissionStatusEnum.submitted,
        submitted_at=datetime.now(timezone.utc),
    )
    db.add(new_sub)
    await db.flush()  # To get submission_id

    # Upload files
    from app.models.submission import SubmissionFile

    for upload in files:
        if not upload.filename:
            continue
        storage_key = _build_storage_key(current_user.user_id, upload.filename)
        size_bytes = await upload_file_to_supabase(
            supabase,
            bucket=SUBMISSION_FILES_BUCKET,
            storage_key=storage_key,
            upload=upload,
        )
        db.add(
            SubmissionFile(
                submission_id=new_sub.submission_id,
                file_name=upload.filename,
                storage_key=storage_key,
                mime_type=upload.content_type or "application/octet-stream",
                size_bytes=size_bytes,
            )
        )

    await db.commit()

    # Refetch fully populated
    populated_sub = await submission_repository.get_unofficial_by_id_for_student(
        db,
        submission_id=new_sub.submission_id,
        group_id=group.group_id,
    )

    from app.schemas.submission_schema import StudentUnofficialSubmissionDetail

    uploaded_files = []
    for f in populated_sub.files:
        url = None
        if f.storage_key:
            try:
                url = supabase.storage.from_(SUBMISSION_FILES_BUCKET).get_public_url(
                    f.storage_key
                )
            except Exception:
                pass

        uploaded_files.append(
            StudentSubmissionFileResponse(
                file_id=f.file_id,
                file_name=f.file_name,
                url=url,
                storage_key=f.storage_key,
                mime_type=f.mime_type,
                size_bytes=f.size_bytes,
                uploaded_at=f.uploaded_at,
            )
        )

    return StudentUnofficialSubmissionDetail(
        submission_id=populated_sub.submission_id,
        title=populated_sub.title,
        note=populated_sub.note,
        status=populated_sub.status,
        submitted_at=populated_sub.submitted_at or populated_sub.updated_at,
        updated_at=populated_sub.updated_at,
        supervisor_feedback=populated_sub.supervisor_feedback,
        files=uploaded_files,
    )


# ─── UNOFFICIAL SUBMISSIONS: EDIT (PATCH) ─────────────────────────────────────


@router.patch(
    "/unofficial/{submission_id}", response_model=StudentUnofficialSubmissionDetail
)
async def edit_unofficial_submission(
    submission_id: UUID,
    title: Optional[str] = Form(None, description="New title"),
    note: Optional[str] = Form(None, description="New note/comment"),
    keep_file_ids: Optional[str] = Form(
        None, description="Comma-separated IDs of existing files to keep"
    ),
    files: List[UploadFile] = File(default=[], description="New files to append"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Student: Edit an unofficial submission and its files."""
    if current_user.role != RoleEnum.student:
        raise HTTPException(status_code=403, detail="Student only")

    group = await submission_repository.get_student_group(db, current_user.user_id)
    if not group:
        raise HTTPException(status_code=404, detail="You are not part of any group")

    submission = await submission_repository.get_unofficial_by_id_for_student(
        db,
        submission_id=submission_id,
        group_id=group.group_id,
    )
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    # Update basic fields
    if title is not None:
        submission.title = title.strip()
    if note is not None:
        submission.note = note.strip() or None

    # Unofficial submissions are always user-submitted work, so any edit/resubmit
    # should keep the record in submitted state.
    submission.status = SubmissionStatusEnum.submitted
    if submission.submitted_at is None:
        submission.submitted_at = datetime.now(timezone.utc)

    # Sync existing files
    if keep_file_ids is not None:
        try:
            keep_ids = {
                UUID(fid.strip()) for fid in keep_file_ids.split(",") if fid.strip()
            }
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid keep_file_ids format")

        for existing_file in list(submission.files):
            if existing_file.file_id not in keep_ids:
                try:
                    await delete_file_from_supabase(
                        supabase,
                        bucket=SUBMISSION_FILES_BUCKET,
                        storage_key=existing_file.storage_key,
                    )
                except Exception:
                    pass
                await db.delete(existing_file)

    # Upload new files
    from app.models.submission import SubmissionFile

    for upload in files:
        if not upload.filename:
            continue
        storage_key = _build_storage_key(current_user.user_id, upload.filename)
        size_bytes = await upload_file_to_supabase(
            supabase,
            bucket=SUBMISSION_FILES_BUCKET,
            storage_key=storage_key,
            upload=upload,
        )
        db.add(
            SubmissionFile(
                submission_id=submission_id,
                file_name=upload.filename,
                storage_key=storage_key,
                mime_type=upload.content_type or "application/octet-stream",
                size_bytes=size_bytes,
            )
        )

    submission.updated_at = datetime.now(timezone.utc)
    await db.commit()

    # Refetch
    populated_sub = await submission_repository.get_unofficial_by_id_for_student(
        db,
        submission_id=submission_id,
        group_id=group.group_id,
    )

    from app.schemas.submission_schema import StudentUnofficialSubmissionDetail

    uploaded_files = []
    for f in populated_sub.files:
        url = None
        if f.storage_key:
            try:
                url = supabase.storage.from_(SUBMISSION_FILES_BUCKET).create_signed_url(
                    f.storage_key, 3600
                )["signedURL"]
            except Exception:
                pass

        uploaded_files.append(
            StudentSubmissionFileResponse(
                file_id=f.file_id,
                file_name=f.file_name,
                url=url,
                storage_key=f.storage_key,
                mime_type=f.mime_type,
                size_bytes=f.size_bytes,
                uploaded_at=f.uploaded_at,
            )
        )

    return StudentUnofficialSubmissionDetail(
        submission_id=populated_sub.submission_id,
        title=populated_sub.title,
        note=populated_sub.note,
        status=populated_sub.status,
        submitted_at=populated_sub.submitted_at or populated_sub.updated_at,
        updated_at=populated_sub.updated_at,
        supervisor_feedback=populated_sub.supervisor_feedback,
        files=uploaded_files,
    )


# ─── UNOFFICIAL SUBMISSIONS: DELETE ───────────────────────────────────────────


@router.delete("/unofficial/{submission_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_unofficial_submission(
    submission_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Student: Delete an entire unofficial submission and all its files."""
    if current_user.role != RoleEnum.student:
        raise HTTPException(status_code=403, detail="Student only")

    group = await submission_repository.get_student_group(db, current_user.user_id)
    if not group:
        raise HTTPException(status_code=404, detail="You are not part of any group")

    submission = await submission_repository.get_unofficial_by_id_for_student(
        db,
        submission_id=submission_id,
        group_id=group.group_id,
    )
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    # Delete all attached files from Supabase block first
    for f in submission.files:
        try:
            await delete_file_from_supabase(
                supabase,
                bucket=SUBMISSION_FILES_BUCKET,
                storage_key=f.storage_key,
            )
        except Exception:
            pass  # Storage failure shouldn't block DB delete

    # Delete DB row (cascades file rows automatically if FK is setup, else SA deletes)
    await db.delete(submission)
    await db.commit()
