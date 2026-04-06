# app/schemas/jury_matching_schema.py
"""Schemas for jury matching requests and responses."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class JuryReindexResponse(BaseModel):
    """Response for the jury re-index endpoint."""

    status: str = Field(..., description="ok / error")
    message: str = Field(..., description="Human-readable status message")


# ─── Jury Assignment Schemas (Background Waiter) ─────────────────────


class JuryAssignRequest(BaseModel):
    """Admin input to trigger batch jury assignment."""

    max_groups_per_pair: int = Field(
        ...,
        ge=1,
        le=10,
        description="Maximum number of projects one jury pair can evaluate",
    )
    min_jury_per_project: int = Field(
        default=1,
        ge=1,
        le=10,
        description="Minimum number of jury pairs per project",
    )
    fyp_cycles: List[str] = Field(
        ...,
        description="Which FYP cycles to assign for, e.g. ['fyp1'], ['fyp2'], or ['fyp1','fyp2']",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "max_groups_per_pair": 5,
                "min_jury_per_project": 1,
                "fyp_cycles": ["fyp1"],
            }
        }


class JuryAssignResponse(BaseModel):
    """Immediate response when assignment is triggered (the ticket)."""

    batch_id: str = Field(..., description="Unique batch ID to poll for status")
    status: str = Field(..., description="Current status: processing")
    message: str = Field(..., description="Human-readable message")


# ─── Jury Pair Schemas ───────────────────────────────────────────────


class JuryPairDetail(BaseModel):
    """Detail of a jury pair."""

    jury_id: str = Field(..., description="Pair UUID")
    jury_number: Optional[int] = Field(None, description="Sequential number: 1, 2, 3…")
    faculty_1_id: str
    faculty_1_name: Optional[str] = None
    faculty_2_id: str
    faculty_2_name: Optional[str] = None


class JuryPairDropdownItem(BaseModel):
    """Minimal jury pair info for dropdown selection."""

    jury_id: str = Field(..., description="Pair UUID (value)")
    label: str = Field(
        ...,
        description="Display label e.g. 'Jury 1 — Dr. Ali & Dr. Sara'",
    )
    faculty_1_name: Optional[str] = None
    faculty_2_name: Optional[str] = None


# ─── Assignment Detail Schemas ───────────────────────────────────────


class JuryAssignmentDetail(BaseModel):
    """A single jury-pair ↔ project assignment."""

    id: str
    project_id: str
    project_name: Optional[str] = None
    pair_id: Optional[str] = None
    jury_number: Optional[int] = None
    faculty_1_name: Optional[str] = None
    faculty_2_name: Optional[str] = None
    score: Optional[float] = None
    reason: Optional[str] = None


class JuryBatchStatusResponse(BaseModel):
    """Polling response for batch assignment status."""

    batch_id: str
    status: str = Field(..., description="processing / completed / failed")
    fyp_cycle: Optional[str] = None
    error_log: Optional[str] = None
    created_at: Optional[datetime] = None
    total_assigned: int = 0
    assignments: List[JuryAssignmentDetail] = Field(
        default_factory=list,
        description="Individual assignments (populated when completed)",
    )


# ─── Patch / Manual Edit Schemas ─────────────────────────────────────


class JuryAssignmentPatchRequest(BaseModel):
    """Request to change the jury pair for a specific assignment."""

    pair_id: str = Field(..., description="New jury pair UUID to assign")


class JuryAssignmentPatchResponse(BaseModel):
    """Response after updating a jury assignment."""

    id: str
    project_id: str
    old_pair_id: Optional[str] = None
    new_pair_id: str
    message: str = "Jury assignment updated successfully"


# ─── Delete Response ─────────────────────────────────────────────────


class JuryDeleteResponse(BaseModel):
    """Response after clearing all jury assignments."""

    message: str
    deleted_assignments: int = 0
    deleted_pairs: int = 0
    deleted_batches: int = 0


# ─── Frontend-Matched Grouped Response Schemas ──────────────────────


class GroupMemberInfo(BaseModel):
    """A student member of a group."""

    name: str
    rollNumber: str


class AssignedGroupInfo(BaseModel):
    """A group/project assigned to a jury pair (maps to a JuryAssignment row)."""

    id: str = Field(
        ..., description="Assignment ID (use for PATCH /assignments/{id}/jury)"
    )
    projectName: str
    fypId: Optional[str] = None
    fypCycle: Optional[str] = None
    members: List[GroupMemberInfo] = Field(default_factory=list)


class JurySupervisorInfo(BaseModel):
    """Faculty member info within a jury pair."""

    name: str
    department: Optional[str] = None


class JuryMatchItem(BaseModel):
    """A jury pair with its assigned groups — matches frontend MOCK_JURY_MATCHES."""

    id: str = Field(..., description="Jury pair ID")
    jury_number: Optional[int] = Field(
        None, description="Sequential number: Jury 1, 2, …"
    )
    supervisors: List[JurySupervisorInfo] = Field(default_factory=list)
    groups: List[AssignedGroupInfo] = Field(default_factory=list)


class JuryAssignmentsResponse(BaseModel):
    """Response for jury assignment endpoints — grouped by jury pair."""

    batch_id: str
    status: str = Field(..., description="processing / completed / failed / none")
    fyp_cycles: Optional[List[str]] = None
    error_log: Optional[str] = None
    created_at: Optional[datetime] = None
    total_assigned: int = 0
    jury_matches: List[JuryMatchItem] = Field(
        default_factory=list,
        description="Assignments grouped by jury pair (populated when completed)",
    )
