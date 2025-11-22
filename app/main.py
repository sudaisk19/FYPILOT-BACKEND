# app/main.py

from pathlib import Path

from dotenv import load_dotenv

# Load .env (override any existing OS env vars)
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path, override=True)

import logging

import uvicorn
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware  # ← NEW

from app.api.http.router import (
    router as api_router,  # includes users, groups, health, etc.
)
from app.auth.routes import router as auth_router  # your signup/login endpoints
from app.core.config import settings  # ← NEW (for session_secret)
from app.core.exceptions import register_exception_handlers
from app.db import AsyncSessionLocal, Base, engine  # async engine & session
from app.services.cache import cache  # Redis cache

# Configure logger
logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="FYPilot Backend")

# CORS origins
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://fypilot-frontend.vercel.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3) Sessions (required for OAuth state and any server-side session usage)
#    NOTE: requires `itsdangerous` to be installed.
is_production = str(
    getattr(settings, "ENV", getattr(settings, "environment", "development"))
).lower() in {"prod", "production"}
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,  # from .env -> SESSION_SECRET
    same_site="lax",
    https_only=is_production,  # True when you serve over HTTPS in prod
    max_age=60 * 60 * 24 * 30,  # 30 days
    session_cookie="fyp_session",
)

# Mount routers
app.include_router(
    auth_router, prefix="/auth"
)  # /auth/login, /auth/signup, /auth/oauth/...
app.include_router(
    api_router, prefix="/api"
)  # /api/groups, /api/users, /api/students, /api/supervisors, /api/admins, /health

# Global exception handlers
register_exception_handlers(app)


@app.on_event("startup")
async def on_startup():
    # 1) Create all tables if they don't exist (async)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created/verified successfully.")
        logger.info("Database connection verified through table creation.")
    except Exception as e:
        logger.error(f"Database table creation failed: {e}")
        # Don't fail startup for table creation issues

    # Note: Skipping additional connection test to avoid prepared statement issues
    # The table creation above already proves the database connection works

    # 2) Initialize Redis cache connection
    await cache.connect()


@app.on_event("shutdown")
async def on_shutdown():
    # Gracefully close Redis connection
    await cache.disconnect()


if __name__ == "__main__":
    # Local dev
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
