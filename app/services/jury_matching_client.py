# app/services/jury_matching_client.py
"""
HTTP Client for the Jury Matching AI Microservice.

This client communicates with the Jury Matching endpoints on the
AI Recommender service (/api/v1/jury/*).

The jury service lives on the SAME host as the supervisor recommender
(default: http://localhost:8001), just under different API paths.
"""

import logging
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class JuryMatchingServiceError(Exception):
    """Custom exception for Jury Matching service errors."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class JuryMatchingClient:
    """
    HTTP Client for the Jury Matching microservice.

    Endpoints consumed:
    - POST /api/v1/jury/batch    → Get jury recommendations for ALL projects
    - POST /api/v1/jury/reindex  → Rebuild FAISS indexes
    """

    def __init__(self):
        """Initialize the Jury Matching client with configuration."""
        # Same base URL as the supervisor recommender (same service)
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
        Check if the AI service (jury endpoints) is healthy.

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
            logger.warning(f"Jury Matching health check failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during jury health check: {e}")
            return False

    async def batch_match(
        self,
        fyp_cycles: Optional[List[str]] = None,
        min_groups_per_pair: Optional[int] = None,
        max_groups_per_pair: Optional[int] = None,
        min_jury_per_project: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get jury recommendations for ALL projects in one call.

        The AI service uses pre-built FAISS indexes to find the best-fit
        jury panel for every FYP project.

        Returns:
            List of dicts, each containing project_id, title, and ranked matches.

        Raises:
            JuryMatchingServiceError: If the request fails.
        """
        logger.info("Requesting batch jury matching from AI service")

        try:
            # Optional keys mirror the AI recommender contract; assignment flow
            # always sends min/max groups per jury pair plus internal min pairs/project.
            payload = {}
            if fyp_cycles:
                payload["fyp_cycles"] = fyp_cycles
            if min_groups_per_pair is not None:
                payload["min_groups_per_pair"] = min_groups_per_pair
            if max_groups_per_pair is not None:
                payload["max_groups_per_pair"] = max_groups_per_pair
            if min_jury_per_project is not None:
                payload["min_jury_per_project"] = min_jury_per_project

            response = await self.client.post("/api/v1/jury/batch", json=payload)

            if response.status_code == 200:
                result = response.json()
                logger.info(f"Received jury matches for {len(result)} projects")
                return result
            else:
                error_detail = response.text
                logger.error(
                    f"Jury Matching service error: {response.status_code} - {error_detail}"
                )
                raise JuryMatchingServiceError(
                    message=f"Jury service returned error: {error_detail}",
                    status_code=response.status_code,
                )

        except httpx.TimeoutException as e:
            logger.error(f"Jury Matching service timeout: {e}")
            raise JuryMatchingServiceError(
                message="Jury Matching service request timed out",
                status_code=504,
            )
        except httpx.RequestError as e:
            logger.error(f"Jury Matching service connection error: {e}")
            raise JuryMatchingServiceError(
                message=f"Failed to connect to Jury Matching service: {str(e)}",
                status_code=503,
            )

    async def reindex(self) -> Dict[str, Any]:
        """
        Trigger a full re-index of jury + project FAISS indexes.

        This runs in the background on the AI service (~10-30 seconds).

        Returns:
            Dict with status and message from the AI service.

        Raises:
            JuryMatchingServiceError: If the request fails.
        """
        logger.info("Triggering jury matching re-index on AI service")

        try:
            response = await self.client.post("/api/v1/jury/reindex")

            if response.status_code == 200:
                result = response.json()
                logger.info(f"Jury re-index triggered: {result}")
                return result
            else:
                error_detail = response.text
                logger.error(
                    f"Jury re-index error: {response.status_code} - {error_detail}"
                )
                raise JuryMatchingServiceError(
                    message=f"Failed to trigger jury re-index: {error_detail}",
                    status_code=response.status_code,
                )

        except httpx.TimeoutException as e:
            logger.error(f"Jury re-index timeout: {e}")
            raise JuryMatchingServiceError(
                message="Jury re-index request timed out",
                status_code=504,
            )
        except httpx.RequestError as e:
            logger.error(f"Jury re-index connection error: {e}")
            raise JuryMatchingServiceError(
                message=f"Failed to connect to AI service for re-index: {str(e)}",
                status_code=503,
            )

    async def close(self):
        """Close the HTTP client connection."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
            logger.debug("Jury Matching client connection closed")


# Global singleton instance
jury_matching_client = JuryMatchingClient()
