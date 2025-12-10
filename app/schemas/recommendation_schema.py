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

    class Config:
        json_schema_extra = {
            "example": {
                "group_id": "123e4567-e89b-12d3-a456-426614174000",
                "idea_domain": "Machine Learning",
                "idea_description": "A recommendation system for e-commerce",
                "idea_industry": "E-commerce",
                "project_type": "research",
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


class RecommendationResponse(BaseModel):
    """Response schema for supervisor recommendations."""

    recommendations: List[SupervisorRecommendation] = Field(
        description="List of top 5 recommended supervisors"
    )
