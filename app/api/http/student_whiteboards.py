"""
Student Whiteboards API — group-shared Excalidraw scenes (Postgres JSONB).
"""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase_auth import get_current_user
from app.db import get_db
from app.models.user import User
from app.models.whiteboard import Whiteboard
from app.repositories.whiteboard_repository import whiteboard_repo
from app.schemas.whiteboard_schema import (
    WhiteboardCreate,
    WhiteboardListItem,
    WhiteboardPatch,
    WhiteboardResponse,
)
from app.services.document_access import user_is_group_member

router = APIRouter()


async def _creator_full_name(db: AsyncSession, user_id: UUID) -> str:
    result = await db.execute(select(User.full_name).where(User.user_id == user_id))
    name = result.scalar_one_or_none()
    return name or str(user_id)


async def _to_whiteboard_response(
    db: AsyncSession, wb: Whiteboard
) -> WhiteboardResponse:
    created_by_name = await _creator_full_name(db, wb.created_by)
    elements = wb.elements if isinstance(wb.elements, list) else []
    app_state = wb.app_state if isinstance(wb.app_state, dict) else {}
    files = wb.files if isinstance(wb.files, dict) else {}
    return WhiteboardResponse(
        id=wb.id,
        group_id=wb.group_id,
        created_by=wb.created_by,
        created_by_name=created_by_name,
        title=wb.title,
        elements=elements,
        app_state=app_state,
        files=files,
        created_at=wb.created_at,
        updated_at=wb.updated_at,
        updated_by=wb.updated_by,
    )


@router.get(
    "/students/whiteboards",
    response_model=List[WhiteboardListItem],
)
async def list_whiteboards(
    group_id: UUID = Query(..., description="Postgres group UUID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not await user_is_group_member(db, current_user.user_id, group_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this group.",
        )
    return await whiteboard_repo.get_group_whiteboards(db, group_id)


@router.post(
    "/students/whiteboards",
    response_model=WhiteboardResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_whiteboard(
    body: WhiteboardCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not await user_is_group_member(db, current_user.user_id, body.group_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this group.",
        )
    wb = await whiteboard_repo.create_whiteboard(
        db,
        group_id=body.group_id,
        created_by=current_user.user_id,
        title=body.title,
    )
    return await _to_whiteboard_response(db, wb)


@router.get(
    "/students/whiteboards/{whiteboard_id}",
    response_model=WhiteboardResponse,
)
async def get_whiteboard(
    whiteboard_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    wb = await whiteboard_repo.get_whiteboard(db, whiteboard_id)
    if wb is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Whiteboard not found",
        )
    if not await user_is_group_member(db, current_user.user_id, wb.group_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of the group that owns this whiteboard.",
        )
    return await _to_whiteboard_response(db, wb)


@router.patch(
    "/students/whiteboards/{whiteboard_id}",
    response_model=WhiteboardResponse,
)
async def patch_whiteboard(
    whiteboard_id: UUID,
    body: WhiteboardPatch,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Partial update: rename (`title`) and/or save Excalidraw scene (`elements`, `app_state`, `files`)."""
    wb = await whiteboard_repo.get_whiteboard(db, whiteboard_id)
    if wb is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Whiteboard not found",
        )
    if not await user_is_group_member(db, current_user.user_id, wb.group_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of the group that owns this whiteboard.",
        )
    patch = body.model_dump(exclude_unset=True)
    updated = await whiteboard_repo.patch_whiteboard(
        db,
        whiteboard_id=whiteboard_id,
        updated_by=current_user.user_id,
        patch=patch,
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Whiteboard not found",
        )
    return await _to_whiteboard_response(db, updated)


@router.delete(
    "/students/whiteboards/{whiteboard_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_whiteboard(
    whiteboard_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    wb = await whiteboard_repo.get_whiteboard(db, whiteboard_id)
    if wb is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Whiteboard not found",
        )
    if not await user_is_group_member(db, current_user.user_id, wb.group_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of the group that owns this whiteboard.",
        )
    deleted = await whiteboard_repo.soft_delete_whiteboard(db, whiteboard_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Whiteboard not found",
        )
