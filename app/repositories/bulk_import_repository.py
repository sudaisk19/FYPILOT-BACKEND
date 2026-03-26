from typing import List, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bulk_import import BulkImportItem, BulkImportJob, BulkItemStatus
from app.repositories.base import BaseRepository


class BulkImportRepository(BaseRepository[BulkImportJob]):
    """Repository for BulkImportJob model operations."""

    def __init__(self):
        super().__init__(BulkImportJob)

    async def get_job_by_id(
        self, db: AsyncSession, job_id: UUID
    ) -> Optional[BulkImportJob]:
        """Fetch a bulk import job by ID."""
        return await self.get_by_id(db, job_id)

    async def count_jobs(self, db: AsyncSession) -> int:
        """Get the total number of bulk import jobs."""
        query = select(func.count()).select_from(BulkImportJob)
        result = await db.execute(query)
        return result.scalar_one()

    async def list_jobs_paginated(
        self, db: AsyncSession, offset: int, limit: int
    ) -> List[BulkImportJob]:
        """List bulk import jobs with pagination."""
        query = (
            select(BulkImportJob)
            .order_by(BulkImportJob.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_recent_errors(
        self, db: AsyncSession, job_id: UUID, limit: int = 10
    ) -> List[BulkImportItem]:
        """Fetch the most recent errors for a specific bulk import job."""
        query = (
            select(BulkImportItem)
            .where(
                BulkImportItem.job_id == job_id,
                BulkImportItem.status.in_(
                    [BulkItemStatus.failed, BulkItemStatus.skipped]
                ),
            )
            .order_by(BulkImportItem.row_number)
            .limit(limit)
        )
        result = await db.execute(query)
        return list(result.scalars().all())


# Singleton instance
bulk_import_repository = BulkImportRepository()
