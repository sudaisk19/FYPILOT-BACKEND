# app/schemas/supervisor_schema.py

from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator
from pydantic.config import ConfigDict


class ProjectType(str, Enum):
    """
    Enumeration of valid project types a supervisor can oversee.
    """

    RESEARCH = "research"
    PRODUCT = "product"
    PRODUCT_AND_RESEARCH = "product and research"


class SupervisorProfileBase(BaseModel):
    """
    Base schema for supervisor profile with common fields and validations.
    Includes academic information and project supervision preferences.
    """

    department: Optional[str] = Field(
        default=None,
        max_length=120,
        description="Academic department name",
    )

    designation: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Academic designation or title",
    )

    office: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Office location or room number",
    )

    requirements: Optional[List[str]] = Field(
        default_factory=list,
        description="List of requirements for potential projects",
    )

    project_types: List[ProjectType] = Field(
        default_factory=list,
        description="Types of projects willing to supervise",
    )

    capacity_max: int = Field(
        default=8,
        ge=0,
        le=20,
        description="Maximum number of students that can be supervised",
    )

    capacity_filled: int = Field(
        default=0,
        ge=0,
        description="Current number of students being supervised",
    )

    @field_validator("department")
    @classmethod
    def validate_department(cls, v: Optional[str]) -> Optional[str]:
        """Ensures department name contains only valid characters."""
        if v is None:
            return v
        v = v.strip()
        if not v:
            return None
        if not v.replace(" ", "").replace("-", "").isalnum():
            raise ValueError(
                "Department should only contain letters, numbers, spaces, and hyphens"
            )
        return v.title()  # Capitalize each word

    @field_validator("capacity_filled")
    @classmethod
    def validate_capacity(cls, v: int, values) -> int:
        """Ensures capacity_filled doesn't exceed capacity_max."""
        if "capacity_max" in values.data:
            max_capacity = values.data["capacity_max"]
            if v > max_capacity:
                raise ValueError(
                    f"Filled capacity ({v}) cannot exceed maximum capacity ({max_capacity})"
                )
        return v


class SupervisorProfileOut(SupervisorProfileBase):
    """
    Schema for returning supervisor profile data.
    Includes user_id and inherits all fields from SupervisorProfileBase.
    Used for API responses.
    """

    user_id: UUID = Field(..., description="Supervisor's unique identifier")

    model_config = ConfigDict(
        from_attributes=True,  # Enable ORM model conversion
        json_schema_extra={
            "example": {
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "department": "Computer Science",
                "designation": "Associate Professor",
                "office": "CS-304",
                "requirements": ["Strong programming skills", "Knowledge of ML"],
                "project_types": ["research", "thesis"],
                "capacity_max": 8,
                "capacity_filled": 3,
            }
        },
    )


class SupervisorProfileCreate(SupervisorProfileBase):
    """
    Schema for creating a new supervisor profile.
    Inherits all fields from SupervisorProfileBase.
    Used for initial profile creation.
    """


class SupervisorProfileUpdate(SupervisorProfileBase):
    """
    Schema for updating an existing supervisor profile.
    Inherits all fields from SupervisorProfileBase.
    Follows PATCH semantics where only provided fields are updated.
    """


class SupervisorSearchParams(BaseModel):
    """
    Schema for supervisor search parameters.
    Used for filtering supervisors based on various criteria.
    """

    department: Optional[str] = Field(None, description="Filter by department")
    project_type: Optional[ProjectType] = Field(
        None, description="Filter by project type"
    )
    has_capacity: Optional[bool] = Field(
        None, description="Filter by availability (capacity_filled < capacity_max)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "department": "Computer Science",
                "project_type": "research",
                "has_capacity": True,
            }
        }
    )
