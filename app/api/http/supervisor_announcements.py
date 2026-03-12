# app/api/http/supervisor_announcements.py
"""
Supervisor Announcements API

Provides CRUD endpoints for supervisors to create, read, update, and delete
regular announcements (not submission requests) targeted at their managed groups.
"""

import os
import re
from typing import List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from sqlalchemy import delete, func, or_, select
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
from app.models.group import Group
from app.models.user import RoleEnum, User
from app.schemas.admin_announcement_schema import (
    PaginatedAnnouncements as PaginatedAdminAnnouncements,
)
from app.schemas.supervisor_announcement_schema import (
    PaginatedSupervisorAnnouncements,
    SupervisorAnnouncementFileResponse,
    SupervisorAnnouncementResponse,
    SupervisorAnnouncementTargetResponse,
)
from app.services.storage_service import (
    ANNOUNCEMENTS_BUCKET,
    delete_file_from_supabase,
    upload_file_to_supabase,
)

router = APIRouter(tags=["faculty-announcements"])


# ─── HELPERS ──────────────────────────────────────────────────────────────────


def _safe_filename(name: str) -> str:
    base, ext = os.path.splitext(name)
    safe_base = re.sub(r"[^A-Za-z0-9._-]", "_", base or "file")
    safe_ext = re.sub(r"[^A-Za-z0-9._-]", "_", ext)
    cleaned = f"{safe_base}{safe_ext}" if safe_ext else safe_base
    return cleaned or "file"


def _build_storage_key(user_id: UUID, filename: str) -> str:
    safe_name = _safe_filename(filename)
    return f"announcements/{uuid4()}-{safe_name}"


def _resolve_file_type(raw: Optional[str]) -> FileTypeEnum:
    if raw and raw.strip().lower() == "template":
        raise HTTPException(
            status_code=403, detail="Only admins can upload template files"
        )
    return FileTypeEnum.Document


async def _get_managed_groups(user_id: UUID, db: AsyncSession) -> List[Group]:
    """Fetch all groups where the supervisor is primary or co-supervisor."""
    result = await db.execute(
        select(Group)
        .options(selectinload(Group.project))
        .where(
            or_(
                Group.supervisor_id == user_id,
                Group.cosupervisor_ids.contains([user_id]),
            )
        )
    )
    return result.scalars().all()


def _assign_to_label(
    targets: List[AnnouncementTarget], managed_groups: List[Group]
) -> str:
    """Convert announcement targets into a human-readable label."""
    if not targets:
        return "None"

    target_group_ids = {t.group_id for t in targets if t.group_id}
    managed_group_ids = {g.group_id for g in managed_groups}

    if (
        managed_group_ids
        and len(target_group_ids) == len(managed_group_ids)
        and target_group_ids == managed_group_ids
    ):
        return "all"

    if len(target_group_ids) == 1:
        return str(list(target_group_ids)[0])

    return "Multiple Groups"


def _build_response(
    announcement: Announcement, managed_groups: List[Group]
) -> SupervisorAnnouncementResponse:
    """Build a supervisor announcement response from an ORM object."""

    # Build a group_id -> project_name lookup for friendly target names
    project_name_map = {
        g.group_id: g.project.name if g.project else "Unknown Project"
        for g in managed_groups
    }

    targets = [
        SupervisorAnnouncementTargetResponse(
            group_id=t.group_id,
            project_name=project_name_map.get(t.group_id) if t.group_id else None,
        )
        for t in announcement.targets
    ]

    files = [
        SupervisorAnnouncementFileResponse(
            file_id=f.file_id,
            file_name=f.file_name,
            storage_key=f.storage_key,
            file_type=f.file_type,
            mime_type=f.mime_type,
            size_bytes=f.size_bytes,
            is_template=getattr(f, "is_template", False),
        )
        for f in announcement.files
    ]

    return SupervisorAnnouncementResponse(
        announcement_id=announcement.announcement_id,
        title=announcement.title,
        description=announcement.description,
        assign_to=_assign_to_label(announcement.targets, managed_groups),
        created_at=announcement.created_at,
        updated_at=announcement.updated_at,
        targets=targets,
        files=files,
    )


