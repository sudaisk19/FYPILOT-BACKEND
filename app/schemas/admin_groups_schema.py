<<<<<<< HEAD
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

import app.schemas.group_schema as gs

=======
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime
import app.schemas.group_schema as gs 
>>>>>>> 91164a0 (Admin: Implemented GET APIs for students, supervisors, and groups)

# --- Existing Pagination Schemas (Keep as is) ---
class GroupCardInfo(BaseModel):
    group_id: str
    project_name: Optional[str] = None
    project_description: Optional[str] = None
    fyp_cycle: Optional[str] = None
    fyp_stage: Optional[str] = None
    cohort_year: Optional[int] = None
    members_count: int = 0
    supervisor_name: Optional[str] = None
    cosupervisor_name: Optional[str] = None
    domains: List[str] = []
    tech_tags: List[str] = []

<<<<<<< HEAD

=======
>>>>>>> 91164a0 (Admin: Implemented GET APIs for students, supervisors, and groups)
class PaginatedGroupResponse(BaseModel):
    groups: List[GroupCardInfo]
    total: int
    page: int
    per_page: int
    total_pages: int
    has_next: bool
    has_prev: bool

<<<<<<< HEAD

# --- NEW: Admin Detailed Schemas (Optimized for Swagger) ---


class AdminGroupMemberInfo(gs.GroupMemberInfo):
    """Detailed student info for Admin dashboard."""

=======
# --- NEW: Admin Detailed Schemas (Optimized for Swagger) ---

class AdminGroupMemberInfo(gs.GroupMemberInfo):
    """Detailed student info for Admin dashboard."""
>>>>>>> 91164a0 (Admin: Implemented GET APIs for students, supervisors, and groups)
    roll_number: str
    department: str
    cgpa: float
    experience: Optional[str] = None
<<<<<<< HEAD
    skills: List[Any] = []
    portfolio_projects: List[str] = []


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
    group_name: str
    supervisor_id: str
    supervisor_name: str
    role: str
=======
    skills: List[Any] = [] 
    portfolio_projects: List[str] = []

class AdminGroupProfileResponse(BaseModel):
    """Full Group Profile for Admin with explicit structure."""
    group: dict = Field(..., description="Group metadata") 
    members: List[AdminGroupMemberInfo]
    supervisors: Dict[str, Optional[gs.SupervisorInfo]]
    project: Optional[gs.ProjectInfo] = None
    # If invites info is causing issues, we can use a simple dict here too
    invites: Optional[dict] = None
    
>>>>>>> 91164a0 (Admin: Implemented GET APIs for students, supervisors, and groups)
