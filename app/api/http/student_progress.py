from __future__ import annotations

from typing import Dict, List, Optional
from uuid import UUID, uuid4
from fastapi import Form
import os
import re
from app.core.config import settings

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
    Form
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase_auth import get_current_user
from app.db import get_db, supabase
from app.models.group_milestone import SprintStatusEnum
from app.models.task import Task, TaskPriorityEnum, TaskStatusEnum
from app.models.user import RoleEnum, User
from app.repositories import group_repository, sprint_repository, task_repository
from app.schemas.task_schema import (
    MemberSummary,
    PaginatedTasksResponse,
    SprintCreate,
    SprintListResponse,
    SprintResponse,
    SprintUpdate,
    TaskAttachmentResponse,
    TaskCreate,
    TaskResponse,
    TaskUpdate,
)
from app.services.storage_service import (
    delete_file_from_supabase,
    upload_file_to_supabase,
)

router = APIRouter(prefix="/{group_id}/progress", tags=["student-progress"])

TASK_ATTACHMENTS_BUCKET = "task_attachments"

def _safe_filename(name: str) -> str:
    base, ext = os.path.splitext(name)
    # Special characters ko underscore (_) se replace karta hai
    safe_base = re.sub(r"[^A-Za-z0-9._-]", "_", base or "file")
    safe_ext = re.sub(r"[^A-Za-z0-9._-]", "_", ext)
    cleaned = f"{safe_base}{safe_ext}" if safe_ext else safe_base
    return cleaned or "file"

