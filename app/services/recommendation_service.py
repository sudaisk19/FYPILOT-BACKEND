# app/services/recommendation_service.py
"""
<<<<<<< HEAD
<<<<<<< HEAD
Supervisor Recommendation Service - Refactored to use External AI Microservice.

This service acts as a bridge between the main backend API and the external
AI Recommender microservice. It:
1. Fetches group and member data from the database
2. Transforms the data into the format expected by the AI service
3. Calls the external AI service for recommendations (with caching & circuit breaker)
4. Returns the results to the API layer

Features:
- Response caching to reduce AI service load
- Circuit breaker for fault tolerance
- Request deduplication
=======
AI-Powered Supervisor Recommendation Service - Refactored to use Repository Pattern
=======
Supervisor Recommendation Service - Refactored to use External AI Microservice.
>>>>>>> 2021c1d (integration of recom & batch reisgtration api)

This service acts as a bridge between the main backend API and the external
AI Recommender microservice. It:
1. Fetches group and member data from the database
2. Transforms the data into the format expected by the AI service
3. Calls the external AI service for recommendations (with caching & circuit breaker)
4. Returns the results to the API layer

<<<<<<< HEAD
REFACTORED:
- initialize_index() uses supervisor_repository.list_all_with_users()
  and supervisor_repository.get_domains/get_industries()
- recommend_supervisors() uses group_repository.get_with_members()
>>>>>>> 1706dee (refactored: repository pattern implementation)
=======
Features:
- Response caching to reduce AI service load
- Circuit breaker for fault tolerance
- Request deduplication
>>>>>>> 2021c1d (integration of recom & batch reisgtration api)
"""

import logging
from typing import Any, Dict, List, Optional

<<<<<<< HEAD
<<<<<<< HEAD
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.ai_recommender import (
    ai_recommender_circuit,
    recommendation_cache,
    request_deduplicator,
)
from app.repositories import group_repository
from app.services.ai_recommender import (
    AIRecommenderServiceError,
    ai_recommender_client,
)
=======
import numpy as np

# Import repositories instead of direct models
from sqlalchemy.ext.asyncio import AsyncSession

# AI libraries
try:
    import faiss
    import ollama
    from sentence_transformers import SentenceTransformer
except ImportError:
    logging.warning("AI libraries not installed. Recommendation service will not work.")

from app.repositories import group_repository, supervisor_repository
>>>>>>> 1706dee (refactored: repository pattern implementation)
=======
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.ai_recommender import (
    ai_recommender_circuit,
    recommendation_cache,
    request_deduplicator,
)
from app.repositories import group_repository
from app.services.ai_recommender import (
    AIRecommenderServiceError,
    ai_recommender_client,
)
>>>>>>> 2021c1d (integration of recom & batch reisgtration api)

logger = logging.getLogger(__name__)


class RecommendationService:
    """Service for generating supervisor recommendations via external AI service."""

    def __init__(self):
        """Initialize the recommendation service."""
        self._ai_client = ai_recommender_client
        self._cache = recommendation_cache
        self._circuit = ai_recommender_circuit
        self._deduplicator = request_deduplicator

    async def health_check(self) -> bool:
        """
        Check if the AI Recommender service is available.

<<<<<<< HEAD
<<<<<<< HEAD
=======
>>>>>>> 2021c1d (integration of recom & batch reisgtration api)
        Returns:
            bool: True if service is healthy, False otherwise.
        """
        return await self._ai_client.health_check()
