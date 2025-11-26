# app/schemas/profile_schema.py

from datetime import datetime
from enum import Enum
from typing import Any, ClassVar, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.user import Role


# Project type enum for validation
class ProjectType(str, Enum):
    research = "research"
    product = "product"
    both = "both"


# Base user fields (common to all roles)
class BaseUserFields(BaseModel):
    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[str] = Field(
        None, max_length=255
    )  # Changed from EmailStr to str to allow empty strings
    profile_avatar: Optional[str] = Field(None, max_length=5000)

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v):
        """Validate full name field - convert empty strings to None"""
        if v is None:
            return None
        if isinstance(v, str):
            if v.strip() == "":
                return None
            return v
        return v

    @field_validator("profile_avatar")
    @classmethod
    def validate_profile_avatar(cls, v):
        """Validate profile avatar - accepts any non-empty string (URL or data URI)"""
        if v is None:
            return None
        if isinstance(v, str):
            v = v.strip()
            if v == "":
                return None
            # Accept any non-empty string (URL, data URI, or other format)
            # Frontend is responsible for ensuring valid format
            return v
        # If not a string, let Pydantic handle type validation
        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        """Validate email field - allow None, empty string, or valid email"""
        if v is None:
            return None
        if isinstance(v, str):
            if v.strip() == "":
                return None
            # Basic email validation
            if "@" not in v or "." not in v.split("@")[-1]:
                raise ValueError("Invalid email format")
            return v
        # If not a string, return as-is (Pydantic will handle type validation)
        return v


# Student-specific fields
class StudentFields(BaseModel):
    roll_number: Optional[str] = Field(None, max_length=50)
    department: Optional[str] = Field(None, max_length=255)
    cgpa: Optional[float] = Field(None, ge=0.0, le=4.0)
    interests: Optional[List[str]] = Field(None, max_items=20)
    experience: Optional[str] = Field(None, max_length=2000)
    portfolio_projects: Optional[Dict[str, Any]] = None
    skills: Optional[List[str]] = Field(None, max_items=50)
    skills_levels: Optional[Dict[str, int]] = Field(
        None,
        description="Mapping of skill names to their levels (1-5). Skills without explicit levels default to 1.",
    )

    @field_validator("roll_number", "department", "experience")
    @classmethod
    def validate_string_fields(cls, v):
        """Convert empty strings to None for string fields"""
        if v is None:
            return None
        if isinstance(v, str):
            if v.strip() == "":
                return None
            return v
        # If not a string, return as-is (Pydantic will handle type validation)
        return v


# Supervisor-specific fields
class SupervisorFields(BaseModel):
    department: Optional[str] = Field(None, max_length=255)
    designation: Optional[str] = Field(None, max_length=255)
    office: Optional[str] = Field(None, max_length=255)
    requirements: Optional[List[str]] = Field(None, max_items=20)
    project_types: Optional[List[ProjectType]] = Field(None, max_items=10)
    capacity_max: Optional[int] = Field(None, ge=0, le=20)

    @field_validator("project_types")
    @classmethod
    def validate_project_types(cls, v):
        """Convert project type values to their enum values"""
        if v is None:
            return v
        # Convert enum objects to their string values for storage
        return [pt.value if isinstance(pt, ProjectType) else pt for pt in v]


# Admin-specific fields
class AdminFields(BaseModel):
    phone: Optional[str] = Field(None, max_length=20)
    profile_pic: Optional[str] = Field(None, max_length=5000)


# Request schemas for PATCH endpoints
class StudentProfileUpdate(BaseUserFields, StudentFields):
    """Schema for updating student profile (user + student fields)"""


class StudentProfilePatchUpdate(BaseModel):
    """Schema for PATCH updates - excludes immutable fields like roll_number"""

    # User fields (mutable)
    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[str] = Field(None, max_length=255)
    profile_avatar: Optional[str] = Field(None, max_length=5000)

    # Student fields (mutable - excluding roll_number)
    department: Optional[str] = Field(None, max_length=255)
    cgpa: Optional[float] = Field(None, ge=0.0, le=4.0)
    interests: Optional[List[str]] = Field(None, max_items=20)
    experience: Optional[str] = Field(None, max_length=2000)
    portfolio_projects: Optional[Dict[str, Any]] = None
    skills: Optional[List[str]] = Field(None, max_items=50)
    skills_levels: Optional[Dict[str, int]] = Field(
        None,
        description="Mapping of skill names to their levels (1-5). Skills without explicit levels default to 1.",
    )

    @field_validator("full_name", "profile_avatar", "department", "experience")
    @classmethod
    def validate_string_fields(cls, v):
        """Validate string fields - convert empty strings to None"""
        if v is None:
            return None
        if isinstance(v, str):
            if v.strip() == "":
                return None
            return v
        # If not a string, return as-is (Pydantic will handle type validation)
        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        """Validate email field - allow None, empty string, or valid email"""
        if v is None or v.strip() == "":
            return None
        # Basic email validation
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email format")
        return v


class SupervisorProfileUpdate(BaseUserFields, SupervisorFields):
    """Schema for updating supervisor profile (user + supervisor fields)"""


