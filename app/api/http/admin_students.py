# app/api/http/admin_students.py
# this api is displaying all the stidents to the admin
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase_auth import get_current_user
from app.db import get_db
from app.models.group import FYPCycleEnum, Group, GroupMember
from app.models.project import Project
from app.models.student import Student
from app.models.user import RoleEnum, User
from app.schemas.admin_students_schema import (
    PaginatedStudentResponse,
    StudentActiveToggleRequest,
    StudentCardInfo,
)

router = APIRouter()


@router.get("/students", response_model=PaginatedStudentResponse)
async def list_students(
    batch: Optional[int] = Query(None),
    cycle: Optional[FYPCycleEnum] = Query(None),
    group: Literal["all", "assigned", "unassigned"] = Query("all"),
    department: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role != RoleEnum.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    # ── 1. Check Redis Cache ──────────────────────────────────────────────
    # Construct unique key based on ALL filters
    cache_key = (
        f"admin:students:{batch}:{cycle}:{group}:{department}:"
        f"{search}:{page}:{per_page}"
    )
    from app.services.cache import cache

    cached = await cache.get_json(cache_key)
    if cached:
        return cached

    # ✅ Select Project.name ONLY (not Project entity)
    query = (
        select(
            User,
            Student,
            Group,
            GroupMember,
            Project.name.label("project_name"),
        )
        .join(Student, User.user_id == Student.user_id)
        .outerjoin(GroupMember, GroupMember.student_id == Student.user_id)
        .outerjoin(Group, Group.group_id == GroupMember.group_id)
        .outerjoin(Project, Project.group_id == Group.group_id)
        .where(User.role == RoleEnum.student)
    )

    filters = []

    # Assignment filter (based on group membership)
    if group == "assigned":
        filters.append(GroupMember.student_id.isnot(None))
    elif group == "unassigned":
        filters.append(GroupMember.student_id.is_(None))

    if department:
        filters.append(Student.department.ilike(f"%{department}%"))

    if batch is not None:
        prefix = f"{batch - 2004}K"
        filters.append(Student.roll_number.ilike(f"{prefix}%"))

    if cycle is not None:
        filters.append(Group.fyp_cycle == cycle)

    if search:
        s = f"%{search}%"
        # SARGable fix: cohort_year is INTEGER — casting to String for ILIKE
        # prevents index usage and causes a full table scan. Instead, we try to
        # parse the search term as an integer and compare directly. We also
        # search the text `cohort` column (e.g. "F24") with prefix matching.
        cohort_year_filter = []
        try:
            cohort_year_int = int(search)
            cohort_year_filter.append(Group.cohort_year == cohort_year_int)
        except (ValueError, TypeError):
            pass

        filters.append(
            or_(
                User.full_name.ilike(s),
                User.email.ilike(s),
                Student.roll_number.ilike(s),
                Project.name.ilike(s),  # project name search
                # Text cohort code (e.g. "F24") — trailing wildcard is SARGable
                Group.cohort.ilike(f"{search}%"),
                *cohort_year_filter,
            )
        )

    if filters:
        query = query.where(and_(*filters))

    # Count unique students (safe)
    count_query = (
        select(func.count(func.distinct(User.user_id)))
        .select_from(User)
        .join(Student, User.user_id == Student.user_id)
        .outerjoin(GroupMember, GroupMember.student_id == Student.user_id)
        .outerjoin(Group, Group.group_id == GroupMember.group_id)
        .outerjoin(Project, Project.group_id == Group.group_id)
        .where(User.role == RoleEnum.student)
    )
    if filters:
        count_query = count_query.where(and_(*filters))

    total = (await db.execute(count_query)).scalar() or 0

    offset = (page - 1) * per_page
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1

    query = query.order_by(User.full_name.asc()).offset(offset).limit(per_page)
    rows = (await db.execute(query)).all()

    students_out = []
    for user, student, group, gm, project_name in rows:
        assigned = gm is not None

        # UI logic:
        # - project label: project_name if exists else "Not assigned"
        students_out.append(
            StudentCardInfo(
                user_id=str(user.user_id),
                full_name=user.full_name,
                email=user.email,
                roll_number=student.roll_number,
                department=student.department,
                project_name=project_name if project_name else None,
                fyp_cycle=group.fyp_cycle.value if group else None,
                cohort_year=group.cohort_year if group else None,
                assigned=assigned,
                is_active=student.is_active,
            )
        )

    response = PaginatedStudentResponse(
        students=students_out,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )

    # ── Cache Result (TTL 60s) ────────────────────────────────────────────
    await cache.set_json(cache_key, response.model_dump(), ttl_seconds=60)

    return response


@router.patch("/students/{user_id}/toggle-active")
async def toggle_student_active(
    user_id: str,
    payload: StudentActiveToggleRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manual override for student active status."""
    if current_user.role != RoleEnum.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    # Fetch the student
    from uuid import UUID

    try:
        uuid_id = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID")

    student = await db.get(Student, uuid_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    # Update status
    student.is_active = payload.is_active
    await db.commit()

    # Clear cache for this admin view
    from app.services.cache import cache

    await cache.clear_pattern("admin:students:*")

    return {
        "message": f"Student {'activated' if payload.is_active else 'deactivated'} successfully"
    }
