from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase_auth import get_current_user
from app.db import get_db
from app.models.group import FYPCycleEnum, Group, GroupMember
from app.models.jury_assignment import JuryAssignment, JuryPair
from app.models.milestone import JuryFormTypeEnum
from app.models.project import Project
from app.models.student import Student
from app.models.user import RoleEnum, User
from app.repositories import (
    milestone_repository,
    proposal_evaluation_repository,
    supervisor_evaluation_repository,
    jury_evaluation_repository,
)
from app.schemas.admin_milestone_schema import (
    MilestoneListItem,
    SupervisorMilestoneResponse,
)
from app.schemas.supervisor_evaluation_schema import (
    SupervisorEvaluationPayload,
    SupervisorEvaluationResponse,
)
from app.schemas.jury_evaluation_schema import (
    JuryAssignedGroupResponse,
    JuryEvaluationEnvelope,
    JuryEvaluationPayload,
    JuryEvaluationResponse,
    ProposalEvaluationPayload,
    ProposalEvaluationResponse,
)
from pydantic import ValidationError

router = APIRouter(prefix="/milestones")


def _parse_jury_payload(form_type: JuryFormTypeEnum, raw_payload: dict):
    payload = raw_payload

    if isinstance(raw_payload, dict):
        provided_form_type = raw_payload.get("form_type")
        if provided_form_type and provided_form_type != form_type.value:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Payload form_type does not match milestone jury_form_type",
            )

        # Accept envelope payloads from FE and unwrap active form body.
        if form_type == JuryFormTypeEnum.normal:
            for key in ("jury", "normal", "evaluation", "payload", "data"):
                if isinstance(raw_payload.get(key), dict):
                    payload = raw_payload[key]
                    break
        elif form_type == JuryFormTypeEnum.proposal:
            for key in ("proposal", "evaluation", "payload", "data"):
                if isinstance(raw_payload.get(key), dict):
                    payload = raw_payload[key]
                    break

    try:
        if form_type == JuryFormTypeEnum.normal:
            return JuryEvaluationPayload(**payload)
        return ProposalEvaluationPayload(**payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(),
        )


def _build_envelope(form_type: JuryFormTypeEnum, evaluation) -> JuryEvaluationEnvelope:
    if form_type == JuryFormTypeEnum.normal:
        return JuryEvaluationEnvelope(
            form_type=form_type,
            jury=JuryEvaluationResponse.model_validate(evaluation),
        )
    return JuryEvaluationEnvelope(
        form_type=form_type,
        proposal=ProposalEvaluationResponse.model_validate(evaluation),
    )


def _ensure_active_jury(user: User) -> None:
    if user.role != RoleEnum.faculty:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Faculty only"
        )
    if not user.faculty_profile or not user.faculty_profile.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your faculty account is inactive. Contact an administrator.",
        )
    if not user.faculty_profile.is_jury:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only faculty with jury privileges can access this resource",
        )


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


async def _get_jury_assigned_group(
    db: AsyncSession,
    *,
    jury_id: UUID,
    group_id: UUID,
) -> Optional[Group]:
    result = await db.execute(
        select(Group)
        .join(Project, Project.group_id == Group.group_id)
        .join(JuryAssignment, JuryAssignment.project_id == Project.project_id)
        .join(JuryPair, JuryPair.jury_id == JuryAssignment.pair_id)
        .where(
            Group.group_id == group_id,
            or_(
                JuryPair.faculty_1_id == jury_id,
                JuryPair.faculty_2_id == jury_id,
            ),
        )
    )
    return result.scalar_one_or_none()


async def _list_jury_assigned_groups_for_milestone(
    db: AsyncSession,
    *,
    jury_id: UUID,
    milestone_fyp_cycle: FYPCycleEnum,
) -> List[JuryAssignedGroupResponse]:
    result = await db.execute(
        select(Group, Project)
        .join(Project, Project.group_id == Group.group_id)
        .join(JuryAssignment, JuryAssignment.project_id == Project.project_id)
        .join(JuryPair, JuryPair.jury_id == JuryAssignment.pair_id)
        .where(
            Group.fyp_cycle == milestone_fyp_cycle,
            or_(
                JuryPair.faculty_1_id == jury_id,
                JuryPair.faculty_2_id == jury_id,
            ),
        )
        .order_by(Project.name.asc())
    )

    rows = result.all()
    group_ids = [group.group_id for group, _ in rows]

    members_by_group = {}
    if group_ids:
        member_rows = await db.execute(
            select(
                GroupMember.group_id,
                User.full_name,
                Student.roll_number,
            )
            .join(Student, Student.user_id == GroupMember.student_id)
            .join(User, User.user_id == Student.user_id)
            .where(GroupMember.group_id.in_(group_ids))
            .order_by(Student.roll_number.asc())
        )

        members_by_group = {}
        for gid, full_name, roll_number in member_rows.all():
            members_by_group.setdefault(gid, []).append(
                JuryAssignedGroupResponse.Member(
                    full_name=full_name,
                    roll_number=roll_number,
                )
            )

    return [
        JuryAssignedGroupResponse(
            group_id=group.group_id,
            project_id=project.project_id,
            project_name=project.name,
            fyp_id=project.fyp_id,
            fyp_cycle=group.fyp_cycle,
            members=members_by_group.get(group.group_id, []),
        )
        for group, project in rows
    ]


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


