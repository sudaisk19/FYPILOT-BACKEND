from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.jury_evaluation import ProposalEvaluation
from app.schemas.jury_evaluation_schema import (
    ProposalEvaluationConfigUpdate,
    ProposalEvaluationPayload,
)


@dataclass
class ProposalEvaluationStaticConfig:
    intro_max: float = 2.0
    literature_max: float = 2.0
    methodology_max: float = 2.0
    planning_max: float = 2.0
    diagram_max: float = 2.0


def _build_default_config() -> ProposalEvaluationStaticConfig:
    return ProposalEvaluationStaticConfig()


async def get_config(db: AsyncSession) -> ProposalEvaluationStaticConfig:
    # Config table is intentionally not used right now; keep fixed rubric caps.
    return _build_default_config()


async def update_config(
    db: AsyncSession,
    payload: ProposalEvaluationConfigUpdate,
) -> ProposalEvaluationStaticConfig:
    # Config updates are disabled while rubric caps are hardcoded.
    _ = db
    _ = payload
    return _build_default_config()


async def get_evaluation(
    db: AsyncSession,
    *,
    milestone_id: UUID,
    group_id: UUID,
    jury_id: UUID,
) -> Optional[ProposalEvaluation]:
    result = await db.execute(
        select(ProposalEvaluation).where(
            ProposalEvaluation.milestone_id == milestone_id,
            ProposalEvaluation.group_id == group_id,
            ProposalEvaluation.jury_id == jury_id,
        )
    )
    return result.scalar_one_or_none()


async def list_evaluations_for_jury(
    db: AsyncSession,
    *,
    milestone_id: UUID,
    jury_id: UUID,
) -> List[ProposalEvaluation]:
    result = await db.execute(
        select(ProposalEvaluation)
        .where(
            ProposalEvaluation.milestone_id == milestone_id,
            ProposalEvaluation.jury_id == jury_id,
        )
        .order_by(ProposalEvaluation.updated_at.desc())
    )
    return result.scalars().all()


def _enforce_max(value: Optional[float], maximum: Optional[Decimal]) -> Optional[float]:
    if value is None or maximum is None:
        return value
    return float(min(value, float(maximum)))


def _compute_total_from_values(
    introduction: Optional[float],
    literature_review: Optional[float],
    methodology: Optional[float],
    planning: Optional[float],
    system_diagram: Optional[float],
) -> Optional[float]:
    fields = [
        introduction,
        literature_review,
        methodology,
        planning,
        system_diagram,
    ]
    values = [v for v in fields if v is not None]
    if not values:
        return None
    return float(round(sum(values), 1))


async def create_evaluation(
    db: AsyncSession,
    *,
    milestone_id: UUID,
    group_id: UUID,
    jury_id: UUID,
    payload: ProposalEvaluationPayload,
) -> ProposalEvaluation:
    config = await get_config(db)
    adjusted = payload.model_dump(exclude_unset=True)
    adjusted["introduction"] = _enforce_max(payload.introduction, config.intro_max)
    adjusted["literature_review"] = _enforce_max(
        payload.literature_review, config.literature_max
    )
    adjusted["methodology"] = _enforce_max(payload.methodology, config.methodology_max)
    adjusted["planning"] = _enforce_max(payload.planning, config.planning_max)
    adjusted["system_diagram"] = _enforce_max(
        payload.system_diagram, config.diagram_max
    )
    if payload.total_marks is not None:
        adjusted["total_marks"] = payload.total_marks
    else:
        adjusted["total_marks"] = _compute_total_from_values(
            adjusted["introduction"],
            adjusted["literature_review"],
            adjusted["methodology"],
            adjusted["planning"],
            adjusted["system_diagram"],
        )

    evaluation = ProposalEvaluation(
        milestone_id=milestone_id,
        group_id=group_id,
        jury_id=jury_id,
        **adjusted,
    )
    db.add(evaluation)
    await db.commit()
    await db.refresh(evaluation)
    return evaluation


async def update_evaluation(
    db: AsyncSession,
    *,
    evaluation: ProposalEvaluation,
    payload: ProposalEvaluationPayload,
) -> ProposalEvaluation:
    config = await get_config(db)
    data = payload.model_dump(exclude_unset=True)
    if "introduction" in data:
        data["introduction"] = _enforce_max(data["introduction"], config.intro_max)
    if "literature_review" in data:
        data["literature_review"] = _enforce_max(
            data["literature_review"], config.literature_max
        )
    if "methodology" in data:
        data["methodology"] = _enforce_max(data["methodology"], config.methodology_max)
    if "planning" in data:
        data["planning"] = _enforce_max(data["planning"], config.planning_max)
    if "system_diagram" in data:
        data["system_diagram"] = _enforce_max(
            data["system_diagram"], config.diagram_max
        )

    if "total_marks" not in data:
        total = _compute_total_from_values(
            data.get("introduction", evaluation.introduction),
            data.get("literature_review", evaluation.literature_review),
            data.get("methodology", evaluation.methodology),
            data.get("planning", evaluation.planning),
            data.get("system_diagram", evaluation.system_diagram),
        )
        data["total_marks"] = total

    for field, value in data.items():
        setattr(evaluation, field, value)

    await db.commit()
    await db.refresh(evaluation)
    return evaluation


async def get_total_marks(
    db: AsyncSession,
    *,
    milestone_id: UUID,
    group_id: UUID,
) -> Optional[float]:
    result = await db.execute(
        select(ProposalEvaluation.total_marks)
        .where(
            ProposalEvaluation.milestone_id == milestone_id,
            ProposalEvaluation.group_id == group_id,
            ProposalEvaluation.total_marks.is_not(None),
        )
        .limit(1)
    )
    total = result.scalar_one_or_none()
    return float(total) if total is not None else None
