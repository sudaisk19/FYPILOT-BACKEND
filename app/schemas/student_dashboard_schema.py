# app/schemas/student_dashboard_schema.py
from datetime import date
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel


# ─── 1. PROFILE / HEADER ──────────────────────────────────────────────────────

class DashboardGroupMember(BaseModel):
    user_id: UUID
    full_name: str
    role: str  # e.g., "Student", "Leader"


class StudentDashboardProfile(BaseModel):
    """Headline information for the student dashboard."""
    project_name: str
    project_description: Optional[str] = None
    fyp_cycle: str
    fyp_stage: str
    supervisor_name: Optional[str] = None
    cosupervisor_names: List[str] = []
    group_members: List[DashboardGroupMember] = []


# ─── 2. UPCOMING DEADLINES ────────────────────────────────────────────────────

class UpcomingDeadlineItem(BaseModel):
    id: UUID
    title: str
    date: str  # Format: "15 Oct 2025"
    days_left: int
    description: str  # e.g., "Submit final proposal document"
    type: Literal["milestone", "submission_request"]


class UpcomingDeadlinesWidget(BaseModel):
    title: str = "Upcoming Deadlines"
    deadlines: List[UpcomingDeadlineItem]


# ─── 3. SKILL-DOMAIN ALIGNMENT ────────────────────────────────────────────────

class SkillAlignmentScore(BaseModel):
    domain: str  # e.g., "AI", "Cybersecurity", "Web Development"
    score: float # 0 to 5


class SkillDomainAlignmentWidget(BaseModel):
    title: str = "Individual & Group Skills-Domain Alignment"
    individual_scores: List[SkillAlignmentScore]
    group_scores: List[SkillAlignmentScore]


# ─── 4. TASKS OVERVIEW ────────────────────────────────────────────────────────

class TaskStatusDistribution(BaseModel):
    not_started: int
    in_progress: int
    completed: int
    blocked: int


class StudentTasksOverviewWidget(BaseModel):
    title: str = "Tasks Overview"
    completion_percentage: float
    status_distribution: TaskStatusDistribution


# ─── 5. SUBMISSION TRENDS ─────────────────────────────────────────────────────

class TrendDataPoint(BaseModel):
    date_label: str  # e.g., "Sep 8", "Sep 10"
    count: int


class SubmissionTrendsWidget(BaseModel):
    title: str = "Submission Trends (Last 30 Days)"
    points: List[TrendDataPoint]


# ─── 6. PROJECT VELOCITY ──────────────────────────────────────────────────────

class VelocityDataPoint(BaseModel):
    week_label: str  # e.g., "1", "2", "3", "4"
    tasks_completed: int


class ProjectVelocityWidget(BaseModel):
    title: str = "Project Velocity (Tasks Completed per Week)"
    points: List[VelocityDataPoint]


# ─── ENVELOPE ─────────────────────────────────────────────────────────────────

class StudentDashboardInsights(BaseModel):
    """Aggregated collection of all student dashboard widgets."""
    profile: StudentDashboardProfile
    upcoming_deadlines: UpcomingDeadlinesWidget
    skill_alignment: SkillDomainAlignmentWidget
    tasks_overview: StudentTasksOverviewWidget
    submission_trends: SubmissionTrendsWidget
    project_velocity: ProjectVelocityWidget


class StudentDashboardEnvelope(BaseModel):
    """Final payload returned to the frontend for student dashboards."""
    student_dashboard: StudentDashboardInsights
