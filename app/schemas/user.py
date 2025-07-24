from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


class UserCreate(BaseModel):
    """
    Schema for incoming “create user” requests.
    """

    full_name: str = Field(..., example="Alice Johnson")
    email: EmailStr = Field(..., example="alice@example.com")
    password: str = Field(..., min_length=6, example="s3cr3t!")
    role: str = Field(
        ...,
        example="student",
        description="Must be either 'student' or 'supervisor'",
    )

    @field_validator("role")
    def validate_role(cls, v: str) -> str:
        """
        Ensure role is exactly 'student' or 'supervisor'.
        If it’s anything else, raise a ValueError with our custom message.
        """
        if v not in ("student", "supervisor"):
            raise ValueError("Role must be either 'student' or 'supervisor'")
        return v


class UserRead(BaseModel):
    user_id: UUID
    full_name: str
    email: EmailStr
    role: str

    class Config:
        orm_mode = True
