from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.invite_schema import RequestSummaryItem


# Basic supervisor info for list view
class SupervisorBasicInfo(BaseModel):
    user_id: UUID
    full_name: str
    email: str
    profile_avatar: Optional[str] = None
    department: Optional[str] = None
    designation: Optional[str] = None
    office: Optional[str] = None
    capacity_max: int = 8
    capacity_filled: int = 0
    available_slots: int = Field(description="Available supervision slots")

    class Config:
        from_attributes = True


# Domain info with id and name
class DomainInfo(BaseModel):
    domain_id: UUID
    name: str

    class Config:
        from_attributes = True


# Industry info with id and name
class IndustryInfo(BaseModel):
    industry_id: UUID
    name: str

    class Config:
        from_attributes = True


class IndustryListResponse(BaseModel):
    """Available industries for dropdown population."""

    industries: List[IndustryInfo]


class SupervisorDetailedInfo(BaseModel):
    # User fields
    user_id: UUID
    full_name: str
    email: str
    profile_avatar: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    # Supervisor fields
    department: Optional[str] = None
    designation: Optional[str] = None
    office: Optional[str] = None
    requirements: List[str] = Field(default_factory=list)
    project_types: List[str] = Field(default_factory=list)
    capacity_max: int = 8
    capacity_filled: int = 0
    available_slots: int = Field(description="Available supervision slots")

    # Expertise and preferences
    domains: List[DomainInfo] = Field(
        default_factory=list, description="Areas of expertise (domains)"
    )
    industries: List[IndustryInfo] = Field(
        default_factory=list, description="Industries of interest"
    )

    # Additional computed fields
    current_groups: int = Field(description="Number of groups currently supervising")
    total_supervised: int = Field(description="Total groups supervised (historical)")

    # Student-specific: list of requests between student's group and this supervisor
    request_history: Optional[list[RequestSummaryItem]] = None

    class Config:
        from_attributes = True


# Pagination response wrapper
class PaginatedSupervisorResponse(BaseModel):
    faculty: List[SupervisorBasicInfo]
    total: int = Field(description="Total number of faculty")
    page: int = Field(description="Current page number")
    per_page: int = Field(description="Items per page")
    total_pages: int = Field(description="Total number of pages")
    has_next: bool = Field(description="Whether there's a next page")
    has_prev: bool = Field(description="Whether there's a previous page")


# Query parameters for filtering
class SupervisorFilters(BaseModel):
    department: Optional[str] = Field(
        None,
        description="Filter by department (e.g., Software Engineering, SE, Computer Science, CS)",
    )
    designation: Optional[str] = Field(
        None, description="Filter by designation (Professor, Associate Professor, etc.)"
    )
    domain: Optional[str] = Field(
        None, description="Filter by domain expertise (e.g., Web, Mobile, AI, etc.)"
    )
    search: Optional[str] = Field(None, description="Search by name or email")
    page: int = Field(1, ge=1, description="Page number")
    per_page: int = Field(10, ge=1, le=50, description="Items per page")


# Response for supervisor not found
class SupervisorNotFoundResponse(BaseModel):
    detail: str = "Supervisor not found"
