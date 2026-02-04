from pydantic import BaseModel, Field
from typing import List, Optional
from uuid import UUID  # <--- THIS FIXES YOUR ERROR

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
    status: str 

class PaginatedSupervisorResponse(BaseModel):
    supervisors: List[SupervisorCardInfo]
    total: int
    page: int
    per_page: int
    total_pages: int
    has_next: bool
    has_prev: bool
    
# Projects listed inside the supervisor profile
class SupervisedProjectInfo(BaseModel):
    project_id: UUID
    name: str
    description: Optional[str]
    fyp_cycle: str
    fyp_stage: Optional[str]
    domains: List[str]

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

# For the "Save" button on capacity
class CapacityUpdateReq(BaseModel):
    capacity_max: int = Field(...,ge=0, description="Maximum groups a supervisor can take")