# app/schemas/admin_schema.py

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, constr, field_validator
from pydantic.config import ConfigDict

# Custom type for phone number validation
PhoneStr = constr(
    strip_whitespace=True,  # Remove leading/trailing whitespace
    min_length=10,  # Minimum length for a valid phone number
    max_length=15,  # Maximum length including country code
    pattern=r"^\+?[0-9-().\s]{10,15}$",  # Allows +, digits, spaces, -, (, )
)


class AdminProfileBase(BaseModel):
    """
    Base schema for admin profile with common fields and validations.
    Contains shared fields between creation, update, and output schemas.
    """

    phone: Optional[str] = Field(
        None,
        description="Admin's contact phone number",
        example="+92 300-1234567",
        min_length=10,
        max_length=15,
    )

    @field_validator("phone")
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        """
        Validates and formats phone numbers.
        Allows international format with optional + prefix.
        """
        if v is None:
            return v
        # Remove all non-digit characters for comparison
        digits = "".join(filter(str.isdigit, v))
        if len(digits) < 10:
            raise ValueError("Phone number must have at least 10 digits")
        if len(digits) > 15:
            raise ValueError("Phone number cannot exceed 15 digits")
        return v.strip()


class AdminProfileOut(AdminProfileBase):
    """
    Schema for returning admin profile data.
    Includes user_id and timestamps for API responses.
    """

    user_id: UUID = Field(
        ...,  # Required field
        description="Admin's unique identifier",
        example="123e4567-e89b-12d3-a456-426614174000",
    )
    created_at: datetime = Field(
        ..., description="Timestamp when the admin profile was created"
    )
    updated_at: datetime = Field(
        ..., description="Timestamp of the last profile update"
    )

    model_config = ConfigDict(
        from_attributes=True,  # Enable ORM model conversion
        json_schema_extra={
            "example": {
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "phone": "+92 300-1234567",
                "created_at": "2025-09-30T12:00:00Z",
                "updated_at": "2025-09-30T12:00:00Z",
            }
        },
    )


class AdminProfileCreate(AdminProfileBase):
    """
    Schema for creating a new admin profile.
    Inherits optional phone field from AdminProfileBase.
    """


class AdminProfileUpdate(AdminProfileBase):
    """
    Schema for updating an existing admin profile.
    Inherits optional phone field from AdminProfileBase.
    Follows PATCH semantics where only provided fields are updated.
    """
