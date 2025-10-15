# app/schemas/student_schema.py
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, constr, field_validator
from pydantic.config import ConfigDict

# Custom type for roll number validation
RollNumber = constr(
    strip_whitespace=True,  # Remove leading/trailing whitespace
    min_length=8,  # Minimum length (e.g., "22K-4364" = 8 chars)
    max_length=8,  # Maximum length (fixed format)
    pattern=r"^[0-9]{2}K-[0-9]{4}$",  # Format: YYK-XXXX (e.g., 22K-4364)
)


class StudentProfileOut(BaseModel):
    user_id: UUID
    roll_number: Optional[str] = None
    department: Optional[str] = None
    cgpa: Optional[float] = None
    interests: Optional[List[str]] = None
    experience: Optional[str] = None
    portfolio_projects: Optional[Dict[str, Any]] = None
    skills: Optional[List[str]] = None

    model_config = ConfigDict(from_attributes=True)


class StudentProfileCreate(BaseModel):
    # All optional for “complete later”
    roll_number: Optional[str] = Field(
        None,
        min_length=8,
        max_length=8,
        pattern=r"^[0-9]{2}k-[0-9]{4}$",
        description="Student's roll number in format YYk-XXXX (e.g., 22k-4364)",
        example="22k-4364",
    )
    department: Optional[str] = Field(None, max_length=120)
    cgpa: Optional[float] = Field(None, ge=0, le=4)  # adjust if your scale differs
    interests: Optional[List[str]] = None
    experience: Optional[str] = None
    portfolio_projects: Optional[Dict[str, Any]] = None  # mirrors jsonb
    skills: Optional[List[str]] = Field(default=None)  # text[]

    @field_validator("skills")
    @classmethod
    def normalize_skills(cls, v):
        if v is None:
            return v
        # trim empties, dedupe (case-insensitive), keep order
        seen, out = set(), []
        for s in (x.strip() for x in v if isinstance(x, str) and x.strip()):
            key = s.lower()
            if key not in seen:
                seen.add(key)
                out.append(s)
        return out


class StudentProfileUpdate(StudentProfileCreate):
    """PATCH semantics (same optional fields)."""
