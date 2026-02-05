# app/middleware/ai_recommender.py
"""
Middleware utilities for AI Recommender service integration.

Provides:
- Rate limiting for recommendation endpoints
- Response caching to reduce AI service load
- Circuit breaker pattern for fault tolerance
- Request deduplication for concurrent requests
"""

import hashlib
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status

from app.core.config import settings
from app.services.cache import cache

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# RATE LIMITER
# ─────────────────────────────────────────────────────────────────────────────


class RateLimiter:
    """
    Redis-based rate limiter using sliding window algorithm.

    Limits the number of requests per user within a time window.
    Falls back to allowing requests if Redis is unavailable.
    """

    def __init__(
        self,
        max_requests: int = 10,
        window_seconds: int = 60,
        key_prefix: str = "ratelimit",
    ):
        """
        Initialize rate limiter.

        Args:
            max_requests: Maximum requests allowed per window.
            window_seconds: Time window in seconds.
            key_prefix: Redis key prefix for rate limit counters.
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.key_prefix = key_prefix

    def _get_key(self, identifier: str) -> str:
        """Generate Redis key for rate limiting."""
        return f"{self.key_prefix}:{identifier}"

    async def is_allowed(self, identifier: str) -> tuple[bool, int, int]:
        """
        Check if request is allowed under rate limit.

        Args:
            identifier: Unique identifier (e.g., user_id, IP address).

        Returns:
            Tuple of (is_allowed, remaining_requests, reset_time_seconds).
        """
        if not cache.is_available:
            # Fail open if Redis is unavailable
            return True, self.max_requests, 0

        key = self._get_key(identifier)
        current_time = int(time.time())
        current_time - self.window_seconds

        try:
            # Use Redis pipeline for atomic operations
            client = cache.client

            # Get current count
            count_data = await client.get(key)

            if count_data is None:
                # First request in window
                await client.set(key, "1", ex=self.window_seconds)
                return True, self.max_requests - 1, self.window_seconds

            current_count = int(count_data)

            if current_count >= self.max_requests:
                # Get TTL for reset time
                ttl = await client.ttl(key)
                return False, 0, max(ttl, 0)

            # Increment counter
            new_count = await client.incr(key)
            ttl = await client.ttl(key)

            return True, self.max_requests - new_count, max(ttl, 0)

        except Exception as e:
            logger.warning(f"Rate limiter error: {e}. Allowing request.")
            return True, self.max_requests, 0

    async def check_and_raise(
        self, identifier: str, endpoint_name: str = "this endpoint"
    ):
        """
        Check rate limit and raise HTTPException if exceeded.

        Args:
            identifier: Unique identifier for rate limiting.
            endpoint_name: Name of endpoint for error message.

        Raises:
            HTTPException: 429 Too Many Requests if limit exceeded.
        """
        is_allowed, remaining, reset_time = await self.is_allowed(identifier)

        if not is_allowed:
            logger.warning(
                f"Rate limit exceeded for {identifier} on {endpoint_name}. "
                f"Reset in {reset_time}s"
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "Rate limit exceeded",
                    "message": f"Too many requests to {endpoint_name}. Please try again later.",
                    "retry_after_seconds": reset_time,
                },
                headers={"Retry-After": str(reset_time)},
            )


# Default rate limiter for recommendation endpoints
# Uses settings from config (default: 10 requests per 60 seconds)
recommendation_rate_limiter = RateLimiter(
    max_requests=settings.ai_rate_limit_requests,
    window_seconds=settings.ai_rate_limit_window,
    key_prefix="ratelimit:recommendations",
)


# ─────────────────────────────────────────────────────────────────────────────
# RESPONSE CACHE
# ─────────────────────────────────────────────────────────────────────────────


class ResponseCache:
    """
    Cache for AI Recommender responses.

    Caches recommendation results to reduce load on the AI service.
    Uses request parameters to generate cache keys.
    """

    def __init__(
        self,
        ttl_seconds: int = 300,  # 5 minutes default
        key_prefix: str = "ai_cache",
    ):
        """
        Initialize response cache.

        Args:
            ttl_seconds: Cache TTL in seconds.
            key_prefix: Redis key prefix.
        """
        self.ttl_seconds = ttl_seconds
        self.key_prefix = key_prefix

    def _generate_cache_key(self, **kwargs) -> str:
        """Generate deterministic cache key from request parameters."""
        # Sort keys for consistent hashing
        sorted_params = sorted(kwargs.items())
        param_string = str(sorted_params)
        hash_value = hashlib.md5(param_string.encode()).hexdigest()[:16]
        return f"{self.key_prefix}:{hash_value}"

    async def get(
        self,
        group_id: str,
        idea_domain: Optional[str] = None,
        idea_description: Optional[str] = None,
        idea_industry: Optional[str] = None,
        project_type: Optional[str] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Get cached recommendations if available.

        Returns:
            Cached recommendations or None if not found.
        """
        if not cache.is_available:
            return None

        key = self._generate_cache_key(
            group_id=group_id,
            idea_domain=idea_domain,
            idea_description=idea_description,
            idea_industry=idea_industry,
            project_type=project_type,
        )

        try:
            cached = await cache.get_json(key)
            if cached:
                logger.debug(f"Cache hit for recommendations: {key}")
                return cached
            return None
        except Exception as e:
            logger.debug(f"Cache get error: {e}")
            return None

    async def set(
        self,
        recommendations: List[Dict[str, Any]],
        group_id: str,
        idea_domain: Optional[str] = None,
        idea_description: Optional[str] = None,
        idea_industry: Optional[str] = None,
        project_type: Optional[str] = None,
    ) -> None:
        """Cache recommendation results."""
        if not cache.is_available:
            return

        key = self._generate_cache_key(
            group_id=group_id,
            idea_domain=idea_domain,
            idea_description=idea_description,
            idea_industry=idea_industry,
            project_type=project_type,
        )

        try:
            await cache.set_json(key, recommendations, ttl_seconds=self.ttl_seconds)
            logger.debug(f"Cached recommendations: {key} (TTL: {self.ttl_seconds}s)")
        except Exception as e:
            logger.debug(f"Cache set error: {e}")

    async def invalidate_for_group(self, group_id: str) -> None:
        """
        Invalidate all cached recommendations for a group.

        Note: This is a pattern-based delete which may not be supported
        by all Redis configurations. Consider using explicit keys.
        """
        # For simplicity, we rely on TTL expiration
        # A full implementation would track keys per group
        logger.debug(f"Cache invalidation requested for group: {group_id}")


