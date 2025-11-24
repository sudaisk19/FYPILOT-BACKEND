# app/api/http/shortlist.py
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase_auth import get_current_user
from app.db import get_db
from app.models.group import GroupMember
from app.models.shortlisted_supervisor import ShortlistedSupervisor
from app.models.supervisor import Supervisor
from app.models.user import User
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
    # Only students, must be a member of the group
    if current_user.role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students can shortlist supervisors",
        )

    # Check membership
    membership = await db.execute(
        select(GroupMember).where(
            GroupMember.group_id == body.group_id,
            GroupMember.student_id == current_user.user_id,
        )
    )
    if membership.scalars().first() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this group",
        )

    # Prevent duplicates (unique pair per group_id + supervisor_id)
    existing = await db.execute(
        select(ShortlistedSupervisor).where(
            ShortlistedSupervisor.group_id == body.group_id,
            ShortlistedSupervisor.supervisor_id == body.supervisor_id,
        )
    )
    if existing.scalars().first() is None:
        entity = ShortlistedSupervisor(
            group_id=body.group_id,
            supervisor_id=body.supervisor_id,
            added_by=current_user.user_id,
        )
        db.add(entity)
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
    # Only students, must be a member of the group
    if current_user.role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students can view shortlist",
        )

    membership = await db.execute(
        select(GroupMember).where(
            GroupMember.group_id == group_id,
            GroupMember.student_id == current_user.user_id,
        )
    )
    if membership.scalars().first() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this group",
        )

    # Try cache
    cache_key = f"shortlist:v2:{group_id}"  # v2 includes capacity fields
    cached = await cache.get_json(cache_key)
    if cached:
        return cached

    # Fetch shortlist joined with users and supervisor meta
    result = await db.execute(
        select(ShortlistedSupervisor, User, Supervisor)
        .join(Supervisor, Supervisor.user_id == ShortlistedSupervisor.supervisor_id)
        .join(User, User.user_id == Supervisor.user_id)
        .where(ShortlistedSupervisor.group_id == group_id)
    )
    rows = result.all()

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

    # Check membership
    membership = await db.execute(
        select(GroupMember).where(
            GroupMember.group_id == group_id,
            GroupMember.student_id == current_user.user_id,
        )
    )
    if membership.scalars().first() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this group",
        )

    # Check if supervisor is in shortlist
    existing = await db.execute(
        select(ShortlistedSupervisor).where(
            ShortlistedSupervisor.group_id == group_id,
            ShortlistedSupervisor.supervisor_id == supervisor_id,
        )
    )
    shortlisted = existing.scalars().first()
    if not shortlisted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supervisor not found in shortlist",
        )

    # Delete from shortlist
    await db.execute(
        delete(ShortlistedSupervisor).where(
            ShortlistedSupervisor.group_id == group_id,
            ShortlistedSupervisor.supervisor_id == supervisor_id,
        )
    )
    await db.commit()

    # Invalidate cache for this group's shortlist
    await cache.delete(f"shortlist:v2:{group_id}")

    return {"message": "Supervisor removed from shortlist"}