async def _validate_jury_milestone_and_group(
    *,
    db: AsyncSession,
    milestone_id: UUID,
    group_id: UUID,
    jury_id: UUID,
) -> tuple:
    milestone = await milestone_repository.get_milestone(db, milestone_id)
    if not milestone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Milestone not found",
        )

    evaluator_value = (milestone.evaluator or "").strip().lower()
    if evaluator_value != "jury":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This milestone is not configured for jury evaluations",
        )

    if milestone.jury_form_type is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Milestone is missing a jury form type",
        )

    group = await _get_jury_assigned_group(db, jury_id=jury_id, group_id=group_id)
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not assigned to this jury",
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
            status_code=status.HTTP_403_FORBIDDEN, detail="Faculty only"
        )

    # Active check
    if not current_user.faculty_profile or not current_user.faculty_profile.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your faculty account is inactive. Contact an administrator.",
        )

    # Check if faculty has supervisor OR jury privileges
    if (
        not current_user.faculty_profile.is_supervisor
        and not current_user.faculty_profile.is_jury
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only faculty with supervisor or jury privileges can access milestones",
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
            status_code=status.HTTP_403_FORBIDDEN, detail="Faculty only"
        )

    # Active check
    if not current_user.faculty_profile or not current_user.faculty_profile.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your faculty account is inactive. Contact an administrator.",
        )

    # Check if faculty has supervisor OR jury privileges
    if (
        not current_user.faculty_profile.is_supervisor
        and not current_user.faculty_profile.is_jury
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only faculty with supervisor or jury privileges can access milestone details",
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
            status_code=status.HTTP_403_FORBIDDEN, detail="Faculty only"
        )

    # Active check
    if not current_user.faculty_profile or not current_user.faculty_profile.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your faculty account is inactive. Contact an administrator.",
        )

    # Check if faculty has supervisor OR jury privileges
    if (
        not current_user.faculty_profile.is_supervisor
        and not current_user.faculty_profile.is_jury
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only faculty with supervisor or jury privileges can access group evaluations",
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
            status_code=status.HTTP_403_FORBIDDEN, detail="Faculty only"
        )

    # Active check
    if not current_user.faculty_profile or not current_user.faculty_profile.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your faculty account is inactive. Contact an administrator.",
        )

    # Check if faculty has supervisor OR jury privileges
    if (
        not current_user.faculty_profile.is_supervisor
        and not current_user.faculty_profile.is_jury
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only faculty with supervisor or jury privileges can list evaluations",
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
            status_code=status.HTTP_403_FORBIDDEN, detail="Faculty only"
        )

    # Active check
    if not current_user.faculty_profile or not current_user.faculty_profile.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your faculty account is inactive. Contact an administrator.",
        )

    # Check if faculty has supervisor OR jury privileges
    if (
        not current_user.faculty_profile.is_supervisor
        and not current_user.faculty_profile.is_jury
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only faculty with supervisor or jury privileges can create evaluations",
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
            status_code=status.HTTP_403_FORBIDDEN, detail="Faculty only"
        )

    # Active check
    if not current_user.faculty_profile or not current_user.faculty_profile.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your faculty account is inactive. Contact an administrator.",
        )

    # Check if faculty has supervisor OR jury privileges
    if (
        not current_user.faculty_profile.is_supervisor
        and not current_user.faculty_profile.is_jury
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only faculty with supervisor or jury privileges can update evaluations",
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


# ─── JURY EVALUATION (NORMAL / PROPOSAL) ─────────────────────────────────────


@router.get(
    "/{milestone_id}/jury-groups",
    response_model=List[JuryAssignedGroupResponse],
    summary="List groups assigned to the current jury member for this milestone",
)
async def list_jury_groups_for_milestone(
    milestone_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_active_jury(current_user)
    milestone = await milestone_repository.get_milestone(db, milestone_id)
    if not milestone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Milestone not found",
        )

    evaluator_value = (milestone.evaluator or "").strip().lower()
    if evaluator_value != "jury":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This milestone is not configured for jury evaluations",
        )

    if milestone.jury_form_type is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Milestone is missing a jury form type",
        )

    return await _list_jury_assigned_groups_for_milestone(
        db,
        jury_id=current_user.user_id,
        milestone_fyp_cycle=milestone.fyp_cycle,
    )


