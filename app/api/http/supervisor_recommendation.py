# app/api/http/supervisor_recommendation.py
"""API endpoints for AI-powered supervisor recommendations."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase_auth import get_current_user
from app.db import get_db
from app.middleware.ai_service import (
    ai_service_circuit,
    supervisor_recommendation_rate_limiter,
)
from app.models.user import User
from app.schemas.supervisor_recommendation_schema import (
    SupervisorRecommendationRequest,
    SupervisorRecommendationResponse,
)
from app.services.supervisor_recommendation_client import (
    SupervisorRecommendationServiceError,
)
from app.services.supervisor_recommendation_service import (
    supervisor_recommendation_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("/health")
async def check_ai_service_health():
    """
    Check if the AI Recommender service is available.

    Returns health status of the external AI service and circuit breaker state.
    """
    is_healthy = await supervisor_recommendation_service.health_check()
    circuit_state = ai_service_circuit.state.value

    if is_healthy:
        return {
            "status": "healthy",
            "ai_service": "connected",
            "circuit_breaker": circuit_state,
            "message": "AI Recommender service is available",
        }
    else:
        return {
            "status": "degraded",
            "ai_service": "unavailable",
            "circuit_breaker": circuit_state,
            "message": "AI Recommender service is not responding",
        }


@router.post("/supervisors", response_model=SupervisorRecommendationResponse)
async def get_supervisor_recommendations(
    request: SupervisorRecommendationRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get top 5 AI-powered supervisor recommendations for a student group.

    This endpoint:
    - Rate limited to 10 requests per minute per user
    - Caches results for 5 minutes
    - Uses circuit breaker for fault tolerance
    - Fetches group member information from the database
    - Sends project details to the external AI Recommender service
    - Returns ranked supervisor recommendations with match scores and explanations

    Only students can access this endpoint.
    """
    # Verify user is a student
    if current_user.role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students can request supervisor recommendations",
        )

    # Apply rate limiting (10 requests per minute per user)
    await supervisor_recommendation_rate_limiter.check_and_raise(
        identifier=str(current_user.user_id),
        endpoint_name="supervisor recommendations",
    )

    # Validate at least one idea field is provided
    if not any(
        [
            request.idea_domain,
            request.idea_description,
            request.idea_industry,
            request.project_type,
        ]
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide at least one of: idea_domain, idea_description, idea_industry, or project_type",
        )

    try:
        recommendations = await supervisor_recommendation_service.recommend_supervisors(
            db=db,
            group_id=request.group_id,
            idea_domain=request.idea_domain,
            idea_description=request.idea_description,
            idea_industry=request.idea_industry,
            project_type=request.project_type,
        )

        logger.info(
            f"Generated {len(recommendations)} recommendations for group {request.group_id}"
        )

        return {"recommendations": recommendations}

    except ValueError as e:
        logger.warning(f"Invalid request: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except SupervisorRecommendationServiceError as e:
        logger.error(f"AI Recommender service error: {e.message}")

        # Map service errors to appropriate HTTP status codes
        if e.status_code == 503:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI Recommender service is currently unavailable. Please try again later.",
            )
        elif e.status_code == 504:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="AI Recommender service request timed out. Please try again.",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="AI Recommender service returned an error. Please try again later.",
            )
    except HTTPException:
        # Re-raise HTTPExceptions (from circuit breaker, rate limiter, etc.)
        raise
    except Exception as e:
        logger.error(f"Error generating recommendations: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate recommendations",
        )


@router.post("/refresh-supervisors")
async def refresh_supervisor_index(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    Trigger a refresh of the supervisor embeddings in the AI service.

    This endpoint should be called when supervisor data is updated.
    Only admins can trigger this refresh.
    """
    # Only allow admins to refresh
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can refresh the supervisor index",
        )

    try:
        result = await supervisor_recommendation_service.refresh_supervisor_index()
        return {
            "status": "success",
            "message": "Supervisor index refresh triggered",
            "details": result,
        }
    except SupervisorRecommendationServiceError as e:
        logger.error(f"Failed to refresh supervisor index: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to refresh supervisor index in AI service",
        )


@router.get("/circuit-status")
async def get_circuit_breaker_status(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    Get the current circuit breaker status.

    Only admins can view this information.
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can view circuit breaker status",
        )

    return {
        "state": ai_service_circuit.state.value,
        "failure_count": ai_service_circuit._failure_count,
        "failure_threshold": ai_service_circuit.failure_threshold,
        "recovery_timeout_seconds": ai_service_circuit.recovery_timeout,
    }
