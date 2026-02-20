from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.supervisor_evaluation import SupervisorEvaluation
from app.schemas.supervisor_evaluation_schema import SupervisorEvaluationPayload


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


async def upsert_evaluation(
    db: AsyncSession,
    *,
    milestone_id: UUID,
    group_id: UUID,
    supervisor_id: UUID,
    payload: SupervisorEvaluationPayload,
) -> SupervisorEvaluation:
    evaluation = await get_evaluation(
        db,
        milestone_id=milestone_id,
        group_id=group_id,
        supervisor_id=supervisor_id,
    )

    data = payload.model_dump(exclude_unset=True)

    if evaluation is None:
        evaluation = SupervisorEvaluation(
            milestone_id=milestone_id,
            group_id=group_id,
            supervisor_id=supervisor_id,
            **data,
        )
        db.add(evaluation)
    else:
        for field, value in data.items():
            setattr(evaluation, field, value)

    await db.commit()
    await db.refresh(evaluation)
    return evaluation
