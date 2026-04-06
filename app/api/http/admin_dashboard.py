"""HTTP endpoints for the admin dashboard widgets."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase_auth import get_current_user
from app.db import get_db
from app.models.user import RoleEnum, User
from app.schemas.dashboard_schema import AdminDashboardEnvelope
from app.services.admin_dashboard_service import AdminDashboardService

router = APIRouter(prefix="/admin/dashboard", tags=["admin-dashboard"])


@router.get("/insights", response_model=AdminDashboardEnvelope)
async def get_admin_dashboard_insights(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AdminDashboardEnvelope:
    """Return the latest aggregated metrics for the admin dashboard UI."""

    if current_user.role != RoleEnum.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    from app.services.cache import cache

    cache_key = "admin_dashboard_insights"
    cached_data = await cache.get_json(cache_key)
    if cached_data:
        return AdminDashboardEnvelope(**cached_data)

    service = AdminDashboardService(db)
    payload = await service.get_dashboard_payload()

    # Cache for 10 minutes (600 seconds)
    await cache.set_json(cache_key, payload.model_dump(mode="json"), ttl_seconds=600)

    return payload
