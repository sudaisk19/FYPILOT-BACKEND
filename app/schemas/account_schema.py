# app/schemas/account_schemas.py

from pydantic import BaseModel, EmailStr, Field


class UserPatch(BaseModel):
    full_name: str | None = Field(None, min_length=2, max_length=120)
    email: EmailStr | None = None  # allowed to change, uniqueness enforced
    profile_avatar: str | None = None


class ChangePasswordBody(BaseModel):
    current_password: str = Field(..., min_length=6)
    new_password: str = Field(..., min_length=6)
