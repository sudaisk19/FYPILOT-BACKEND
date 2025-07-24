# app/schemas/student_schema.py
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class StudentSchema(BaseModel):
    user_id: UUID
    roll_number: str
    department: Optional[str]
    group_id: Optional[UUID]
    skills: List[str]

    from_attributes = True
