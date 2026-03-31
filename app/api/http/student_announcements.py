# app/api/http/student_announcements.py
"""
Student Announcements API

Provides READ-ONLY endpoints for students to view:
  1. Supervisor announcements targeted at their group  → /supervisor
  2. Admin announcements targeted at students          → /admin

All DB logic is delegated to AnnouncementRepository.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase_auth import get_current_user
from app.db import get_db
from app.models.announcement import TargetRoleEnum
from app.models.group import FYPCycleEnum, Group, GroupMember
from app.models.user import RoleEnum, User
from app.repositories.announcement_repository import announcement_repository
from app.schemas.admin_announcement_schema import (
    PaginatedAnnouncements as PaginatedAdminAnnouncements,
)
from app.schemas.student_announcement_schema import (
    PaginatedStudentAnnouncements,
    StudentAnnouncementFileResponse,
    StudentAnnouncementResponse,
    TemplateFileResponse,
)

router = APIRouter(tags=["student-announcements"])


# ─── HELPER ───────────────────────────────────────────────────────────────────


async def _get_student_group(user_id: UUID, db: AsyncSession) -> Optional[Group]:
    """Return the group the student belongs to, or None if ungrouped."""
    result = await db.execute(
        select(Group)
        .join(GroupMember, GroupMember.group_id == Group.group_id)
        .where(GroupMember.student_id == user_id)
        .limit(1)
    )
    return result.scalars().first()


# ─── SUPERVISOR ANNOUNCEMENTS TAB ─────────────────────────────────────────────


@router.get("/supervisor", response_model=PaginatedStudentAnnouncements)
async def get_supervisor_announcements_for_student(
    page: int = Query(1, ge=1, description="Page number starting from 1"),
    per_page: int = Query(10, ge=1, le=50, description="Items per page"),
    search: Optional[str] = Query(None, description="Search by title"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Student: List announcements made by their supervisor for their group."""
    if current_user.role != RoleEnum.student:
        raise HTTPException(status_code=403, detail="Student only")

    student_group = await _get_student_group(current_user.user_id, db)
    if not student_group:
        return PaginatedStudentAnnouncements(
            announcements=[],
            total_items=0,
            total_pages=1,
            current_page=page,
            per_page=per_page,
        )

    announcements, total_items = (
        await announcement_repository.get_supervisor_announcements_for_student(
            db,
            group_id=student_group.group_id,
            page=page,
            per_page=per_page,
            search=search,
        )
    )

    total_pages = (total_items + per_page - 1) // per_page if total_items > 0 else 1

    items = [
        StudentAnnouncementResponse(
            announcement_id=a.announcement_id,
            title=a.title,
            description=a.description,
            supervisor_name=a.creator.full_name if a.creator else None,
            created_at=a.created_at,
            updated_at=a.updated_at,
            files=[
                StudentAnnouncementFileResponse(
                    file_id=f.file_id,
                    file_name=f.file_name,
                    storage_key=f.storage_key,
                    file_type=f.file_type,
                    mime_type=f.mime_type,
                    size_bytes=f.size_bytes,
                )
                for f in a.files
            ],
        )
        for a in announcements
    ]

    return PaginatedStudentAnnouncements(
        announcements=items,
        total_items=total_items,
        total_pages=total_pages,
        current_page=page,
        per_page=per_page,
    )


# ─── ADMIN ANNOUNCEMENTS TAB ──────────────────────────────────────────────────


@router.get("/admin", response_model=PaginatedAdminAnnouncements)
async def get_admin_announcements_for_student(
    page: int = Query(1, ge=1, description="Page number starting from 1"),
    per_page: int = Query(10, ge=1, le=50, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Student: List admin announcements targeted at students.

    Returns announcements with target_role of:
      - all_students  (always visible to all students)
      - both          (visible to both students and supervisors)
      - fyp1_students (only if student's group is fyp1)
      - fyp2_students (only if student's group is fyp2)
    """
    if current_user.role != RoleEnum.student:
        raise HTTPException(status_code=403, detail="Student only")

    # Always include these roles
    relevant_roles = [TargetRoleEnum.all_students, TargetRoleEnum.both]

    # Add fyp-cycle specific role based on the student's group
    student_group = await _get_student_group(current_user.user_id, db)
    if student_group:
        if student_group.fyp_cycle == FYPCycleEnum.fyp1:
            relevant_roles.append(TargetRoleEnum.fyp1_students)
        elif student_group.fyp_cycle == FYPCycleEnum.fyp2:
            relevant_roles.append(TargetRoleEnum.fyp2_students)
    else:
        # Ungrouped student — show all fyp-cycle announcements as fallback
        relevant_roles.append(TargetRoleEnum.fyp1_students)
        relevant_roles.append(TargetRoleEnum.fyp2_students)

    announcements, total_items = (
        await announcement_repository.get_admin_announcements_for_student(
            db,
            target_roles=relevant_roles,
            page=page,
            per_page=per_page,
        )
    )

    total_pages = (total_items + per_page - 1) // per_page if total_items > 0 else 1

    return PaginatedAdminAnnouncements(
        announcements=announcements,
        total_items=total_items,
        total_pages=total_pages,
        current_page=page,
        per_page=per_page,
    )


# ─── TEMPLATE PICKER ──────────────────────────────────────────────────────────


@router.get("/templates", response_model=list[TemplateFileResponse])
async def get_templates_for_student(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return all admin-uploaded Template files visible to the requesting student.

    Scoping rules (same as admin announcements tab):
      - Always includes: all_students, both
      - Includes fyp1_students or fyp2_students based on the student's group FYP cycle
      - Ungrouped students see all FYP-cycle templates as a fallback

    Used by the frontend template picker modal before importing a template
    via POST /api/students/chat-sessions/{session_id}/import-template.
    """
    if current_user.role != RoleEnum.student:
        raise HTTPException(status_code=403, detail="Student only")

    # Determine target roles same way as admin announcements tab
    relevant_roles = [TargetRoleEnum.all_students, TargetRoleEnum.both]
    student_group = await _get_student_group(current_user.user_id, db)
    if student_group:
        if student_group.fyp_cycle == FYPCycleEnum.fyp1:
            relevant_roles.append(TargetRoleEnum.fyp1_students)
        elif student_group.fyp_cycle == FYPCycleEnum.fyp2:
            relevant_roles.append(TargetRoleEnum.fyp2_students)
    else:
        relevant_roles.extend(
            [TargetRoleEnum.fyp1_students, TargetRoleEnum.fyp2_students]
        )

    files = await announcement_repository.get_templates_for_student(
        db, target_roles=relevant_roles
    )

    return [
        TemplateFileResponse(
            file_id=f.file_id,
            file_name=f.file_name,
            mime_type=f.mime_type,
            size_bytes=f.size_bytes,
            uploaded_at=f.uploaded_at,
            announcement_id=f.announcement.announcement_id,
            announcement_title=f.announcement.title,
        )
        for f in files
    ]
