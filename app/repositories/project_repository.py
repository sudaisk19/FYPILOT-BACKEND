# app/repositories/project_repository.py
"""
Project Repository Module

Handles all database operations for the Project model.
"""

from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.domain import Domain
from app.models.project import Project, ProjectDomain

from .base import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    """Repository for Project model operations."""

    def __init__(self):
        super().__init__(Project)

    async def get_by_id(
        self, db: AsyncSession, project_id: UUID
    ) -> Optional[Project]:
        """
        Get project by ID.

        Args:
            db: Database session
            project_id: Project's UUID

        Returns:
            Project instance or None
        """
        return await super().get_by_id(db, project_id, "project_id")

    async def get_by_group_id(
        self, db: AsyncSession, group_id: UUID
    ) -> Optional[Project]:
        """
        Get project by group ID.

        Args:
            db: Database session
            group_id: Group's UUID

        Returns:
            Project instance or None
        """
        query = select(Project).where(Project.group_id == group_id)
        result = await db.execute(query)
        return result.scalars().first()

    async def get_with_domains(
        self, db: AsyncSession, project_id: UUID
    ) -> Optional[Project]:
        """
        Get project with domains loaded.

        Args:
            db: Database session
            project_id: Project's UUID

        Returns:
            Project instance with domains loaded, or None
        """
        query = (
            select(Project)
            .options(selectinload(Project.domains))
            .where(Project.project_id == project_id)
        )
        result = await db.execute(query)
        return result.scalars().first()

    async def create(
        self,
        db: AsyncSession,
        group_id: UUID,
        name: str,
        project_type: Optional[str] = None,
        description: Optional[str] = None,
        abstract: Optional[str] = None,
    ) -> Project:
        """
        Create a new project.

        Args:
            db: Database session
            group_id: Group's UUID
            name: Project name
            project_type: Type of project (research/product)
            description: Project description
            abstract: Project abstract

        Returns:
            Created Project instance
        """
        from app.models.project import ProjectTypeEnum

        project_data = {
            "group_id": group_id,
            "name": name,
        }

        if project_type:
            project_data["project_type"] = ProjectTypeEnum(project_type)
        else:
            project_data["project_type"] = ProjectTypeEnum.research

        if description:
            project_data["description"] = description
        if abstract:
            project_data["abstract"] = abstract

        return await super().create(db, project_data)

    async def update(
        self,
        db: AsyncSession,
        project_id: UUID,
        updates: Dict[str, Any],
    ) -> Optional[Project]:
        """
        Update project fields.

        Args:
            db: Database session
            project_id: Project's UUID
            updates: Dictionary of fields to update

        Returns:
            Updated Project instance or None if not found
        """
        project = await self.get_by_id(db, project_id)
        if not project:
            return None
        return await super().update(db, project, updates)

    async def delete(
        self, db: AsyncSession, project_id: UUID
    ) -> bool:
        """
        Delete a project.

        Args:
            db: Database session
            project_id: Project's UUID

        Returns:
            True if deleted, False if not found
        """
        return await super().delete(db, project_id, "project_id")

    # --- Domain operations ---

    async def get_domains(
        self, db: AsyncSession, project_id: UUID
    ) -> List[Domain]:
        """
        Get all domains for a project.

        Args:
            db: Database session
            project_id: Project's UUID

        Returns:
            List of Domain instances
        """
        query = (
            select(Domain)
            .join(ProjectDomain, Domain.domain_id == ProjectDomain.domain_id)
            .where(ProjectDomain.project_id == project_id)
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    async def set_domains(
        self,
        db: AsyncSession,
        project_id: UUID,
        domain_ids: List[UUID],
    ) -> None:
        """
        Set domains for a project (replaces existing).

        Args:
            db: Database session
            project_id: Project's UUID
            domain_ids: List of domain UUIDs to set
        """
        # Delete existing associations
        await db.execute(
            delete(ProjectDomain).where(ProjectDomain.project_id == project_id)
        )

        # Create new associations
        for domain_id in domain_ids:
            db.add(
                ProjectDomain(
                    project_id=project_id,
                    domain_id=domain_id,
                )
            )

        await db.flush()

    async def add_domain(
        self,
        db: AsyncSession,
        project_id: UUID,
        domain_id: UUID,
    ) -> bool:
        """
        Add a domain to a project.

        Args:
            db: Database session
            project_id: Project's UUID
            domain_id: Domain's UUID

        Returns:
            True if added, False if already exists
        """
        # Check if already exists
        existing = await db.execute(
            select(ProjectDomain).where(
                ProjectDomain.project_id == project_id,
                ProjectDomain.domain_id == domain_id,
            )
        )
        if existing.scalars().first():
            return False

        db.add(
            ProjectDomain(
                project_id=project_id,
                domain_id=domain_id,
            )
        )
        await db.flush()
        return True

    async def remove_domain(
        self,
        db: AsyncSession,
        project_id: UUID,
        domain_id: UUID,
    ) -> bool:
        """
        Remove a domain from a project.

        Args:
            db: Database session
            project_id: Project's UUID
            domain_id: Domain's UUID

        Returns:
            True if removed, False if not found
        """
        result = await db.execute(
            delete(ProjectDomain).where(
                ProjectDomain.project_id == project_id,
                ProjectDomain.domain_id == domain_id,
            )
        )
        await db.flush()
        return result.rowcount > 0


# Singleton instance for convenience
project_repository = ProjectRepository()
