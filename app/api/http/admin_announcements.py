import os
import re
from typing import List, Optional, Tuple
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase_auth import get_current_user
from app.db import get_db, supabase
from app.models.announcement import (
    AnnouncementFile,
    AnnouncementRoleEnum,
    FileTypeEnum,
    TargetRoleEnum,
)
from app.models.user import RoleEnum, User
from app.repositories import announcement_repository
from app.schemas.admin_announcement_schema import (
    AnnouncementResponse,
    PaginatedAnnouncements,
)
from app.services.storage_service import (
    ANNOUNCEMENTS_BUCKET,
    delete_file_from_supabase,
    upload_file_to_supabase,
)


def _safe_filename(name: str) -> str:
    base, ext = os.path.splitext(name)
    safe_base = re.sub(r"[^A-Za-z0-9._-]", "_", base or "file")
    safe_ext = re.sub(r"[^A-Za-z0-9._-]", "_", ext)
    cleaned = f"{safe_base}{safe_ext}" if safe_ext else safe_base
    return cleaned or "file"


def _build_storage_key(user_id: UUID, filename: str) -> str:
    """Build a unique storage key for a file."""
    safe_name = _safe_filename(filename)
    return f"announcements/{uuid4()}-{safe_name}"


def _resolve_file_type(raw: Optional[str]) -> FileTypeEnum:
    if raw and raw.strip().lower() == "template":
        return FileTypeEnum.Template
    return FileTypeEnum.Document


router = APIRouter(prefix="/admin", tags=["admin-announcements"])


