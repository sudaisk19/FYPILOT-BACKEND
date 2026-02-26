from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase_auth import get_current_user
from app.db import get_db
from app.models.group import FYPCycleEnum
from app.models.user import RoleEnum, User
from app.repositories import milestone_repository
from app.schemas.admin_milestone_schema import (
    AdminEvaluationResponse,
    AdminMilestoneCreate,
    AdminMilestoneResponse,
    AdminMilestoneUpdate,
    MilestoneListItem,
)

router = APIRouter(prefix="/admin", tags=["admin-milestones"])


def _ensure_admin(user: User) -> None:
    if user.role != RoleEnum.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")


@router.get(
    "/milestones",
    response_model=List[MilestoneListItem],
    summary="List milestones",
    description="Returns a slim list of milestones (optionally filtered by cycle). Use GET /milestones/{id} for full details.",
)
async def list_admin_milestones(
    cycle: Optional[FYPCycleEnum] = Query(
        None,
        alias="fyp_cycle",
        description="Filter by FYP cycle, e.g. fyp1 or fyp2",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_admin(current_user)
    return await milestone_repository.list_milestones(db, fyp_cycle=cycle)


@router.get(
    "/milestones/{milestone_id}",
    response_model=AdminMilestoneResponse,
    summary="Get milestone detail",
)
async def get_admin_milestone(
    milestone_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_admin(current_user)
    milestone = await milestone_repository.get_milestone(db, milestone_id)
    if not milestone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return milestone


@router.get(
    "/milestones/{milestone_id}/evaluations",
    response_model=List[AdminEvaluationResponse],
    summary="List supervisor evaluations for a milestone",
    description="Returns every supervisor-submitted evaluation with supervisor name, project name and FYP ID.",
)
async def list_supervisor_evaluations_for_milestone(
    milestone_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_admin(current_user)
    milestone = await milestone_repository.get_milestone(db, milestone_id)
    if not milestone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    return await milestone_repository.list_evaluations_for_milestone(db, milestone_id)


@router.post(
    "/milestones",
    response_model=AdminMilestoneResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create milestone",
)
async def create_admin_milestone(
    payload: AdminMilestoneCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_admin(current_user)
    return await milestone_repository.create_milestone(db, payload=payload)


@router.patch(
    "/milestones/{milestone_id}",
    response_model=AdminMilestoneResponse,
    summary="Update milestone",
)
async def update_admin_milestone(
    milestone_id: UUID,
    payload: AdminMilestoneUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_admin(current_user)
    milestone = await milestone_repository.update_milestone(db, milestone_id, payload)
    if not milestone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return milestone


@router.delete(
    "/milestones/{milestone_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete milestone",
)
async def delete_admin_milestone(
    milestone_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_admin(current_user)
    deleted = await milestone_repository.delete_milestone(db, milestone_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)