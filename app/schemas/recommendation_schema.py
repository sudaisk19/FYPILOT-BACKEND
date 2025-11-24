# app/schemas/recommendation_schema.py
"""Schemas for supervisor recommendation requests and responses."""

from typing import List, Optional

from pydantic import BaseModel, Field


class RecommendationRequest(BaseModel):
    """Request schema for supervisor recommendations."""

    group_id: str = Field(..., description="ID of the student group")
    idea_domain: Optional[str] = Field(None, description="Project domain/field")
    idea_description: Optional[str] = Field(None, description="Project description")
    idea_industry: Optional[str] = Field(None, description="Target industry")
    project_type: Optional[str] = Field(
        None, description="Project type (research/product)"
    )
    page: int = Field(1, ge=1, description="Page number")
    per_page: int = Field(10, ge=1, le=50, description="Items per page")

    class Config:
        json_schema_extra = {
            "example": {
                "group_id": "123e4567-e89b-12d3-a456-426614174000",
                "idea_domain": "Machine Learning",
                "idea_description": "A recommendation system for e-commerce",
                "idea_industry": "E-commerce",
                "project_type": "research",
                "page": 1,
                "per_page": 10,
            }
        }


class SupervisorRecommendation(BaseModel):
    """Schema for a single supervisor recommendation."""

    name: str
    department: Optional[str]
    domains: List[str]
    requirements: List[str]
    project_type: List[str]
    user_id: str
    profile_avatar: Optional[str] = None
    score: float
    reason: str


class PaginatedRecommendationResponse(BaseModel):
    """Response schema for paginated supervisor recommendations."""

    recommendations: List[SupervisorRecommendation]
    total: int = Field(description="Total number of recommendations")
    page: int = Field(description="Current page number")
    per_page: int = Field(description="Items per page")
    total_pages: int = Field(description="Total number of pages")
    has_next: bool = Field(description="Whether there's a next page")
    has_prev: bool = Field(description="Whether there's a previous page")
