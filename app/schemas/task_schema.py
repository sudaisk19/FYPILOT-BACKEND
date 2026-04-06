from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.group_milestone import SprintStatusEnum
from app.models.task import TaskPriorityEnum, TaskStatusEnum


class MemberSummary(BaseModel):
    user_id: UUID
    full_name: str
    avatar_url: Optional[str] = None
    initials: Optional[str] = Field(
        default=None,
        description="Convenience field for showing avatar chips",
    )


class TaskAttachmentResponse(BaseModel):
    attachment_id: UUID
    file_name: str
    storage_key: str
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    uploaded_at: Optional[datetime] = None
    url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class TaskCreate(BaseModel):
    title: str = Field(..., max_length=255)
    description: Optional[str] = Field(default=None, max_length=4000)
    priority: TaskPriorityEnum = TaskPriorityEnum.Medium
    status: TaskStatusEnum = TaskStatusEnum.ToDo
    assignee_id: Optional[UUID] = None
    milestone_id: Optional[UUID] = None
    due_date: Optional[date] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = Field(default=None, max_length=4000)
    priority: Optional[TaskPriorityEnum] = None
    status: Optional[TaskStatusEnum] = None
    assignee_id: Optional[UUID] = None
    milestone_id: Optional[UUID] = None
    due_date: Optional[date] = None


class TaskResponse(BaseModel):
    task_id: UUID
    group_id: UUID
    milestone_id: Optional[UUID] = None
    assignee: Optional[MemberSummary] = None
    title: str
    description: Optional[str] = None
    priority: TaskPriorityEnum
    status: TaskStatusEnum
    due_date: Optional[date] = None
    created_at: datetime
    updated_at: datetime
    attachments: List[TaskAttachmentResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class PaginatedTasksResponse(BaseModel):
    tasks: List[TaskResponse]
    total: int
    page: int
    per_page: int
    has_next: bool
    has_prev: bool


class SprintCreate(BaseModel):
    title: str = Field(..., max_length=255)
    sprint_goal: Optional[str] = Field(default=None, max_length=2000)
    start_date: date
    end_date: date


class SprintUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    sprint_goal: Optional[str] = Field(default=None, max_length=2000)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[SprintStatusEnum] = None


class SprintResponse(BaseModel):
    milestone_id: UUID
    group_id: UUID
    title: str
    sprint_goal: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: SprintStatusEnum
    created_at: datetime
    updated_at: datetime
    total_tasks: int = 0
    completed_tasks: int = 0
    tasks: List[TaskResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class SprintListResponse(BaseModel):
    sprints: List[SprintResponse]
    total: int
