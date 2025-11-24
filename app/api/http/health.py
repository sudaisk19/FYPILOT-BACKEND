# app/api/health.py
from fastapi import APIRouter

from app.services.cache import cache

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint that includes Redis status."""
    redis_status = "connected" if cache.is_available else "disconnected"
    return {
        "status": "ok",
        "redis": redis_status,
    }
