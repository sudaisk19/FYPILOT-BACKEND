# app/schemas/dashboard_schema.py

from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class GroupMember(BaseModel):
    """Group member information"""

    user_id: UUID
    full_name: str
    email: str
    role: str


class GroupInfo(BaseModel):
    """Group information for dashboard"""

    group_id: UUID
    group_name: str
    project_title: str
    status: str
    created_at: str
    updated_at: str
    # For students: their role in the group
    role: Optional[str] = None
    # For supervisors: number of members
    members_count: Optional[int] = None
    # For supervisors: list of members
    members: Optional[List[GroupMember]] = None


class DashboardStats(BaseModel):
    """Dashboard statistics"""

    total_groups: int
    active_groups: int
    pending_tasks: Optional[int] = None
    total_students: Optional[int] = None
    completed_projects: Optional[int] = None


class StudentProfileSummary(BaseModel):
    """Student profile summary for dashboard"""

    student_id: str
    department: str
    year: str
    enrollment_date: str
    cgpa: Optional[float] = None
    status: str


class SupervisorProfileSummary(BaseModel):
    """Supervisor profile summary for dashboard"""

    supervisor_id: str
    department: str
    expertise: List[str]
    max_groups: int
    current_groups: int
    status: str


class AdminProfileSummary(BaseModel):
    """Admin profile summary for dashboard"""

    admin_id: str
    department: str
    permissions: List[str]
    status: str


class StudentDashboardResponse(BaseModel):
    """Dashboard response for students"""

    student_profile: StudentProfileSummary
    groups: List[GroupInfo]
    stats: DashboardStats


class SupervisorDashboardResponse(BaseModel):
    """Dashboard response for supervisors"""

    supervisor_profile: SupervisorProfileSummary
    managed_groups: List[GroupInfo]
    stats: DashboardStats


class AdminDashboardResponse(BaseModel):
    """Dashboard response for admins"""

    admin_profile: AdminProfileSummary
    stats: DashboardStats


# Union type for all dashboard responses
DashboardResponse = (
    StudentDashboardResponse | SupervisorDashboardResponse | AdminDashboardResponse
)
