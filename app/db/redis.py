# app/db/redis.py
import logging

from redis.asyncio import Redis

from app.core.config import settings

logger = logging.getLogger(__name__)

# Basic Redis client configuration
# Higher-level abstraction remains in app/services/cache.py
redis_client = Redis.from_url(
    settings.redis_url,
    encoding="utf-8",
    decode_responses=True,
    socket_connect_timeout=2,
    socket_timeout=2,
)


async def test_redis_connection():
    """Test the Redis connection."""
    try:
        await redis_client.ping()
        logger.info(f"Redis connected successfully at {settings.redis_url}")
        return True
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")
        return False
