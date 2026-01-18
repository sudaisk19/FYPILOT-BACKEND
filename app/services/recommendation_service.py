# app/services/recommendation_service.py
"""
AI-Powered Supervisor Recommendation Service - Refactored to use Repository Pattern

This service provides intelligent supervisor recommendations for student groups
using semantic search, heuristic scoring, and LLM-generated explanations.

REFACTORED:
- initialize_index() uses supervisor_repository.list_all_with_users()
  and supervisor_repository.get_domains/get_industries()
- recommend_supervisors() uses group_repository.get_with_members()
"""

import logging
from typing import Any, Dict, List, Optional

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

logger = logging.getLogger(__name__)


class RecommendationService:
    """Service for generating AI-powered supervisor recommendations."""

    def __init__(self):
        """Initialize the recommendation service with AI models."""
        # Model will be loaded lazily on first use
        self._model = None
        self._index = None
        self._supervisors_cache = None

    @property
    def model(self) -> SentenceTransformer:
        """Lazy load the sentence transformer model."""
        if self._model is None:
            logger.info("Loading SentenceTransformer model...")
            self._model = SentenceTransformer("all-MiniLM-L6-v2")
        return self._model

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
            domains_list = await supervisor_repository.get_domains(db, supervisor.user_id)
            domains = [d.name for d in domains_list]

            # Fetch industries for this supervisor using repository
            industries_list = await supervisor_repository.get_industries(db, supervisor.user_id)
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
        Generate AI-powered supervisor recommendations for a student group.

        Args:
            db: Database session
            group_id: ID of the student group
            idea_domain: Project domain/field
            idea_description: Project description
            idea_industry: Target industry
            project_type: Type of project (research/product)
            page: Page number for pagination
            per_page: Items per page

        Returns:
            Tuple of (List of recommended supervisors with scores and AI-generated reasons, total count)
        """
        # Ensure index is initialized
        await self.initialize_index(db)

        # Fetch group with members using repository
        group = await group_repository.get_with_members(db, group_id)

        if not group:
            raise ValueError("Group not found")

        # Build group profile from members
        group_skills = []
        group_interests = []

        for member in group.members:
            student = member.student
            if student.skills:
                group_skills.extend(student.skills)
            if student.interests:
                group_interests.extend(student.interests)

            # Add skills from portfolio projects
            if student.portfolio_projects:
                if isinstance(student.portfolio_projects, list):
                    for project in student.portfolio_projects:
                        if isinstance(project, dict) and "tech_stack" in project:
                            if isinstance(project["tech_stack"], list):
                                group_skills.extend(project["tech_stack"])

        # Build semantic query
        query_text = (
            f"Domain: {idea_domain or ''}. "
            f"Industry: {idea_industry or ''}. "
            f"Project Type: {project_type or ''}. "
            f"Description: {idea_description or ''}. "
            f"Skills: {', '.join(group_skills[:10])}. "
            f"Interests: {', '.join(group_interests[:10])}."
        )

        # Semantic search - get all supervisors for pagination
        q_embedding = self.model.encode([query_text], convert_to_numpy=True)
        q_embedding = q_embedding / np.linalg.norm(q_embedding, axis=1, keepdims=True)

        # Search all supervisors (not just 10)
        search_k = min(50, len(self._supervisors_cache))
        distances, indices = self._index.search(q_embedding, search_k)
        similarities = np.clip(distances[0], 0.0, 1.0)

        # Score candidates
        candidates = []
        for rank, (idx, similarity) in enumerate(zip(indices[0], similarities)):
            sup = self._supervisors_cache[idx]

            # Jaccard similarity for skills and domains
            skills_j = self._jaccard_similarity(group_skills, sup["requirements"])
            interests_j = self._jaccard_similarity(group_interests, sup["domains"])

            # Project type bonus
            type_bonus = 0.05 if project_type in sup["project_types"] else 0.0

            # Weighted score
            raw_score = (
                0.50 * similarity + 0.35 * skills_j + 0.10 * interests_j + type_bonus
            ) * 100

            candidates.append(
                {
                    "name": sup["name"],
                    "department": sup["department"],
                    "domains": sup["domains"],
                    "requirements": sup["requirements"],
                    "project_type": sup["project_types"],
                    "user_id": sup["user_id"],
                    "profile_avatar": sup["profile_avatar"],
                    "similarity": float(similarity),
                    "skills_match": float(skills_j),
                    "interests_match": float(interests_j),
                    "raw_score": float(raw_score),
                }
            )

        # Normalize scores
        max_score = max(c["raw_score"] for c in candidates) if candidates else 1
        for c in candidates:
            c["score"] = round((c["raw_score"] / max_score) * 100, 2)

        # Sort and get top 5 unique candidates
        candidates.sort(key=lambda x: x["score"], reverse=True)
        unique_candidates = self._deduplicate(candidates)[:5]  # Only take top 5

        # Generate AI reasons for all 5 candidates
        try:
            reasons = await self._generate_reasons(
                group,
                unique_candidates,
                idea_domain,
                idea_description,
                idea_industry,
                project_type,
            )

            # Merge reasons with candidates
            result = []
            for sup, reason in zip(unique_candidates, reasons):
                result.append(
                    {
                        "name": sup["name"],
                        "department": sup["department"],
                        "domains": sup["domains"],
                        "requirements": sup["requirements"],
                        "project_type": sup["project_type"],
                        "user_id": sup["user_id"],
                        "profile_avatar": sup["profile_avatar"],
                        "score": sup["score"],
                        "reason": (
                            reason
                            if reason
                            else "Based on matching domains and requirements."
                        ),
                    }
                )

            # Add generic reasons for any remaining candidates
            for sup in unique_candidates[len(reasons) :]:
                result.append(
                    {
                        "name": sup["name"],
                        "department": sup["department"],
                        "domains": sup["domains"],
                        "requirements": sup["requirements"],
                        "project_type": sup["project_type"],
                        "user_id": sup["user_id"],
                        "profile_avatar": sup["profile_avatar"],
                        "score": sup["score"],
                        "reason": "Based on matching domains and requirements.",
                    }
                )

            return result
        except Exception as e:
            logger.error(f"Error generating AI reasons: {e}")
            # Return without reasons if LLM fails
            result = [
                {
                    "name": sup["name"],
                    "department": sup["department"],
                    "domains": sup["domains"],
                    "requirements": sup["requirements"],
                    "project_type": sup["project_type"],
                    "user_id": sup["user_id"],
                    "profile_avatar": sup["profile_avatar"],
                    "score": sup["score"],
                    "reason": "Based on matching domains and requirements.",
                }
                for sup in unique_candidates
            ]

            return result

    async def _generate_reasons(
        self, group, candidates, domain, description, industry, project_type
    ) -> List[str]:
        """Generate AI explanations for recommendations."""
        member_text = "\n".join(
            [
                f"- {member.student.user.full_name if member.student.user else 'Member'} "
                f"(CGPA {member.student.cgpa or 'N/A'})"
                for member in group.members
            ]
        )

        supervisors_text = "\n".join(
            [
                f"{i + 1}. {s['name']} "
                f"(Domains: {', '.join(s['domains'])}, "
                f"Requirements: {', '.join(s['requirements'])}, "
                f"Project Types: {', '.join(s['project_type'])})"
                for i, s in enumerate(candidates)
            ]
        )

        prompt = f"""You are assisting with supervisor recommendations.

