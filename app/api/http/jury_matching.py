# app/api/http/jury_matching.py
"""API endpoints for AI-powered jury matching and automated jury assignment."""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase_auth import get_current_user
from app.db import get_db
from app.middleware.ai_service import ai_service_circuit
from app.models.user import User
from app.schemas.jury_matching_schema import (
    JuryAssignmentPatchRequest,
    JuryAssignmentPatchResponse,
    JuryAssignmentsResponse,
    JuryAssignRequest,
    JuryAssignResponse,
    JuryDeleteResponse,
    JuryPairDropdownItem,
    JuryReindexResponse,
)
from app.services.jury_matching_client import JuryMatchingServiceError
from app.services.jury_matching_service import jury_matching_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jury-matching", tags=["jury-matching"])


# ── Helper ───────────────────────────────────────────────────────────────────


def _require_admin(current_user: User) -> None:
    """Raise 403 if the current user is not an admin."""
    role = (
        current_user.role.value
        if hasattr(current_user.role, "value")
        else current_user.role
    )
    if role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can access this endpoint",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Health Check
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/health")
async def check_jury_service_health():
    """Check if the Jury Matching AI service is available."""
    is_healthy = await jury_matching_service.health_check()
    circuit_state = ai_service_circuit.state.value

    if is_healthy:
        return {
            "status": "healthy",
            "ai_service": "connected",
            "circuit_breaker": circuit_state,
            "message": "Jury Matching AI service is available",
        }
    else:
        return {
            "status": "degraded",
            "ai_service": "unavailable",
            "circuit_breaker": circuit_state,
            "message": "Jury Matching AI service is not responding",
        }


