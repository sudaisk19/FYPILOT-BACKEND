# app/schemas/dashboard_schema.py

from datetime import date
from typing import List, Literal, Optional
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
    project_name: str
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


class AdminDashboardResponse(BaseModel):
    """Dashboard response for admins"""

    admin_profile: AdminProfileSummary
    stats: DashboardStats


class AdminTopCards(BaseModel):
    """Headline metrics for the admin dashboard."""

    total_users: int
    active_students: int
    active_supervisors: int
    active_projects: int


class SupervisorsPerDepartment(BaseModel):
    """Histogram-friendly representation of supervisor counts per department."""

    title: str
    type: Literal["bar_chart"]
    x_axis: List[str]
    y_axis: List[int]


class StudentsPerTermPoint(BaseModel):
    """Single data point for the students start-term trend graph."""

    term: str
    count: int


class StudentsPerTermChart(BaseModel):
    """Line chart friendly payload for student start terms."""

    title: str
    type: Literal["line_chart"]
    points: List[StudentsPerTermPoint]
    trend_delta: Optional[int] = None


class ProjectsPerCycleEntry(BaseModel):
    """Represents the number of active projects for a single cycle."""

    cycle: str
    active_projects: int


class ProjectsPerCycleChart(BaseModel):
    """Bar chart data for active projects per FYP cycle."""

    title: str
    type: Literal["bar_chart"]
    cycles: List[ProjectsPerCycleEntry]
    total_active_projects: int


class EvaluationStatusSummary(BaseModel):
    """Progress-style summary for the active milestone evaluations."""

    title: str
    type: Literal["progress_summary"]
    active_milestone: Optional[str]
    evaluations_submitted: int
    evaluations_required: int
    missing_evaluations: int
    wbs_failure_count: int
    percentage_submitted: float
    last_updated: Optional[str] = None


class SupervisorCapacityUsage(BaseModel):
    """Pie chart friendly supervisor capacity snapshot."""

    title: str
    type: Literal["pie_chart"]
    total_slots: int
    filled_slots: int
    remaining_slots: int


class SupervisorWorkloadInsights(BaseModel):
    """Histogram showing how many groups each supervisor manages."""

    title: str
    type: Literal["histogram"]
    x_axis: List[str]
    y_axis: List[int]
    tooltip: Optional[str] = None


class MilestoneSummary(BaseModel):
    """Compact milestone representation for upcoming deadlines."""

    milestone: str
    date: date
    cycle: str


class UpcomingMilestones(BaseModel):
    """Upcoming milestone collection for the admin dashboard."""

    title: str
    milestones: List[MilestoneSummary]


class AdminDashboardInsights(BaseModel):
    """Aggregated collection of all admin dashboard widgets."""

    top_cards: AdminTopCards
    supervisors_per_department: SupervisorsPerDepartment
    students_per_term: StudentsPerTermChart
    projects_per_cycle: ProjectsPerCycleChart
    supervisor_capacity_usage: SupervisorCapacityUsage
    supervisor_workload_insights: SupervisorWorkloadInsights
    upcoming_milestones: UpcomingMilestones
    evaluation_status: EvaluationStatusSummary


class AdminDashboardEnvelope(BaseModel):
    """Final payload returned to the frontend for admin dashboards."""

    admin_dashboard: AdminDashboardInsights
