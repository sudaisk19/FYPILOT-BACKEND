# app/api/http/shortlist.py
"""
Shortlist API Module - Refactored to use Repository Pattern

This module handles supervisor shortlisting operations for student groups.
All database operations are delegated to repositories.

REFACTORED: Removed direct SQLAlchemy queries, now uses:
- group_repository.check_membership()
- shortlist_repository.exists()
- shortlist_repository.add()
- shortlist_repository.remove()
- shortlist_repository.list_by_group()
"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase_auth import get_current_user
from app.db import get_db
from app.models.user import User
from app.repositories import group_repository, shortlist_repository
from app.schemas.shortlist_schema import (
    ShortlistAddRequest,
    ShortlistItem,
    ShortlistListResponse,
)
from app.services.cache import cache

router = APIRouter(prefix="/shortlist", tags=["shortlist"])


@router.post("/supervisors", status_code=status.HTTP_201_CREATED)
async def add_to_shortlist(
    body: ShortlistAddRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Add a supervisor to the group's shortlist.

    Only students who are members of the group can add supervisors to shortlist.
    """
    # Only students can shortlist
    if current_user.role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students can shortlist supervisors",
        )

    # Check membership using repository
    is_member = await group_repository.check_membership(
        db, body.group_id, current_user.user_id
    )
    if not is_member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this group",
        )

    # Prevent duplicates - check if already shortlisted using repository
    already_exists = await shortlist_repository.exists(
        db, body.group_id, body.supervisor_id
    )
    if not already_exists:
        await shortlist_repository.add(
            db, body.group_id, body.supervisor_id, current_user.user_id
        )
        await db.commit()

    # Invalidate cache for this group's shortlist
    await cache.delete(f"shortlist:v2:{body.group_id}")

    return {"message": "Supervisor shortlisted"}


@router.get("/supervisors", response_model=ShortlistListResponse)
async def list_shortlisted_supervisors(
    group_id: UUID = Query(..., description="Group id to fetch shortlist for"),
    current_user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
):
    """
    List all shortlisted supervisors for a group.

    Only students who are members of the group can view the shortlist.
    """
    # Only students can view shortlist
    if current_user.role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students can view shortlist",
        )

    # Check membership using repository
    is_member = await group_repository.check_membership(
        db, group_id, current_user.user_id
    )
    if not is_member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this group",
        )

    # Try cache
    cache_key = f"shortlist:v2:{group_id}"
    cached = await cache.get_json(cache_key)
    if cached:
        return cached

    # Fetch shortlist using repository
    rows = await shortlist_repository.list_by_group(db, group_id)

    items: list[ShortlistItem] = []
    for sl, user, sup in rows:
        items.append(
            ShortlistItem(
                supervisor_id=user.user_id,
                full_name=user.full_name,
                profile_avatar=user.profile_avatar,
                department=sup.department,
                designation=sup.designation,
                capacity_filled=sup.capacity_filled,
                capacity_max=sup.capacity_max,
            )
        )

    response = ShortlistListResponse(group_id=group_id, supervisors=items)

    # Cache
    await cache.set_json(cache_key, response.model_dump(), ttl_seconds=300)

    return response


@router.delete("/supervisors/{supervisor_id}", status_code=status.HTTP_200_OK)
async def remove_from_shortlist(
    supervisor_id: UUID = Path(
        ..., description="Supervisor user_id to remove from shortlist"
    ),
    group_id: UUID = Query(..., description="Group id"),
    current_user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
):
    """
    Remove a supervisor from the group's shortlist.

    Only students who are members of the group can remove supervisors from the shortlist.
    """
    # Only students can remove from shortlist
    if current_user.role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students can remove supervisors from shortlist",
        )

    # Check membership using repository
    is_member = await group_repository.check_membership(
        db, group_id, current_user.user_id
    )
    if not is_member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this group",
        )

    # Check if supervisor is in shortlist using repository
    exists = await shortlist_repository.exists(db, group_id, supervisor_id)
    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supervisor not found in shortlist",
        )

    # Delete from shortlist using repository
    await shortlist_repository.remove(db, group_id, supervisor_id)
    await db.commit()

    # Invalidate cache for this group's shortlist
    await cache.delete(f"shortlist:v2:{group_id}")

    return {"message": "Supervisor removed from shortlist"}
