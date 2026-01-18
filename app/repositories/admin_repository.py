# app/repositories/admin_repository.py
"""
Admin Repository Module

Handles all database operations for the Admin model and system statistics.
"""

from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import Admin
from app.models.group import Group
from app.models.project import Project
from app.models.student import Student
from app.models.supervisor import Supervisor

from .base import BaseRepository


class AdminRepository(BaseRepository[Admin]):
    """Repository for Admin model operations."""

    def __init__(self):
        super().__init__(Admin)

    async def get_by_user_id(
        self, db: AsyncSession, user_id: UUID
    ) -> Optional[Admin]:
        """
        Get admin profile by user ID.

        Args:
            db: Database session
            user_id: User's UUID

        Returns:
            Admin instance or None
        """
        query = select(Admin).where(Admin.user_id == user_id)
        result = await db.execute(query)
        return result.scalars().first()

    async def create(
        self,
        db: AsyncSession,
        user_id: UUID,
        phone: Optional[str] = None,
        profile_pic: Optional[str] = None,
    ) -> Admin:
        """
        Create a new admin profile.

        Args:
            db: Database session
            user_id: User's UUID (foreign key)
            phone: Admin's phone number
            profile_pic: Profile picture URL

        Returns:
            Created Admin instance
        """
        admin_data = {"user_id": user_id}

        if phone is not None:
            admin_data["phone"] = phone
        if profile_pic is not None:
            admin_data["profile_pic"] = profile_pic

        return await super().create(db, admin_data)

    async def update(
        self,
        db: AsyncSession,
        user_id: UUID,
        updates: Dict[str, Any],
    ) -> Optional[Admin]:
        """
        Update admin profile fields.

        Args:
            db: Database session
            user_id: User's UUID
            updates: Dictionary of fields to update

        Returns:
            Updated Admin instance or None if not found
        """
        admin = await self.get_by_user_id(db, user_id)
        if not admin:
            return None
        return await super().update(db, admin, updates)

    async def exists(
        self, db: AsyncSession, user_id: UUID
    ) -> bool:
        """
        Check if an admin profile exists for the given user.

        Args:
            db: Database session
            user_id: User's UUID

        Returns:
            True if profile exists, False otherwise
        """
        admin = await self.get_by_user_id(db, user_id)
        return admin is not None

    # --- System Statistics ---

    async def get_system_stats(
        self, db: AsyncSession
    ) -> Dict[str, int]:
        """
        Get system-wide statistics for admin dashboard.

        Args:
            db: Database session

        Returns:
            Dictionary with counts for students, supervisors, groups, projects, pending_invites
        """
        try:
            # Count students
            students_count = await db.execute(
                select(func.count()).select_from(Student)
            )
            total_students = students_count.scalar_one()

            # Count supervisors
            supervisors_count = await db.execute(
                select(func.count()).select_from(Supervisor)
            )
            total_supervisors = supervisors_count.scalar_one()

            # Count groups
            groups_count = await db.execute(
                select(func.count()).select_from(Group)
            )
            total_groups = groups_count.scalar_one()

            # Count projects
            projects_count = await db.execute(
                select(func.count()).select_from(Project)
            )
            total_projects = projects_count.scalar_one()

            # Count pending invites using raw SQL to avoid enum constraint issues
            try:
                invites_count = await db.execute(
                    text(
                        """
                        SELECT COUNT(*) 
                        FROM group_invites 
                        WHERE status = 'pending'::invite_status_enum
                    """
                    )
                )
                pending_invites = invites_count.scalar_one()
            except Exception:
                pending_invites = 0

            return {
                "total_students": total_students,
                "total_supervisors": total_supervisors,
                "total_groups": total_groups,
                "total_projects": total_projects,
                "pending_invites": pending_invites,
            }
        except Exception:
            # Return default stats if there's an error
            return {
                "total_students": 0,
                "total_supervisors": 0,
                "total_groups": 0,
                "total_projects": 0,
                "pending_invites": 0,
            }

    async def count_students(self, db: AsyncSession) -> int:
        """Count total students."""
        result = await db.execute(select(func.count()).select_from(Student))
        return result.scalar_one()

    async def count_supervisors(self, db: AsyncSession) -> int:
        """Count total supervisors."""
        result = await db.execute(select(func.count()).select_from(Supervisor))
        return result.scalar_one()

    async def count_groups(self, db: AsyncSession) -> int:
        """Count total groups."""
        result = await db.execute(select(func.count()).select_from(Group))
        return result.scalar_one()

    async def count_projects(self, db: AsyncSession) -> int:
        """Count total projects."""
        result = await db.execute(select(func.count()).select_from(Project))
        return result.scalar_one()


# Singleton instance for convenience
admin_repository = AdminRepository()
