# app/schemas/invite_schema.py
from datetime import datetime
from typing import List
from uuid import UUID

from pydantic import BaseModel, Field


class InviteRole(str):
    PRIMARY = "primary"
    CO = "co"


class SendSupervisorInviteRequest(BaseModel):
    faculty_id: UUID = Field(..., description="Faculty user_id")
    role: str = Field(
        ...,
        pattern="^(supervisor|cosupervisor)$",
        description="Requested role (must match db enum)",
    )
    message: str | None = Field(None, description="Optional message to supervisor")


class AcceptRequestBody(BaseModel):
    """Body for accepting a supervisor request."""

    feedback: str | None = Field(
        None, description="Optional feedback/condition from supervisor"
    )


class RejectRequestBody(BaseModel):
    """Body for rejecting a supervisor request."""

    feedback: str = Field(..., description="Mandatory feedback/reason for rejection")


class PendingInviteItem(BaseModel):
    request_id: UUID
    group_id: UUID
    requested_role: str = Field(..., description="supervisor or cosupervisor")
    created_at: datetime
    project_name: str | None = Field(None, description="Project name if project exists")
    project_type: str | None = Field(
        None, description="Project type (research/product/both)"
    )
    project_domains: List[str] = Field(
        default_factory=list, description="List of project domain names"
    )


class PendingInvitesResponse(BaseModel):
    requests: List[PendingInviteItem] = Field(default_factory=list)


class SentRequestItem(BaseModel):
    """Request sent by a group to a supervisor."""

    request_id: UUID
    faculty_id: UUID
    supervisor_name: str = Field(..., description="Supervisor's full name")
    requested_role: str = Field(..., description="supervisor or cosupervisor")
    status: str = Field(..., description="pending, accepted, declined, or cancelled")
    message: str | None = Field(None, description="Student's message to supervisor")
    feedback: str | None = Field(None, description="Supervisor's feedback/reason")
    created_at: datetime
    updated_at: datetime


class RequestSummaryItem(BaseModel):
    """Summary of a request between a group and supervisor."""

    request_id: UUID
    status: str = Field(..., description="pending, accepted, declined, or cancelled")
    message: str | None = Field(None, description="Student's message to supervisor")
    feedback: str | None = Field(None, description="Supervisor's feedback/reason")
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SentRequestsResponse(BaseModel):
    """All requests sent by a group."""

    group_id: UUID
    requests: List[SentRequestItem] = Field(default_factory=list)


# Detailed request view schemas for supervisor
class StudentSkillLevel(BaseModel):
    """Skill level mapping for a student."""

    skill: str
    level: int


class PortfolioProject(BaseModel):
    """Portfolio project information."""

    title: str
    link: str


class StudentDetail(BaseModel):
    """Detailed student information for supervisor view."""

    user_id: UUID
    name: str
    roll_number: str
    department: str | None = None
    cgpa: float | None = None
    skills: List[str] = Field(default_factory=list)
    skills_levels: dict[str, int] = Field(
        default_factory=dict,
        description="Skill name to level mapping (1-5). Currently empty as not stored in database.",
    )
    interests: List[str] = Field(default_factory=list)
    experience: str | None = None
    portfolio_projects: List[PortfolioProject] = Field(default_factory=list)


class ProjectDomainInfo(BaseModel):
    """Project domain information."""

    name: str


class ProjectDetail(BaseModel):
    """Detailed project information."""

    name: str
    description: str | None = None
    objectives: List[str] = Field(default_factory=list)
    tech_stack: List[str] = Field(default_factory=list)
    project_type: str | None = None
    github_repositories: List[str] = Field(default_factory=list)
    domains: List[ProjectDomainInfo] = Field(default_factory=list)


class SupervisorRequestDetailResponse(BaseModel):
    """Detailed request information for supervisor to view group details."""

    request_id: UUID
    group_id: UUID
    faculty_id: UUID
    status: str
    message: str | None = Field(None, description="Student's message to supervisor")
    feedback: str | None = Field(None, description="Supervisor's feedback/reason")
    created_at: datetime
    expires_at: datetime
    project_brief: str | None = Field(
        None, description="Project description used as brief"
    )
    project: ProjectDetail | None = None
    students: List[StudentDetail] = Field(default_factory=list)
    request_history: List[RequestSummaryItem] = Field(
        default_factory=list, description="All past requests from this group"
    )
