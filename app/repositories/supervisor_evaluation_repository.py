from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.supervisor_evaluation import SupervisorEvaluation
from app.schemas.supervisor_evaluation_schema import SupervisorEvaluationPayload


async def get_marks_for_group_milestone(
    db: AsyncSession,
    *,
    milestone_id: UUID,
    group_id: UUID,
) -> Optional[float]:
    """Return marks from the first evaluation found for this group + milestone."""
    result = await db.execute(
        select(SupervisorEvaluation.marks)
        .where(
            SupervisorEvaluation.milestone_id == milestone_id,
            SupervisorEvaluation.group_id == group_id,
            SupervisorEvaluation.marks.is_not(None),
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_evaluation(
    db: AsyncSession,
    *,
    milestone_id: UUID,
    group_id: UUID,
    supervisor_id: UUID,
) -> Optional[SupervisorEvaluation]:
    result = await db.execute(
        select(SupervisorEvaluation).where(
            SupervisorEvaluation.milestone_id == milestone_id,
            SupervisorEvaluation.group_id == group_id,
            SupervisorEvaluation.supervisor_id == supervisor_id,
        )
    )
    return result.scalar_one_or_none()


async def list_evaluations_for_supervisor(
    db: AsyncSession,
    *,
    milestone_id: UUID,
    supervisor_id: UUID,
) -> List[SupervisorEvaluation]:
    result = await db.execute(
        select(SupervisorEvaluation)
        .where(
            SupervisorEvaluation.milestone_id == milestone_id,
            SupervisorEvaluation.supervisor_id == supervisor_id,
        )
        .order_by(SupervisorEvaluation.updated_at.desc())
    )
    return result.scalars().all()


async def list_evaluations_for_milestone(
    db: AsyncSession,
    *,
    milestone_id: UUID,
) -> List[SupervisorEvaluation]:
    result = await db.execute(
        select(SupervisorEvaluation)
        .where(SupervisorEvaluation.milestone_id == milestone_id)
        .order_by(SupervisorEvaluation.updated_at.desc())
    )
    return result.scalars().all()


async def create_evaluation(
    db: AsyncSession,
    *,
    milestone_id: UUID,
    group_id: UUID,
    supervisor_id: UUID,
    payload: SupervisorEvaluationPayload,
) -> SupervisorEvaluation:
    data = payload.model_dump(exclude_unset=True)
    evaluation = SupervisorEvaluation(
        milestone_id=milestone_id,
        group_id=group_id,
        supervisor_id=supervisor_id,
        **data,
    )
    db.add(evaluation)
    await db.commit()
    await db.refresh(evaluation)
    return evaluation


async def update_evaluation(
    db: AsyncSession,
    *,
    evaluation: SupervisorEvaluation,
    payload: SupervisorEvaluationPayload,
) -> SupervisorEvaluation:
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(evaluation, field, value)

    await db.commit()
    await db.refresh(evaluation)
    return evaluation
