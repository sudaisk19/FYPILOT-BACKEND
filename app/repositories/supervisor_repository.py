# app/repositories/supervisor_repository.py
"""
Supervisor Repository Module

Handles all database operations for the Supervisor model,
including complex queries with joins for domains and industries.
"""

from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.domain import Domain
from app.models.industry import Industry
from app.models.supervisor import Supervisor
from app.models.supervisor_domain import SupervisorDomain
from app.models.supervisor_industry import SupervisorIndustry
from app.models.user import User

from .base import BaseRepository


class SupervisorRepository(BaseRepository[Supervisor]):
    """Repository for Supervisor model operations."""

    def __init__(self):
        super().__init__(Supervisor)

    async def get_by_user_id(
        self, db: AsyncSession, user_id: UUID
    ) -> Optional[Supervisor]:
        """
        Get supervisor profile by user ID.

        Args:
            db: Database session
            user_id: User's UUID

        Returns:
            Supervisor instance or None
        """
        query = select(Supervisor).where(Supervisor.user_id == user_id)
        result = await db.execute(query)
        return result.scalars().first()

    async def get_with_user(
        self, db: AsyncSession, user_id: UUID
    ) -> Optional[Tuple[User, Supervisor]]:
        """
        Get supervisor with user data.

        Args:
            db: Database session
            user_id: User's UUID

        Returns:
            Tuple of (User, Supervisor) or None
        """
        query = (
            select(User, Supervisor)
            .join(Supervisor, User.user_id == Supervisor.user_id)
            .where(User.user_id == user_id)
        )
        result = await db.execute(query)
        return result.first()

    async def get_with_domains_industries(
        self, db: AsyncSession, user_id: UUID
    ) -> Optional[Supervisor]:
        """
        Get supervisor with domains and industries loaded.

        Args:
            db: Database session
            user_id: User's UUID

        Returns:
            Supervisor instance with relationships loaded, or None
        """
        query = (
            select(Supervisor)
            .options(
                selectinload(Supervisor.domains),
                selectinload(Supervisor.industries),
            )
            .where(Supervisor.user_id == user_id)
        )
        result = await db.execute(query)
        return result.scalars().first()

    async def list_all_with_users(
        self, db: AsyncSession
    ) -> List[Tuple[Supervisor, User]]:
        """
        Get all supervisors with their user data.

        Args:
            db: Database session

        Returns:
            List of (Supervisor, User) tuples
        """
        query = select(Supervisor, User).join(User, Supervisor.user_id == User.user_id)
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
    ) -> Tuple[List[Tuple[User, Supervisor]], int]:
        """
        Search supervisors with filtering and pagination.

        Args:
            db: Database session
            department: Filter by department (supports aliases)
            designation: Filter by designation
            domain: Filter by domain expertise
            search: Search by name or email
            page: Page number (1-indexed)
            per_page: Items per page

        Returns:
            Tuple of (list of (User, Supervisor) tuples, total count)
        """
        # Build base query
        query = (
            select(User, Supervisor)
            .join(Supervisor, User.user_id == Supervisor.user_id)
            .where(User.role == "supervisor")
        )

        filters = []

        # Department filter
        if department:
            filters.append(Supervisor.department.ilike(f"%{department}%"))

        # Designation filter
        if designation:
            filters.append(Supervisor.designation.ilike(f"%{designation}%"))

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
                    SupervisorDomain,
                    Supervisor.user_id == SupervisorDomain.supervisor_id,
                )
                .join(Domain, SupervisorDomain.domain_id == Domain.domain_id)
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
    ) -> Supervisor:
        """
        Create a new supervisor profile.

        Args:
            db: Database session
            user_id: User's UUID (foreign key)
            department: Supervisor's department
            designation: Supervisor's designation
            office: Office location
            requirements: List of requirements for students
            project_type: Preferred project type
            capacity_max: Maximum capacity for groups

        Returns:
            Created Supervisor instance
        """
        supervisor_data = {
            "user_id": user_id,
            "capacity_max": capacity_max,
            "capacity_filled": 0,
        }

        if department is not None:
            supervisor_data["department"] = department
        if designation is not None:
            supervisor_data["designation"] = designation
        if office is not None:
            supervisor_data["office"] = office
        if requirements is not None:
            supervisor_data["requirements"] = requirements
        if project_type is not None:
            supervisor_data["project_type"] = project_type

        return await super().create(db, supervisor_data)

    async def update(
        self,
        db: AsyncSession,
        user_id: UUID,
        updates: Dict[str, Any],
    ) -> Optional[Supervisor]:
        """
        Update supervisor profile fields.

        Args:
            db: Database session
            user_id: User's UUID
            updates: Dictionary of fields to update

        Returns:
            Updated Supervisor instance or None if not found
        """
        supervisor = await self.get_by_user_id(db, user_id)
        if not supervisor:
            return None
        return await super().update(db, supervisor, updates)

    async def get_domains(self, db: AsyncSession, supervisor_id: UUID) -> List[Domain]:
        """
        Get all domains for a supervisor.

        Args:
            db: Database session
            supervisor_id: Supervisor's user ID

        Returns:
            List of Domain instances
        """
        query = (
            select(Domain)
            .join(SupervisorDomain, Domain.domain_id == SupervisorDomain.domain_id)
            .where(SupervisorDomain.supervisor_id == supervisor_id)
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_industries(
        self, db: AsyncSession, supervisor_id: UUID
    ) -> List[Industry]:
        """
        Get all industries for a supervisor.

        Args:
            db: Database session
            supervisor_id: Supervisor's user ID

        Returns:
            List of Industry instances
        """
        query = (
            select(Industry)
            .join(
                SupervisorIndustry,
                Industry.industry_id == SupervisorIndustry.industry_id,
            )
            .where(SupervisorIndustry.supervisor_id == supervisor_id)
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
        Set domains for a supervisor (replaces existing).

        Args:
            db: Database session
            supervisor_id: Supervisor's user ID
            domain_ids: List of domain UUIDs to set
        """
        from sqlalchemy import delete

        # Delete existing associations
        await db.execute(
            delete(SupervisorDomain).where(
                SupervisorDomain.supervisor_id == supervisor_id
            )
        )

        # Create new associations
        for domain_id in domain_ids:
            db.add(
                SupervisorDomain(
                    supervisor_id=supervisor_id,
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
        Set industries for a supervisor (replaces existing).

        Args:
            db: Database session
            supervisor_id: Supervisor's user ID
            industry_ids: List of industry UUIDs to set
        """
        from sqlalchemy import delete

        # Delete existing associations
        await db.execute(
            delete(SupervisorIndustry).where(
                SupervisorIndustry.supervisor_id == supervisor_id
            )
        )

        # Create new associations
        for industry_id in industry_ids:
            db.add(
                SupervisorIndustry(
                    supervisor_id=supervisor_id,
                    industry_id=industry_id,
                )
            )

        await db.flush()

    async def increment_capacity_filled(
        self, db: AsyncSession, supervisor_id: UUID
    ) -> Optional[Supervisor]:
        """
        Increment the capacity_filled counter.

        Args:
            db: Database session
            supervisor_id: Supervisor's user ID

        Returns:
            Updated Supervisor instance or None
        """
        supervisor = await self.get_by_user_id(db, supervisor_id)
        if supervisor:
            supervisor.capacity_filled += 1
            await db.flush()
        return supervisor

    async def decrement_capacity_filled(
        self, db: AsyncSession, supervisor_id: UUID
    ) -> Optional[Supervisor]:
        """
        Decrement the capacity_filled counter (minimum 0).

        Args:
            db: Database session
            supervisor_id: Supervisor's user ID

        Returns:
            Updated Supervisor instance or None
        """
        supervisor = await self.get_by_user_id(db, supervisor_id)
        if supervisor and supervisor.capacity_filled > 0:
            supervisor.capacity_filled -= 1
            await db.flush()
        return supervisor


# Singleton instance for convenience
supervisor_repository = SupervisorRepository()
