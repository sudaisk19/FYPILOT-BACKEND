# app/repositories/milestone_repository.py
import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.faculty import Faculty
from app.models.group import FYPCycleEnum, Group
from app.models.jury_evaluation import JuryEvaluation, ProposalEvaluation
from app.models.milestone import AdminMilestone, JuryFormTypeEnum
from app.models.supervisor_evaluation import SupervisorEvaluation
from app.schemas.admin_milestone_schema import (
    AdminEvaluationResponse,
    AdminMilestoneCreate,
    AdminMilestoneUpdate,
)

logger = logging.getLogger(__name__)


def _faculty_display_name(faculty: Optional[Faculty]) -> Optional[str]:
    if faculty and getattr(faculty, "user", None):
        return faculty.user.full_name
    return None


def _project_labels(group: Optional[Group]) -> Tuple[Optional[str], Optional[str]]:
    if group and group.project:
        return group.project.name, group.project.fyp_id
    return None, None


def _numeric_optional(value) -> Optional[float]:
    if value is None:
        return None
    return float(value)


def _proposal_feedback_text(ev: ProposalEvaluation) -> Optional[str]:
    parts: List[str] = []
    if ev.deliverables:
        parts.append(ev.deliverables.strip())
    if ev.recommended_changes:
        parts.append(f"Recommended changes: {ev.recommended_changes.strip()}")
    if ev.project_status is not None:
        parts.append(f"Status: {ev.project_status.value}")
    if not parts:
        return None
    return "\n\n".join(parts)


async def _list_supervisor_evaluations(
    db: AsyncSession,
    milestone_id: UUID,
) -> List[AdminEvaluationResponse]:
    result = await db.execute(
        select(SupervisorEvaluation)
        .options(
            joinedload(SupervisorEvaluation.supervisor).joinedload(Faculty.user),
            joinedload(SupervisorEvaluation.group).joinedload(Group.project),
        )
        .where(SupervisorEvaluation.milestone_id == milestone_id)
        .order_by(SupervisorEvaluation.updated_at.desc())
    )
    evaluations = result.scalars().unique().all()

    rows: List[AdminEvaluationResponse] = []
    for ev in evaluations:
        project_name, fyp_id = _project_labels(ev.group)
        rows.append(
            AdminEvaluationResponse(
                evaluation_id=ev.evaluation_id,
                milestone_id=ev.milestone_id,
                group_id=ev.group_id,
                supervisor_id=ev.supervisor_id,
                supervisor_name=_faculty_display_name(ev.supervisor),
                project_name=project_name,
                fyp_id=fyp_id,
                marks=_numeric_optional(ev.marks),
                feedback=ev.feedback,
                wbs_achieved=ev.wbs_achieved,
                created_at=ev.created_at,
                updated_at=ev.updated_at,
                is_jury_evaluation=False,
            )
        )
    return rows


async def _list_jury_normal_evaluations_admin(
    db: AsyncSession,
    milestone_id: UUID,
) -> List[AdminEvaluationResponse]:
    result = await db.execute(
        select(JuryEvaluation)
        .options(
            joinedload(JuryEvaluation.group).joinedload(Group.project),
            joinedload(JuryEvaluation.jury_member).joinedload(Faculty.user),
        )
        .where(JuryEvaluation.milestone_id == milestone_id)
        .order_by(JuryEvaluation.updated_at.desc())
    )
    evaluations = result.scalars().unique().all()

    rows: List[AdminEvaluationResponse] = []
    for ev in evaluations:
        project_name, fyp_id = _project_labels(ev.group)
        grade = getattr(ev.letter_grade, "value", str(ev.letter_grade))
        fb_parts = [f"Letter grade: {grade}"]
        if ev.comments:
            fb_parts.append(ev.comments)
        feedback = "\n\n".join(fb_parts)

        rows.append(
            AdminEvaluationResponse(
                evaluation_id=ev.evaluation_id,
                milestone_id=ev.milestone_id,
                group_id=ev.group_id,
                supervisor_id=ev.jury_id,
                supervisor_name=_faculty_display_name(ev.jury_member),
                project_name=project_name,
                fyp_id=fyp_id,
                marks=_numeric_optional(ev.numeric_marks),
                feedback=feedback,
                wbs_achieved=None,
                created_at=ev.created_at,
                updated_at=ev.updated_at,
                is_jury_evaluation=True,
            )
        )
    return rows


