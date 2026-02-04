# app/services/ai_recommender.py
"""
HTTP Client for AI Recommender Microservice.

This service provides a clean interface for communicating with the
external AI Recommender FastAPI service for supervisor recommendations.
"""

import logging
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class AIRecommenderServiceError(Exception):
    """Custom exception for AI Recommender service errors."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class AIRecommenderClient:
    """
    HTTP Client for the AI Recommender microservice.

    This client handles all communication with the external recommendation
    service, including health checks and supervisor recommendations.
    """

    def __init__(self):
        """Initialize the AI Recommender client with configuration."""
        self.base_url = settings.ai_recommender_url.rstrip("/")
        self.timeout = settings.ai_recommender_timeout
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Lazy initialization of the async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout),
                headers={"Content-Type": "application/json"},
            )
        return self._client

    async def health_check(self) -> bool:
        """
        Check if the AI Recommender service is healthy.

        Returns:
            bool: True if service is healthy, False otherwise.
        """
        try:
            response = await self.client.get("/health")
            if response.status_code == 200:
                data = response.json()
                return data.get("status") == "healthy"
            return False
        except httpx.RequestError as e:
            logger.warning(f"AI Recommender health check failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during health check: {e}")
            return False

    async def get_recommendations(
        self,
        project_domain: str,
        description: str,
        members: List[Dict[str, Any]],
        industry: Optional[str] = None,
        project_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get supervisor recommendations from the AI service.

        Args:
            project_domain: The project domain/field (e.g., "Machine Learning")
            description: Project description
            members: List of group members with their skills, cgpa, and past_projects
            industry: Optional target industry
            project_type: Optional project type (research/product)

        Returns:
            Dict containing the recommendation results from the AI service.

        Raises:
            AIRecommenderServiceError: If the request fails or service is unavailable.
        """
        payload = {
            "project_domain": project_domain or "",
            "description": description or "",
            "members": members,
        }

        # Add optional fields only if provided
        if industry:
            payload["industry"] = industry
        if project_type:
            payload["project_type"] = project_type

        logger.debug(f"Sending recommendation request to AI service: {payload}")

        try:
            response = await self.client.post("/recommend", json=payload)

            if response.status_code == 200:
                result = response.json()
                logger.info(
                    f"Received {len(result.get('results', []))} recommendations from AI service"
                )
                return result
            else:
                error_detail = response.text
                logger.error(
                    f"AI Recommender service error: {response.status_code} - {error_detail}"
                )
                raise AIRecommenderServiceError(
                    message=f"AI service returned error: {error_detail}",
                    status_code=response.status_code,
                )

        except httpx.TimeoutException as e:
            logger.error(f"AI Recommender service timeout: {e}")
            raise AIRecommenderServiceError(
                message="AI Recommender service request timed out",
                status_code=504,
            )
        except httpx.RequestError as e:
            logger.error(f"AI Recommender service connection error: {e}")
            raise AIRecommenderServiceError(
                message=f"Failed to connect to AI Recommender service: {str(e)}",
                status_code=503,
            )

    async def refresh_supervisors(
        self, webhook_secret: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Trigger a refresh of supervisor embeddings in the AI service.

        Args:
            webhook_secret: Optional webhook secret for authentication.

        Returns:
            Dict containing the refresh status and count of embedded supervisors.
        """
        headers = {}
        if webhook_secret:
            headers["X-Webhook-Secret"] = webhook_secret

        try:
            response = await self.client.post(
                "/refresh-supervisors",
                headers=headers,
            )

            if response.status_code == 200:
                return response.json()
            else:
                raise AIRecommenderServiceError(
                    message=f"Failed to refresh supervisors: {response.text}",
                    status_code=response.status_code,
                )

        except httpx.RequestError as e:
            logger.error(f"Failed to refresh supervisors: {e}")
            raise AIRecommenderServiceError(
                message=f"Failed to connect to AI service: {str(e)}",
                status_code=503,
            )

    async def close(self):
        """Close the HTTP client connection."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
            logger.debug("AI Recommender client connection closed")


# Global singleton instance
ai_recommender_client = AIRecommenderClient()