<<<<<<< HEAD
=======
    async def initialize_index(self, db: AsyncSession):
        """Build and cache the FAISS index for supervisor embeddings."""
        if self._index is not None:
            return

        logger.info("Building FAISS index for supervisors...")

        # Fetch all supervisors using repository
        rows = await supervisor_repository.list_all_with_users(db)

        supervisors_data = []
        supervisors_list = []

        for supervisor, user in rows:
            # Fetch domains for this supervisor using repository
            domains_list = await supervisor_repository.get_domains(
                db, supervisor.user_id
            )
            domains = [d.name for d in domains_list]

            # Fetch industries for this supervisor using repository
            industries_list = await supervisor_repository.get_industries(
                db, supervisor.user_id
            )
            [i.name for i in industries_list]

            # Build descriptive text for this supervisor
            domains_str = ", ".join(domains) if domains else "General"
            requirements_str = (
                ", ".join(supervisor.requirements)
                if supervisor.requirements
                else "None specified"
            )
            project_types_str = (
                supervisor.project_type if supervisor.project_type else "Any"
            )

            sup_text = (
                f"Name: {user.full_name}. "
                f"Department: {supervisor.department or 'N/A'}. "
                f"Domains: {domains_str}. "
                f"Requirements: {requirements_str}. "
                f"Project Types: {project_types_str}."
            )

            supervisors_data.append(
                {"supervisor": supervisor, "user": user, "text": sup_text}
            )
            supervisors_list.append(
                {
                    "name": user.full_name,
                    "department": supervisor.department,
                    "domains": domains,
                    "requirements": supervisor.requirements or [],
                    "project_types": (
                        [supervisor.project_type] if supervisor.project_type else []
                    ),
                    "user_id": str(user.user_id),
                    "profile_avatar": user.profile_avatar,
                }
            )

        # Generate embeddings
        texts = [item["text"] for item in supervisors_data]
        embeddings = self.model.encode(texts, convert_to_numpy=True)
        embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)

        # Build FAISS index
        dimension = embeddings.shape[1]
        self._index = faiss.IndexFlatIP(dimension)
        self._index.add(embeddings)

        # Cache supervisor data
        self._supervisors_cache = supervisors_list

        logger.info(f"Index built with {len(supervisors_list)} supervisors")
