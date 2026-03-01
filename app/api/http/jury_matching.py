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
    JuryAssignmentDetail,
    JuryAssignRequest,
    JuryAssignResponse,
    JuryBatchResponse,
    JuryBatchStatusResponse,
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


@router.post("/batch", response_model=JuryBatchResponse)
async def batch_jury_match(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Get AI-powered jury recommendations for ALL projects."""
    _require_admin(current_user)

    try:
        results = await jury_matching_service.get_batch_matches()
        return JuryBatchResponse(results=results, total_projects=len(results))

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

    1. Creates a batch record (the "ticket")
    2. Returns batch_id immediately (HTTP 202)
    3. Runs assignment in background (AI + algorithm + DB writes)
    4. Poll GET /assign/{batch_id}/status for completion
    """
    _require_admin(current_user)

    if request.fyp_cycle not in ("fyp1", "fyp2"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="fyp_cycle must be 'fyp1' or 'fyp2'",
        )

    try:
        # Create the batch (the "ticket")
        batch = await jury_matching_service.create_assignment_batch(db)

        # Schedule the background task with config params
        background_tasks.add_task(
            jury_matching_service.run_assignment_job,
            batch.batch_id,
            request.max_groups_per_jury,
            request.min_jury_per_project,
            request.fyp_cycle,
        )

        logger.info(
            f"Admin {current_user.email} triggered jury assignment "
            f"batch {batch.batch_id}"
        )

        return JuryAssignResponse(
            batch_id=str(batch.batch_id),
            status="processing",
            message=(
                f"Jury assignment started. "
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
    response_model=JuryBatchStatusResponse,
    summary="Poll jury assignment status",
)
async def get_assignment_status(
    batch_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Poll the status of a jury assignment batch."""
    _require_admin(current_user)

    batch = await jury_matching_service.get_batch_status(db, batch_id)
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Jury assignment batch not found",
        )

    # Build assignment details (only when completed)
    assignment_details = []
    if batch.status.value == "completed" and batch.assignments:
        for a in batch.assignments:
            project_name = a.project.name if a.project else None
            jury_name = None
            if a.jury_user:
                jury_name = (
                    a.jury_user.full_name
                    if hasattr(a.jury_user, "full_name")
                    else str(a.jury_user.email)
                )

            assignment_details.append(
                JuryAssignmentDetail(
                    id=str(a.id),
                    project_id=str(a.project_id),
                    project_name=project_name,
                    jury_id=str(a.jury_id),
                    jury_name=jury_name,
                    score=a.score,
                    reason=a.reason,
                )
            )

    return JuryBatchStatusResponse(
        batch_id=str(batch.batch_id),
        status=batch.status.value,
        error_log=batch.error_log,
        created_at=batch.created_at,
        total_assigned=len(assignment_details),
        assignments=assignment_details,
    )


@router.get(
    "/assignments",
    response_model=list[JuryBatchStatusResponse],
    summary="List all jury assignment batches",
)
async def list_assignment_batches(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """List all jury assignment batches (most recent first)."""
    _require_admin(current_user)

    batches = await jury_matching_service.get_all_batches(db)

    return [
        JuryBatchStatusResponse(
            batch_id=str(b.batch_id),
            status=b.status.value,
            error_log=b.error_log,
            created_at=b.created_at,
            total_assigned=0,
            assignments=[],
        )
        for b in batches
    ]
