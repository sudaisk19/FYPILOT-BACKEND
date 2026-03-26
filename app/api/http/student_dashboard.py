"""HTTP endpoints for the student dashboard widgets."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase_auth import get_current_user
from app.db import get_db
from app.models.user import RoleEnum, User
from app.schemas.student_dashboard_schema import StudentDashboardEnvelope
from app.services.student_dashboard_service import StudentDashboardService

router = APIRouter(tags=["student-dashboard"])


@router.get("/insights", response_model=StudentDashboardEnvelope)
async def get_student_dashboard_insights(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StudentDashboardEnvelope:
    """Return the aggregated metrics for the student dashboard UI."""

    if current_user.role != RoleEnum.student:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Student only"
        )

    from app.services.cache import cache

    cache_key = f"student_dashboard:{current_user.user_id}"
    cached_data = await cache.get_json(cache_key)
    if cached_data:
        # Avoid validation overhead if possible, but since response_model handles it,
        # we can just return the raw dict or the validated model. Returning model ensures type safety.
        return StudentDashboardEnvelope(**cached_data)

    service = StudentDashboardService(db)
    payload = await service.get_dashboard_payload(current_user.user_id)

    # Cache for 10 minutes (600 seconds)
    await cache.set_json(cache_key, payload.model_dump(mode="json"), ttl_seconds=600)

    return payload
