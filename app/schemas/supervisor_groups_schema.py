# app/schemas/supervisor_groups_schema.py
"""
Schemas for the Supervisor Groups endpoints:
  - Directory listing (GET /supervisors/my-groups)
  - Group profile detail (GET /supervisors/my-groups/{group_id})
"""

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field

# ─────────────────────────────────────────────────────────────────────────────
# Directory listing schemas (GET /supervisors/my-groups)
# ─────────────────────────────────────────────────────────────────────────────


class SupervisorGroupInfo(BaseModel):
    """Basic group metadata shown on a directory card."""

    group_id: str
    fyp_id: Optional[str] = None
    project_name: str
    fyp_stage: Optional[str] = None
    fyp_cycle: Optional[str] = None
    cohort_year: Optional[int] = None


class SupervisorGroupMember(BaseModel):
    """Minimal member info for the supervisor's group directory card."""

    student_id: str
    full_name: str


class SupervisorGroupProject(BaseModel):
    """Project summary for the supervisor's group directory card."""

    project_id: str
    fyp_id: Optional[str] = None
    name: str
    description: Optional[str] = None
    project_type: Optional[str] = None
    tech_stack: List[str] = Field(default_factory=list)


class GroupDirectoryCard(BaseModel):
    """A single group card in the supervisor's directory."""

    group: SupervisorGroupInfo
    members: List[SupervisorGroupMember] = Field(default_factory=list)
    project: Optional[SupervisorGroupProject] = None


class SupervisorGroupsDirectoryResponse(BaseModel):
    """Top-level response for GET /supervisors/my-groups."""

    group_directory: List[GroupDirectoryCard] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Group profile detail schemas (GET /supervisors/my-groups/{group_id})
# ─────────────────────────────────────────────────────────────────────────────


class GroupProfileGroupInfo(BaseModel):
    """Group metadata for the detailed profile view."""

    group_id: str
    fyp_id: Optional[str] = None
    project_name: str
    fyp_stage: Optional[str] = None
    fyp_cycle: Optional[str] = None
    cohort_year: Optional[int] = None
    supervisor_acceptance_feedback: Optional[str] = None


class GroupProfileMember(BaseModel):
    """Member detail for group profile."""

    student_id: str
    full_name: str
    email: str


class DomainInfo(BaseModel):
    """Domain detail for the project."""

    domain_id: str
    name: str


class RepoLink(BaseModel):
    """A single repo/design link with a label."""

    label: Optional[str] = None
    url: str


class IndustryInfo(BaseModel):
    """Industry detail for the project."""

    industry_id: str
    name: str


class GroupProfileProject(BaseModel):
    """Full project detail for the group profile."""

    project_id: str
    name: str
    description: Optional[str] = None
    project_type: Optional[str] = None
    domains: List[DomainInfo] = Field(default_factory=list)
    industry: Optional[IndustryInfo] = None
    objectives: Optional[List[Any]] = Field(default_factory=list)
    tech_stack: List[str] = Field(default_factory=list)
    repo_links: List[RepoLink] = Field(default_factory=list)
    last_updated: Optional[datetime] = None


class GroupProfileSupervisor(BaseModel):
    """Supervisor detail for group profile."""

    user_id: str
    name: str
    email: str
    type: str  # "primary" or "co_supervisor"


class SupervisorGroupProfileResponse(BaseModel):
    """Top-level response for GET /supervisors/my-groups/{group_id}."""

    group: GroupProfileGroupInfo
    project: Optional[GroupProfileProject] = None
    members: List[GroupProfileMember] = Field(default_factory=list)
    supervisors: List[GroupProfileSupervisor] = Field(default_factory=list)
    supervisor_acceptance_feedback: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Dropdown listing schemas (GET /supervisors/my-groups/dropdown)
# ─────────────────────────────────────────────────────────────────────────────


class SupervisorGroupDropdownItem(BaseModel):
    """Simple group item for dropdowns."""

    group_id: str
    project_name: str


class SupervisorGroupDropdownResponse(BaseModel):
    """Response for the dropdown listing."""

    groups: List[SupervisorGroupDropdownItem] = Field(default_factory=list)
