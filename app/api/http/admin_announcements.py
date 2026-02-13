import os
import re
import uuid
from datetime import datetime
from uuid import UUID, uuid4
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
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
from app.schemas.admin_announcement_schema import PaginatedAnnouncements
from app.services.storage_service import (
    ANNOUNCEMENTS_BUCKET,
    upload_file_to_supabase,
    delete_file_from_supabase,
)


def _safe_filename(name: str) -> str:
    base, ext = os.path.splitext(name)
    safe_base = re.sub(r"[^A-Za-z0-9._-]", "_", base or "file")
    safe_ext = re.sub(r"[^A-Za-z0-9._-]", "_", ext)
    cleaned = f"{safe_base}{safe_ext}" if safe_ext else safe_base
    return cleaned or "file"


def _build_storage_key(user_id: UUID, filename: str) -> str:
    safe_name = _safe_filename(filename)
    return f"announcements/{safe_name}"


router = APIRouter(prefix="/admin", tags=["admin-announcements"])

@router.get("/announcements", response_model=PaginatedAnnouncements)
async def get_all_announcements(
    page: int = Query(1, ge=1, description="Page number starting from 1"),
    per_page: int = Query(10, ge=1, description="Number of items per page"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
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

@router.post("/announcements", status_code=201)
async def post_announcement(
    title: str = Form(...),
    description: Optional[str] = Form(None),
    target_type: TargetRoleEnum = Form(...),
    due_at: Optional[str] = Form(None, description="ISO datetime; e.g. 2026-02-12T00:00:00Z"),
    total_marks: Optional[float] = Form(None),
    files: Optional[List[UploadFile]] = File(None),
    file_types: Optional[str] = Form(None, description="Comma separated types matching files (Document/Template)"),
    file_modules: Optional[str] = Form(None, description="Comma separated module names for template files"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Only admins can create announcements")

    parsed_due_at = None
    if due_at:
        try:
            parsed_due_at = datetime.fromisoformat(due_at.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid due_at format; use ISO datetime")

    file_payloads: List[Tuple[str, str, FileTypeEnum, Optional[str], Optional[int], Optional[str]]] = []
    types_list = [t.strip() for t in file_types.split(",")] if file_types else []
    modules_list = [m.strip() for m in file_modules.split(",")] if file_modules else []

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

            ftype_raw = types_list[idx] if idx < len(types_list) else "Document"
            ftype = FileTypeEnum.Template if ftype_raw.lower() == "template" else FileTypeEnum.Document
            module_val = None
            if ftype == FileTypeEnum.Template:
                module_val = modules_list[idx] if idx < len(modules_list) and modules_list[idx] else None

            file_payloads.append(
                (
                    upload.filename,
                    storage_key,
                    ftype,
                    upload.content_type,
                    size_bytes,
                    module_val,
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
        due_at=parsed_due_at,
        total_marks=total_marks,
    )

    await db.commit()
    await db.refresh(new_announcement)

    return {
        "status": "success",
        "message": f"Announcement created for {target_type.value}",
        "announcement_id": str(new_announcement.announcement_id),
    }


@router.delete("/announcements/{announcement_id}")
async def delete_announcement(
    announcement_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Only admins can delete announcements")

    announcement = await announcement_repository.get_by_id(db, announcement_id)
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")

    await announcement_repository.delete(db, announcement)
    await db.commit()

    return {
        "status": "success",
        "message": "Announcement deleted",
        "announcement_id": str(announcement_id),
    }


@router.patch("/announcements/{announcement_id}")
async def update_announcement(
    announcement_id: UUID,
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    # Dropdown ke liye Enum use karein taake 422 na aaye
    target_type: Optional[TargetRoleEnum] = Form(None), 
    due_at: Optional[str] = Form(None),
    total_marks: Optional[float] = Form(None),
    keep_file_ids: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = File(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Only admins can update")

    # 1. Fetch Announcement
    announcement = await announcement_repository.get_by_id(db, announcement_id)
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")

    # 2. Date Parsing with Safety
    parsed_due_at = None
    if due_at and due_at.strip():
        try:
            parsed_due_at = datetime.fromisoformat(due_at.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format")
        
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
        due_at=parsed_due_at,
        total_marks=total_marks,
        keep_file_ids=parsed_keep_ids
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
                        await delete_file_from_supabase(supabase, ANNOUNCEMENTS_BUCKET, existing_file.storage_key)
                    except Exception: pass # Cloud failure should not block DB consistency
                    
                    await db.delete(existing_file)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid UUID format in keep_file_ids")

    # 6. Adding New Files
    if files:
        for upload in files:
            if not upload.filename: continue
            
            storage_key = f"announcements/{upload.filename}"
            size_bytes = await upload_file_to_supabase( supabase, bucket=ANNOUNCEMENTS_BUCKET,  storage_key=storage_key, upload=upload)

            announcement.files.append(
                AnnouncementFile(
                    file_name=upload.filename,
                    storage_key=storage_key,
                    mime_type=upload.content_type,
                    size_bytes=size_bytes,
                    file_type=FileTypeEnum.Document
                )
            )

    await db.commit()
    await db.refresh(announcement)
    return {"status": "success", "message": "Announcement updated"}