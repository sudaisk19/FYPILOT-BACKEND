# app/services/cache.py
from __future__ import annotations

import json
import logging
from typing import Any, Optional

try:
    from redis.asyncio import Redis  # type: ignore
    from redis.exceptions import ConnectionError as RedisConnectionError  # type: ignore

    _HAS_REDIS = True
except Exception:  # pragma: no cover
    Redis = None  # type: ignore
    RedisConnectionError = Exception  # type: ignore
    _HAS_REDIS = False

from app.core.config import settings

logger = logging.getLogger(__name__)


class Cache:
    def __init__(self, url: Optional[str] = None):
        self._client: Optional[Redis] = None
        self._url: str = url or settings.redis_url
        self._is_connected: bool = False
        if _HAS_REDIS:
            # socket_timeout must exceed longest blocking Redis command (e.g. BRPOP
            # timeout=5 in collaborative_chat_worker); a 2s read timeout causes false
            # TimeoutError on idle queues.
            self._client = Redis.from_url(
                self._url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=30,
                retry_on_timeout=False,
            )  # type: ignore
        else:
            logger.warning(
                "Redis package not installed. Caching will be disabled. "
                "Install with: pip install redis"
            )

    @property
    def client(self) -> Redis:
        if not self._client:
            raise RuntimeError(
                "Redis client not available - install 'redis' or configure REDIS_URL"
            )
        return self._client

    @property
    def is_available(self) -> bool:
        """Check if Redis is available and connected."""
        return self._is_connected and self._client is not None

    async def connect(self) -> bool:
        """Test Redis connection and initialize if needed."""
        if not _HAS_REDIS:
            logger.warning("Redis not available - caching disabled")
            return False

        if not self._client:
            self._client = Redis.from_url(
                self._url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=30,
                retry_on_timeout=False,
            )

        try:
            # Test connection with a simple ping
            await self._client.ping()
            self._is_connected = True
            logger.info(f"✅ Redis connected successfully at {self._url}")
            return True
        except RedisConnectionError as e:
            self._is_connected = False
            logger.warning(
                f"⚠️ Redis connection failed at {self._url}: {e}. "
                "Caching will be disabled. The app will continue to work without cache."
            )
            return False
        except Exception as e:
            self._is_connected = False
            logger.warning(f"⚠️ Redis connection error: {e}. Caching will be disabled.")
            return False

    async def disconnect(self) -> None:
        """Gracefully close Redis connection."""
        if self._client:
            try:
                await self._client.close()
                self._is_connected = False
                logger.info("Redis connection closed")
            except Exception as e:
                logger.warning(f"Error closing Redis connection: {e}")

    async def get_json(self, key: str) -> Optional[Any]:
        if not self._is_connected or not self._client:
            return None
        try:
            data = await self._client.get(key)
            if data is None:
                return None
            return json.loads(data)
        except Exception as e:
            logger.debug(f"Cache get error for key '{key}': {e}")
            return None

    async def set_json(self, key: str, value: Any, ttl_seconds: int = 900) -> None:
        if not self._is_connected or not self._client:
            return
        try:
            payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            await self._client.set(key, payload, ex=ttl_seconds)
        except Exception as e:
            logger.debug(f"Cache set error for key '{key}': {e}")

    async def delete(self, key: str) -> None:
        """Delete a key from cache."""
        if not self._is_connected or not self._client:
            return
        try:
            await self._client.delete(key)
        except Exception as e:
            logger.debug(f"Cache delete error for key '{key}': {e}")

    async def acquire_lock(self, key: str, ttl_seconds: int = 30) -> bool:
        if not self._is_connected or not self._client:
            return True
        try:
            return (
                await self._client.set(name=key, value="1", nx=True, ex=ttl_seconds)
                is True
            )
        except Exception as e:
            logger.debug(f"Cache lock error for key '{key}': {e}")
            return True  # Fail open

    async def release_lock(self, key: str) -> None:
        if not self._is_connected or not self._client:
            return
        try:
            await self._client.delete(key)
        except Exception as e:
            logger.debug(f"Cache lock release error for key '{key}': {e}")


cache = Cache()
