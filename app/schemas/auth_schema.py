# app/schemas/auth_schema.py

from typing import ClassVar

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


class RoleUpdateRequest(BaseModel):
    role: str  # "student", "supervisor", or "admin"


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

    @field_validator("confirm_password")
    def validate_confirm_password(cls, v: str, info) -> str:
        if "new_password" in info.data and v != info.data["new_password"]:
            raise ValueError("Passwords do not match")
        return v


class ResetPasswordResponse(BaseModel):
    message: str
