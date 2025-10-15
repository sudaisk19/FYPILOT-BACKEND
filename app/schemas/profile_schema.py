# app/schemas/profile_schema.py

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.schemas.user import Role


# Base user fields (common to all roles)
class BaseUserFields(BaseModel):
    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    profile_avatar: Optional[str] = Field(None, max_length=500)


# Student-specific fields
class StudentFields(BaseModel):
    roll_number: Optional[str] = Field(None, min_length=1, max_length=50)
    department: Optional[str] = Field(None, max_length=255)
    cgpa: Optional[float] = Field(None, ge=0.0, le=4.0)
    interests: Optional[List[str]] = Field(None, max_items=20)
    experience: Optional[str] = Field(None, max_length=2000)
    portfolio_projects: Optional[Dict[str, Any]] = None
    skills: Optional[List[str]] = Field(None, max_items=50)


# Supervisor-specific fields
class SupervisorFields(BaseModel):
    department: Optional[str] = Field(None, max_length=255)
    designation: Optional[str] = Field(None, max_length=255)
    office: Optional[str] = Field(None, max_length=255)
    requirements: Optional[List[str]] = Field(None, max_items=20)
    project_types: Optional[List[str]] = Field(None, max_items=10)
    capacity_max: Optional[int] = Field(None, ge=0, le=20)


# Admin-specific fields
class AdminFields(BaseModel):
    phone: Optional[str] = Field(None, max_length=20)
    profile_pic: Optional[str] = Field(None, max_length=500)


# Request schemas for PATCH endpoints
class StudentProfileUpdate(BaseUserFields, StudentFields):
    """Schema for updating student profile (user + student fields)"""


class SupervisorProfileUpdate(BaseUserFields, SupervisorFields):
    """Schema for updating supervisor profile (user + supervisor fields)"""


class AdminProfileUpdate(BaseUserFields, AdminFields):
    """Schema for updating admin profile (user + admin fields)"""


# Response schemas for GET endpoints
class StudentProfileResponse(BaseModel):
    # User fields
    user_id: UUID
    full_name: str
    email: EmailStr
    role: Role
    profile_avatar: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    # Student fields
    roll_number: str
    department: Optional[str] = None
    cgpa: Optional[float] = None
    interests: List[str] = Field(default_factory=list)
    experience: Optional[str] = None
    portfolio_projects: Optional[Dict[str, Any]] = None
    skills: List[str] = Field(default_factory=list)


# Response schemas for PATCH endpoints (with success messages)
class StudentProfileUpdateResponse(BaseModel):
    message: str = "Student profile updated successfully"
    profile: StudentProfileResponse


class SupervisorProfileResponse(BaseModel):
    # User fields
    user_id: UUID
    full_name: str
    email: EmailStr
    role: Role
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


class SupervisorProfileUpdateResponse(BaseModel):
    message: str = "Supervisor profile updated successfully"
    profile: SupervisorProfileResponse


class AdminProfileResponse(BaseModel):
    # User fields
    user_id: UUID
    full_name: str
    email: EmailStr
    role: Role
    profile_avatar: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    # Admin fields
    phone: Optional[str] = None
    profile_pic: Optional[str] = None


class AdminProfileUpdateResponse(BaseModel):
    message: str = "Admin profile updated successfully"
    profile: AdminProfileResponse


# Change password schema (common to all roles)
class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)


class ChangePasswordResponse(BaseModel):
    message: str = "Password updated successfully"
