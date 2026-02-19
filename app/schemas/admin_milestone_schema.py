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
    due_date: Optional[date] = Field(None, description="Date when this milestone will occur")
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


class AdminMilestoneCreate(AdminMilestoneBase):
    """Request body when an admin creates a milestone."""
    pass


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
    admin_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    activated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

