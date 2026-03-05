# app/schemas/shortlist_schema.py
from typing import List
from uuid import UUID

from pydantic import BaseModel, Field


class ShortlistAddRequest(BaseModel):
    group_id: UUID = Field(..., description="Target group id")
    faculty_id: UUID = Field(..., description="Faculty user_id to shortlist")


class ShortlistItem(BaseModel):
    faculty_id: UUID
    full_name: str
    profile_avatar: str | None = None
    department: str | None = None
    designation: str | None = None
    capacity_filled: int = Field(..., description="Number of slots currently filled")
    capacity_max: int = Field(..., description="Total number of slots available")


class ShortlistListResponse(BaseModel):
    group_id: UUID
    faculty: List[ShortlistItem] = Field(default_factory=list)
