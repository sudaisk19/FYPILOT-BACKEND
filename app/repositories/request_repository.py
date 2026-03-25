# app/repositories/request_repository.py
"""
Request Repository Module

Handles all database operations for the Request model (supervisor invites/requests).
"""

from datetime import datetime
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.faculty import Faculty
from app.models.group import Group, InviteStatusEnum
from app.models.request import Request, RequestTypeEnum
from app.models.user import User

from .base import BaseRepository


class RequestRepository(BaseRepository[Request]):
    """Repository for Request model operations."""

    def __init__(self):
        super().__init__(Request)

    async def get_by_id(self, db: AsyncSession, request_id: UUID) -> Optional[Request]:
        """
        Get request by ID.

        Args:
            db: Database session
            request_id: Request's UUID

        Returns:
            Request instance or None
        """
        return await super().get_by_id(db, request_id, "request_id")

    async def create(
        self,
        db: AsyncSession,
        group_id: UUID,
        faculty_id: UUID,
        request_type: RequestTypeEnum,
    ) -> Request:
        """
        Create a new supervisor request.

        Args:
            db: Database session
            group_id: Group's UUID
            faculty_id: Faculty's user ID
            request_type: Type of request (supervisor/cosupervisor)

        Returns:
            Created Request instance
        """
        request_data = {
            "group_id": group_id,
            "faculty_id": faculty_id,
            "request_type": request_type,
            "status": InviteStatusEnum.pending,
            "created_at": datetime.utcnow(),
        }
        return await super().create(db, request_data)

    async def get_pending_for_supervisor(
        self,
        db: AsyncSession,
        faculty_id: UUID,
    ) -> List[Tuple[Request, Group]]:
        """
        Get all pending requests for a supervisor.

        Args:
            db: Database session
            faculty_id: Faculty's user ID

        Returns:
            List of (Request, Group) tuples
        """
        query = (
            select(Request, Group)
            .join(Group, Group.group_id == Request.group_id)
            .where(
                Request.faculty_id == faculty_id,
                Request.status == InviteStatusEnum.pending,
            )
            .order_by(Request.created_at.desc())
        )
        result = await db.execute(query)
        return list(result.all())

    async def get_by_group(
        self,
        db: AsyncSession,
        group_id: UUID,
        exclude_cancelled: bool = True,
    ) -> List[Tuple[Request, Faculty, User]]:
        """
        Get all requests sent by a group.

        Args:
            db: Database session
            group_id: Group's UUID
            exclude_cancelled: Whether to exclude cancelled requests

        Returns:
            List of (Request, Faculty, User) tuples
        """
        query = (
            select(Request, Faculty, User)
            .join(Faculty, Faculty.user_id == Request.faculty_id)
            .join(User, User.user_id == Faculty.user_id)
            .where(Request.group_id == group_id)
        )

        if exclude_cancelled:
            query = query.where(Request.status != InviteStatusEnum.cancelled)

        query = query.order_by(Request.created_at.desc())

        result = await db.execute(query)
        return list(result.all())

    async def exists_pending(
        self,
        db: AsyncSession,
        group_id: UUID,
        faculty_id: UUID,
    ) -> bool:
        """
        Check if a pending request exists for a group-supervisor pair.

        Args:
            db: Database session
            group_id: Group's UUID
            faculty_id: Faculty's user ID

        Returns:
            True if pending request exists, False otherwise
        """
        query = select(Request).where(
            Request.group_id == group_id,
            Request.faculty_id == faculty_id,
            Request.status == InviteStatusEnum.pending,
        )
        result = await db.execute(query)
        return result.scalars().first() is not None

    async def get_pending_by_group_supervisor(
        self,
        db: AsyncSession,
        group_id: UUID,
        faculty_id: UUID,
    ) -> Optional[Request]:
        """
        Get a pending request for a specific group-supervisor pair.

        Args:
            db: Database session
            group_id: Group's UUID
            faculty_id: Faculty's user ID

        Returns:
            Request instance or None
        """
        query = select(Request).where(
            Request.group_id == group_id,
            Request.faculty_id == faculty_id,
            Request.status == InviteStatusEnum.pending,
        )
        result = await db.execute(query)
        return result.scalars().first()

    async def update_status(
        self,
        db: AsyncSession,
        request_id: UUID,
        status: InviteStatusEnum,
    ) -> Optional[Request]:
        """
        Update the status of a request.

        Args:
            db: Database session
            request_id: Request's UUID
            status: New status

        Returns:
            Updated Request instance or None if not found
        """
        request = await self.get_by_id(db, request_id)
        if not request:
            return None

        request.status = status
        request.updated_at = datetime.utcnow()
        await db.flush()
        return request

    async def delete(self, db: AsyncSession, request_id: UUID) -> bool:
        """
        Delete a request.

        Args:
            db: Database session
            request_id: Request's UUID

        Returns:
            True if deleted, False if not found
        """
        result = await db.execute(
            delete(Request).where(Request.request_id == request_id)
        )
        await db.flush()
        return result.rowcount > 0

    async def get_for_supervisor_validation(
        self,
        db: AsyncSession,
        request_id: UUID,
        faculty_id: UUID,
    ) -> Optional[Request]:
        """
        Get a pending request that belongs to a specific supervisor.
        Useful for validating actions like accept/reject.

        Args:
            db: Database session
            request_id: Request's UUID
            faculty_id: Faculty's user ID

        Returns:
            Request instance or None
        """
        query = select(Request).where(
            Request.request_id == request_id,
            Request.faculty_id == faculty_id,
            Request.status == InviteStatusEnum.pending,
        )
        result = await db.execute(query)
        return result.scalars().first()

    async def cancel_all_pending_for_group_role(
        self,
        db: AsyncSession,
        group_id: UUID,
        request_type: RequestTypeEnum,
    ) -> int:
        """
        Cancel all pending requests for a specific role in a group.
        Used when a supervisor is assigned.

        Args:
            db: Database session
            group_id: Group's UUID
            request_type: Type of request to cancel

        Returns:
            Number of requests cancelled
        """
        result = await db.execute(
            update(Request)
            .where(
                Request.group_id == group_id,
                Request.request_type == request_type,
                Request.status == InviteStatusEnum.pending,
            )
            .values(
                status=InviteStatusEnum.cancelled,
                updated_at=datetime.utcnow(),
            )
        )
        await db.flush()
        return result.rowcount

    async def get_recent_by_group_supervisor_statuses(
        self,
        db: AsyncSession,
        group_id: UUID,
        faculty_id: UUID,
        statuses: list[InviteStatusEnum],
    ) -> Optional[Request]:
        """
        Get the most recent request for a specific group-supervisor pair with status in the given list.
        """
        query = (
            select(Request)
            .where(
                Request.group_id == group_id,
                Request.faculty_id == faculty_id,
                Request.status.in_(statuses),
            )
            .order_by(Request.created_at.desc())
        )
        result = await db.execute(query)
        return result.scalars().first()


# Singleton instance for convenience
request_repository = RequestRepository()