STUDENT GROUP
{member_text}

FYP IDEA
- Domain: {domain or 'N/A'}
- Industry: {industry or 'N/A'}
- Project Type: {project_type or 'N/A'}
- Description: {description or 'N/A'}

TOP 5 SUPERVISORS
{supervisors_text}

TASK
For each supervisor (in the same order), write exactly ONE reason (20-25 words) 
explaining why they fit the group, based ONLY on their domains, requirements, and project type.

Return exactly 5 bullet points. Do not repeat names or scores.
"""

        response = ollama.chat(
            model="phi3",
            messages=[{"role": "user", "content": prompt}],
            options={
                "temperature": 0.1,
                "top_p": 0.9,
            },
        )

        reasons = response["message"]["content"].strip().split("\n")
        reasons = [r.strip("-•12345. ") for r in reasons if r.strip()]
        return reasons[:5]

    @staticmethod
    def _jaccard_similarity(a, b):
        """Calculate Jaccard similarity between two sets."""
        if not a and not b:
            return 0.0
        set_a, set_b = set(a), set(b)
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return intersection / union if union else 0.0

    @staticmethod
    def _deduplicate(candidates):
        """Remove duplicate candidates by name."""
        seen = set()
        unique = []
        for c in candidates:
            if c["name"] not in seen:
                seen.add(c["name"])
                unique.append(c)
        return unique


# Global instance
recommendation_service = RecommendationService()