@router.get(
    "/{milestone_id}/groups/{group_id}/jury-evaluation",
    response_model=JuryEvaluationEnvelope,
    summary="Get jury evaluation for a group",
)
async def get_jury_evaluation(
    milestone_id: UUID,
    group_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_active_jury(current_user)
    milestone, _ = await _validate_jury_milestone_and_group(
        db=db,
        milestone_id=milestone_id,
        group_id=group_id,
        jury_id=current_user.user_id,
    )

    if milestone.jury_form_type == JuryFormTypeEnum.normal:
        evaluation = await jury_evaluation_repository.get_evaluation(
            db,
            milestone_id=milestone_id,
            group_id=group_id,
            jury_id=current_user.user_id,
        )
    else:
        evaluation = await proposal_evaluation_repository.get_evaluation(
            db,
            milestone_id=milestone_id,
            group_id=group_id,
            jury_id=current_user.user_id,
        )

    if not evaluation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation not found",
        )

    return _build_envelope(milestone.jury_form_type, evaluation)


@router.post(
    "/{milestone_id}/groups/{group_id}/jury-evaluation",
    response_model=JuryEvaluationEnvelope,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new jury evaluation",
)
async def create_jury_evaluation(
    milestone_id: UUID,
    group_id: UUID,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_active_jury(current_user)
    milestone, _ = await _validate_jury_milestone_and_group(
        db=db,
        milestone_id=milestone_id,
        group_id=group_id,
        jury_id=current_user.user_id,
    )

    parsed_payload = _parse_jury_payload(milestone.jury_form_type, payload)
    if not parsed_payload.model_dump(exclude_unset=True):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields provided for update",
        )

    if milestone.jury_form_type == JuryFormTypeEnum.normal:
        existing = await jury_evaluation_repository.get_evaluation(
            db,
            milestone_id=milestone_id,
            group_id=group_id,
            jury_id=current_user.user_id,
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Evaluation already exists",
            )
        evaluation = await jury_evaluation_repository.create_evaluation(
            db,
            milestone_id=milestone_id,
            group_id=group_id,
            jury_id=current_user.user_id,
            payload=parsed_payload,
        )
    else:
        existing = await proposal_evaluation_repository.get_evaluation(
            db,
            milestone_id=milestone_id,
            group_id=group_id,
            jury_id=current_user.user_id,
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Evaluation already exists",
            )
        evaluation = await proposal_evaluation_repository.create_evaluation(
            db,
            milestone_id=milestone_id,
            group_id=group_id,
            jury_id=current_user.user_id,
            payload=parsed_payload,
        )

    return _build_envelope(milestone.jury_form_type, evaluation)


@router.patch(
    "/{milestone_id}/groups/{group_id}/jury-evaluation",
    response_model=JuryEvaluationEnvelope,
    summary="Update an existing jury evaluation",
)
async def update_jury_evaluation(
    milestone_id: UUID,
    group_id: UUID,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_active_jury(current_user)
    milestone, _ = await _validate_jury_milestone_and_group(
        db=db,
        milestone_id=milestone_id,
        group_id=group_id,
        jury_id=current_user.user_id,
    )

    parsed_payload = _parse_jury_payload(milestone.jury_form_type, payload)
    if not parsed_payload.model_dump(exclude_unset=True):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields provided for update",
        )

    if milestone.jury_form_type == JuryFormTypeEnum.normal:
        evaluation = await jury_evaluation_repository.get_evaluation(
            db,
            milestone_id=milestone_id,
            group_id=group_id,
            jury_id=current_user.user_id,
        )
        if not evaluation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Evaluation not found",
            )
        updated = await jury_evaluation_repository.update_evaluation(
            db,
            evaluation=evaluation,
            payload=parsed_payload,
        )
    else:
        evaluation = await proposal_evaluation_repository.get_evaluation(
            db,
            milestone_id=milestone_id,
            group_id=group_id,
            jury_id=current_user.user_id,
        )
        if not evaluation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Evaluation not found",
            )
        updated = await proposal_evaluation_repository.update_evaluation(
            db,
            evaluation=evaluation,
            payload=parsed_payload,
        )

    return _build_envelope(milestone.jury_form_type, updated)


@router.get(
    "/{milestone_id}/jury-evaluations",
    response_model=List[JuryEvaluationEnvelope],
    summary="List jury evaluations submitted by the current faculty",
)
async def list_jury_evaluations_for_milestone(
    milestone_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_active_jury(current_user)
    milestone = await milestone_repository.get_milestone(db, milestone_id)
    if not milestone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Milestone not found",
        )

    evaluator_value = (milestone.evaluator or "").strip().lower()
    if evaluator_value != "jury":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This milestone is not configured for jury evaluations",
        )

    if milestone.jury_form_type == JuryFormTypeEnum.normal:
        evaluations = await jury_evaluation_repository.list_evaluations_for_jury(
            db,
            milestone_id=milestone_id,
            jury_id=current_user.user_id,
        )
    else:
        evaluations = await proposal_evaluation_repository.list_evaluations_for_jury(
            db,
            milestone_id=milestone_id,
            jury_id=current_user.user_id,
        )

    return [
        _build_envelope(milestone.jury_form_type, evaluation)
        for evaluation in evaluations
    ]
