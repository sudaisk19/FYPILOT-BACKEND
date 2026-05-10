from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase_auth import get_current_user
from app.db import get_db
from app.models.industry import Industry
from app.models.user import User
from app.schemas.supervisor_explore_schema import IndustryListResponse

router = APIRouter()


@router.get(
    "/industries",
    response_model=IndustryListResponse,
    summary="List available industries",
    description="Return the list of all available industries for dropdown population (all authenticated roles).",
)
async def get_industries(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Expose all industries so FE dropdowns can be populated for selecting industries."""

    # Fetch all industries from database
    result = await db.execute(select(Industry).order_by(Industry.name))
    industries = result.scalars().all()

    return IndustryListResponse(
        industries=[
            {"industry_id": ind.industry_id, "name": ind.name} for ind in industries
        ]
    )
