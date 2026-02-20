# app/schemas/jury_matching_schema.py
"""Schemas for jury matching requests and responses."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class JuryMatchCandidate(BaseModel):
    """A single jury candidate recommendation for a project."""

    jury_id: str = Field(
        ..., description="Supervisor's UUID (use this to assign in DB)"
    )
    name: str = Field(..., description="Supervisor's full name")
    department: str = Field(..., description="Department name")
    designation: str = Field(
        ..., description="e.g. Professor, Associate Professor, Lecturer"
    )
    score: float = Field(..., description="Match score 0-100. Higher = better fit")
    reason: str = Field(
        ...,
        description="Human-readable explanation of why this match was made",
    )


class ProjectJuryMatches(BaseModel):
    """Jury recommendations for a single project."""

    project_id: str = Field(..., description="The project's UUID")
    title: str = Field(..., description="The project name")
    matches: List[JuryMatchCandidate] = Field(
        default_factory=list,
        description="Ranked list of jury candidates (best first)",
    )


class JuryBatchResponse(BaseModel):
    """Response wrapper for the batch jury matching endpoint."""

    results: List[ProjectJuryMatches] = Field(
        ..., description="Jury match recommendations for all projects"
    )
    total_projects: int = Field(..., description="Total number of projects processed")


class JuryReindexResponse(BaseModel):
    """Response for the jury re-index endpoint."""

    status: str = Field(..., description="ok / error")
    message: str = Field(..., description="Human-readable status message")


# ─── Jury Assignment Schemas (Background Waiter) ─────────────────────


class JuryAssignRequest(BaseModel):
    """Admin input to trigger batch jury assignment."""

    max_groups_per_jury: int = Field(
        ...,
        ge=1,
        le=20,
        description="Maximum number of projects one jury member can evaluate",
    )
    min_jury_per_project: int = Field(
        default=2,
        ge=1,
        le=5,
        description="Minimum number of jury members per project",
    )
    fyp_cycle: str = Field(
        ...,
        description="Which FYP cycle to assign for: 'fyp1' or 'fyp2'",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "max_groups_per_jury": 5,
                "min_jury_per_project": 2,
                "fyp_cycle": "fyp2",
            }
        }


class JuryAssignResponse(BaseModel):
    """Immediate response when assignment is triggered (the ticket)."""

    batch_id: str = Field(..., description="Unique batch ID to poll for status")
    status: str = Field(..., description="Current status: processing")
    message: str = Field(..., description="Human-readable message")


class JuryAssignmentDetail(BaseModel):
    """A single jury↔project assignment."""

    id: str
    project_id: str
    project_name: Optional[str] = None
    jury_id: str
    jury_name: Optional[str] = None
    score: Optional[float] = None
    reason: Optional[str] = None


class JuryBatchStatusResponse(BaseModel):
    """Polling response for batch assignment status."""

    batch_id: str
    status: str = Field(..., description="processing / completed / failed")
    error_log: Optional[str] = None
    created_at: Optional[datetime] = None
    total_assigned: int = 0
    assignments: List[JuryAssignmentDetail] = Field(
        default_factory=list,
        description="Individual assignments (populated when completed)",
    )
