from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class SupervisorEvaluationPayload(BaseModel):
    marks: Optional[float] = Field(None, description="Marks awarded for the milestone")
    feedback: Optional[str] = Field(
        None, description="Supervisor feedback for the group"
    )
    wbs_achieved: Optional[bool] = Field(
        None,
        description="Whether the group's WBS milestones were achieved",
    )


class SupervisorEvaluationResponse(SupervisorEvaluationPayload):
    evaluation_id: UUID
    milestone_id: UUID
    group_id: UUID
    supervisor_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
