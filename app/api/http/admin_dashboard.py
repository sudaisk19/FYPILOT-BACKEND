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

    service = AdminDashboardService(db)
    return await service.get_dashboard_payload()
