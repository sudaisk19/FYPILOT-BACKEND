# app/schemas/group_schema.py

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class CreateGroupRequest(BaseModel):
    name: str


class GroupResponse(BaseModel):
    group_id: UUID
    name: str
    project_id: Optional[UUID] = None


class InviteRequest(BaseModel):
    email: EmailStr


class MessageResponse(BaseModel):
    message: str


class DeleteGroupResponse(BaseModel):
    message: str
    group_id: UUID
    deleted_at: str


# Group Profile Schemas
class GroupMemberInfo(BaseModel):
    user_id: UUID
    full_name: str
    avatar_initial: str = Field(..., description="First letter of full name")
    avatar_url: Optional[str] = None
    joined_at: datetime


class SupervisorInfo(BaseModel):
    user_id: UUID
    full_name: str
    department: Optional[str] = None
    designation: Optional[str] = None
    email: str
    avatar_url: Optional[str] = None


class DomainInfo(BaseModel):
    domain_id: UUID
    name: str


class IndustryInfo(BaseModel):
    industry_id: UUID
    name: str


class ProjectInfo(BaseModel):
    project_id: UUID
    name: str
    description: Optional[str] = None
    objectives: Optional[List[Any]] = Field(default_factory=list)
    tech_stack: Optional[List[str]] = Field(default_factory=list)
    domains: List[DomainInfo] = Field(default_factory=list)
    industry: Optional[IndustryInfo] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    project_type: str
    repo_links: Optional[List[str]] = Field(default_factory=list)
    updated_at: datetime


class GroupProfileResponse(BaseModel):
    group: Dict[str, Any] = Field(..., description="Group basic information")
    members: List[GroupMemberInfo] = Field(default_factory=list)
    supervisors: Dict[str, Optional[SupervisorInfo]] = Field(
        default_factory=lambda: {"primary": None, "co_supervisor": None}
    )
    project: Optional[ProjectInfo] = None
    invites: Dict[str, int] = Field(default_factory=lambda: {"pending_count": 0})


# PATCH Request Schemas
class GroupUpdateData(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    fyp_stage: Optional[str] = Field(
        None,
        pattern="^(ideation|proposal|approval|implementation|evaluation|completed)$",
    )
    fyp_cycle: Optional[str] = Field(None, pattern="^(fyp1|fyp2)$")
    cohort_year: Optional[int] = Field(None, ge=2020, le=2030)
    supervisor_id: Optional[UUID] = None
    cosupervisor_id: Optional[UUID] = None


class ProjectUpdateData(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    objectives: Optional[List[Any]] = None
    tech_stack: Optional[List[str]] = None
    domain_ids: Optional[List[UUID]] = Field(None, max_items=10)
    industry_id: Optional[UUID] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    project_type: Optional[str] = Field(None, pattern="^(capstone|research|industry)$")
    repo_links: Optional[List[str]] = Field(None, max_items=10)


class GroupProfileUpdateRequest(BaseModel):
    group: Optional[GroupUpdateData] = None
    project: Optional[ProjectUpdateData] = None


class GroupProfileUpdateResponse(BaseModel):
    message: str = "Group profile updated successfully"
    updated_at: datetime
