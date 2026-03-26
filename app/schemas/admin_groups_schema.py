from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

import app.schemas.group_schema as gs
from app.models.group import FYPCycleEnum


# --- Existing Pagination Schemas (Keep as is) ---
class GroupCardInfo(BaseModel):
    group_id: str
    project_name: Optional[str] = None
    fyp_cycle: Optional[str] = None
    fyp_stage: Optional[str] = None
    members_count: int = 0
    supervisor_name: Optional[str] = None
    cosupervisor_name: Optional[str] = None
    cohort: Optional[str] = None


class PaginatedGroupResponse(BaseModel):
    groups: List[GroupCardInfo]
    total: int
    page: int
    per_page: int
    total_pages: int
    has_next: bool
    has_prev: bool


# --- NEW: Admin Detailed Schemas (Optimized for Swagger) ---


class AdminGroupMemberInfo(gs.GroupMemberInfo):
    """Detailed student info for Admin dashboard."""

    roll_number: str
    department: str
    cgpa: float
    experience: Optional[str] = None
    skills: List[Any] = []
    portfolio_projects: Dict[str, Any] = Field(default_factory=dict)


class AdminGroupProfileResponse(BaseModel):
    """Full Group Profile for Admin with explicit structure."""

    group: dict = Field(..., description="Group metadata")
    members: List[AdminGroupMemberInfo]
    supervisors: Dict[str, Any]
    project: Optional[gs.ProjectInfo] = None
    # If invites info is causing issues, we can use a simple dict here too
    invites: Optional[dict] = None


# ─── Admin Supervisor Assignment ───────────────────────────────────────────
class AssignSupervisorRequest(BaseModel):
    """Request body for admin to assign supervisor/cosupervisor"""

    supervisor_id: UUID = Field(..., description="UUID of the supervisor to assign")

    class Config:
        json_schema_extra = {
            "example": {
                "supervisor_id": "550e8400-e29b-41d4-a716-446655440000",
                "role": "supervisor",
            }
        }


class AssignSupervisorResponse(BaseModel):
    """Response after successful supervisor assignment"""

    message: str
    group_id: str
    project_name: str
    supervisor_id: str
    supervisor_name: str
    role: str


class CohortCycleUpdateRequest(BaseModel):
    target_cycle: FYPCycleEnum = Field(
        ..., description="Cycle to apply to every group in the cohort"
    )


class CohortCycleUpdateResponse(BaseModel):
    message: str
    cohort: str
    target_cycle: FYPCycleEnum
    updated_count: int
