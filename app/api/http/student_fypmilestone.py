# app/api/http/student_fypmilestone.py
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase_auth import get_current_user
from app.db import get_db
from app.models.group import FYPCycleEnum, Group, GroupMember
from app.models.user import RoleEnum, User
from app.repositories import milestone_repository
from app.schemas.admin_milestone_schema import AdminMilestoneResponse

router = APIRouter(prefix="/milestones", tags=["student-milestones"])


async def _resolve_student_cycle(student_id: UUID, db: AsyncSession) -> FYPCycleEnum:
    """Look up the student's active group and return its FYP cycle."""
    query = (
        select(Group.fyp_cycle)
        .join(GroupMember, GroupMember.group_id == Group.group_id)
        .where(GroupMember.student_id == student_id)
        .limit(1)
    )
    result = await db.execute(query)
    cycle = result.scalar_one_or_none()

    if cycle is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No group assigned; timeline unavailable.",
        )
    return cycle


@router.get("", response_model=List[AdminMilestoneResponse])
async def list_student_milestones(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != RoleEnum.student:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Student only")

    cycle = await _resolve_student_cycle(current_user.user_id, db)
    return await milestone_repository.list_milestones(db, fyp_cycle=cycle)


@router.get("/{milestone_id}", response_model=AdminMilestoneResponse)
async def get_student_milestone(
    milestone_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != RoleEnum.student:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Student only")

    cycle = await _resolve_student_cycle(current_user.user_id, db)
    milestone = await milestone_repository.get_milestone(db, milestone_id)
    if not milestone or milestone.fyp_cycle != cycle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return milestone