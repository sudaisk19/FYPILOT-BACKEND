<<<<<<< HEAD
from typing import List, Optional
from uuid import UUID  # <--- THIS FIXES YOUR ERROR

from pydantic import BaseModel, Field


=======
from pydantic import BaseModel, Field
from typing import List, Optional
from uuid import UUID  # <--- THIS FIXES YOUR ERROR

>>>>>>> 91164a0 (Admin: Implemented GET APIs for students, supervisors, and groups)
# Mirroring your Student pagination style
class SupervisorCardInfo(BaseModel):
    user_id: str
    full_name: str
    email: str
    department: Optional[str]
    designation: Optional[str]
    domains: List[str]
    capacity_max: int
    capacity_filled: int
    free_slots: int
<<<<<<< HEAD
    status: str

=======
    status: str 
>>>>>>> 91164a0 (Admin: Implemented GET APIs for students, supervisors, and groups)

class PaginatedSupervisorResponse(BaseModel):
    supervisors: List[SupervisorCardInfo]
    total: int
    page: int
    per_page: int
    total_pages: int
    has_next: bool
    has_prev: bool
<<<<<<< HEAD


=======
    
>>>>>>> 91164a0 (Admin: Implemented GET APIs for students, supervisors, and groups)
# Projects listed inside the supervisor profile
class SupervisedProjectInfo(BaseModel):
    project_id: UUID
    name: str
    description: Optional[str]
    fyp_cycle: str
    fyp_stage: Optional[str]
    domains: List[str]

<<<<<<< HEAD

=======
>>>>>>> 91164a0 (Admin: Implemented GET APIs for students, supervisors, and groups)
# Full Profile Response
class AdminSupervisorProfileOut(BaseModel):
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
    domains: List[str]
    industries: List[str]
    projects: List[SupervisedProjectInfo]

<<<<<<< HEAD

# For the "Save" button on capacity
class CapacityUpdateReq(BaseModel):
    capacity_max: int = Field(
        ..., ge=0, description="Maximum groups a supervisor can take"
    )


# For searchable dropdown in admin assignment forms
class SupervisorDropdownItem(BaseModel):
    """
    Minimal supervisor info for fast dropdown/combobox.

    Frontend displays: "{full_name} - {department}"
    Frontend sends: user_id when form is submitted
    Frontend disables: items where is_available=false
    """

    user_id: str  # ← Sent to backend on form submit
    full_name: str  # ← Display in dropdown
    department: Optional[str] = None  # ← Display in dropdown (e.g., "Dr. Ahmed - CS")
    is_available: bool = True  # ← Disable selection if False (supervisor is FULL)

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "550e8400-e29b-41d4-a716-446655440000",
                "full_name": "Dr. Ahmed Khan",
                "department": "Computer Science",
                "is_available": True,
            }
        }
=======
# For the "Save" button on capacity
class CapacityUpdateReq(BaseModel):
    capacity_max: int = Field(...,ge=0, description="Maximum groups a supervisor can take")
>>>>>>> 91164a0 (Admin: Implemented GET APIs for students, supervisors, and groups)