class SupervisorProfilePatchUpdate(BaseModel):
    """Schema for PATCH updates - excludes immutable fields like project_types, capacity_max, capacity_filled"""

    # User fields (mutable)
    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[str] = Field(None, max_length=255)
    profile_avatar: Optional[str] = Field(None, max_length=5000)

    # Supervisor fields (mutable - excluding required fields)
    department: Optional[str] = Field(None, max_length=255)
    designation: Optional[str] = Field(None, max_length=255)
    office: Optional[str] = Field(None, max_length=255)
    requirements: Optional[List[str]] = Field(None, max_items=20)
    # Note: project_types, capacity_max, capacity_filled are immutable

    @field_validator("full_name", "department", "designation", "office")
    @classmethod
    def validate_string_fields(cls, v):
        """Validate string fields - convert empty strings to None"""
        if v is None:
            return None
        if isinstance(v, str):
            if v.strip() == "":
                return None
            return v
        # If not a string, return as-is (Pydantic will handle type validation)
        return v

    @field_validator("profile_avatar")
    @classmethod
    def validate_profile_avatar(cls, v):
        """Validate profile avatar - accepts any non-empty string (URL or data URI)"""
        if v is None:
            return None
        if isinstance(v, str):
            v = v.strip()
            if v == "":
                return None
            # Accept any non-empty string (URL, data URI, or other format)
            # Frontend is responsible for ensuring valid format
            return v
        # If not a string, let Pydantic handle type validation
        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        """Validate email field - allow None, empty string, or valid email"""
        if v is None:
            return None
        if isinstance(v, str):
            if v.strip() == "":
                return None
            # Basic email validation
            if "@" not in v or "." not in v.split("@")[-1]:
                raise ValueError("Invalid email format")
            return v
        # If not a string, return as-is (Pydantic will handle type validation)
        return v


class AdminProfileUpdate(BaseUserFields, AdminFields):
    """Schema for updating admin profile (user + admin fields)"""


class AdminProfilePatchUpdate(BaseModel):
    """Schema for PATCH updates - all admin fields are mutable"""

    # User fields (mutable)
    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[str] = Field(None, max_length=255)
    profile_avatar: Optional[str] = Field(None, max_length=5000)

    # Admin fields (all mutable)
    phone: Optional[str] = Field(None, max_length=20)
    profile_pic: Optional[str] = Field(None, max_length=5000)

    @field_validator("full_name", "phone", "profile_pic")
    @classmethod
    def validate_string_fields(cls, v):
        """Validate string fields - convert empty strings to None"""
        if v is None:
            return None
        if isinstance(v, str):
            if v.strip() == "":
                return None
            return v
        # If not a string, return as-is (Pydantic will handle type validation)
        return v

    @field_validator("profile_avatar")
    @classmethod
    def validate_profile_avatar(cls, v):
        """Validate profile avatar - accepts any non-empty string (URL or data URI)"""
        if v is None:
            return None
        if isinstance(v, str):
            v = v.strip()
            if v == "":
                return None
            # Accept any non-empty string (URL, data URI, or other format)
            # Frontend is responsible for ensuring valid format
            return v
        # If not a string, let Pydantic handle type validation
        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        """Validate email field - allow None, empty string, or valid email"""
        if v is None:
            return None
        if isinstance(v, str):
            if v.strip() == "":
                return None
            # Basic email validation
            if "@" not in v or "." not in v.split("@")[-1]:
                raise ValueError("Invalid email format")
            return v
        # If not a string, return as-is (Pydantic will handle type validation)
        return v


# Group-related schemas for student profile
class GroupMemberInfo(BaseModel):
    """Minimal group member information"""

    user_id: UUID
    full_name: str
    email: EmailStr
    roll_number: str


class GroupInfo(BaseModel):
    """Minimal group information"""

    group_id: UUID
    name: str
    fyp_stage: str
    fyp_cycle: str
    cohort_year: Optional[int] = None
    max_members: int
    supervisor_name: Optional[str] = None
    cosupervisor_name: Optional[str] = None
    project_name: Optional[str] = None
    members: List[GroupMemberInfo] = Field(default_factory=list)


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
    skills_levels: Dict[str, int] = Field(
        default_factory=dict,
        description="Mapping of skill names to their levels (1-5). Skills without explicit levels default to 1.",
    )

    # Group information (optional - only if student is in a group)
    group: Optional[GroupInfo] = None


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
    # Class variable for password validation
    SPECIAL_CHARS: ClassVar[str] = '!@#$%^&*(),.?":{}|<>'

    current_password: str = Field(..., min_length=1)
    new_password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description=(
            "Password requirements:\n"
            "- Minimum 8 characters\n"
            "- At least 1 uppercase letter\n"
            "- At least 1 lowercase letter\n"
            "- At least 1 number\n"
            '- At least 1 special character from: !@#$%^&*(),.?":{}|<>'
        ),
        example="NewSecureP@ss123",
    )

    @field_validator("new_password")
    def validate_new_password(cls, v: str) -> str:
        errors = []

        if len(v) < 8:
            errors.append("Password must be at least 8 characters long")

        if not any(c.isupper() for c in v):
            errors.append("Password must contain at least one uppercase letter (A-Z)")
        if not any(c.islower() for c in v):
            errors.append("Password must contain at least one lowercase letter (a-z)")
        if not any(c.isdigit() for c in v):
            errors.append("Password must contain at least one number (0-9)")
        if not any(c in cls.SPECIAL_CHARS for c in v):
            errors.append(
                f"Password must contain at least one special character from: {cls.SPECIAL_CHARS}"
            )

        if errors:
            raise ValueError("\n".join(errors))

        return v


class ChangePasswordResponse(BaseModel):
    message: str = "Password updated successfully"
