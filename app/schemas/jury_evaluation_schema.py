from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.group import FYPCycleEnum
from app.models.jury_evaluation import JuryGradeEnum, ProposalStatusEnum
from app.models.milestone import JuryFormTypeEnum


class JuryEvaluationPayload(BaseModel):
    letter_grade: JuryGradeEnum = Field(
        ..., description="Letter grade assigned by the jury"
    )
    comments: Optional[str] = Field(
        None, description="Free-form feedback from the jury"
    )


class JuryEvaluationResponse(JuryEvaluationPayload):
    numeric_marks: Optional[float] = Field(
        None,
        ge=0,
        description="Numeric score computed by the database trigger",
    )
    evaluation_id: UUID
    milestone_id: UUID
    group_id: UUID
    jury_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProposalEvaluationPayload(BaseModel):
    introduction: float = Field(
        ...,
        ge=0,
        le=2,
        description="Intro section marks (0-2)",
    )
    literature_review: float = Field(
        ...,
        ge=0,
        le=2,
        description="Literature review marks (0-2)",
    )
    methodology: float = Field(
        ...,
        ge=0,
        le=2,
        description="Methodology marks (0-2)",
    )
    planning: float = Field(
        ...,
        ge=0,
        le=2,
        description="Planning & timeline marks (0-2)",
    )
    system_diagram: float = Field(
        ...,
        ge=0,
        le=2,
        description="System diagram / architecture marks (0-2)",
    )
    total_marks: Optional[float] = Field(
        None, ge=0, description="Total computed marks (auto-calculated when omitted)"
    )
    deliverables: Optional[str] = Field(
        None, description="Expected deliverables or notes shared during proposal review"
    )
    recommended_changes: Optional[str] = Field(
        None, description="Recommended changes or feedback"
    )
    project_status: ProposalStatusEnum = Field(
        ..., description="Final status recommendation for the proposal"
    )


class ProposalEvaluationResponse(ProposalEvaluationPayload):
    evaluation_id: UUID
    milestone_id: UUID
    group_id: UUID
    jury_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProposalEvaluationConfigResponse(BaseModel):
    intro_max: float = 2.0
    literature_max: float = 2.0
    methodology_max: float = 2.0
    planning_max: float = 2.0
    diagram_max: float = 2.0

    class Config:
        from_attributes = True


class ProposalEvaluationConfigUpdate(BaseModel):
    intro_max: Optional[float] = Field(None, ge=0)
    literature_max: Optional[float] = Field(None, ge=0)
    methodology_max: Optional[float] = Field(None, ge=0)
    planning_max: Optional[float] = Field(None, ge=0)
    diagram_max: Optional[float] = Field(None, ge=0)


class JuryEvaluationEnvelope(BaseModel):
    """Wrapper that tells the FE which form type is active plus the stored payload."""

    form_type: JuryFormTypeEnum
    jury: Optional[JuryEvaluationResponse] = None
    proposal: Optional[ProposalEvaluationResponse] = None


class JuryAssignedGroupResponse(BaseModel):
    class Member(BaseModel):
        full_name: str
        roll_number: str

    group_id: UUID
    project_id: UUID
    project_name: Optional[str] = None
    fyp_id: Optional[str] = None
    fyp_cycle: FYPCycleEnum
    members: List[Member] = Field(default_factory=list)