@router.get("/tasks", response_model=PaginatedTasksResponse)
async def list_tasks(
    group_id: UUID,
    milestone_id: Optional[UUID] = None,
    backlog_only: bool = False,
    status: Optional[TaskStatusEnum] = Query(None),
    priority: Optional[TaskPriorityEnum] = Query(None),
    assignee_id: Optional[List[UUID]] = Query(None),
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _ensure_group_access(db, group_id, current_user)

    skip = (page - 1) * per_page
    tasks, total = await task_repository.list_by_group(
        db,
        group_id,
        milestone_id=milestone_id,
        backlog_only=backlog_only,
        statuses=status,
        priorities=priority,
        assignee_ids=assignee_id,
        search=search,
        skip=skip,
        limit=per_page,
    )

    items = [_task_to_response(task) for task in tasks]
    has_next = skip + len(items) < total

    return PaginatedTasksResponse(
        tasks=items,
        total=total,
        page=page,
        per_page=per_page,
        has_next=has_next,
        has_prev=page > 1,
    )


@router.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    group_id: UUID,
    title: str = Form(...),
    description: Optional[str] = Form(None),
    priority: TaskPriorityEnum = Form(...),
    status: TaskStatusEnum = Form(...),
    assignee_id: Optional[UUID] = Form(None),
    milestone_id: Optional[UUID] = Form(None),
    due_date: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = File(None),
    links: Optional[str] = Form(None, description="Comma separated URLs"), 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    print("Received priority in endpoint:", priority, type(priority))
    await _ensure_group_access(db, group_id, current_user)

    if assignee_id:
        await _ensure_member(db, group_id, assignee_id)
    if milestone_id:
        await _ensure_sprint(db, milestone_id, group_id)

    from datetime import date
    due_date_obj = date.fromisoformat(due_date) if due_date else None

    task = await task_repository.create_task(
        db,
        {
            "group_id": group_id,
            "title": title,
            "description": description,
            "priority": priority.value,
            "status": status.value,
            "assignee_id": assignee_id,
            "milestone_id": milestone_id,
            "due_date": due_date_obj,
            "group_id": group_id,
        },
    )
    if links:
        from app.models.task_attachment import TaskAttachment
        link_list = [l.strip() for l in links.split(",") if l.strip()]
        for link in link_list:
            db.add(TaskAttachment(
                task_id=task.task_id,
                file_name="External Link", # Frontend se bhi name le sakte hain
                storage_key=link,         # Direct URL save ho raha hai
                mime_type="application/url",
                size_bytes=0
            ))
    
    if files:
        for upload in files:
            if not upload.filename:
                continue

            # Naming consistent with your build_storage_key logic
            storage_key = f"tasks/{group_id}/{task.task_id}/{upload.filename}"
            
            # File upload to Supabase (using existing service)
            size_bytes = await upload_file_to_supabase(
                supabase,
                bucket="task_attachments", # Ensure this bucket exists in Supabase
                storage_key=storage_key,
                upload=upload,
            )

            # DB mein attachment save karein
            from app.models.task_attachment import TaskAttachment
            attachment = TaskAttachment(
                task_id=task.task_id,
                file_name=upload.filename,
                storage_key=storage_key,
                mime_type=upload.content_type,
                size_bytes=size_bytes
            )
            db.add(attachment)
            
    await db.commit()

    full_task = await task_repository.get_with_details(db, task.task_id)
    if not full_task:
        raise HTTPException(status_code=500, detail="Unable to load task")
    return _task_to_response(full_task)


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(
    group_id: UUID,
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _ensure_group_access(db, group_id, current_user)
    task = await _get_task_for_group(db, task_id, group_id)
    return _task_to_response(task)


@router.patch("/tasks/{task_id}", response_model=TaskResponse)
async def update_task(
    group_id: UUID,
    task_id: UUID,
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    status: Optional[TaskStatusEnum] = Form(None),
    priority: Optional[TaskPriorityEnum] = Form(None),
    assignee_id: Optional[UUID] = Form(None),
    milestone_id: Optional[UUID] = Form(None),
    due_date: Optional[str] = Form(None),
    # Announcement style: Kaunsi purani files rakhni hain?
    keep_file_ids: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = File(None),
    links: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _ensure_group_access(db, group_id, current_user)
    task = await _get_task_for_group(db, task_id, group_id)

    # 1. Base Task Fields Update
    updates = {}
    if title is not None: updates["title"] = title
    if description is not None: updates["description"] = description
    if status is not None: updates["status"] = status.value
    if priority is not None: updates["priority"] = priority.value
    if assignee_id is not None:
        await _ensure_member(db, group_id, assignee_id)
        updates["assignee_id"] = assignee_id
    if milestone_id is not None:
        await _ensure_sprint(db, milestone_id, group_id)
        updates["milestone_id"] = milestone_id

    if updates:
        await task_repository.update_task(db, task_id, updates)

    # 2. Sync Files (Keep or Delete logic)
    if keep_file_ids is not None:
        try:
            # Jo IDs list mein NAI hain, unhein delete kar dain
            keep_ids = {UUID(fid.strip()) for fid in keep_file_ids.split(",") if fid.strip()}
            
            # Repository se current attachments mangwaein
            current_attachments = await task_repository.list_attachments(db, task_id)
            for att in current_attachments:
                if att.attachment_id not in keep_ids:
                    # Supabase se file urayein
                    await delete_file_from_supabase(
    client=supabase, 
    bucket="task_attachments", 
    storage_key=att.storage_key
)
                    # DB se record urayein
                    await db.delete(att)
        except ValueError:
            pass # Invalid ID format ko ignore karein

    # 3. New Files Upload (Post wali logic)
    if files:
        for upload in files:
            if not upload.filename: continue
            safe_name = _safe_filename(upload.filename)
            # Wahi storage path jo POST mein tha
            storage_key = f"tasks/{group_id}/{task_id}/{safe_name}"
            
            size_bytes = await upload_file_to_supabase(
                supabase, bucket="task_attachments", storage_key=storage_key, upload=upload
            )
            
            from app.models.task_attachment import TaskAttachment
            db.add(TaskAttachment(
                task_id=task_id, 
                file_name=upload.filename, 
                storage_key=storage_key,
                mime_type=upload.content_type, 
                size_bytes=size_bytes
            ))
    if links:
        from app.models.task_attachment import TaskAttachment
        for link in [l.strip() for l in links.split(",") if l.strip()]:
            db.add(TaskAttachment(
                task_id=task_id,
                file_name="External Link",
                storage_key=link,
                mime_type="application/url",
                size_bytes=0
            ))

    await db.commit()
    
    refreshed = await _get_task_for_group(db, task_id, group_id)
    return _task_to_response(refreshed)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    group_id: UUID,
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _ensure_group_access(db, group_id, current_user)
    
    # Task fetch karein details ke saath (attachments load karne ke liye)
    task = await task_repository.get_with_details(db, task_id)
    if not task or task.group_id != group_id:
        raise HTTPException(status_code=404, detail="Task not found")

    # 1. Storage se saari files delete karein
    for attachment in task.attachments:
        # Check karein agar ye file hai (link nahi)
        if attachment.storage_key and not attachment.storage_key.startswith("http"):
            await delete_file_from_supabase(
                client=supabase,
                bucket="task_attachments", # Ya aapka TASK_ATTACHMENTS_BUCKET variable
                storage_key=attachment.storage_key,
            )

    # 2. Database se task delete karein 
    # (Aapka repository automatic attachments bhi delete kar dega agar cascade delete on hai)
    deleted = await task_repository.delete_task(db, task_id)
    if not deleted:
        raise HTTPException(status_code=500, detail="Unable to delete task")
    
    await db.commit()
    return None


@router.get("/sprints", response_model=SprintListResponse)
async def list_sprints(
    group_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _ensure_group_access(db, group_id, current_user)

    # Summary view ke liye tasks load karne ki zaroorat nahi hai
    sprints = await sprint_repository.list_by_group(db, group_id, include_tasks=False)
    
    # Milestone IDs nikal kar unke aggregated stats layein
    milestone_ids = [s.milestone_id for s in sprints]
    stats = await sprint_repository.task_counts(db, milestone_ids)
    
    # Payload banate waqt har sprint ko uske specific stats bhejain
    payload = [_sprint_to_response(sprint, stats.get(sprint.milestone_id)) for sprint in sprints]
    
    return SprintListResponse(sprints=payload, total=len(payload))

@router.post("/sprints", response_model=SprintResponse, status_code=status.HTTP_201_CREATED)
async def create_sprint(
    group_id: UUID,
    payload: SprintCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _ensure_group_access(db, group_id, current_user)
    
    # 1. Improved Date Validation
    from datetime import date
    today = date.today()
    if payload.start_date < today:
        raise HTTPException(
            status_code=400, 
            detail="Sprint cannot start in the past"
        )
    _validate_dates(payload.start_date, payload.end_date)

    # 2. Default Status 'planned'
    # Repository ko payload bhejte waqt status ensure karein
    sprint = await sprint_repository.create_sprint(
        db,
        group_id=group_id,
        title=payload.title,
        sprint_goal=payload.sprint_goal,
        start_date=payload.start_date,
        end_date=payload.end_date,
        status=SprintStatusEnum.Planned.value 
    )
    await db.commit()

    # 3. Fetch full details for response
    full = await sprint_repository.get_with_tasks(db, sprint.milestone_id)
    return _sprint_to_response(full, None)


@router.get("/sprints/{sprint_id}", response_model=SprintResponse)
async def get_sprint(
    group_id: UUID,
    sprint_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _ensure_group_access(db, group_id, current_user)
    
    # Eager load tasks (with assignee and attachments) using repository helper
    sprint = await sprint_repository.get_with_tasks(db, sprint_id)
    
    if not sprint or sprint.group_id != group_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sprint not found")

    # 1. Base response banayein (Status counts calculate honge)
    resp = _sprint_to_response(sprint, None)
    
    # 2. Tasks ki detailed mapping karein (Boards ke liye)
    if hasattr(sprint, "tasks") and sprint.tasks:
        resp.tasks = [_task_to_response(task) for task in sprint.tasks]
    else:
        resp.tasks = []
        
    return resp

@router.patch("/sprints/{sprint_id}", response_model=SprintResponse)
async def update_sprint(
    group_id: UUID,
    sprint_id: UUID,
    payload: SprintUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _ensure_group_access(db, group_id, current_user)
    sprint = await sprint_repository.get_by_id(db, sprint_id)
    if not sprint or sprint.group_id != group_id:
        raise HTTPException(status_code=404, detail="Not found")

    # 1. model_dump use karein aur explicitly None values ko filter out karein
    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}

    if not updates:
        # Agar kuch update karne ko nahi hai toh purana sprint return kar dain
        return _sprint_to_response(sprint, None)

    # 2. Date Validation (Sirf agar nayi dates aai hain)
    start_date = updates.get("start_date", sprint.start_date)
    end_date = updates.get("end_date", sprint.end_date)
    _validate_dates(start_date, end_date)

    # 3. Status Logic
    new_status = updates.get("status")
    if new_status and new_status == SprintStatusEnum.Active.value:
        existing = await sprint_repository.get_active_sprint(db, group_id)
        if existing and existing.milestone_id != sprint_id:
            raise HTTPException(
                status_code=400,
                detail="Another sprint is already active",
            )

    # 4. DB Update
    updated = await sprint_repository.update_sprint(db, sprint_id, updates)
    await db.commit()

    # Refreshed data load karein detail view ke liye
    refreshed = await sprint_repository.get_with_tasks(db, sprint_id)
    resp = _sprint_to_response(refreshed, None)
    if hasattr(refreshed, "tasks") and refreshed.tasks:
        resp.tasks = [_task_to_response(t) for t in refreshed.tasks]
    
    return resp

@router.delete("/sprints/{sprint_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sprint(
    group_id: UUID,
    sprint_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _ensure_group_access(db, group_id, current_user)
    
    # 1. Sprint fetch karein
    sprint = await sprint_repository.get_with_tasks(db, sprint_id)
    if not sprint or sprint.group_id != group_id:
        raise HTTPException(status_code=404, detail="Sprint not found")

    # 2. Tasks ko pehle hi Backlog mein move karein (Explicit Commit)
    if hasattr(sprint, "tasks") and sprint.tasks:
        from app.models.task import Task
        from sqlalchemy import update
        
        # Tasks ko un-link karein
        await db.execute(
            update(Task)
            .where(Task.milestone_id == sprint_id)
            .values(milestone_id=None)
        )
        # Yahan commit karna zaroori hai taake tasks ka relation khatam ho jaye
        await db.commit() 
        # Session refresh karein taake delete safe ho
        await db.begin() 

    # 3. Ab Sprint delete karein (Ab tasks delete nahi honge kyunke unka link toot chuka hai)
    deleted = await sprint_repository.delete_sprint(db, sprint_id)
    if not deleted:
        raise HTTPException(status_code=500, detail="Unable to delete sprint")
    
    await db.commit()
    return None


async def _ensure_group_access(
    db: AsyncSession,
    group_id: UUID,
    current_user: User,
):
    group = await group_repository.get_by_id(db, group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    if current_user.role == RoleEnum.admin:
        return group

    if current_user.role == RoleEnum.supervisor:
        cosupervisors = group.cosupervisor_ids or []
        if group.supervisor_id == current_user.user_id or current_user.user_id in cosupervisors:
            return group

    is_member = await group_repository.check_membership(db, group_id, current_user.user_id)
    if not is_member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not allowed to manage this group's progress",
        )
    return group


async def _ensure_member(db: AsyncSession, group_id: UUID, student_id: UUID) -> None:
    is_member = await group_repository.check_membership(db, group_id, student_id)
    if not is_member:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Assignee must belong to the group",
        )


async def _ensure_sprint(db: AsyncSession, milestone_id: UUID, group_id: UUID) -> None:
    sprint = await sprint_repository.get_by_id(db, milestone_id)
    if not sprint or sprint.group_id != group_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sprint does not belong to this group",
        )


async def _get_task_for_group(
    db: AsyncSession, task_id: UUID, group_id: UUID
) -> Task:
    task = await task_repository.get_with_details(db, task_id)
    if not task or task.group_id != group_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return task


def _task_to_response(task: Task) -> TaskResponse:
    assignee = _member_summary(task)
    # Supabase Public Storage ka base path
    BASE_URL = f"{settings.supabase_url}/storage/v1/object/public/task_attachment/"
    
    attachments_payload = []
    for att in task.attachments:
        # 1. Pydantic model se data nikal kar dictionary banayein
        att_data = TaskAttachmentResponse.model_validate(att, from_attributes=True).model_dump()
        
        # 2. Logic: Agar storage_key link hai (starts with http) toh wahi rakho, 
        # warna BASE_URL ke sath joro
        is_link = str(att.storage_key).startswith(("http://", "https://"))
        att_data["url"] = att.storage_key if is_link else f"{BASE_URL}{att.storage_key}"
        
        # 3. Wapas model mein convert karke list mein daal dein
        attachments_payload.append(TaskAttachmentResponse(**att_data))

    return TaskResponse(
        task_id=task.task_id,
        group_id=task.group_id,
        milestone_id=task.milestone_id,
        assignee=assignee,
        title=task.title,
        description=task.description,
        priority=task.priority,
        status=task.status,
        due_date=task.due_date,
        created_at=task.created_at,
        updated_at=task.updated_at,
        attachments=attachments_payload, # <-- Updated list yahan use hogi
    )

def _member_summary(task: Task) -> Optional[MemberSummary]:
    student = task.assignee
    if not student or not student.user:
        return None
    full_name = student.user.full_name
    initials = None
    if full_name:
        parts = [part for part in full_name.split() if part]
        if parts:
            initials = "".join(part[0].upper() for part in parts[:2])
    return MemberSummary(
        user_id=student.user_id,
        full_name=full_name,
        avatar_url=student.user.profile_avatar,
        initials=initials,
    )


def _sprint_to_response(
    sprint, stats: Optional[Dict[str, int]]
) -> SprintResponse:
    # 1. Stats se counts nikalain (Repository se filtered data)
    status_counts = stats or {}
    
    # Check karein ke total tasks kitne hain
    total_tasks = sum(status_counts.values())
    
    # Sirf 'done' status waale tasks ka count
    completed = status_counts.get(TaskStatusEnum.Done.value, 0)

    # Note: Hum yahan 'sprint.tasks' ko touch nahi kar rahe taake 
    # Lazy Loading wala error (MissingGreenlet) na aaye.
    return SprintResponse(
        milestone_id=sprint.milestone_id,
        group_id=sprint.group_id,
        title=sprint.title,
        sprint_goal=sprint.sprint_goal,
        start_date=sprint.start_date,
        end_date=sprint.end_date,
        status=sprint.status,
        created_at=sprint.created_at,
        updated_at=sprint.updated_at,
        total_tasks=total_tasks,
        completed_tasks=completed,
    )


def _validate_dates(start_date, end_date) -> None:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sprint start date cannot be after end date",
        )


async def _store_attachment(
    db: AsyncSession,
    task: Task,
    file: UploadFile,
):
    ext = ""
    if file.filename and "." in file.filename:
        ext = file.filename[file.filename.rfind(".") :]
    storage_key = f"groups/{task.group_id}/tasks/{task.task_id}/{uuid4()}{ext}"

    size_bytes = await upload_file_to_supabase(
        client=supabase,
        bucket=TASK_ATTACHMENTS_BUCKET,
        storage_key=storage_key,
        upload=file,
    )

    return await task_repository.add_attachment(
        db,
        task.task_id,
        file_name=file.filename or "attachment",
        storage_key=storage_key,
        mime_type=file.content_type,
        size_bytes=size_bytes,
    )