>>>>>>> d174ec0 (feat: bugs fixing v3)
=======
>>>>>>> 2021c1d (integration of recom & batch reisgtration api)

    async def recommend_supervisors(
        self,
        db: AsyncSession,
        group_id: str,
        idea_domain: Optional[str] = None,
        idea_description: Optional[str] = None,
        idea_industry: Optional[str] = None,
        project_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Generate supervisor recommendations for a student group.

        This method:
        1. Checks the circuit breaker status
        2. Looks for cached recommendations
        3. Fetches group/member data from DB if cache miss
        4. Sends data to AI Recommender service
        5. Caches and returns the results

        Args:
            db: Database session
            group_id: ID of the student group
            idea_domain: Project domain/field
            idea_description: Project description
            idea_industry: Target industry
            project_type: Type of project (research/product)

        Returns:
            List of recommended supervisors with scores and AI-generated reasons.
<<<<<<< HEAD

        Raises:
            ValueError: If the group is not found.
            AIRecommenderServiceError: If the AI service fails.
            HTTPException: If circuit breaker is open.
        """
        # 1. Check circuit breaker
        self._circuit.check_and_raise()

<<<<<<< HEAD
=======

        Raises:
            ValueError: If the group is not found.
            AIRecommenderServiceError: If the AI service fails.
            HTTPException: If circuit breaker is open.
        """
        # 1. Check circuit breaker
        self._circuit.check_and_raise()

>>>>>>> 2021c1d (integration of recom & batch reisgtration api)
        # 2. Check cache first
        cached_recommendations = await self._cache.get(
            group_id=group_id,
            idea_domain=idea_domain,
            idea_description=idea_description,
            idea_industry=idea_industry,
            project_type=project_type,
        )
<<<<<<< HEAD
=======
        # Fetch group with members using repository
        group = await group_repository.get_with_members(db, group_id)
>>>>>>> 1706dee (refactored: repository pattern implementation)
=======
>>>>>>> 2021c1d (integration of recom & batch reisgtration api)

        if cached_recommendations is not None:
            logger.info(f"Returning cached recommendations for group {group_id}")
            return cached_recommendations

        # 3. Try to acquire deduplication lock
        lock_acquired, lock_key = await self._deduplicator.acquire(
            group_id=group_id,
            idea_domain=idea_domain,
            idea_description=idea_description,
            idea_industry=idea_industry,
            project_type=project_type,
        )

        if not lock_acquired:
            # Another request is in progress, wait a bit and check cache
            import asyncio

            await asyncio.sleep(1)

            cached = await self._cache.get(
                group_id=group_id,
                idea_domain=idea_domain,
                idea_description=idea_description,
                idea_industry=idea_industry,
                project_type=project_type,
            )

            if cached is not None:
                return cached

            # Still no cache, allow this request through
            lock_acquired = True
            lock_key = ""

        try:
            # 4. Fetch group with members using repository
            group = await group_repository.get_with_members(db, group_id)

            if not group:
                raise ValueError(f"Group not found: {group_id}")

            # 5. Transform group members into AI service format
            members_data = self._transform_members(group.members)

            logger.info(
                f"Requesting recommendations for group {group_id} with {len(members_data)} members"
            )

            # 6. Call the external AI Recommender service
            result = await self._ai_client.get_recommendations(
                project_domain=idea_domain or "",
                description=idea_description or "",
                members=members_data,
                industry=idea_industry,
                project_type=project_type,
            )

            # 7. Record success with circuit breaker
            self._circuit.record_success()

            # 8. Transform the response
            recommendations = self._transform_recommendations(result)

            # 9. Cache the results
            await self._cache.set(
                recommendations=recommendations,
                group_id=group_id,
                idea_domain=idea_domain,
                idea_description=idea_description,
                idea_industry=idea_industry,
                project_type=project_type,
            )

            logger.info(
                f"Received {len(recommendations)} recommendations for group {group_id}"
            )

            return recommendations

        except AIRecommenderServiceError as e:
            # Record failure with circuit breaker
            self._circuit.record_failure()
            logger.error(
                f"AI Recommender service error for group {group_id}: {e.message}"
            )
            raise

        finally:
            # Release deduplication lock
            if lock_acquired and lock_key:
                await self._deduplicator.release(lock_key)

    def _transform_members(self, members) -> List[Dict[str, Any]]:
        """
        Transform group members into the format expected by the AI service.

        Expected format for each member:
        {
            "skills": {"Python": "advanced", "ML": "intermediate"},
            "cgpa": 3.5,
            "past_projects": ["Project 1", "Project 2"]
        }

        Args:
            members: List of GroupMember objects from the database.

        Returns:
            List of member dictionaries in the AI service format.
        """
        members_data = []

        for member in members:
            student = member.student

            # Transform skills from list to dict format
            # The AI service expects skills as {"skill_name": "level"}
            # Our DB stores skills as a list, so we'll default to "intermediate"
            skills_dict = {}
            if student.skills:
                for skill in student.skills:
                    if isinstance(skill, str):
                        skills_dict[skill] = "intermediate"
                    elif isinstance(skill, dict):
                        # If skills are already stored as dicts
                        skills_dict.update(skill)

            # Extract past project names from portfolio
            past_projects = []
            if student.portfolio_projects:
                if isinstance(student.portfolio_projects, list):
                    for project in student.portfolio_projects:
                        if isinstance(project, dict):
                            # Get project title/name
                            title = project.get("title") or project.get("name", "")
                            if title:
                                past_projects.append(title)
                            # Also add tech stack as skills if not already present
                            tech_stack = project.get("tech_stack", [])
                            if isinstance(tech_stack, list):
                                for tech in tech_stack:
                                    if tech not in skills_dict:
                                        skills_dict[tech] = "intermediate"

            member_data = {
                "skills": skills_dict,
                "cgpa": float(student.cgpa) if student.cgpa else 0.0,
                "past_projects": past_projects,
            }

            members_data.append(member_data)

        return members_data

    def _transform_recommendations(
        self, ai_response: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Transform AI service response to match our API response format.

        The AI service returns:
        {
            "results": [
                {
                    "supervisor_id": "...",
                    "name": "...",
                    "department": "...",
                    "score": 0.89,
                    "reason": "...",
                    "domains": [...],
                    "requirements": [...],
                    "project_type": [...],
                    "user_id": "...",
                    "profile_avatar": "..."
                }
            ]
        }

        Our API expects:
        [
            {
                "name": "...",
                "department": "...",
                "domains": [...],
                "requirements": [...],
                "project_type": [...],
                "user_id": "...",
                "profile_avatar": "...",
                "score": 89.0,
                "reason": "..."
            }
        ]
        """
        results = ai_response.get("results", [])
        recommendations = []

        for result in results:
            # Convert score from 0-1 to 0-100 if needed
            score = result.get("score", 0)
            if score <= 1:
                score = round(score * 100, 2)

            recommendation = {
                "name": result.get("name", ""),
                "department": result.get("department"),
                "domains": result.get("domains", []),
                "requirements": result.get("requirements", []),
                "project_type": result.get("project_type", []),
                "user_id": result.get("user_id", ""),
                "profile_avatar": result.get("profile_avatar"),
                "score": score,
                "reason": result.get(
                    "reason", "Based on matching domains and requirements."
                ),
            }

            recommendations.append(recommendation)

        return recommendations

    async def refresh_supervisor_index(
        self, webhook_secret: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Trigger a refresh of supervisor embeddings in the AI service.

        This should be called when supervisor data is updated in the database.

        Args:
            webhook_secret: Optional webhook secret for authentication.

        Returns:
            Dict containing the refresh status.
        """
        return await self._ai_client.refresh_supervisors(webhook_secret)


# Global instance
recommendation_service = RecommendationService()
