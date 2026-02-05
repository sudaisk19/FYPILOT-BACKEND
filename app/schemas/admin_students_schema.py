# app/schemas/admin_students_schema.py
#this schema is for the admin_students.py api that is displaying all the stidents to the admin 
from pydantic import BaseModel
from typing import List, Optional

class StudentCardInfo(BaseModel):
    user_id: str
    full_name: str
    email: str
    roll_number: str
    department: Optional[str] = None
    project_name: Optional[str] = None
    fyp_cycle: Optional[str] = None
    cohort_year: Optional[int] = None
    assigned: bool = False

class PaginatedStudentResponse(BaseModel):
    students: List[StudentCardInfo]
    total: int
    page: int
    per_page: int
    total_pages: int
    has_next: bool
    has_prev: bool
