# app/api/http/router.py
from fastapi import APIRouter

from app.api.http.admin_groups import router as admin_groups_router
from app.api.http.admin_profile import router as admin_profile_router

# Import admin router
from app.api.http.admin_students import router as admin_students_router
from app.api.http.admin_supervisors import router as admin_supervisors_router

# Import bulk import router
from app.api.http.bulk_import import router as bulk_import_router
from app.api.http.group import router as group_router

# Import each feature's router
from app.api.http.health import router as health_router

# Import profile status router
from app.api.http.profile_status import router as profile_status_router
from app.api.http.shortlist import router as shortlist_router

# Import profile routers
from app.api.http.student_profile import router as student_profile_router

# Import explore routers
from app.api.http.supervisor_explore import router as supervisor_explore_router
from app.api.http.supervisor_groups import router as supervisor_groups_router
from app.api.http.supervisor_invites import router as invites_router
from app.api.http.supervisor_profile import router as supervisor_profile_router
from app.api.http.supervisor_recommendation import (
    router as supervisor_recommendation_router,
)
from app.api.http.users import router as user_router

# Create a "master" router that mounts all HTTP routers
router = APIRouter()

# Mount them under their prefixes
router.include_router(health_router, prefix="/health", tags=["health"])

router.include_router(group_router, tags=["groups"])
router.include_router(user_router, prefix="/users")

# Mount profile routers
router.include_router(
    student_profile_router, prefix="/students", tags=["student-profile"]
)
router.include_router(
    supervisor_profile_router, prefix="/supervisors", tags=["supervisor-profile"]
)
router.include_router(admin_profile_router, prefix="/admins", tags=["admin-profile"])

# Mount explore routers
router.include_router(
    supervisor_explore_router, prefix="/explore", tags=["supervisor-explore"]
)

# Mount recommendation router
router.include_router(supervisor_recommendation_router)

# Mount shortlist router
router.include_router(shortlist_router)

# Mount supervisor invites router
router.include_router(invites_router)

# Mount supervisor groups directory router
router.include_router(supervisor_groups_router)

# Mount profile status router
router.include_router(profile_status_router, tags=["profile-status"])

# Mount admin routers
router.include_router(admin_profile_router, prefix="/admins", tags=["admin-profile"])

router.include_router(admin_students_router, prefix="/admin", tags=["admin-students"])

router.include_router(
    admin_supervisors_router, prefix="/admin", tags=["admin-supervisors"]
)

router.include_router(admin_groups_router)

# Mount bulk import router (admin only)
router.include_router(
    bulk_import_router, prefix="/admin/bulk-imports", tags=["admin-bulk-import"]
)