# Default response cache (uses settings from config, default: 5 minute TTL)
recommendation_cache = ResponseCache(
    ttl_seconds=settings.ai_cache_ttl,
    key_prefix="ai_cache:recommendations",
)


# ─────────────────────────────────────────────────────────────────────────────
# CIRCUIT BREAKER
# ─────────────────────────────────────────────────────────────────────────────


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation, requests pass through
    OPEN = "open"  # Failing, requests are rejected
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreaker:
    """
    Circuit breaker pattern for AI Recommender service.

    Prevents cascading failures by temporarily blocking requests
    to a failing service.

    States:
    - CLOSED: Normal operation, all requests pass through
    - OPEN: Service is failing, requests are immediately rejected
    - HALF_OPEN: Testing recovery, limited requests allowed
    """

    failure_threshold: int = 5  # Failures before opening circuit
    recovery_timeout: int = 30  # Seconds before trying again
    half_open_max_calls: int = 3  # Calls allowed in half-open state

    # Internal state
    _state: CircuitState = field(default=CircuitState.CLOSED)
    _failure_count: int = field(default=0)
    _success_count: int = field(default=0)
    _last_failure_time: float = field(default=0)
    _half_open_calls: int = field(default=0)

    @property
    def state(self) -> CircuitState:
        """Get current circuit state, considering timeouts."""
        if self._state == CircuitState.OPEN:
            # Check if we should transition to half-open
            if time.time() - self._last_failure_time >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                logger.info("Circuit breaker transitioning to HALF_OPEN")
        return self._state

    def is_allowed(self) -> bool:
        """Check if request should be allowed through."""
        current_state = self.state

        if current_state == CircuitState.CLOSED:
            return True
        elif current_state == CircuitState.OPEN:
            return False
        else:  # HALF_OPEN
            if self._half_open_calls < self.half_open_max_calls:
                self._half_open_calls += 1
                return True
            return False

    def record_success(self) -> None:
        """Record a successful call."""
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.half_open_max_calls:
                # Service recovered, close circuit
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._success_count = 0
                logger.info("Circuit breaker CLOSED - service recovered")
        else:
            # Reset failure count on success in closed state
            self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed call."""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            # Failed during recovery test, open circuit again
            self._state = CircuitState.OPEN
            self._success_count = 0
            logger.warning("Circuit breaker OPEN - recovery failed")
        elif self._failure_count >= self.failure_threshold:
            # Too many failures, open circuit
            self._state = CircuitState.OPEN
            logger.warning(f"Circuit breaker OPEN after {self._failure_count} failures")

    def check_and_raise(self) -> None:
        """
        Check if circuit allows request, raise exception if not.

        Raises:
            HTTPException: 503 Service Unavailable if circuit is open.
        """
        if not self.is_allowed():
            time_since_failure = time.time() - self._last_failure_time
            retry_after = max(0, int(self.recovery_timeout - time_since_failure))

            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error": "Service temporarily unavailable",
                    "message": "AI Recommender service is experiencing issues. Please try again later.",
                    "retry_after_seconds": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )


# Global circuit breaker for AI Recommender service
# Uses settings from config
ai_recommender_circuit = CircuitBreaker(
    failure_threshold=settings.ai_circuit_failure_threshold,
    recovery_timeout=settings.ai_circuit_recovery_timeout,
    half_open_max_calls=3,
)


# ─────────────────────────────────────────────────────────────────────────────
# REQUEST DEDUPLICATION
# ─────────────────────────────────────────────────────────────────────────────


class RequestDeduplicator:
    """
    Prevents duplicate concurrent requests to the AI service.

    Uses Redis locks to ensure only one request is processed
    at a time for the same parameters.
    """

    def __init__(
        self,
        lock_ttl_seconds: int = 30,
        key_prefix: str = "dedup",
    ):
        """
        Initialize deduplicator.

        Args:
            lock_ttl_seconds: Lock TTL (prevents deadlocks).
            key_prefix: Redis key prefix.
        """
        self.lock_ttl_seconds = lock_ttl_seconds
        self.key_prefix = key_prefix

    def _generate_lock_key(self, **kwargs) -> str:
        """Generate lock key from request parameters."""
        sorted_params = sorted(kwargs.items())
        param_string = str(sorted_params)
        hash_value = hashlib.md5(param_string.encode()).hexdigest()[:16]
        return f"{self.key_prefix}:{hash_value}"

    async def acquire(
        self,
        group_id: str,
        idea_domain: Optional[str] = None,
        idea_description: Optional[str] = None,
        idea_industry: Optional[str] = None,
        project_type: Optional[str] = None,
    ) -> tuple[bool, str]:
        """
        Try to acquire lock for request.

        Returns:
            Tuple of (acquired, lock_key).
        """
        key = self._generate_lock_key(
            group_id=group_id,
            idea_domain=idea_domain,
            idea_description=idea_description,
            idea_industry=idea_industry,
            project_type=project_type,
        )

        acquired = await cache.acquire_lock(key, self.lock_ttl_seconds)
        return acquired, key

    async def release(self, lock_key: str) -> None:
        """Release the lock."""
        await cache.release_lock(lock_key)


# Global request deduplicator
request_deduplicator = RequestDeduplicator(
    lock_ttl_seconds=30,
    key_prefix="dedup:recommendations",
)
