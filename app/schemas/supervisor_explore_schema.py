# app/schemas/supervisor_explore_schema.py

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


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


# Detailed supervisor info for individual view
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

    # Additional computed fields
    current_groups: int = Field(description="Number of groups currently supervising")
    total_supervised: int = Field(description="Total groups supervised (historical)")

    class Config:
        from_attributes = True


# Pagination response wrapper
class PaginatedSupervisorResponse(BaseModel):
    supervisors: List[SupervisorBasicInfo]
    total: int = Field(description="Total number of supervisors")
    page: int = Field(description="Current page number")
    per_page: int = Field(description="Items per page")
    total_pages: int = Field(description="Total number of pages")
    has_next: bool = Field(description="Whether there's a next page")
    has_prev: bool = Field(description="Whether there's a previous page")


# Query parameters for filtering
class SupervisorFilters(BaseModel):
    department: Optional[str] = Field(None, description="Filter by department")
    designation: Optional[str] = Field(
        None, description="Filter by designation (Professor, Associate Professor, etc.)"
    )
    project_type: Optional[str] = Field(
        None, description="Filter by project type (web, mobile, ai, etc.)"
    )
    search: Optional[str] = Field(None, description="Search by name or email")
    page: int = Field(1, ge=1, description="Page number")
    per_page: int = Field(10, ge=1, le=50, description="Items per page")


# Response for supervisor not found
class SupervisorNotFoundResponse(BaseModel):
    detail: str = "Supervisor not found"
