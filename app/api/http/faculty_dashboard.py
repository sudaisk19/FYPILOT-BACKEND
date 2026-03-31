"""HTTP endpoints for the faculty dashboard widgets."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase_auth import get_current_user
from app.db import get_db
from app.models.user import RoleEnum, User
from app.schemas.dashboard_schema import FacultyDashboardEnvelope
from app.services.faculty_dashboard_service import FacultyDashboardService

router = APIRouter(prefix="/faculty/dashboard", tags=["faculty-dashboard"])


@router.get("/insights", response_model=FacultyDashboardEnvelope)
async def get_faculty_dashboard_insights(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FacultyDashboardEnvelope:
    """Return the aggregated metrics for the faculty dashboard UI."""

    if current_user.role != RoleEnum.faculty:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Faculty only"
        )

    faculty_profile = current_user.faculty_profile
    if not faculty_profile or not faculty_profile.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Faculty profile is inactive",
        )

    from app.services.cache import cache

    cache_key = f"faculty_dashboard:{current_user.user_id}"
    cached = await cache.get_json(cache_key)
    if cached:
        return FacultyDashboardEnvelope(**cached)

    service = FacultyDashboardService(db)
    payload = await service.get_dashboard_payload(faculty_profile)
    await cache.set_json(cache_key, payload.model_dump(mode="json"), ttl_seconds=600)
    return payload
