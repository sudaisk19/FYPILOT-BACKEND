from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase_auth import get_current_user
from app.db import get_db
from app.models.announcement import (
    Announcement,
    AnnouncementFile,
    AnnouncementRoleEnum,
    AnnouncementTarget,
    FileTypeEnum,
)
from app.models.group import Group
from app.models.user import RoleEnum, User
from app.schemas.submission_schema import FileOutput, SubmissionAnnouncementResponse
from app.services.file_service import FileService

router = APIRouter(prefix="/supervisors/submissions", tags=["supervisor-submissions"])

ALLOWED_EXTENSIONS = {".csv", ".pdf", ".docx"}


@router.post(
    "",
    response_model=SubmissionAnnouncementResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a submission task for managed groups (Supervisor)",
    description="Create a submission task/announcement for one or all managed groups. Handles file uploads (CSV, PDF, DOCX).",
)
async def create_supervisor_submission_task(
    group_id: str = Form(
        ..., description="Target Group ID or 'all' to assign task to all managed groups"
    ),
    title: str = Form(..., description="Title of the submission task"),
    description: Optional[str] = Form(None, description="Description of the task"),
    dueDate: str = Form(..., description="Due date in ISO format (mandatory)"),
    total_marks: Optional[float] = Form(
        None, description="Total marks for the submission"
    ),
    files: List[UploadFile] = [],  # FastAPI automatically processes file uploads
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 1. Role Check
    if current_user.role != RoleEnum.supervisor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only supervisors can create submission tasks via this endpoint.",
        )

    # 2. Validate Files
    processed_files = []
    for file in files:
        filename = file.filename or ""
        ext = "." + filename.split(".")[-1].lower() if "." in filename else ""
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File type '{ext}' is not allowed. Only CSV, PDF, and DOCX are permitted.",
            )
        processed_files.append(file)

    # 3. Validate Due Date
    try:
        # Assuming format like "2023-12-31T23:59:59" or with timezone
        due_at_dt = datetime.fromisoformat(dueDate.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid ISO format for dueDate.",
        )

    # 4. Resolve Target Groups
    target_group_ids: List[UUID] = []

    if group_id == "all":
        # Select all groups where user is supervisor or co-supervisor
        stmt = select(Group.group_id).where(
            or_(
                Group.supervisor_id == current_user.user_id,
                Group.cosupervisor_ids.contains([current_user.user_id]),
            )
        )
        result = await db.execute(stmt)
        target_group_ids = list(result.scalars().all())

        if not target_group_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No groups found for this supervisor.",
            )

    else:
        # Specific group
        try:
            gid = UUID(group_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid group_id format.",
            )

        # Verify access
        stmt = select(Group).where(Group.group_id == gid)
        result = await db.execute(stmt)
        group = result.scalars().first()

        if not group:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Group not found."
            )

        # Check authorization
        is_supervisor = group.supervisor_id == current_user.user_id
        is_cosupervisor = (group.cosupervisor_ids is not None) and (
            current_user.user_id in group.cosupervisor_ids
        )

        if not (is_supervisor or is_cosupervisor):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to assign tasks to this group.",
            )

        target_group_ids = [gid]

    # 5. Upload Files (if any)
    uploaded_files_data = []
    if processed_files:
        # Use existing FileService, folder 'announcements' is appropriate here as it is an announcement type
        uploaded_files_data = await FileService.upload_multiple_files(
            processed_files, folder="announcements"
        )

    # 6. Create Announcement Record
    new_announcement = Announcement(
        created_by=current_user.user_id,
        created_by_role=AnnouncementRoleEnum.supervisor,
        title=title,
        description=description,
        is_submission_request=True,  # This defines it as a submission task
        due_at=due_at_dt,
        total_marks=total_marks,
    )
    db.add(new_announcement)
    await db.flush()  # Generate ID

    # 7. Create Announcement Targets
    # We create a target for each group.
    for gid in target_group_ids:
        target = AnnouncementTarget(
            announcement_id=new_announcement.announcement_id,
            group_id=gid,
            target_role=None,  # Specific group targeting requires target_role to be None
        )
        db.add(target)

    # 8. Link Files
    file_output_list = []
    for file_meta in uploaded_files_data:
        ann_file = AnnouncementFile(
            announcement_id=new_announcement.announcement_id,
            file_name=file_meta["file_name"],
            storage_key=file_meta["storage_key"],
            mime_type=file_meta["mime_type"],
            size_bytes=file_meta["size_bytes"],
            file_type=FileTypeEnum.Document,  # Enforce Document type
            module=None,  # No module for supervisor uploads
        )
        db.add(ann_file)
        await db.flush()  # to get ID

        file_output_list.append(
            FileOutput(
                id=ann_file.file_id,
                name=ann_file.file_name,
                url=ann_file.storage_key,
                type=ann_file.file_type.value,
                mimeType=ann_file.mime_type,
                size=ann_file.size_bytes,
            )
        )

    await db.commit()
    await db.refresh(new_announcement)

    # 9. Build Response
    return SubmissionAnnouncementResponse(
        id=new_announcement.announcement_id,
        title=new_announcement.title,
        description=new_announcement.description,
        dueDate=new_announcement.due_at,
        total_marks=new_announcement.total_marks,
        assignTo=(
            group_id if group_id == "all" else str(target_group_ids[0])
        ),  # Representing assignment logic roughly
        isSubmission=new_announcement.is_submission_request,
        files=file_output_list,
        createdAt=new_announcement.created_at,
        updatedAt=new_announcement.updated_at,
    )
