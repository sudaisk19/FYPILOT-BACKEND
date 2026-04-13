from fastapi import APIRouter, Depends

from app.auth.supabase_auth import get_current_user
from app.core.departments import COMMON_UNIVERSITY_DEPARTMENTS
from app.models.user import User
from app.schemas.bulk_import_schema import DepartmentListResponse

router = APIRouter()


@router.get(
    "/departments",
    response_model=DepartmentListResponse,
    summary="List allowed departments",
    description="Return the canonical list of departments for dropdown population (all authenticated roles).",
)
async def get_departments(
    current_user: User = Depends(get_current_user),
):
    """Expose canonical departments so FE dropdowns stay in sync with backend validation."""

    return DepartmentListResponse(departments=COMMON_UNIVERSITY_DEPARTMENTS)
