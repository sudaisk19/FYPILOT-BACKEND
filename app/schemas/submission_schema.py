from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.submission import SubmissionStatusEnum, SubmissionTypeEnum


class SubmissionFileResponse(BaseModel):
    file_name: str
    file_url: str

    class Config:
        from_attributes = True


class SubmissionHistoryResponse(BaseModel):
    submission_id: UUID
    title: str
    type: SubmissionTypeEnum
    status: SubmissionStatusEnum
    submitted_at: Optional[datetime]
    supervisor_marks: Optional[float] = Field(
        None, description="Marks given by the supervisor"
    )
    files: List[SubmissionFileResponse] = Field(default_factory=list)

    class Config:
        from_attributes = True
