# app/repositories/shortlist_repository.py
"""
Shortlist Repository Module

Handles all database operations for the ShortlistedSupervisor model.
"""

from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.faculty import Faculty
from app.models.shortlisted_supervisor import ShortlistedSupervisor
from app.models.user import User

from .base import BaseRepository


class ShortlistRepository(BaseRepository[ShortlistedSupervisor]):
    """Repository for ShortlistedSupervisor model operations."""

    def __init__(self):
        super().__init__(ShortlistedSupervisor)

    async def add(
        self,
        db: AsyncSession,
        group_id: UUID,
        supervisor_id: UUID,
        added_by: UUID,
    ) -> ShortlistedSupervisor:
        """
        Add a supervisor to a group's shortlist.

        Args:
            db: Database session
            group_id: Group's UUID
            supervisor_id: Supervisor's user ID
            added_by: User ID of who added this entry

        Returns:
            Created ShortlistedSupervisor instance
        """
        shortlist_data = {
            "group_id": group_id,
            "supervisor_id": supervisor_id,
            "added_by": added_by,
        }
        return await super().create(db, shortlist_data)

    async def remove(
        self,
        db: AsyncSession,
        group_id: UUID,
        supervisor_id: UUID,
    ) -> bool:
        """
        Remove a supervisor from a group's shortlist.

        Args:
            db: Database session
            group_id: Group's UUID
            supervisor_id: Supervisor's user ID

        Returns:
            True if removed, False if not found
        """
        result = await db.execute(
            delete(ShortlistedSupervisor).where(
                ShortlistedSupervisor.group_id == group_id,
                ShortlistedSupervisor.faculty_id == supervisor_id,
            )
        )
        await db.flush()
        return result.rowcount > 0

    async def exists(
        self,
        db: AsyncSession,
        group_id: UUID,
        supervisor_id: UUID,
    ) -> bool:
        """
        Check if a supervisor is in a group's shortlist.

        Args:
            db: Database session
            group_id: Group's UUID
            supervisor_id: Supervisor's user ID

        Returns:
            True if shortlisted, False otherwise
        """
        query = select(ShortlistedSupervisor).where(
            ShortlistedSupervisor.group_id == group_id,
            ShortlistedSupervisor.faculty_id == supervisor_id,
        )
        result = await db.execute(query)
        return result.scalars().first() is not None

    async def get_entry(
        self,
        db: AsyncSession,
        group_id: UUID,
        supervisor_id: UUID,
    ) -> Optional[ShortlistedSupervisor]:
        """
        Get a specific shortlist entry.

        Args:
            db: Database session
            group_id: Group's UUID
            supervisor_id: Supervisor's user ID

        Returns:
            ShortlistedSupervisor instance or None
        """
        query = select(ShortlistedSupervisor).where(
            ShortlistedSupervisor.group_id == group_id,
            ShortlistedSupervisor.faculty_id == supervisor_id,
        )
        result = await db.execute(query)
        return result.scalars().first()

    async def list_by_group(
        self,
        db: AsyncSession,
        group_id: UUID,
    ) -> List[Tuple[ShortlistedSupervisor, User, Faculty]]:
        """
        Get all shortlisted supervisors for a group with user and supervisor data.

        Args:
            db: Database session
            group_id: Group's UUID

        Returns:
            List of (ShortlistedSupervisor, User, Faculty) tuples
        """
        query = (
            select(ShortlistedSupervisor, User, Faculty)
            .join(Faculty, Faculty.user_id == ShortlistedSupervisor.faculty_id)
            .join(User, User.user_id == Faculty.user_id)
            .where(ShortlistedSupervisor.group_id == group_id)
        )
        result = await db.execute(query)
        return list(result.all())

    async def list_by_group_simple(
        self,
        db: AsyncSession,
        group_id: UUID,
    ) -> List[ShortlistedSupervisor]:
        """
        Get all shortlisted supervisors for a group (simple query).

        Args:
            db: Database session
            group_id: Group's UUID

        Returns:
            List of ShortlistedSupervisor instances
        """
        query = select(ShortlistedSupervisor).where(
            ShortlistedSupervisor.group_id == group_id
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    async def count_by_group(self, db: AsyncSession, group_id: UUID) -> int:
        """
        Count shortlisted supervisors for a group.

        Args:
            db: Database session
            group_id: Group's UUID

        Returns:
            Number of shortlisted supervisors
        """
        from sqlalchemy import func

        query = (
            select(func.count())
            .select_from(ShortlistedSupervisor)
            .where(ShortlistedSupervisor.group_id == group_id)
        )
        result = await db.execute(query)
        return result.scalar_one()

    async def clear_group_shortlist(self, db: AsyncSession, group_id: UUID) -> int:
        """
        Remove all shortlisted supervisors for a group.

        Args:
            db: Database session
            group_id: Group's UUID

        Returns:
            Number of entries removed
        """
        result = await db.execute(
            delete(ShortlistedSupervisor).where(
                ShortlistedSupervisor.group_id == group_id
            )
        )
        await db.flush()
        return result.rowcount


# Singleton instance for convenience
shortlist_repository = ShortlistRepository()
