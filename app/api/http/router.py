# app/api/http/router.py
from fastapi import APIRouter

from app.api.http.group import router as group_router

# Import each feature’s router
from app.api.http.health import router as health_router

# Create a “master” router that mounts all HTTP routers
router = APIRouter()

# Mount them under their prefixes
router.include_router(health_router, prefix="/health", tags=["health"])

router.include_router(group_router, tags=["groups"])
