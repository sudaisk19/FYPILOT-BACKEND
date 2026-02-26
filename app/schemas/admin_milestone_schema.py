from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.group import FYPCycleEnum


class AdminMilestoneBase(BaseModel):
    title: str = Field(..., min_length=1, description="Milestone name")
    weightage: Optional[float] = Field(
        None, ge=0, le=100, description="Percentage weight of this milestone"
    )
    due_date: Optional[date] = Field(
        None, description="Date when this milestone will occur"
    )
    evaluator: Optional[str] = Field(
        None, description="Who will grade or evaluate this milestone"
    )
    fyp_cycle: FYPCycleEnum = Field(
        default=FYPCycleEnum.fyp1,
        description="Cycle (fyp1 / fyp2) this milestone applies to",
    )
    is_active: bool = Field(False, description="Whether the milestone is active/visible")
    marks_visible_to_students: bool = Field(
        False,
        description="If true, students can see marks released for this milestone",
    )


class MilestoneListItem(BaseModel):
    """Slim milestone item for list views."""

    milestone_id: UUID
    title: str
    fyp_cycle: FYPCycleEnum
    is_active: bool
    due_date: Optional[date] = None
    weightage: Optional[float] = None

    class Config:
        from_attributes = True


class AdminMilestoneCreate(AdminMilestoneBase):
    """Request body when an admin creates a milestone."""


class AdminMilestoneUpdate(BaseModel):
    """Patch body; every field is optional."""

    title: Optional[str] = None
    weightage: Optional[float] = Field(None, ge=0, le=100)
    due_date: Optional[date] = None
    evaluator: Optional[str] = None
    fyp_cycle: Optional[FYPCycleEnum] = None
    is_active: Optional[bool] = None
    marks_visible_to_students: Optional[bool] = None


class AdminMilestoneResponse(AdminMilestoneBase):
    milestone_id: UUID
    created_at: datetime
    updated_at: datetime
    activated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SupervisorMilestoneResponse(AdminMilestoneResponse):
    marks_visible_to_students: Optional[bool] = Field(None, exclude=True)


class StudentMilestoneListItem(BaseModel):
    """Slim milestone item for student list view — excludes admin/internal fields."""

    milestone_id: UUID
    title: str
    fyp_cycle: FYPCycleEnum
    due_date: Optional[date] = None
    weightage: Optional[float] = None

    class Config:
        from_attributes = True


class StudentMilestoneResponse(AdminMilestoneBase):
    """Detailed milestone for students — excludes is_active and activated_at."""

    milestone_id: UUID
    marks_visible_to_students: bool
    marks: Optional[float] = Field(None, description="Student's group marks, shown only when marks_visible_to_students is true")
    created_at: datetime
    updated_at: datetime
    is_active: Optional[bool] = Field(None, exclude=True)

    class Config:
        from_attributes = True


class AdminEvaluationResponse(BaseModel):
    """Enriched evaluation row returned to admin, including supervisor name and project info."""

    evaluation_id: UUID
    milestone_id: UUID
    group_id: UUID
    supervisor_id: UUID
    supervisor_name: Optional[str] = None
    project_name: Optional[str] = None
    fyp_id: Optional[str] = None
    marks: Optional[float] = None
    feedback: Optional[str] = None
    wbs_achieved: Optional[bool] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
