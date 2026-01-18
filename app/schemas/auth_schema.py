# app/schemas/auth_schema.py

from datetime import datetime
from typing import ClassVar, List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    remember_me: bool = False


class TokenResponse(BaseModel):
    message: str = "Authentication successful"
    access_token: str
    token_type: str  # e.g. "bearer"
    role: str  # User role for frontend routing


class LoginResponse(BaseModel):
    message: str = "Login successful"
    access_token: str
    token_type: str
    role: str
    user: dict  # Full user object with profile flags


class SignupResponse(BaseModel):
    message: str = "Account created successfully"
    access_token: str
    token_type: str
    role: str
    user: dict  # Full user object with profile flags


class RoleUpdateRequest(BaseModel):
    role: str  # "student" or "supervisor" only

    @field_validator("role")
    @classmethod
    def validate_role(cls, v):
        """Validate that role is either student or supervisor"""
        if v not in ["student", "supervisor"]:
            raise ValueError("Role must be 'student' or 'supervisor'")
        return v


class RoleUpdateResponse(BaseModel):
    message: str
    role: str
    user: dict  # Updated user object


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    message: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(
        ...,
        min_length=8,
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
    confirm_password: str

    # Class variable for password validation
    SPECIAL_CHARS: ClassVar[str] = '!@#$%^&*(),.?":{}|<>'

    @field_validator("new_password")
    def validate_new_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError(
                "Password must be at least 8 characters (e.g., SecureP@ss123)"
            )

        if not any(c.isupper() for c in v):
            raise ValueError(
                "Password must contain at least one uppercase letter (e.g., SecureP@ss123)"
            )
        if not any(c.islower() for c in v):
            raise ValueError(
                "Password must contain at least one lowercase letter (e.g., SecureP@ss123)"
            )
        if not any(c.isdigit() for c in v):
            raise ValueError(
                "Password must contain at least one number (e.g., SecureP@ss123)"
            )
        if not any(c in cls.SPECIAL_CHARS for c in v):
            raise ValueError(
                f"Password must contain a special character like !@#$%^&* (e.g., SecureP@ss123)"
            )

        return v

    @field_validator("confirm_password")
    def validate_confirm_password(cls, v: str, info) -> str:
        if "new_password" in info.data and v != info.data["new_password"]:
            raise ValueError("Passwords do not match")
        return v


class ResetPasswordResponse(BaseModel):
    message: str


# Role-specific schemas for /auth/me endpoint
class StudentInfo(BaseModel):
    """Student profile information"""

    roll_number: str
    department: Optional[str] = None
    cgpa: Optional[float] = None
    interests: Optional[List[str]] = None
    experience: Optional[str] = None
    portfolio_projects: Optional[dict] = None
    skills: Optional[List[str]] = None
    skills_levels: Optional[dict] = None


class GroupInfo(BaseModel):
    group_id: Optional[UUID] = None
    group_name: Optional[str] = None
    fyp_stage: Optional[str] = None
    fyp_cycle: Optional[str] = None
    cohort_year: Optional[int] = None
    supervisor_id: Optional[UUID] = None
    cosupervisor_id: Optional[UUID] = None
    project_id: Optional[UUID] = None


class SupervisedGroup(BaseModel):
    group_id: UUID
    group_name: str
    fyp_stage: str
    fyp_cycle: str
    member_count: int
    project_id: Optional[UUID] = None


class DomainInfo(BaseModel):
    domain_id: UUID
    name: str


class IndustryInfo(BaseModel):
    industry_id: UUID
    name: str


class SupervisorInfo(BaseModel):
    department: Optional[str] = None
    designation: Optional[str] = None
    office: Optional[str] = None
    capacity_max: int
    capacity_filled: int
    project_types: List[str] = []
    requirements: List[str] = []
    supervised_groups: List[SupervisedGroup] = []
    domains: List[DomainInfo] = []
    industries: List[IndustryInfo] = []


class SystemStats(BaseModel):
    total_students: int
    total_supervisors: int
    total_groups: int
    total_projects: int
    pending_invites: int


class AdminInfo(BaseModel):
    phone: Optional[str] = None
    profile_pic: Optional[str] = None
    system_stats: SystemStats


class UserProfileResponse(BaseModel):
    user_id: UUID
    full_name: str
    email: str
    role: str
    profile_avatar: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    student_info: Optional[StudentInfo] = None  # Student profile data
    group_info: Optional[GroupInfo] = None  # For students
    supervisor_info: Optional[SupervisorInfo] = None  # For supervisors
    admin_info: Optional[AdminInfo] = None  # For admins