# ─────────────────────────────────────────────────────────────────────────────
# Batch Match — Get AI recommendations (suggestions only, no DB writes)
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/batch")
async def batch_jury_match(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    Get AI-powered jury recommendations for ALL projects.

    Returns the raw response from the AI service as-is.
    """
    _require_admin(current_user)

    try:
        results = await jury_matching_service.get_batch_matches()
        return results

    except JuryMatchingServiceError as e:
        logger.error(f"Jury Matching service error: {e.message}")
        if e.status_code == 503:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Jury Matching AI service is currently unavailable.",
            )
        elif e.status_code == 504:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Jury Matching AI service request timed out.",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Jury Matching AI service returned an error.",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during batch jury matching: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to perform batch jury matching",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Re-Index — Rebuild FAISS indexes
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/reindex", response_model=JuryReindexResponse)
async def reindex_jury_data(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Trigger a full re-index of jury and project data in the AI service."""
    _require_admin(current_user)

    try:
        result = await jury_matching_service.trigger_reindex()
        return JuryReindexResponse(
            status=result.get("status", "ok"),
            message=result.get("message", "Re-indexing started."),
        )
    except JuryMatchingServiceError as e:
        logger.error(f"Failed to trigger jury re-index: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to trigger jury data re-indexing.",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering jury re-index: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to trigger jury data re-indexing",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Jury Pairs — Dropdown for admin to pick a jury pair
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/jury-pairs",
    response_model=list[JuryPairDropdownItem],
    summary="Get jury pairs for dropdown",
)
async def get_jury_pairs_dropdown(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get all jury pairs for a dropdown selection.

    Returns jury pairs with display labels like "Jury 1 — Dr. Ali & Dr. Sara".
    Used when admin wants to manually change a project's jury.
    """
    _require_admin(current_user)

    try:
        pairs = await jury_matching_service.get_all_jury_pairs(db)

        return [
            JuryPairDropdownItem(
                jury_id=p["jury_id"],
                label=(
                    f"Jury {p['jury_number'] or '?'} — "
                    f"{p['faculty_1_name']} & {p['faculty_2_name']}"
                ),
                faculty_1_name=p["faculty_1_name"],
                faculty_2_name=p["faculty_2_name"],
            )
            for p in pairs
        ]
    except Exception as e:
        logger.error(f"Error fetching jury pairs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch jury pairs",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Jury Assignment — Background Waiter Pattern
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/assign",
    response_model=JuryAssignResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger automated jury assignment",
)
async def trigger_jury_assignment(
    request: JuryAssignRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
):
    """
    Start automated jury assignment (Background Waiter).

    This will:
    1. DELETE all existing jury data (pairs, assignments, batches) — clean slate
    2. Create a new batch record (the "ticket")
    3. Return batch_id immediately (HTTP 202)
    4. Run AI matching + pair creation + assignment in background
    5. Poll GET /assign/{batch_id}/status for completion
    """
    _require_admin(current_user)

    # Validate cycles
    valid_cycles = {"fyp1", "fyp2"}
    invalid_cycles = [c for c in request.fyp_cycles if c not in valid_cycles]
    if invalid_cycles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid fyp_cycles: {invalid_cycles}. Allowed values are 'fyp1', 'fyp2'.",
        )
    if not request.fyp_cycles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="fyp_cycles list cannot be empty.",
        )

    try:
        # Create the batch (the "ticket")
        batch = await jury_matching_service.create_assignment_batch(
            db=db,
            fyp_cycles=request.fyp_cycles,
            created_by=(
                current_user.user_id if hasattr(current_user, "user_id") else None
            ),
        )

        # Schedule the background task with config params
        background_tasks.add_task(
            jury_matching_service.run_assignment_job,
            batch.batch_id,
            request.fyp_cycles,
            request.min_groups_per_pair,
            request.max_groups_per_pair,
        )

        logger.info(
            f"Admin {current_user.email} triggered jury assignment "
            f"batch {batch.batch_id} "
            f"(min_groups_per_pair={request.min_groups_per_pair}, "
            f"max_groups_per_pair={request.max_groups_per_pair})"
        )

        return JuryAssignResponse(
            batch_id=str(batch.batch_id),
            status="processing",
            message=(
                f"Jury assignment started (all previous data cleared). "
                f"Poll GET /api/jury-matching/assign/{batch.batch_id}/status"
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create jury assignment batch: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start jury assignment",
        )


@router.get(
    "/assign/{batch_id}/status",
    response_model=JuryAssignmentsResponse,
    summary="Poll jury assignment status",
)
async def get_assignment_status(
    batch_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Poll the status of a jury assignment batch (grouped by jury pair)."""
    _require_admin(current_user)

    result = await jury_matching_service.get_jury_matches(db, batch_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Jury assignment batch not found",
        )

    batch = result["batch"]
    jury_matches = result["jury_matches"]

    return JuryAssignmentsResponse(
        batch_id=str(batch.batch_id),
        status=batch.status.value,
        fyp_cycles=batch.fyp_cycles,
        error_log=batch.error_log,
        created_at=batch.created_at,
        total_assigned=sum(len(m["groups"]) for m in jury_matches),
        jury_matches=jury_matches,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Delete All — Manual admin reset
# ─────────────────────────────────────────────────────────────────────────────


@router.delete(
    "/assignments",
    response_model=JuryDeleteResponse,
    summary="Delete all jury assignments, pairs, and batches",
)
async def delete_all_jury_data(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Clear ALL jury data — assignments, pairs, and batches.

    This is a manual admin action to completely reset the jury system.
    """
    _require_admin(current_user)

    try:
        counts = await jury_matching_service.reset_all_jury_data(db)

        logger.info(f"Admin {current_user.email} deleted all jury data: {counts}")

        return JuryDeleteResponse(
            message="All jury data cleared successfully",
            deleted_assignments=counts["deleted_assignments"],
            deleted_pairs=counts["deleted_pairs"],
            deleted_batches=counts["deleted_batches"],
        )

    except Exception as e:
        logger.error(f"Failed to delete jury data: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete jury data",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Patch — Change jury pair for a specific assignment
# ─────────────────────────────────────────────────────────────────────────────


@router.patch(
    "/assignments/{assignment_id}/jury",
    response_model=JuryAssignmentPatchResponse,
    summary="Change the jury pair for a specific assignment",
)
async def patch_assignment_jury(
    assignment_id: UUID,
    body: JuryAssignmentPatchRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Change the jury pair assigned to a specific project/group.

    Admin selects a new jury pair from the dropdown
    (GET /jury-matching/jury-pairs) and submits the pair_id here.
    """
    _require_admin(current_user)

    try:
        new_pair_uuid = UUID(body.pair_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid pair_id format",
        )

    # Get the old pair_id for the response
    from sqlalchemy import select as sa_select

    from app.models.jury_assignment import JuryAssignment

    old_query = sa_select(JuryAssignment.pair_id).where(
        JuryAssignment.id == assignment_id
    )
    old_result = await db.execute(old_query)
    old_row = old_result.scalar_one_or_none()
    old_pair_id = str(old_row) if old_row else None

    updated = await jury_matching_service.update_assignment_jury(
        db=db,
        assignment_id=assignment_id,
        new_pair_id=new_pair_uuid,
    )

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment or jury pair not found",
        )

    logger.info(
        f"Admin {current_user.email} changed assignment "
        f"{assignment_id} jury from {old_pair_id} to {body.pair_id}"
    )

    return JuryAssignmentPatchResponse(
        id=str(updated.id),
        project_id=str(updated.project_id),
        old_pair_id=old_pair_id,
        new_pair_id=str(updated.pair_id),
    )


@router.get(
    "/assignments",
    response_model=JuryAssignmentsResponse,
    summary="Get jury assignment results",
)
async def list_jury_assignments(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get the latest jury assignment results grouped by jury pair.

    Returns assignments in the format expected by the frontend:
    each jury pair with its supervisors (name + department) and
    assigned groups (project name, FYP ID, cycle, members with roll numbers).

    Each group's ``id`` is the assignment ID — use it for
    ``PATCH /assignments/{id}/jury`` to change that group's jury.
    """
    _require_admin(current_user)

    result = await jury_matching_service.get_jury_matches(db)

    if not result:
        return JuryAssignmentsResponse(
            batch_id="",
            status="none",
            total_assigned=0,
            jury_matches=[],
        )

    batch = result["batch"]
    jury_matches = result["jury_matches"]

    return JuryAssignmentsResponse(
        batch_id=str(batch.batch_id),
        status=batch.status.value,
        fyp_cycles=batch.fyp_cycles,
        error_log=batch.error_log,
        created_at=batch.created_at,
        total_assigned=sum(len(m["groups"]) for m in jury_matches),
        jury_matches=jury_matches,
    )
