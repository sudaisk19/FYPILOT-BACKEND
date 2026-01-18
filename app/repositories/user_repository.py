# app/repositories/user_repository.py
"""
User Repository Module

Handles all database operations for the User model.
"""

from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.user import RoleEnum, User

from .base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Repository for User model operations."""

    def __init__(self):
        super().__init__(User)

    async def get_by_id(
        self, db: AsyncSession, user_id: UUID
    ) -> Optional[User]:
        """
        Get user by ID.

        Args:
            db: Database session
            user_id: User's UUID

        Returns:
            User instance or None
        """
        return await super().get_by_id(db, user_id, "user_id")

    async def get_by_email(
        self, db: AsyncSession, email: str
    ) -> Optional[User]:
        """
        Get user by email address.

        Args:
            db: Database session
            email: User's email address

        Returns:
            User instance or None
        """
        query = select(User).where(User.email == email)
        result = await db.execute(query)
        return result.scalars().first()

    async def get_with_profiles(
        self, db: AsyncSession, user_id: UUID
    ) -> Optional[User]:
        """
        Get user with all profile relationships loaded.

        Args:
            db: Database session
            user_id: User's UUID

        Returns:
            User instance with profiles loaded, or None
        """
        query = (
            select(User)
            .options(
                selectinload(User.student_profile),
                selectinload(User.supervisor_profile),
                selectinload(User.admin_profile),
            )
            .where(User.user_id == user_id)
        )
        result = await db.execute(query)
        return result.scalars().first()

    async def get_by_email_with_profiles(
        self, db: AsyncSession, email: str
    ) -> Optional[User]:
        """
        Get user by email with all profile relationships loaded.

        Args:
            db: Database session
            email: User's email address

        Returns:
            User instance with profiles loaded, or None
        """
        query = (
            select(User)
            .options(
                selectinload(User.student_profile),
                selectinload(User.supervisor_profile),
                selectinload(User.admin_profile),
            )
            .where(User.email == email)
        )
        result = await db.execute(query)
        return result.scalars().first()

    async def exists_by_email(
        self, db: AsyncSession, email: str
    ) -> bool:
        """
        Check if a user with the given email exists.

        Args:
            db: Database session
            email: Email to check

        Returns:
            True if user exists, False otherwise
        """
        user = await self.get_by_email(db, email)
        return user is not None

    async def create(
        self,
        db: AsyncSession,
        full_name: str,
        email: str,
        password_hash: str,
        role: RoleEnum,
        profile_avatar: Optional[str] = None,
    ) -> User:
        """
        Create a new user.

        Args:
            db: Database session
            full_name: User's full name
            email: User's email address
            password_hash: Hashed password
            role: User's role (student, supervisor, admin)
            profile_avatar: Optional avatar URL

        Returns:
            Created User instance
        """
        user_data = {
            "full_name": full_name,
            "email": email,
            "password_hash": password_hash,
            "role": role,
        }
        if profile_avatar:
            user_data["profile_avatar"] = profile_avatar

        return await super().create(db, user_data)

    async def update(
        self,
        db: AsyncSession,
        user_id: UUID,
        updates: Dict[str, Any],
    ) -> Optional[User]:
        """
        Update user fields.

        Args:
            db: Database session
            user_id: User's UUID
            updates: Dictionary of fields to update

        Returns:
            Updated User instance or None if not found
        """
        user = await self.get_by_id(db, user_id)
        if not user:
            return None
        return await super().update(db, user, updates)

    async def get_users_by_role(
        self, db: AsyncSession, role: RoleEnum, skip: int = 0, limit: int = 100
    ) -> List[User]:
        """
        Get all users with a specific role.

        Args:
            db: Database session
            role: Role to filter by
            skip: Number of records to skip
            limit: Maximum records to return

        Returns:
            List of User instances
        """
        query = (
            select(User)
            .where(User.role == role)
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(query)
        return list(result.scalars().all())


# Singleton instance for convenience
user_repository = UserRepository()
