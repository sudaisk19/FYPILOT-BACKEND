# app/repositories/supervisor_repository.py
"""
Faculty Repository Module (formerly Supervisor Repository)

Handles all database operations for the Faculty model,
including complex queries with joins for domains and industries.
"""

from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.domain import Domain
from app.models.faculty import Faculty
from app.models.faculty_domain import FacultyDomain
from app.models.faculty_industry import FacultyIndustry
from app.models.industry import Industry
from app.models.user import User

from .base import BaseRepository


class SupervisorRepository(BaseRepository[Faculty]):
    """Repository for Faculty model operations."""

    def __init__(self):
        super().__init__(Faculty)

    async def get_by_user_id(
        self, db: AsyncSession, user_id: UUID
    ) -> Optional[Faculty]:
        """
        Get faculty profile by user ID.

        Args:
            db: Database session
            user_id: User's UUID

        Returns:
            Faculty instance or None
        """
        query = select(Faculty).where(Faculty.user_id == user_id)
        result = await db.execute(query)
        return result.scalars().first()

    async def get_with_user(
        self, db: AsyncSession, user_id: UUID
    ) -> Optional[Tuple[User, Faculty]]:
        """
        Get faculty with user data.

        Args:
            db: Database session
            user_id: User's UUID

        Returns:
            Tuple of (User, Faculty) or None
        """
        query = (
            select(User, Faculty)
            .join(Faculty, User.user_id == Faculty.user_id)
            .where(User.user_id == user_id)
        )
        result = await db.execute(query)
        return result.first()

    async def get_with_domains_industries(
        self, db: AsyncSession, user_id: UUID
    ) -> Optional[Faculty]:
        """
        Get faculty with domains and industries loaded.

        Args:
            db: Database session
            user_id: User's UUID

        Returns:
            Faculty instance with relationships loaded, or None
        """
        query = (
            select(Faculty)
            .options(
                selectinload(Faculty.domains),
                selectinload(Faculty.industries),
            )
            .where(Faculty.user_id == user_id)
        )
        result = await db.execute(query)
        return result.scalars().first()

    async def list_all_with_users(self, db: AsyncSession) -> List[Tuple[Faculty, User]]:
        """
        Get all faculty with their user data.

        Args:
            db: Database session

        Returns:
            List of (Faculty, User) tuples
        """
        query = select(Faculty, User).join(User, Faculty.user_id == User.user_id)
        result = await db.execute(query)
        return list(result.all())

    async def search(
        self,
        db: AsyncSession,
        department: Optional[str] = None,
        designation: Optional[str] = None,
        domain: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
        per_page: int = 10,
    ) -> Tuple[List[Tuple[User, Faculty]], int]:
        """
        Search faculty with filtering and pagination.

        Args:
            db: Database session
            department: Filter by department (supports aliases)
            designation: Filter by designation
            domain: Filter by domain expertise
            search: Search by name or email
            page: Page number (1-indexed)
            per_page: Items per page

        Returns:
            Tuple of (list of (User, Faculty) tuples, total count)
        """
        # Build base query
        query = (
            select(User, Faculty)
            .join(Faculty, User.user_id == Faculty.user_id)
            .where(User.role == "faculty")
        )

        filters = []

        # Department filter
        if department:
            filters.append(Faculty.department.ilike(f"%{department}%"))

        # Designation filter
        if designation:
            filters.append(Faculty.designation.ilike(f"%{designation}%"))

        # Search filter (name or email)
        if search:
            filters.append(
                or_(
                    User.full_name.ilike(f"%{search}%"),
                    User.email.ilike(f"%{search}%"),
                )
            )

        # Domain filter (requires join)
        if domain:
            query = (
                query.join(
                    FacultyDomain,
                    Faculty.user_id == FacultyDomain.faculty_id,
                )
                .join(Domain, FacultyDomain.domain_id == Domain.domain_id)
                .where(Domain.name.ilike(f"%{domain}%"))
            )

        # Apply filters
        if filters:
            query = query.where(and_(*filters))

        # Apply distinct to avoid duplicates from joins
        query = query.distinct()

        # Get total count
        count_subquery = query.subquery()
        count_query = select(func.count()).select_from(count_subquery)
        total = (await db.execute(count_query)).scalar() or 0

        # Apply pagination
        offset = (page - 1) * per_page
        query = query.order_by(User.full_name.asc()).offset(offset).limit(per_page)

        # Execute query
        result = await db.execute(query)
        rows = list(result.all())

        return rows, total

    async def create(
        self,
        db: AsyncSession,
        user_id: UUID,
        department: Optional[str] = None,
        designation: Optional[str] = None,
        office: Optional[str] = None,
        requirements: Optional[List[str]] = None,
        project_type: Optional[str] = None,
        capacity_max: int = 8,
    ) -> Faculty:
        """
        Create a new faculty profile.

        Args:
            db: Database session
            user_id: User's UUID (foreign key)
            department: Faculty member's department
            designation: Faculty member's designation
            office: Office location
            requirements: List of requirements for students
            project_type: Preferred project type
            capacity_max: Maximum capacity for groups

        Returns:
            Created Faculty instance
        """
        faculty_data = {
            "user_id": user_id,
            "capacity_max": capacity_max,
            "capacity_filled": 0,
        }

        if department is not None:
            faculty_data["department"] = department
        if designation is not None:
            faculty_data["designation"] = designation
        if office is not None:
            faculty_data["office"] = office
        if requirements is not None:
            faculty_data["requirements"] = requirements
        if project_type is not None:
            from app.models.project import parse_project_type

            faculty_data["project_type"] = parse_project_type(project_type)

        return await super().create(db, faculty_data)

    async def update(
        self,
        db: AsyncSession,
        user_id: UUID,
        updates: Dict[str, Any],
    ) -> Optional[Faculty]:
        """
        Update faculty profile fields.

        Args:
            db: Database session
            user_id: User's UUID
            updates: Dictionary of fields to update

        Returns:
            Updated Faculty instance or None if not found
        """
        faculty_member = await self.get_by_user_id(db, user_id)
        if not faculty_member:
            return None
        # Normalize project_type if present in updates
        if "project_type" in updates and updates["project_type"] is not None:
            from app.models.project import parse_project_type

            updates["project_type"] = parse_project_type(updates["project_type"])
        return await super().update(db, faculty_member, updates)

    async def get_domains(self, db: AsyncSession, supervisor_id: UUID) -> List[Domain]:
        """
        Get all domains for a faculty member.

        Args:
            db: Database session
            supervisor_id: Faculty member's user ID

        Returns:
            List of Domain instances
        """
        query = (
            select(Domain)
            .join(FacultyDomain, Domain.domain_id == FacultyDomain.domain_id)
            .where(FacultyDomain.faculty_id == supervisor_id)
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_industries(
        self, db: AsyncSession, supervisor_id: UUID
    ) -> List[Industry]:
        """
        Get all industries for a faculty member.

        Args:
            db: Database session
            supervisor_id: Faculty member's user ID

        Returns:
            List of Industry instances
        """
        query = (
            select(Industry)
            .join(
                FacultyIndustry,
                Industry.industry_id == FacultyIndustry.industry_id,
            )
            .where(FacultyIndustry.faculty_id == supervisor_id)
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    async def set_domains(
        self,
        db: AsyncSession,
        supervisor_id: UUID,
        domain_ids: List[UUID],
    ) -> None:
        """
        Set domains for a faculty member (replaces existing).

        Args:
            db: Database session
            supervisor_id: Faculty member's user ID
            domain_ids: List of domain UUIDs to set
        """
        from sqlalchemy import delete

        # Delete existing associations
        await db.execute(
            delete(FacultyDomain).where(FacultyDomain.faculty_id == supervisor_id)
        )

        # Create new associations
        for domain_id in domain_ids:
            db.add(
                FacultyDomain(
                    faculty_id=supervisor_id,
                    domain_id=domain_id,
                )
            )

        await db.flush()

    async def set_industries(
        self,
        db: AsyncSession,
        supervisor_id: UUID,
        industry_ids: List[UUID],
    ) -> None:
        """
        Set industries for a faculty member (replaces existing).

        Args:
            db: Database session
            supervisor_id: Faculty member's user ID
            industry_ids: List of industry UUIDs to set
        """
        from sqlalchemy import delete

        # Delete existing associations
        await db.execute(
            delete(FacultyIndustry).where(FacultyIndustry.faculty_id == supervisor_id)
        )

        # Create new associations
        for industry_id in industry_ids:
            db.add(
                FacultyIndustry(
                    faculty_id=supervisor_id,
                    industry_id=industry_id,
                )
            )

        await db.flush()

    async def increment_capacity_filled(
        self, db: AsyncSession, supervisor_id: UUID
    ) -> Optional[Faculty]:
        """
        Increment the capacity_filled counter.

        Args:
            db: Database session
            supervisor_id: Faculty member's user ID

        Returns:
            Updated Faculty instance or None
        """
        faculty_member = await self.get_by_user_id(db, supervisor_id)
        if faculty_member:
            faculty_member.capacity_filled += 1
            await db.flush()
        return faculty_member

    async def decrement_capacity_filled(
        self, db: AsyncSession, supervisor_id: UUID
    ) -> Optional[Faculty]:
        """
        Decrement the capacity_filled counter (minimum 0).

        Args:
            db: Database session
            supervisor_id: Faculty member's user ID

        Returns:
            Updated Faculty instance or None
        """
        faculty_member = await self.get_by_user_id(db, supervisor_id)
        if faculty_member and faculty_member.capacity_filled > 0:
            faculty_member.capacity_filled -= 1
            await db.flush()
        return faculty_member

    async def get_full_profile(self, db: AsyncSession, user_id: UUID) -> Optional[User]:
        """Fetch faculty with user, domains, industries, and supervised projects."""
        from app.models.group import Group
        from app.models.project import Project

        query = (
            select(User)
            .options(
                selectinload(User.faculty_profile).selectinload(Faculty.domains),
                selectinload(User.faculty_profile).selectinload(Faculty.industries),
                selectinload(User.faculty_profile)
                .selectinload(Faculty.supervised_groups)
                .selectinload(Group.project)
                .selectinload(Project.domains),
                selectinload(User.faculty_profile)
                .selectinload(Faculty.co_supervised_groups)
                .selectinload(Group.project)
                .selectinload(Project.domains),
            )
            .where(User.user_id == user_id)
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()


# Singleton instance for convenience
supervisor_repository = SupervisorRepository()
