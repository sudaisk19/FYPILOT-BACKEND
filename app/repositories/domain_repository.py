# app/repositories/domain_repository.py
"""
Domain Repository Module

Handles all database operations for the Domain model.
"""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain import Domain

from .base import BaseRepository


class DomainRepository(BaseRepository[Domain]):
    """Repository for Domain model operations."""

    def __init__(self):
        super().__init__(Domain)

<<<<<<< HEAD
    async def get_by_id(self, db: AsyncSession, domain_id: UUID) -> Optional[Domain]:
=======
    async def get_by_id(
        self, db: AsyncSession, domain_id: UUID
    ) -> Optional[Domain]:
>>>>>>> 1706dee (refactored: repository pattern implementation)
        """
        Get domain by ID.

        Args:
            db: Database session
            domain_id: Domain's UUID

        Returns:
            Domain instance or None
        """
        return await super().get_by_id(db, domain_id, "domain_id")

<<<<<<< HEAD
    async def get_by_name(self, db: AsyncSession, name: str) -> Optional[Domain]:
=======
    async def get_by_name(
        self, db: AsyncSession, name: str
    ) -> Optional[Domain]:
>>>>>>> 1706dee (refactored: repository pattern implementation)
        """
        Get domain by name.

        Args:
            db: Database session
            name: Domain name

        Returns:
            Domain instance or None
        """
        query = select(Domain).where(Domain.name == name)
        result = await db.execute(query)
        return result.scalars().first()

<<<<<<< HEAD
    async def get_all(self, db: AsyncSession) -> List[Domain]:
=======
    async def get_all(
        self, db: AsyncSession
    ) -> List[Domain]:
>>>>>>> 1706dee (refactored: repository pattern implementation)
        """
        Get all domains.

        Args:
            db: Database session

        Returns:
            List of all Domain instances
        """
        query = select(Domain).order_by(Domain.name)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_by_ids(
        self, db: AsyncSession, domain_ids: List[UUID]
    ) -> List[Domain]:
        """
        Get domains by list of IDs.

        Args:
            db: Database session
            domain_ids: List of domain UUIDs

        Returns:
            List of Domain instances
        """
        if not domain_ids:
            return []

        query = select(Domain).where(Domain.domain_id.in_(domain_ids))
        result = await db.execute(query)
        return list(result.scalars().all())

<<<<<<< HEAD
    async def search_by_name(self, db: AsyncSession, search_term: str) -> List[Domain]:
=======
    async def search_by_name(
        self, db: AsyncSession, search_term: str
    ) -> List[Domain]:
>>>>>>> 1706dee (refactored: repository pattern implementation)
        """
        Search domains by name (case-insensitive partial match).

        Args:
            db: Database session
            search_term: Search term

        Returns:
            List of matching Domain instances
        """
        query = (
            select(Domain)
            .where(Domain.name.ilike(f"%{search_term}%"))
            .order_by(Domain.name)
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    async def create(
        self,
        db: AsyncSession,
        name: str,
    ) -> Domain:
        """
        Create a new domain.

        Args:
            db: Database session
            name: Domain name

        Returns:
            Created Domain instance
        """
        return await super().create(db, {"name": name})

    async def get_or_create(
        self,
        db: AsyncSession,
        name: str,
    ) -> Domain:
        """
        Get an existing domain by name or create a new one.

        Args:
            db: Database session
            name: Domain name

        Returns:
            Domain instance (existing or newly created)
        """
        domain = await self.get_by_name(db, name)
        if domain:
            return domain
        return await self.create(db, name)


# Singleton instance for convenience
domain_repository = DomainRepository()
