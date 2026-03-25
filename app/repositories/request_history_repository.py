# app/repositories/request_history_repository.py
from typing import List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.request_history import RequestHistory

class RequestHistoryRepository:
    @staticmethod
    async def get_by_group_and_faculty(db: AsyncSession, group_id: UUID, faculty_id: UUID) -> List[RequestHistory]:
        result = await db.execute(
            select(RequestHistory)
            .where(RequestHistory.group_id == group_id, RequestHistory.faculty_id == faculty_id)
            .order_by(RequestHistory.timestamp)
        )
        return result.scalars().all()
