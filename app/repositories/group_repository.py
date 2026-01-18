# app/repositories/group_repository.py
"""
Group Repository Module

Handles all database operations for the Group and GroupMember models.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.group import Group, GroupMember
from app.models.student import Student
from app.models.user import User

from .base import BaseRepository


class GroupRepository(BaseRepository[Group]):
    """Repository for Group model operations."""

    def __init__(self):
        super().__init__(Group)

<<<<<<< HEAD
<<<<<<< HEAD
    async def get_by_id(self, db: AsyncSession, group_id: UUID) -> Optional[Group]:
=======
    async def get_by_id(
        self, db: AsyncSession, group_id: UUID
    ) -> Optional[Group]:
>>>>>>> 1706dee (refactored: repository pattern implementation)
=======
    async def get_by_id(self, db: AsyncSession, group_id: UUID) -> Optional[Group]:
>>>>>>> 1d2f81f (refactored: repository pattern implementation)
        """
        Get group by ID.

        Args:
            db: Database session
            group_id: Group's UUID

        Returns:
            Group instance or None
        """
        return await super().get_by_id(db, group_id, "group_id")

    async def get_with_members(
        self, db: AsyncSession, group_id: UUID
    ) -> Optional[Group]:
        """
        Get group with members loaded.

        Args:
            db: Database session
            group_id: Group's UUID

        Returns:
            Group instance with members loaded, or None
        """
        query = (
            select(Group)
            .options(
                selectinload(Group.members)
                .selectinload(GroupMember.student)
                .selectinload(Student.user)
            )
            .where(Group.group_id == group_id)
        )
        result = await db.execute(query)
        return result.scalars().first()

    async def get_with_project(
        self, db: AsyncSession, group_id: UUID
    ) -> Optional[Group]:
        """
        Get group with project loaded.

        Args:
            db: Database session
            group_id: Group's UUID

        Returns:
            Group instance with project loaded, or None
        """
        query = (
            select(Group)
            .options(selectinload(Group.project))
            .where(Group.group_id == group_id)
        )
        result = await db.execute(query)
        return result.scalars().first()

    async def create(
        self,
        db: AsyncSession,
        name: str,
        fyp_stage: Optional[str] = None,
        fyp_cycle: Optional[str] = None,
        cohort_year: Optional[int] = None,
    ) -> Group:
        """
        Create a new group.

        Args:
            db: Database session
            name: Group name
            fyp_stage: FYP stage enum value
            fyp_cycle: FYP cycle enum value
            cohort_year: Cohort year

        Returns:
            Created Group instance
        """
        from app.models.group import FYPCycleEnum, FYPStageEnum

        group_data = {
            "name": name,
            "created_at": datetime.utcnow(),
        }

        if fyp_stage:
            group_data["fyp_stage"] = FYPStageEnum(fyp_stage)
        else:
            group_data["fyp_stage"] = FYPStageEnum.ideation

        if fyp_cycle:
            group_data["fyp_cycle"] = FYPCycleEnum(fyp_cycle)
        else:
            group_data["fyp_cycle"] = FYPCycleEnum.fyp1

        if cohort_year:
            group_data["cohort_year"] = cohort_year

        return await super().create(db, group_data)

    async def update(
        self,
        db: AsyncSession,
        group_id: UUID,
        updates: Dict[str, Any],
    ) -> Optional[Group]:
        """
        Update group fields.

        Args:
            db: Database session
            group_id: Group's UUID
            updates: Dictionary of fields to update

        Returns:
            Updated Group instance or None if not found
        """
        group = await self.get_by_id(db, group_id)
        if not group:
            return None
        return await super().update(db, group, updates)

<<<<<<< HEAD
<<<<<<< HEAD
    async def delete(self, db: AsyncSession, group_id: UUID) -> bool:
=======
    async def delete(
        self, db: AsyncSession, group_id: UUID
    ) -> bool:
>>>>>>> 1706dee (refactored: repository pattern implementation)
=======
    async def delete(self, db: AsyncSession, group_id: UUID) -> bool:
>>>>>>> 1d2f81f (refactored: repository pattern implementation)
        """
        Delete a group.

        Args:
            db: Database session
            group_id: Group's UUID

        Returns:
            True if deleted, False if not found
        """
        return await super().delete(db, group_id, "group_id")

    # --- Membership operations ---

<<<<<<< HEAD
<<<<<<< HEAD
    async def get_members(self, db: AsyncSession, group_id: UUID) -> List[GroupMember]:
=======
    async def get_members(
        self, db: AsyncSession, group_id: UUID
    ) -> List[GroupMember]:
>>>>>>> 1706dee (refactored: repository pattern implementation)
=======
    async def get_members(self, db: AsyncSession, group_id: UUID) -> List[GroupMember]:
>>>>>>> 1d2f81f (refactored: repository pattern implementation)
        """
        Get all members of a group.

        Args:
            db: Database session
            group_id: Group's UUID

        Returns:
            List of GroupMember instances
        """
        query = select(GroupMember).where(GroupMember.group_id == group_id)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_members_with_users(
        self, db: AsyncSession, group_id: UUID
    ) -> List[Tuple[User, Student, GroupMember]]:
        """
        Get all members of a group with user and student data.

        Args:
            db: Database session
            group_id: Group's UUID

        Returns:
            List of (User, Student, GroupMember) tuples
        """
        query = (
            select(User, Student, GroupMember)
            .join(Student, User.user_id == Student.user_id)
            .join(GroupMember, Student.user_id == GroupMember.student_id)
            .where(GroupMember.group_id == group_id)
        )
        result = await db.execute(query)
        return list(result.all())

    async def add_member(
        self,
        db: AsyncSession,
        group_id: UUID,
        student_id: UUID,
    ) -> GroupMember:
        """
        Add a student to a group.

        Args:
            db: Database session
            group_id: Group's UUID
            student_id: Student's user ID

        Returns:
            Created GroupMember instance
        """
        member = GroupMember(
            group_id=group_id,
            student_id=student_id,
            joined_at=datetime.utcnow(),
        )
        db.add(member)
        await db.flush()
        return member

    async def remove_member(
        self,
        db: AsyncSession,
        group_id: UUID,
        student_id: UUID,
    ) -> bool:
        """
        Remove a student from a group.

        Args:
            db: Database session
            group_id: Group's UUID
            student_id: Student's user ID

        Returns:
            True if removed, False if not found
        """
        from sqlalchemy import delete

        result = await db.execute(
            delete(GroupMember).where(
                GroupMember.group_id == group_id,
                GroupMember.student_id == student_id,
            )
        )
        await db.flush()
        return result.rowcount > 0

    async def check_membership(
        self,
        db: AsyncSession,
        group_id: UUID,
        student_id: UUID,
    ) -> bool:
        """
        Check if a student is a member of a group.

        Args:
            db: Database session
            group_id: Group's UUID
            student_id: Student's user ID

        Returns:
            True if member, False otherwise
        """
        query = select(GroupMember).where(
            GroupMember.group_id == group_id,
            GroupMember.student_id == student_id,
        )
        result = await db.execute(query)
        return result.scalars().first() is not None

<<<<<<< HEAD
<<<<<<< HEAD
    async def count_members(self, db: AsyncSession, group_id: UUID) -> int:
=======
    async def count_members(
        self, db: AsyncSession, group_id: UUID
    ) -> int:
>>>>>>> 1706dee (refactored: repository pattern implementation)
=======
    async def count_members(self, db: AsyncSession, group_id: UUID) -> int:
>>>>>>> 1d2f81f (refactored: repository pattern implementation)
        """
        Count members in a group.

        Args:
            db: Database session
            group_id: Group's UUID

        Returns:
            Number of members
        """
        query = (
            select(func.count())
            .select_from(GroupMember)
            .where(GroupMember.group_id == group_id)
        )
        result = await db.execute(query)
        return result.scalar_one()

    async def get_student_group(
        self, db: AsyncSession, student_id: UUID
    ) -> Optional[Group]:
        """
        Get the group a student belongs to.

        Args:
            db: Database session
            student_id: Student's user ID

        Returns:
            Group instance or None if student is not in any group
        """
        query = (
            select(Group)
            .join(GroupMember, Group.group_id == GroupMember.group_id)
            .where(GroupMember.student_id == student_id)
        )
        result = await db.execute(query)
        return result.scalars().first()

    async def get_student_membership(
        self, db: AsyncSession, student_id: UUID
    ) -> Optional[GroupMember]:
        """
        Get the membership record for a student.

        Args:
            db: Database session
            student_id: Student's user ID

        Returns:
            GroupMember instance or None
        """
        query = select(GroupMember).where(GroupMember.student_id == student_id)
        result = await db.execute(query)
        return result.scalars().first()

<<<<<<< HEAD
<<<<<<< HEAD
    async def is_student_in_any_group(self, db: AsyncSession, student_id: UUID) -> bool:
=======
    async def is_student_in_any_group(
        self, db: AsyncSession, student_id: UUID
    ) -> bool:
>>>>>>> 1706dee (refactored: repository pattern implementation)
=======
    async def is_student_in_any_group(self, db: AsyncSession, student_id: UUID) -> bool:
>>>>>>> 1d2f81f (refactored: repository pattern implementation)
        """
        Check if a student is in any group.

        Args:
            db: Database session
            student_id: Student's user ID

        Returns:
            True if in a group, False otherwise
        """
        membership = await self.get_student_membership(db, student_id)
        return membership is not None

    async def get_supervised_groups(
        self,
        db: AsyncSession,
        supervisor_id: UUID,
    ) -> List[Group]:
        """
        Get all groups supervised by a supervisor (as main or co-supervisor).

        Args:
            db: Database session
            supervisor_id: Supervisor's user ID

        Returns:
            List of Group instances
        """
        query = select(Group).where(
            or_(
                Group.supervisor_id == supervisor_id,
                Group.cosupervisor_id == supervisor_id,
            )
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    async def set_supervisor(
        self,
        db: AsyncSession,
        group_id: UUID,
        supervisor_id: UUID,
    ) -> Optional[Group]:
        """
        Set the main supervisor for a group.

        Args:
            db: Database session
            group_id: Group's UUID
            supervisor_id: Supervisor's user ID

        Returns:
            Updated Group instance or None
        """
        return await self.update(db, group_id, {"supervisor_id": supervisor_id})

    async def set_cosupervisor(
        self,
        db: AsyncSession,
        group_id: UUID,
        cosupervisor_id: UUID,
    ) -> Optional[Group]:
        """
        Set the co-supervisor for a group.

        Args:
            db: Database session
            group_id: Group's UUID
            cosupervisor_id: Co-supervisor's user ID

        Returns:
            Updated Group instance or None
        """
        return await self.update(db, group_id, {"cosupervisor_id": cosupervisor_id})


# Singleton instance for convenience
group_repository = GroupRepository()