# ─── LIST ─────────────────────────────────────────────────────────────────────


@router.get("", response_model=PaginatedSupervisorAnnouncements)
async def get_supervisor_announcements(
    page: int = Query(1, ge=1, description="Page number starting from 1"),
    per_page: int = Query(10, ge=1, le=50, description="Items per page"),
    search: Optional[str] = Query(None, description="Search by title"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Supervisor: List all regular announcements created by me."""
    if current_user.role != RoleEnum.faculty:
        raise HTTPException(status_code=403, detail="Faculty only")

    # Active check
    if not current_user.faculty_profile or not current_user.faculty_profile.is_active:
        raise HTTPException(
            status_code=403,
            detail="Your faculty account is inactive. Contact an administrator.",
        )

    # Check if faculty has supervisor privileges
    if not current_user.faculty_profile.is_supervisor:
        raise HTTPException(
            status_code=403,
            detail="Only faculty with supervisor privileges can manage announcements",
        )

    base_filters = [
        Announcement.created_by == current_user.user_id,
        Announcement.created_by_role.in_(AnnouncementRoleEnum.supervisor_values()),
        Announcement.is_submission_request == False,  # noqa: E712
    ]

    query = (
        select(Announcement)
        .options(
            selectinload(Announcement.targets),
            selectinload(Announcement.files),
        )
        .where(*base_filters)
    )

    if search:
        query = query.where(Announcement.title.ilike(f"%{search}%"))

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total_items = (await db.execute(count_query)).scalar_one()

    # Paginate
    offset = (page - 1) * per_page
    total_pages = (total_items + per_page - 1) // per_page if total_items > 0 else 1

    query = (
        query.order_by(Announcement.created_at.desc()).offset(offset).limit(per_page)
    )
    result = await db.execute(query)
    announcements = result.scalars().all()

    managed_groups = await _get_managed_groups(current_user.user_id, db)

    return PaginatedSupervisorAnnouncements(
        announcements=[_build_response(a, managed_groups) for a in announcements],
        total_items=total_items,
        total_pages=total_pages,
        current_page=page,
        per_page=per_page,
    )


# ─── ADMIN ANNOUNCEMENTS FOR SUPERVISORS ──────────────────────────────────────


@router.get("/admin-announcements", response_model=PaginatedAdminAnnouncements)
async def get_admin_announcements_for_supervisor(
    page: int = Query(1, ge=1, description="Page number starting from 1"),
    per_page: int = Query(10, ge=1, le=50, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Supervisor: List admin announcements targeted at supervisors (all_supervisors / both)."""
    if current_user.role != RoleEnum.faculty:
        raise HTTPException(status_code=403, detail="Faculty only")

    # Active check
    if not current_user.faculty_profile or not current_user.faculty_profile.is_active:
        raise HTTPException(
            status_code=403,
            detail="Your faculty account is inactive. Contact an administrator.",
        )

    # Check if faculty has supervisor privileges
    if not current_user.faculty_profile.is_supervisor:
        raise HTTPException(
            status_code=403,
            detail="Only faculty with supervisor privileges can view announcements",
        )

    # Only admin-created, non-submission announcements
    # whose target_role is all_supervisors or both
    base_query = (
        select(Announcement)
        .join(AnnouncementTarget)
        .options(
            selectinload(Announcement.targets),
            selectinload(Announcement.files),
        )
        .where(
            Announcement.created_by_role == AnnouncementRoleEnum.admin,
            Announcement.is_submission_request == False,  # noqa: E712
            AnnouncementTarget.target_role.in_(
                [
                    TargetRoleEnum.all_supervisors,
                    TargetRoleEnum.both,
                ]
            ),
        )
    )

    # Count
    count_query = select(func.count()).select_from(base_query.subquery())
    total_items = (await db.execute(count_query)).scalar_one()

    # Paginate
    offset = (page - 1) * per_page
    total_pages = (total_items + per_page - 1) // per_page if total_items > 0 else 1

    paginated_query = (
        base_query.order_by(Announcement.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    result = await db.execute(paginated_query)
    announcements = result.scalars().unique().all()

    return PaginatedAdminAnnouncements(
        announcements=announcements,
        total_items=total_items,
        total_pages=total_pages,
        current_page=page,
        per_page=per_page,
    )


# ─── GET BY ID ────────────────────────────────────────────────────────────────


@router.get("/{announcement_id}", response_model=SupervisorAnnouncementResponse)
async def get_supervisor_announcement_by_id(
    announcement_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Supervisor: Get a single announcement by ID (ownership check)."""
    if current_user.role != RoleEnum.faculty:
        raise HTTPException(status_code=403, detail="Faculty only")

    # Active check
    if not current_user.faculty_profile or not current_user.faculty_profile.is_active:
        raise HTTPException(
            status_code=403,
            detail="Your faculty account is inactive. Contact an administrator.",
        )

    # Check if faculty has supervisor privileges
    if not current_user.faculty_profile.is_supervisor:
        raise HTTPException(
            status_code=403,
            detail="Only faculty with supervisor privileges can manage announcements",
        )

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

    if announcement.created_by != current_user.user_id:
        raise HTTPException(
            status_code=403, detail="You did not create this announcement."
        )

    if announcement.is_submission_request:
        raise HTTPException(status_code=404, detail="Announcement not found")

    managed_groups = await _get_managed_groups(current_user.user_id, db)
    return _build_response(announcement, managed_groups)


# ─── CREATE ───────────────────────────────────────────────────────────────────


@router.post("", status_code=201, response_model=SupervisorAnnouncementResponse)
async def create_supervisor_announcement(
    request: Request,
    title: str = Form(..., description="Title of the announcement"),
    group_id: str = Form(
        ..., description="Target group ID or 'all' for all managed groups"
    ),
    description: Optional[str] = Form(None, description="Description"),
    file_types: Optional[str] = Form(
        None, description="Comma separated types matching files (Document/Template)"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Supervisor: Create a regular announcement for managed group(s)."""
    if current_user.role != RoleEnum.faculty:
        raise HTTPException(status_code=403, detail="Faculty only")

    # Active check
    if not current_user.faculty_profile or not current_user.faculty_profile.is_active:
        raise HTTPException(
            status_code=403,
            detail="Your faculty account is inactive. Contact an administrator.",
        )

    # Check if faculty has supervisor privileges
    if not current_user.faculty_profile.is_supervisor:
        raise HTTPException(
            status_code=403,
            detail="Only faculty with supervisor privileges can create announcements",
        )

    # Resolve groups
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
        is_submission_request=False,
    )
    db.add(announcement)
    await db.flush()

    # 2. Create Targets (group_id set, target_role = None for DB constraint)
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
        if k == "files" and getattr(v, "filename", None)
    ]

    types_list = [t.strip() for t in file_types.split(",")] if file_types else []

    for idx, upload in enumerate(incoming_files):
        storage_key = _build_storage_key(current_user.user_id, upload.filename)
        size_bytes = await upload_file_to_supabase(
            supabase,
            bucket=ANNOUNCEMENTS_BUCKET,
            storage_key=storage_key,
            upload=upload,
        )

        ftype_raw = types_list[idx] if idx < len(types_list) else None
        ftype = _resolve_file_type(ftype_raw)

        db.add(
            AnnouncementFile(
                announcement_id=announcement.announcement_id,
                file_name=upload.filename,
                storage_key=storage_key,
                mime_type=upload.content_type or "application/octet-stream",
                size_bytes=size_bytes,
                file_type=ftype,
                is_template=False,
            )
        )

    await db.commit()

    # Re-fetch with relationships
    result = await db.execute(
        select(Announcement)
        .options(
            selectinload(Announcement.targets),
            selectinload(Announcement.files),
        )
        .where(Announcement.announcement_id == announcement.announcement_id)
    )
    announcement = result.scalars().first()

    return _build_response(announcement, managed_groups)


# ─── DELETE ───────────────────────────────────────────────────────────────────


@router.delete("/{announcement_id}", response_model=SupervisorAnnouncementResponse)
async def delete_supervisor_announcement(
    announcement_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Supervisor: Delete an announcement (ownership check + storage cleanup)."""
    if current_user.role != RoleEnum.faculty:
        raise HTTPException(status_code=403, detail="Faculty only")

    # Active check
    if not current_user.faculty_profile or not current_user.faculty_profile.is_active:
        raise HTTPException(
            status_code=403,
            detail="Your faculty account is inactive. Contact an administrator.",
        )

    # Check if faculty has supervisor privileges
    if not current_user.faculty_profile.is_supervisor:
        raise HTTPException(
            status_code=403,
            detail="Only faculty with supervisor privileges can delete announcements",
        )

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

    if announcement.created_by != current_user.user_id:
        raise HTTPException(
            status_code=403, detail="You did not create this announcement."
        )

    managed_groups = await _get_managed_groups(current_user.user_id, db)
    snapshot = _build_response(announcement, managed_groups)

    # Clean up files from storage
    if announcement.files:
        for file_record in announcement.files:
            try:
                await delete_file_from_supabase(
                    supabase,
                    bucket=ANNOUNCEMENTS_BUCKET,
                    storage_key=file_record.storage_key,
                )
            except Exception:
                pass  # Cloud failure should not block DB cleanup

    await db.delete(announcement)
    await db.commit()

    return snapshot


# ─── UPDATE (PATCH) ───────────────────────────────────────────────────────────


@router.patch("/{announcement_id}", response_model=SupervisorAnnouncementResponse)
async def update_supervisor_announcement(
    request: Request,
    announcement_id: UUID,
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    group_id: Optional[str] = Form(None, description="Update target group(s)"),
    keep_file_ids: Optional[str] = Form(None),
    file_types: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Supervisor: Partially update an announcement."""
    if current_user.role != RoleEnum.faculty:
        raise HTTPException(status_code=403, detail="Faculty only")

    # Active check
    if not current_user.faculty_profile or not current_user.faculty_profile.is_active:
        raise HTTPException(
            status_code=403,
            detail="Your faculty account is inactive. Contact an administrator.",
        )

    # Check if faculty has supervisor privileges
    if not current_user.faculty_profile.is_supervisor:
        raise HTTPException(
            status_code=403,
            detail="Only faculty with supervisor privileges can update announcements",
        )

    # Fetch
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

    if announcement.created_by != current_user.user_id:
        raise HTTPException(
            status_code=403, detail="You did not create this announcement."
        )

    # Update text fields
    if title and title.strip():
        announcement.title = title.strip()
    if description is not None:
        announcement.description = description.strip() if description.strip() else None

    # Update targets
    managed_groups = await _get_managed_groups(current_user.user_id, db)

    if group_id:
        # Remove old targets
        await db.execute(
            delete(AnnouncementTarget).where(
                AnnouncementTarget.announcement_id == announcement_id
            )
        )

        new_target_ids: List[UUID] = []
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

        for gid in new_target_ids:
            db.add(
                AnnouncementTarget(
                    announcement_id=announcement_id,
                    group_id=gid,
                    target_role=None,
                )
            )

    # Sync existing files via keep_file_ids
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
                except Exception:
                    pass
                await db.delete(existing_file)

    # Upload new files
    content_type = (request.headers.get("content-type", "") or "").lower()
    incoming_files = []
    types_list: List[str] = []

    if "multipart/form-data" in content_type:
        form = await request.form()
        incoming_files = [
            v
            for k, v in form.multi_items()
            if k == "files" and getattr(v, "filename", None)
        ]
        if file_types:
            types_list = [t.strip() for t in file_types.split(",") if t.strip()]

    for idx, upload in enumerate(incoming_files):
        storage_key = _build_storage_key(current_user.user_id, upload.filename)
        size_bytes = await upload_file_to_supabase(
            supabase,
            bucket=ANNOUNCEMENTS_BUCKET,
            storage_key=storage_key,
            upload=upload,
        )

        ftype = _resolve_file_type(types_list[idx] if idx < len(types_list) else None)

        db.add(
            AnnouncementFile(
                announcement_id=announcement_id,
                file_name=upload.filename,
                storage_key=storage_key,
                mime_type=upload.content_type or "application/octet-stream",
                size_bytes=size_bytes,
                file_type=ftype,
                is_template=False,
            )
        )

    await db.commit()

    # Re-fetch
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
        raise HTTPException(status_code=500, detail="Failed to load announcement")

    return _build_response(announcement, managed_groups)
