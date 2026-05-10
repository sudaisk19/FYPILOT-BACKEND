from typing import List, Optional
from uuid import UUID  # <--- THIS FIXES YOUR ERROR

from pydantic import BaseModel, Field


# Mirroring your Student pagination style
class FacultyCardInfo(BaseModel):
    user_id: str
    full_name: str
    email: str
    department: Optional[str]
    designation: Optional[str]
    domains: List[str]
    capacity_max: int
    capacity_filled: int
    free_slots: int
    status: str
    is_supervisor: bool
    is_jury: bool
    is_active: bool


class PaginatedFacultyResponse(BaseModel):
    faculty: List[FacultyCardInfo]
    total: int
    page: int
    per_page: int
    total_pages: int
    has_next: bool
    has_prev: bool


# Projects listed inside the supervisor profile
class SupervisedProjectInfo(BaseModel):
    group_id: UUID
    project_id: UUID
    fyp_id: Optional[str] = None
    name: str
    description: Optional[str]
    fyp_cycle: str
    fyp_stage: Optional[str]
    domains: List[str]


# Full Profile Response
class AdminFacultyProfileOut(BaseModel):
    user_id: UUID
    full_name: str
    email: str
    profile_avatar: Optional[str]
    department: Optional[str]
    designation: Optional[str]
    office: Optional[str]
    requirements: List[str]
    project_type: Optional[str]
    capacity_max: int
    capacity_filled: int
    is_supervisor: bool
    is_jury: bool
    is_active: bool
    domains: List[str]
    industries: List[str]
    projects: List[SupervisedProjectInfo]


# For the "Save" button on capacity
class CapacityUpdateReq(BaseModel):
    capacity_max: Optional[int] = Field(
        None, ge=0, description="Maximum groups a faculty member can take"
    )
    is_supervisor: Optional[bool] = Field(
        None, description="Toggle faculty availability for supervision"
    )
    is_jury: Optional[bool] = Field(
        None, description="Toggle faculty availability for jury duties"
    )


# For searchable dropdown in admin assignment forms
class FacultyDropdownItem(BaseModel):
    """
    Minimal faculty info for fast dropdown/combobox.

    Frontend displays: "{full_name} - {department}"
    Frontend sends: user_id when form is submitted
    Frontend disables: items where is_available=false
    """

    user_id: str  # ← Sent to backend on form submit
    full_name: str  # ← Display in dropdown
    department: Optional[str] = None  # ← Display in dropdown (e.g., "Dr. Ahmed - CS")
    is_available: bool = True  # ← Disable selection if False (faculty is FULL)

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "550e8400-e29b-41d4-a716-446655440000",
                "full_name": "Dr. Ahmed Khan",
                "department": "Computer Science",
                "is_available": True,
            }
        }
