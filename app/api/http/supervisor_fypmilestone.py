from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase_auth import get_current_user
from app.db import get_db
from app.models.group import FYPCycleEnum
from app.models.user import RoleEnum, User
from app.repositories import milestone_repository
from app.schemas.admin_milestone_schema import AdminMilestoneResponse

router = APIRouter(prefix="/milestones", tags=["supervisor-milestones"])


@router.get("", response_model=List[AdminMilestoneResponse])
async def list_supervisor_milestones(
    cycle: Optional[FYPCycleEnum] = Query(
        None,
        alias="fyp_cycle",
        description="Filter milestones by FYP cycle (fyp1/fyp2). Defaults to fyp1.",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != RoleEnum.supervisor:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Supervisor only")

    # When cycle is omitted, return both FYP1 and FYP2 milestones.
    return await milestone_repository.list_milestones(db, fyp_cycle=cycle)


@router.get("/{milestone_id}", response_model=AdminMilestoneResponse)
async def get_supervisor_milestone(
    milestone_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != RoleEnum.supervisor:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Supervisor only")

    milestone = await milestone_repository.get_milestone(db, milestone_id)
    if not milestone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return milestone