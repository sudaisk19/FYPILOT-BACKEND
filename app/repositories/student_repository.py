# app/repositories/student_repository.py
"""
Student Repository Module

Handles all database operations for the Student model.
"""

from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.group import Group
from app.models.student import Student

from .base import BaseRepository


class StudentRepository(BaseRepository[Student]):
    """Repository for Student model operations."""

    def __init__(self):
        super().__init__(Student)

    async def get_by_user_id(
        self, db: AsyncSession, user_id: UUID
    ) -> Optional[Student]:
        """
        Get student profile by user ID.

        Args:
            db: Database session
            user_id: User's UUID

        Returns:
            Student instance or None
        """
        query = select(Student).where(Student.user_id == user_id)
        result = await db.execute(query)
        return result.scalars().first()

    async def get_with_user(self, db: AsyncSession, user_id: UUID) -> Optional[Student]:
        """
        Get student profile with user relationship loaded.

        Args:
            db: Database session
            user_id: User's UUID

        Returns:
            Student instance with user loaded, or None
        """
        query = (
            select(Student)
            .options(selectinload(Student.user))
            .where(Student.user_id == user_id)
        )
        result = await db.execute(query)
        return result.scalars().first()

    async def get_with_groups(
        self, db: AsyncSession, user_id: UUID
    ) -> Optional[Student]:
        """
        Get student profile with group relationships loaded.

        Args:
            db: Database session
            user_id: User's UUID

        Returns:
            Student instance with groups loaded, or None
        """
        query = (
            select(Student)
            .options(selectinload(Student.groups).selectinload(Group.project))
            .where(Student.user_id == user_id)
        )
        result = await db.execute(query)
        return result.scalars().first()

    async def create(
        self,
        db: AsyncSession,
        user_id: UUID,
        roll_number: Optional[str] = None,
        department: Optional[str] = None,
        cgpa: Optional[float] = None,
        interests: Optional[List[str]] = None,
        skills: Optional[List[str]] = None,
        skills_levels: Optional[Dict[str, int]] = None,
        experience: Optional[str] = None,
        portfolio_projects: Optional[List[Dict]] = None,
    ) -> Student:
        """
        Create a new student profile.

        Args:
            db: Database session
            user_id: User's UUID (foreign key)
            roll_number: Student's roll number
            department: Student's department
            cgpa: Student's CGPA
            interests: List of interests
            skills: List of skills
            skills_levels: Dictionary mapping skills to levels (1-5)
            experience: Experience description
            portfolio_projects: List of portfolio project objects

        Returns:
            Created Student instance
        """
        student_data = {"user_id": user_id}

        if roll_number is not None:
            student_data["roll_number"] = roll_number
        if department is not None:
            student_data["department"] = department
        if cgpa is not None:
            student_data["cgpa"] = cgpa
        if interests is not None:
            student_data["interests"] = interests
        if skills is not None:
            student_data["skills"] = skills
        if skills_levels is not None:
            student_data["skills_levels"] = skills_levels
        if experience is not None:
            student_data["experience"] = experience
        if portfolio_projects is not None:
            student_data["portfolio_projects"] = portfolio_projects

        return await super().create(db, student_data)

    async def update(
        self,
        db: AsyncSession,
        user_id: UUID,
        updates: Dict[str, Any],
    ) -> Optional[Student]:
        """
        Update student profile fields.

        Args:
            db: Database session
            user_id: User's UUID
            updates: Dictionary of fields to update

        Returns:
            Updated Student instance or None if not found
        """
        student = await self.get_by_user_id(db, user_id)
        if not student:
            return None
        return await super().update(db, student, updates)

    async def exists(self, db: AsyncSession, user_id: UUID) -> bool:
        """
        Check if a student profile exists for the given user.

        Args:
            db: Database session
            user_id: User's UUID

        Returns:
            True if profile exists, False otherwise
        """
        student = await self.get_by_user_id(db, user_id)
        return student is not None

    async def has_roll_number(self, db: AsyncSession, user_id: UUID) -> bool:
        """
        Check if student has a roll number set.

        Args:
            db: Database session
            user_id: User's UUID

        Returns:
            True if roll number exists and is not empty
        """
        student = await self.get_by_user_id(db, user_id)
        return student is not None and bool(student.roll_number)

    async def deactivate_expired_students(self, db: AsyncSession) -> int:
        """
        Deactivate students whose FYP batch period has expired based on their start year and semester.
        """
        from sqlalchemy import text

        _DEACTIVATION_SQL = text(
            """
            UPDATE students
            SET is_active = false
            WHERE is_active = true
            AND fyp_start_semester IS NOT NULL
            AND fyp_start_year IS NOT NULL
            AND CURRENT_DATE >
                CASE
                    WHEN LOWER(fyp_start_semester) = 'fall'
                        THEN make_date(fyp_start_year + 1, 6, 1)
                    WHEN LOWER(fyp_start_semester) = 'spring'
                        THEN make_date(fyp_start_year + 1, 1, 15)
                END
            """
        )
        result = await db.execute(_DEACTIVATION_SQL)
        return result.rowcount

    async def get_profile_full(self, db: AsyncSession, user_id: UUID) -> Optional[Any]:
        """
        Get full student profile including user data, groups, and project.
        Returns the User object with loaded relationships.
        """
        from app.models.user import User

        query = (
            select(User)
            .options(
                selectinload(User.student_profile)
                .selectinload(Student.groups)
                .selectinload(Group.project)
            )
            .where(User.user_id == user_id)
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_group_members_details(
        self, db: AsyncSession, group_id: UUID
    ) -> List[Tuple[Any, Student]]:
        """
        Get all members of a group with their User and Student details.
        Returns a list of tuples (User, Student).
        """
        from app.models.group import GroupMember
        from app.models.user import User

        query = (
            select(User, Student)
            .join(Student, User.user_id == Student.user_id)
            .join(GroupMember, Student.user_id == GroupMember.student_id)
            .where(GroupMember.group_id == group_id)
        )
        result = await db.execute(query)
        return list(result.all())

    async def get_supervisors_names(
        self,
        db: AsyncSession,
        supervisor_id: Optional[UUID],
        cosupervisor_ids: Optional[List[UUID]],
    ) -> Tuple[Optional[str], List[str]]:
        """
        Get the names of a supervisor and list of cosupervisors.
        Returns (supervisor_name, [cosupervisor_names])
        """
        from app.models.user import User

        sup_name = None
        co_names = []

        if supervisor_id:
            query = select(User.full_name).where(User.user_id == supervisor_id)
            result = await db.execute(query)
            sup_name = result.scalar_one_or_none()

        if cosupervisor_ids and len(cosupervisor_ids) > 0:
            query = select(User.full_name).where(User.user_id.in_(cosupervisor_ids))
            result = await db.execute(query)
            co_names = list(result.scalars().all())

        return sup_name, co_names


# Singleton instance for convenience
student_repository = StudentRepository()
