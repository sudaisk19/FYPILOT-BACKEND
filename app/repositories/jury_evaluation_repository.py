from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.jury_evaluation import JuryEvaluation
from app.schemas.jury_evaluation_schema import JuryEvaluationPayload


async def get_evaluation(
    db: AsyncSession,
    *,
    milestone_id: UUID,
    group_id: UUID,
    jury_id: UUID,
) -> Optional[JuryEvaluation]:
    result = await db.execute(
        select(JuryEvaluation).where(
            JuryEvaluation.milestone_id == milestone_id,
            JuryEvaluation.group_id == group_id,
            JuryEvaluation.jury_id == jury_id,
        )
    )
    return result.scalar_one_or_none()


async def list_evaluations_for_jury(
    db: AsyncSession,
    *,
    milestone_id: UUID,
    jury_id: UUID,
) -> List[JuryEvaluation]:
    result = await db.execute(
        select(JuryEvaluation)
        .where(
            JuryEvaluation.milestone_id == milestone_id,
            JuryEvaluation.jury_id == jury_id,
        )
        .order_by(JuryEvaluation.updated_at.desc())
    )
    return result.scalars().all()


async def create_evaluation(
    db: AsyncSession,
    *,
    milestone_id: UUID,
    group_id: UUID,
    jury_id: UUID,
    payload: JuryEvaluationPayload,
) -> JuryEvaluation:
    data = payload.model_dump(exclude_unset=True)
    evaluation = JuryEvaluation(
        milestone_id=milestone_id,
        group_id=group_id,
        jury_id=jury_id,
        **data,
    )
    db.add(evaluation)
    await db.commit()
    await db.refresh(evaluation)
    return evaluation


async def update_evaluation(
    db: AsyncSession,
    *,
    evaluation: JuryEvaluation,
    payload: JuryEvaluationPayload,
) -> JuryEvaluation:
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(evaluation, field, value)
    await db.commit()
    await db.refresh(evaluation)
    return evaluation


async def get_numeric_marks(
    db: AsyncSession,
    *,
    milestone_id: UUID,
    group_id: UUID,
) -> Optional[float]:
    result = await db.execute(
        select(JuryEvaluation.numeric_marks)
        .where(
            JuryEvaluation.milestone_id == milestone_id,
            JuryEvaluation.group_id == group_id,
            JuryEvaluation.numeric_marks.is_not(None),
        )
        .limit(1)
    )
    marks = result.scalar_one_or_none()
    return float(marks) if marks is not None else None
