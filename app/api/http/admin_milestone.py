from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase_auth import get_current_user
from app.db import get_db
from app.models.group import FYPCycleEnum
from app.models.user import RoleEnum, User
from app.models.milestone import JuryFormTypeEnum
from app.repositories import milestone_repository, proposal_evaluation_repository
from app.schemas.admin_milestone_schema import (
    AdminEvaluationResponse,
    AdminMilestoneCreate,
    AdminMilestoneResponse,
    AdminMilestoneUpdate,
    MilestoneListItem,
)
from app.schemas.jury_evaluation_schema import (
    ProposalEvaluationConfigResponse,
    ProposalEvaluationConfigUpdate,
)

router = APIRouter(prefix="/admin", tags=["admin-milestones"])


def _ensure_admin(user: User) -> None:
    if user.role != RoleEnum.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")


def _apply_jury_form_rules(
    *,
    data: dict,
    current_evaluator: Optional[str] = None,
    current_form_type: Optional[JuryFormTypeEnum] = None,
) -> dict:
    evaluator_value = (data.get("evaluator") or current_evaluator or "").strip().lower()

    if evaluator_value == "jury":
        final_form = data.get("jury_form_type", current_form_type)
        if final_form is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="jury_form_type is required when evaluator is set to 'jury'",
            )
        data["jury_form_type"] = final_form
    else:
        data["jury_form_type"] = None

    return data


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
    summary="List faculty evaluations for a milestone",
    description=(
        "Returns supervisor evaluations plus, when the milestone evaluator is jury, "
        "all jury or proposal evaluations for the same milestone. "
        "Jury rows use is_jury_evaluation=true; supervisor_id is the jury member's user id."
    ),
)
async def list_faculty_evaluations_for_milestone(
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
    normalized_data = _apply_jury_form_rules(data=payload.model_dump())
    normalized_payload = AdminMilestoneCreate(**normalized_data)
    return await milestone_repository.create_milestone(db, payload=normalized_payload)


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
    existing = await milestone_repository.get_milestone(db, milestone_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    normalized_data = _apply_jury_form_rules(
        data=payload.model_dump(exclude_unset=True),
        current_evaluator=existing.evaluator,
        current_form_type=existing.jury_form_type,
    )
    normalized_payload = AdminMilestoneUpdate(**normalized_data)

    milestone = await milestone_repository.update_milestone(
        db, milestone_id, normalized_payload
    )
    if not milestone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return milestone


@router.get(
    "/milestones/proposal-evaluation-config",
    response_model=ProposalEvaluationConfigResponse,
    summary="Get proposal evaluation rubric caps",
)
async def get_proposal_evaluation_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_admin(current_user)
    config = await proposal_evaluation_repository.get_config(db)
    return ProposalEvaluationConfigResponse.model_validate(config)


@router.patch(
    "/milestones/proposal-evaluation-config",
    response_model=ProposalEvaluationConfigResponse,
    summary="Update proposal evaluation rubric caps (disabled)",
)
async def update_proposal_evaluation_config(
    payload: ProposalEvaluationConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_admin(current_user)
    _ = payload
    _ = db
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Proposal evaluation config updates are disabled while rubric caps are hardcoded to 2.",
    )


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
