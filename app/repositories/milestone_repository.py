# app/repositories/milestone_repository.py
import logging
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.milestone import AdminMilestone
from app.models.group import FYPCycleEnum
from app.schemas.admin_milestone_schema import (
    AdminMilestoneCreate,
    AdminMilestoneUpdate,
)

logger = logging.getLogger(__name__)


async def list_milestones(
    db: AsyncSession,
    fyp_cycle: Optional[FYPCycleEnum] = None,
) -> List[AdminMilestone]:
    """Return all milestones, optionally filtered by cycle."""
    query = select(AdminMilestone).order_by(AdminMilestone.due_date, AdminMilestone.created_at)
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
    admin_id: UUID,
) -> AdminMilestone:
    """Create and persist a new milestone."""
    data = payload.model_dump()
    if data.get("is_active") and not data.get("activated_at"):
        data["activated_at"] = datetime.now(timezone.utc)

    milestone = AdminMilestone(
        admin_id=admin_id,
        **data,
    )
    db.add(milestone)
    await db.commit()
    await db.refresh(milestone)
    logger.info("Milestone %s created by admin %s", milestone.milestone_id, admin_id)
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
    is_active_change = update_data.get("is_active") if "is_active" in update_data else None
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