from datetime import date, datetime
from typing import Optional
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
    activity: Optional[str] = Field(
        None, description="Short description of what students must do"
    )
    fyp_cycle: FYPCycleEnum = Field(
        default=FYPCycleEnum.fyp1,
        description="Cycle (fyp1 / fyp2) this milestone applies to",
    )


class AdminMilestoneCreate(AdminMilestoneBase):
    """Request body when an admin creates a milestone."""


class AdminMilestoneUpdate(BaseModel):
    """Patch body; every field is optional."""

    title: Optional[str] = None
    weightage: Optional[float] = Field(None, ge=0, le=100)
    due_date: Optional[date] = None
    evaluator: Optional[str] = None
    activity: Optional[str] = None
    fyp_cycle: Optional[FYPCycleEnum] = None


class AdminMilestoneResponse(AdminMilestoneBase):
    milestone_id: UUID
    admin_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
