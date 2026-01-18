# app/repositories/base.py
"""
Base Repository Module

Provides a generic base class for all repositories with common CRUD operations.
All repositories should inherit from this base class.
"""

from typing import Any, Dict, Generic, List, Optional, Type, TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Generic type for SQLAlchemy models
ModelType = TypeVar("ModelType")


class BaseRepository(Generic[ModelType]):
    """
    Generic base repository with common CRUD operations.

    Type Parameters:
        ModelType: The SQLAlchemy model class this repository manages

    Usage:
        class UserRepository(BaseRepository[User]):
            def __init__(self):
                super().__init__(User)
    """

    def __init__(self, model: Type[ModelType]):
        """
        Initialize repository with a model class.

        Args:
            model: SQLAlchemy model class
        """
        self.model = model

    async def get_by_id(
        self, db: AsyncSession, id: UUID, id_field: str = "id"
    ) -> Optional[ModelType]:
        """
        Get a single record by its primary key.

        Args:
            db: Database session
            id: Primary key value
            id_field: Name of the primary key field (default: "id")

        Returns:
            Model instance or None if not found
        """
        query = select(self.model).where(getattr(self.model, id_field) == id)
        result = await db.execute(query)
        return result.scalars().first()

    async def get_all(
        self, db: AsyncSession, skip: int = 0, limit: int = 100
    ) -> List[ModelType]:
        """
        Get all records with pagination.

        Args:
            db: Database session
            skip: Number of records to skip (offset)
            limit: Maximum number of records to return

        Returns:
            List of model instances
        """
        query = select(self.model).offset(skip).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def create(self, db: AsyncSession, obj_in: Dict[str, Any]) -> ModelType:
        """
        Create a new record.

        Args:
            db: Database session
            obj_in: Dictionary of field values

        Returns:
            Created model instance
        """
        db_obj = self.model(**obj_in)
        db.add(db_obj)
        await db.flush()
        return db_obj

    async def update(
        self,
        db: AsyncSession,
        db_obj: ModelType,
        obj_in: Dict[str, Any],
    ) -> ModelType:
        """
        Update an existing record.

        Args:
            db: Database session
            db_obj: Existing model instance to update
            obj_in: Dictionary of field values to update

        Returns:
            Updated model instance
        """
        for field, value in obj_in.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)
        await db.flush()
        return db_obj

<<<<<<< HEAD
    async def delete(self, db: AsyncSession, id: UUID, id_field: str = "id") -> bool:
=======
    async def delete(
        self, db: AsyncSession, id: UUID, id_field: str = "id"
    ) -> bool:
>>>>>>> 1706dee (refactored: repository pattern implementation)
        """
        Delete a record by its primary key.

        Args:
            db: Database session
            id: Primary key value
            id_field: Name of the primary key field (default: "id")

        Returns:
            True if deleted, False if not found
        """
        db_obj = await self.get_by_id(db, id, id_field)
        if db_obj:
            await db.delete(db_obj)
            await db.flush()
            return True
        return False

<<<<<<< HEAD
    async def exists(self, db: AsyncSession, id: UUID, id_field: str = "id") -> bool:
=======
    async def exists(
        self, db: AsyncSession, id: UUID, id_field: str = "id"
    ) -> bool:
>>>>>>> 1706dee (refactored: repository pattern implementation)
        """
        Check if a record exists by its primary key.

        Args:
            db: Database session
            id: Primary key value
            id_field: Name of the primary key field (default: "id")

        Returns:
            True if exists, False otherwise
        """
        obj = await self.get_by_id(db, id, id_field)
        return obj is not None

    async def count(self, db: AsyncSession) -> int:
        """
        Count total records.

        Args:
            db: Database session

        Returns:
            Total count of records
        """
        from sqlalchemy import func

        query = select(func.count()).select_from(self.model)
        result = await db.execute(query)
        return result.scalar_one()
