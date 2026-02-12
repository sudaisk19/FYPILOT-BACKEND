from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.supabase_auth import get_current_user
from app.db import get_db
from app.models.announcement import Announcement
from app.models.submission import (
    Submission,
    SubmissionStatusEnum,
    SubmissionTypeEnum,
)
from app.models.user import User
from app.schemas.submission_schema import (
    SubmissionFileResponse,
    SubmissionHistoryResponse,
)

router = APIRouter(prefix="/submission-history", tags=["submission-history"])


@router.get(
    "",
    response_model=List[SubmissionHistoryResponse],
    summary="Get submission history for a group",
    description="Fetch all submissions for a specific group with filtering and sorting options.",
)
async def get_submission_history(
    group_id: UUID,
    status: Optional[SubmissionStatusEnum] = Query(
        None, description="Filter by submission status"
    ),
    type: Optional[SubmissionTypeEnum] = Query(
        None, description="Filter by submission type"
    ),
    search: Optional[str] = Query(
        None, description="Search keyword in submission title or announcement title"
    ),
    is_graded: Optional[bool] = Query(None, description="Filter by graded status"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get submission history for a group.

    Filters:
    - status: SubmissionStatusEnum
    - type: SubmissionTypeEnum
    - is_graded: Boolean (true for having marks, false for otherwise)
    - search: String (matches submission title or linked announcement title)

    Returns list of submissions sorted by submitted_at (newest first).
    """

    # Build query
    query = (
        select(Submission)
        .options(
            selectinload(Submission.files), selectinload(Submission.linked_announcement)
        )
        .where(Submission.group_id == group_id)
    )

    # Apply Filters
    if status:
        query = query.where(Submission.status == status)

    if type:
        query = query.where(Submission.type == type)

    if is_graded is not None:
        if is_graded:
            query = query.where(Submission.supervisor_marks.is_not(None))
        else:
            query = query.where(Submission.supervisor_marks.is_(None))

    if search:
        # Search in submission title OR announcement title
        term = f"%{search.strip()}%"
        # We need to join Announcement to filter by its title
        # Use outerjoin in case linked_announcement is null
        query = query.outerjoin(
            Announcement,
            Submission.linked_announcement_id == Announcement.announcement_id,
        )
        query = query.where(
            or_(Submission.title.ilike(term), Announcement.title.ilike(term))
        )

    # Sort results directly in DB query
    query = query.order_by(Submission.submitted_at.desc().nulls_last())

    result = await db.execute(query)
    submissions = result.scalars().all()

    # Map to response model
    response = []
    for sub in submissions:
        files_data = [
            SubmissionFileResponse(
                file_name=f.file_name,
                file_url=f.storage_key,  # Using storage_key as the URL for now
            )
            for f in sub.files
        ]

        response.append(
            SubmissionHistoryResponse(
                submission_id=sub.submission_id,
                title=sub.title,
                type=sub.type,
                status=sub.status,
                submitted_at=sub.submitted_at,
                supervisor_marks=sub.supervisor_marks,
                files=files_data,
            )
        )

    return response
