"""
Group membership checks for group_documents (student workspace docs).
"""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.models.group import GroupMember
from app.models.group_document import GroupDocument
from app.models.user import User
from app.repositories.group_document_repository import group_document_repo


async def user_is_group_member(db: AsyncSession, user_id: UUID, group_id: UUID) -> bool:
    stmt = select(GroupMember).where(
        GroupMember.group_id == group_id,
        GroupMember.student_id == user_id,
    )
    result = await db.execute(stmt)
    return result.scalars().first() is not None


async def require_group_document_for_user(
    db: AsyncSession,
    doc_id: UUID,
    current_user: User,
) -> GroupDocument:
    """
    Load the document and require that the current user is a member of its group.
    Returns 404 if missing/inactive; 403 if not a member.
    """
    doc = await group_document_repo.get_by_id(db, doc_id)
    if doc is None or not doc.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    if not await user_is_group_member(db, current_user.user_id, doc.group_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of the group that owns this document.",
        )
    return doc


async def student_can_access_document_ws(user_id: UUID, doc_id_str: str) -> bool:
    """WebSocket: validate UUID and group membership (no HTTPException)."""
    try:
        doc_id = UUID(doc_id_str)
    except (ValueError, TypeError):
        return False
    try:
        async with AsyncSessionLocal() as db:
            doc = await group_document_repo.get_by_id(db, doc_id)
            if doc is None or not doc.is_active:
                return False
            return await user_is_group_member(db, user_id, doc.group_id)
    except Exception:
        return False