@router.get("/announcements", response_model=PaginatedAnnouncements)
async def get_all_announcements(
    page: int = Query(1, ge=1, description="Page number starting from 1"),
    per_page: int = Query(10, ge=1, description="Number of items per page"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Admin only")

    announcements, total_items = await announcement_repository.get_paginated(
        db, page, per_page
    )
    total_pages = (total_items + per_page - 1) // per_page if total_items > 0 else 1

    return PaginatedAnnouncements(
        announcements=announcements,
        total_items=total_items,
        total_pages=total_pages,
        current_page=page,
        per_page=per_page,
    )


@router.get("/announcements/{announcement_id}", response_model=AnnouncementResponse)
async def get_announcement_by_id(
    announcement_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Admin only")

    announcement = await announcement_repository.get_by_id(db, announcement_id)
    if (
        not announcement
        or announcement.created_by_role != AnnouncementRoleEnum.admin
        or announcement.is_submission_request
    ):
        raise HTTPException(status_code=404, detail="Announcement not found")

    return announcement


@router.post("/announcements", status_code=201, response_model=AnnouncementResponse)
async def post_announcement(
    title: str = Form(...),
    description: Optional[str] = Form(None),
    target_type: TargetRoleEnum = Form(...),
    files: Optional[List[UploadFile]] = File(None),
    file_types: Optional[str] = Form(
        None, description="Comma separated types matching files (Document/Template)"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != RoleEnum.admin:
        raise HTTPException(
            status_code=403, detail="Only admins can create announcements"
        )

    file_payloads: List[Tuple[str, str, FileTypeEnum, Optional[str], Optional[int]]] = (
        []
    )
    types_list = [t.strip() for t in file_types.split(",")] if file_types else []

    if files:
        for idx, upload in enumerate(files):
            if not upload or not upload.filename:
                continue
            storage_key = _build_storage_key(current_user.user_id, upload.filename)
            size_bytes = await upload_file_to_supabase(
                supabase,
                bucket=ANNOUNCEMENTS_BUCKET,
                storage_key=storage_key,
                upload=upload,
            )

            ftype_raw = types_list[idx] if idx < len(types_list) else None
            ftype = _resolve_file_type(ftype_raw)

            file_payloads.append(
                (
                    upload.filename,
                    storage_key,
                    ftype,
                    upload.content_type,
                    size_bytes,
                )
            )

    new_announcement = await announcement_repository.create_announcement(
        db,
        created_by=current_user.user_id,
        created_by_role=AnnouncementRoleEnum.admin,
        title=title,
        description=description,
        target_role=target_type,
        files=file_payloads or None,
    )

    await db.commit()

    persisted = await announcement_repository.get_by_id(
        db, new_announcement.announcement_id
    )
    if not persisted:
        raise HTTPException(status_code=500, detail="Failed to load announcement")

    return AnnouncementResponse.model_validate(persisted)


@router.delete("/announcements/{announcement_id}", response_model=AnnouncementResponse)
async def delete_announcement(
    announcement_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != RoleEnum.admin:
        raise HTTPException(
            status_code=403, detail="Only admins can delete announcements"
        )

    announcement = await announcement_repository.get_by_id(db, announcement_id)
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")

    snapshot = AnnouncementResponse.model_validate(announcement)

    await announcement_repository.delete(db, announcement)
    await db.commit()

    return snapshot


@router.patch("/announcements/{announcement_id}", response_model=AnnouncementResponse)
async def update_announcement(
    request: Request,
    announcement_id: UUID,
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    # Dropdown ke liye Enum use karein taake 422 na aaye
    target_type: Optional[TargetRoleEnum] = Form(None),
    keep_file_ids: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Only admins can update")

    # 1. Fetch Announcement
    announcement = await announcement_repository.get_by_id(db, announcement_id)
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")

    parsed_keep_ids = None
    if keep_file_ids is not None:
        id_list = [f.strip() for f in keep_file_ids.split(",") if f.strip()]
        parsed_keep_ids = [UUID(fid) for fid in id_list]

    # 3. Update Text Fields (Using your consistent Repo function)
    await announcement_repository.update(
        db,
        announcement,
        title=title.strip() if title else None,
        description=description.strip() if description else None,
        keep_file_ids=parsed_keep_ids,
    )

    # 4. Target Role Update
    if target_type:
        for target in announcement.targets:
            target.target_role = target_type

    # 5. Robust UUID Parsing for File Sync

    if keep_file_ids is not None:
        try:
            # Sirf un IDs ko uthayein jo khali nahi hain
            id_list = [f.strip() for f in keep_file_ids.split(",") if f.strip()]
            keep_ids = {UUID(fid) for fid in id_list}

            for existing_file in list(announcement.files):
                if existing_file.file_id not in keep_ids:
                    # Cloud storage se delete karein
                    try:
                        await delete_file_from_supabase(
                            supabase, ANNOUNCEMENTS_BUCKET, existing_file.storage_key
                        )
                    except Exception:
                        pass  # Cloud failure should not block DB consistency

                    await db.delete(existing_file)
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid UUID format in keep_file_ids"
            )

    content_type = (request.headers.get("content-type", "") or "").lower()
    incoming_files: List[UploadFile] = []
    types_list: List[str] = []

    if "multipart/form-data" in content_type:
        form = await request.form()
        if hasattr(form, "getlist"):
            candidates = form.getlist("files")
            for candidate in candidates:
                filename = getattr(candidate, "filename", None)
                if filename:
                    incoming_files.append(candidate)

        raw_types = form.get("file_types") if hasattr(form, "get") else None
        if raw_types:
            types_list = [t.strip() for t in raw_types.split(",") if t.strip()]

    for idx, upload in enumerate(incoming_files):
        storage_key = _build_storage_key(current_user.user_id, upload.filename)
        size_bytes = await upload_file_to_supabase(
            supabase,
            bucket=ANNOUNCEMENTS_BUCKET,
            storage_key=storage_key,
            upload=upload,
        )

        ftype = _resolve_file_type(types_list[idx] if idx < len(types_list) else None)

        announcement.files.append(
            AnnouncementFile(
                file_name=upload.filename,
                storage_key=storage_key,
                mime_type=upload.content_type,
                size_bytes=size_bytes,
                file_type=ftype,
            )
        )

    await db.commit()

    persisted = await announcement_repository.get_by_id(db, announcement_id)
    if not persisted:
        raise HTTPException(status_code=500, detail="Failed to load announcement")

    return AnnouncementResponse.model_validate(persisted)
