# app/api/http/router.py
from fastapi import APIRouter

# Import admin router
from app.api.http.admin_announcements import router as admin_announcements_router
from app.api.http.admin_dashboard import router as admin_dashboard_router
from app.api.http.admin_groups import router as admin_groups_router
from app.api.http.admin_profile import router as admin_profile_router

# Import admin router
from app.api.http.admin_students import router as admin_students_router
from app.api.http.admin_supervisors import router as admin_faculty_router

# Import bulk import router
from app.api.http.bulk_import import router as bulk_import_router
from app.api.http.faculty_dashboard import router as faculty_dashboard_router
from app.api.http.group import router as group_router

# Import each feature's router
from app.api.http.health import router as health_router

# Import profile status router
from app.api.http.profile_status import router as profile_status_router
from app.api.http.shortlist import router as shortlist_router

# Import profile routers
from app.api.http.student_profile import router as student_profile_router

# Import student progress router
from app.api.http.student_progress import router as student_progress_router
from app.api.http.submissions import router as submissions_router

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
    supervisor_profile_router, prefix="/faculty", tags=["faculty-profile"]
)
router.include_router(admin_profile_router, prefix="/admins", tags=["admin-profile"])

# Mount student progress router
router.include_router(student_progress_router, prefix="/groups")

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

# Mount submissions router
router.include_router(submissions_router)

# Mount profile status router
router.include_router(profile_status_router, tags=["profile-status"])


router.include_router(admin_students_router, prefix="/admin", tags=["admin-students"])

router.include_router(admin_faculty_router, prefix="/admin", tags=["admin-faculty"])

router.include_router(admin_groups_router)

router.include_router(admin_announcements_router)
router.include_router(admin_dashboard_router)
router.include_router(faculty_dashboard_router)
# Mount bulk import router (admin only)
# Mount user registration router (admin only — both single + bulk)
router.include_router(
    bulk_import_router,
    prefix="/admin/user-registration",
    tags=["admin-user-registration"],
)

from app.api.http.admin_submissions import router as admin_submissions_router

router.include_router(admin_submissions_router)

from app.api.http.admin_milestone import router as admin_milestones_router

router.include_router(admin_milestones_router)

from app.api.http.student_fypmilestone import router as student_milestones_router

router.include_router(
    student_milestones_router, prefix="/students", tags=["student-milestones"]
)

from app.api.http.supervisor_fypmilestone import router as supervisor_milestones_router

router.include_router(
    supervisor_milestones_router, prefix="/faculty", tags=["faculty-milestones"]
)
from app.api.http.supervisor_submissions import router as supervisor_submissions_router

router.include_router(supervisor_submissions_router, prefix="/faculty/submissions")

from app.api.http.supervisor_announcements import (
    router as supervisor_announcements_router,
)

router.include_router(supervisor_announcements_router, prefix="/faculty/announcements")

from app.api.http.student_announcements import router as student_announcements_router

router.include_router(
    student_announcements_router,
    prefix="/students/announcements",
    tags=["student-announcements"],
)

from app.api.http.student_dashboard import router as student_dashboard_router

router.include_router(
    student_dashboard_router,
    prefix="/students/dashboard",
    tags=["student-dashboard"],
)

from app.api.http.student_submissions import router as student_submissions_router

router.include_router(
    student_submissions_router,
    prefix="/students/submissions",
    tags=["student-submissions"],
)

# Mount jury matching router
from app.api.http.jury_matching import router as jury_matching_router

router.include_router(jury_matching_router)

# Mount unified group documentation workspace router
from app.api.http.student_documents import router as student_documents_router

router.include_router(student_documents_router, tags=["student-documents"])

from app.api.http.collaborative_chat import router as collaborative_chat_router
from app.api.http.student_whiteboards import router as student_whiteboards_router

router.include_router(collaborative_chat_router)
router.include_router(student_whiteboards_router, tags=["Whiteboards"])
