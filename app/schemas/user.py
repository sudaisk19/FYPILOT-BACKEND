# app/schemas/user.py
from typing import ClassVar, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator
from pydantic.config import ConfigDict

# DB-enforced roles
Role = Literal["student", "supervisor", "admin"]


class UserCreate(BaseModel):
    # Class variables (not fields)
    SPECIAL_CHARS: ClassVar[str] = '!@#$%^&*(),.?":{}|<>'

    # Model fields
    full_name: str = Field(..., min_length=2, max_length=120, example="Alice Johnson")
    email: EmailStr
    password: str = Field(
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
        example="SecureP@ss123",
    )
    role: Role

    @field_validator("password")
    def validate_password(cls, v: str) -> str:
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

    @field_validator("full_name")
    def validate_full_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Full name cannot be empty")
        if any(ch.isdigit() for ch in v):
            raise ValueError("Full name should not contain numbers")
        return v


class UserRead(BaseModel):
    user_id: UUID
    full_name: str
    email: EmailStr
    role: Role
    profile_avatar: Optional[str] = Field(
        None, description="URL or storage key to avatar"
    )
    model_config = ConfigDict(from_attributes=True)


class MeResponse(BaseModel):
    user_id: UUID
    full_name: str
    email: EmailStr
    role: Role
    profile_avatar: Optional[str] = None
    has_student_profile: bool = False
    has_supervisor_profile: bool = False
    has_admin_profile: bool = False
    model_config = ConfigDict(from_attributes=True)