async def _list_jury_proposal_evaluations_admin(
    db: AsyncSession,
    milestone_id: UUID,
) -> List[AdminEvaluationResponse]:
    result = await db.execute(
        select(ProposalEvaluation)
        .options(
            joinedload(ProposalEvaluation.group).joinedload(Group.project),
            joinedload(ProposalEvaluation.jury_member).joinedload(Faculty.user),
        )
        .where(ProposalEvaluation.milestone_id == milestone_id)
        .order_by(ProposalEvaluation.updated_at.desc())
    )
    evaluations = result.scalars().unique().all()

    rows: List[AdminEvaluationResponse] = []
    for ev in evaluations:
        project_name, fyp_id = _project_labels(ev.group)
        rows.append(
            AdminEvaluationResponse(
                evaluation_id=ev.evaluation_id,
                milestone_id=ev.milestone_id,
                group_id=ev.group_id,
                supervisor_id=ev.jury_id,
                supervisor_name=_faculty_display_name(ev.jury_member),
                project_name=project_name,
                fyp_id=fyp_id,
                marks=_numeric_optional(ev.total_marks),
                feedback=_proposal_feedback_text(ev),
                wbs_achieved=None,
                created_at=ev.created_at,
                updated_at=ev.updated_at,
                is_jury_evaluation=True,
            )
        )
    return rows


async def list_evaluations_for_milestone(
    db: AsyncSession,
    milestone_id: UUID,
) -> List[AdminEvaluationResponse]:
    """
    All evaluations visible to admin for a milestone.

    Includes supervisor evaluations. For milestones with evaluator ``jury``,
    also includes rows from ``jury_evaluations`` (normal form) or
    ``proposal_evaluations`` (proposal form), depending on ``jury_form_type``.
    """
    milestone = await get_milestone(db, milestone_id)
    if not milestone:
        return []

    rows = await _list_supervisor_evaluations(db, milestone_id)

    evaluator = (milestone.evaluator or "").strip().lower()
    if evaluator == "jury":
        if milestone.jury_form_type == JuryFormTypeEnum.normal:
            rows.extend(await _list_jury_normal_evaluations_admin(db, milestone_id))
        elif milestone.jury_form_type == JuryFormTypeEnum.proposal:
            rows.extend(await _list_jury_proposal_evaluations_admin(db, milestone_id))

    rows.sort(key=lambda r: r.updated_at, reverse=True)
    return rows


async def list_milestones(
    db: AsyncSession,
    fyp_cycle: Optional[FYPCycleEnum] = None,
) -> List[AdminMilestone]:
    """Return all milestones, optionally filtered by cycle."""
    query = select(AdminMilestone).order_by(
        AdminMilestone.due_date, AdminMilestone.created_at
    )
    if fyp_cycle:
        query = query.where(AdminMilestone.fyp_cycle == fyp_cycle)

    result = await db.execute(query)
    milestones = result.scalars().all()
    logger.debug("Fetched %s milestones (cycle=%s)", len(milestones), fyp_cycle)
    return milestones


async def get_milestone(
    db: AsyncSession,
    milestone_id: UUID,
) -> Optional[AdminMilestone]:
    """Fetch a single milestone by ID."""
    result = await db.execute(
        select(AdminMilestone).where(AdminMilestone.milestone_id == milestone_id)
    )
    milestone = result.scalar_one_or_none()
    if milestone:
        logger.debug("Milestone %s found", milestone_id)
    else:
        logger.debug("Milestone %s not found", milestone_id)
    return milestone


async def create_milestone(
    db: AsyncSession,
    payload: AdminMilestoneCreate,
) -> AdminMilestone:
    """Create and persist a new milestone."""
    data = payload.model_dump()
    if data.get("is_active") and not data.get("activated_at"):
        data["activated_at"] = datetime.now(timezone.utc)

    milestone = AdminMilestone(**data)
    db.add(milestone)
    await db.commit()
    await db.refresh(milestone)
    logger.info("Milestone %s created", milestone.milestone_id)
    return milestone


async def update_milestone(
    db: AsyncSession,
    milestone_id: UUID,
    payload: AdminMilestoneUpdate,
) -> Optional[AdminMilestone]:
    """Update an existing milestone; returns None if not found."""
    milestone = await get_milestone(db, milestone_id)
    if not milestone:
        return None

    update_data = payload.model_dump(exclude_unset=True)
    is_active_change = (
        update_data.get("is_active") if "is_active" in update_data else None
    )
    for field, value in update_data.items():
        setattr(milestone, field, value)

    if is_active_change is True and milestone.activated_at is None:
        milestone.activated_at = datetime.now(timezone.utc)
    elif is_active_change is False:
        milestone.activated_at = None

    await db.commit()
    await db.refresh(milestone)
    logger.info("Milestone %s updated", milestone_id)
    return milestone


async def delete_milestone(
    db: AsyncSession,
    milestone_id: UUID,
) -> bool:
    """Delete a milestone by ID. Returns True if something was deleted."""
    result = await db.execute(
        delete(AdminMilestone).where(AdminMilestone.milestone_id == milestone_id)
    )
    deleted = result.rowcount > 0
    if deleted:
        logger.info("Milestone %s deleted", milestone_id)
        await db.commit()
    else:
        logger.debug("Milestone %s delete requested but not found", milestone_id)
    return deleted
