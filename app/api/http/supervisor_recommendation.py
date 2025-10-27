# app/api/http/supervisor_recommendation.py
"""API endpoints for AI-powered supervisor recommendations."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.supabase_auth import get_current_user
from app.db import get_db
from app.models.user import User
from app.schemas.recommendation_schema import (
    RecommendationRequest,
    PaginatedRecommendationResponse,
)
from app.services.recommendation_service import recommendation_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.post("/supervisors", response_model=PaginatedRecommendationResponse)
async def get_supervisor_recommendations(
    request: RecommendationRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get AI-powered supervisor recommendations for a student group with pagination.

    This endpoint:
    - Analyzes group skills, interests, and project requirements
    - Uses semantic search to find matching supervisors
    - Generates AI explanations for each recommendation
    - Returns paginated results

    Only students can access this endpoint.
    """
    # Verify user is a student
    if current_user.role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students can request supervisor recommendations",
        )

    # Validate at least one idea field is provided
    if not any([
        request.idea_domain,
        request.idea_description,
        request.idea_industry,
        request.project_type,
    ]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide at least one of: idea_domain, idea_description, idea_industry, or project_type",
        )

    try:
        recommendations, total_count = await recommendation_service.recommend_supervisors(
            db=db,
            group_id=request.group_id,
            idea_domain=request.idea_domain,
            idea_description=request.idea_description,
            idea_industry=request.idea_industry,
            project_type=request.project_type,
            page=request.page,
            per_page=request.per_page,
        )

        # Calculate pagination metadata
        total_pages = (total_count + request.per_page - 1) // request.per_page if total_count > 0 else 0

        logger.info(f"Generated {len(recommendations)} recommendations (page {request.page}/{total_pages}) for group {request.group_id}")

        return PaginatedRecommendationResponse(
            recommendations=recommendations,
            total=total_count,
            page=request.page,
            per_page=request.per_page,
            total_pages=total_pages,
            has_next=request.page < total_pages,
            has_prev=request.page > 1,
        )

    except ValueError as e:
        logger.warning(f"Invalid request: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error generating recommendations: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate recommendations",
        )
