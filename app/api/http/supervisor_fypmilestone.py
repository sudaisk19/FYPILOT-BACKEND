from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase_auth import get_current_user
from app.db import get_db
from app.models.group import FYPCycleEnum, Group
from app.models.user import RoleEnum, User
from app.repositories import milestone_repository, supervisor_evaluation_repository
from app.schemas.admin_milestone_schema import (
    MilestoneListItem,
    SupervisorMilestoneResponse,
)
from app.schemas.supervisor_evaluation_schema import (
    SupervisorEvaluationPayload,
    SupervisorEvaluationResponse,
)

router = APIRouter(prefix="/milestones")


async def _get_managed_group(
    db: AsyncSession, *, supervisor_id: UUID, group_id: UUID
) -> Optional[Group]:
    result = await db.execute(
        select(Group).where(
            Group.group_id == group_id,
            or_(
                Group.supervisor_id == supervisor_id,
                Group.cosupervisor_ids.contains([supervisor_id]),
            ),
        )
    )
    return result.scalar_one_or_none()


async def _validate_milestone_and_group(
    *,
    db: AsyncSession,
    milestone_id: UUID,
    group_id: UUID,
    supervisor_id: UUID,
    require_active: bool = False,
):
    milestone = await milestone_repository.get_milestone(db, milestone_id)
    if not milestone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Milestone not found"
        )
    if require_active and not milestone.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Milestone is not active for evaluations",
        )

    group = await _get_managed_group(db, supervisor_id=supervisor_id, group_id=group_id)
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found or not managed by you",
        )

    if group.fyp_cycle != milestone.fyp_cycle:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Group FYP cycle does not match the milestone",
        )

    return milestone, group


@router.get("", response_model=List[MilestoneListItem])
async def list_supervisor_milestones(
    cycle: Optional[FYPCycleEnum] = Query(
        None,
        alias="fyp_cycle",
        description="Filter milestones by FYP cycle (fyp1/fyp2). Defaults to fyp1.",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != RoleEnum.faculty:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Supervisor only"
        )

    # When cycle is omitted, return both FYP1 and FYP2 milestones.
    return await milestone_repository.list_milestones(db, fyp_cycle=cycle)


@router.get("/{milestone_id}", response_model=SupervisorMilestoneResponse)
async def get_supervisor_milestone(
    milestone_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != RoleEnum.faculty:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Supervisor only"
        )

    milestone = await milestone_repository.get_milestone(db, milestone_id)
    if not milestone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return milestone


@router.get(
    "/{milestone_id}/groups/{group_id}/evaluation",
    response_model=SupervisorEvaluationResponse,
    summary="Get supervisor evaluation for a group",
)
async def get_group_evaluation(
    milestone_id: UUID,
    group_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != RoleEnum.faculty:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Supervisor only"
        )

    await _validate_milestone_and_group(
        db=db,
        milestone_id=milestone_id,
        group_id=group_id,
        supervisor_id=current_user.user_id,
    )

    evaluation = await supervisor_evaluation_repository.get_evaluation(
        db,
        milestone_id=milestone_id,
        group_id=group_id,
        supervisor_id=current_user.user_id,
    )
    if not evaluation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Evaluation not found"
        )
    return evaluation


@router.get(
    "/{milestone_id}/evaluations",
    response_model=List[SupervisorEvaluationResponse],
    summary="List supervisor's evaluations for a milestone",
)
async def list_supervisor_evaluations_for_milestone(
    milestone_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != RoleEnum.faculty:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Supervisor only"
        )

    milestone = await milestone_repository.get_milestone(db, milestone_id)
    if not milestone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Milestone not found"
        )

    return await supervisor_evaluation_repository.list_evaluations_for_supervisor(
        db,
        milestone_id=milestone_id,
        supervisor_id=current_user.user_id,
    )


@router.post(
    "/{milestone_id}/groups/{group_id}/evaluation",
    response_model=SupervisorEvaluationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an evaluation for a group",
)
async def create_group_evaluation(
    milestone_id: UUID,
    group_id: UUID,
    payload: SupervisorEvaluationPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != RoleEnum.faculty:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Supervisor only"
        )

    change_set = payload.model_dump(exclude_unset=True)
    if not change_set:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields provided for update",
        )

    await _validate_milestone_and_group(
        db=db,
        milestone_id=milestone_id,
        group_id=group_id,
        supervisor_id=current_user.user_id,
        require_active=True,
    )

    existing = await supervisor_evaluation_repository.get_evaluation(
        db,
        milestone_id=milestone_id,
        group_id=group_id,
        supervisor_id=current_user.user_id,
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Evaluation already exists",
        )

    return await supervisor_evaluation_repository.create_evaluation(
        db,
        milestone_id=milestone_id,
        group_id=group_id,
        supervisor_id=current_user.user_id,
        payload=payload,
    )


@router.patch(
    "/{milestone_id}/groups/{group_id}/evaluation",
    response_model=SupervisorEvaluationResponse,
    summary="Update an evaluation for a group",
)
async def update_group_evaluation(
    milestone_id: UUID,
    group_id: UUID,
    payload: SupervisorEvaluationPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != RoleEnum.faculty:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Supervisor only"
        )

    change_set = payload.model_dump(exclude_unset=True)
    if not change_set:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields provided for update",
        )

    await _validate_milestone_and_group(
        db=db,
        milestone_id=milestone_id,
        group_id=group_id,
        supervisor_id=current_user.user_id,
        require_active=True,
    )

    evaluation = await supervisor_evaluation_repository.get_evaluation(
        db,
        milestone_id=milestone_id,
        group_id=group_id,
        supervisor_id=current_user.user_id,
    )
    if not evaluation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Evaluation not found"
        )

    return await supervisor_evaluation_repository.update_evaluation(
        db,
        evaluation=evaluation,
        payload=payload,
    )
