# app/main.py

from pathlib import Path

from dotenv import load_dotenv

# Load .env (override any existing OS env vars)
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path, override=True)

import asyncio
import logging

import uvicorn
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware  # ← NEW

from app.api.http import llm_chat
from app.api.http.router import (
    router as api_router,  # includes users, groups, health, etc.
)
from app.auth.routes import router as auth_router  # your signup/login endpoints
from app.core.config import settings  # ← NEW (for session_secret)
from app.core.exceptions import register_exception_handlers
from app.db import AsyncSessionLocal, Base, engine  # async engine & session
from app.services.cache import cache  # Redis cache
from app.services.jury_matching_client import (  # Jury Matching HTTP client
    jury_matching_client,
)
from app.services.student_lifecycle_scheduler import (
    create_scheduler,
    run_student_lifecycle_job,
)
from app.services.supervisor_recommendation_client import (  # Supervisor Recommendation HTTP client
    supervisor_recommendation_client,
)

# Configure logger
logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="FYPilot Backend")

# Initialize Scheduler
scheduler = create_scheduler()

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
app.include_router(llm_chat.router, prefix="/llm")

# Global exception handlers
register_exception_handlers(app)


@app.on_event("startup")
async def on_startup():
    """Fast startup - don't block on database operations."""
    logger.info("Application starting...")

    # Initialize Redis cache connection (non-blocking with timeout)
    # If Redis fails, app will continue without cache
    try:
        # Add 3 second timeout to prevent blocking startup
        redis_ok = await asyncio.wait_for(cache.connect(), timeout=3.0)
        if redis_ok:
            logger.info("✅ Redis cache connected and ready.")
        else:
            logger.warning("⚠️ Redis not available. App will run without caching.")
    except asyncio.TimeoutError:
        logger.warning(
            "Redis connection timed out during startup. "
            "App will continue without cache. Caching will be disabled."
        )
    except Exception as e:
        logger.warning(
            f"Redis connection failed during startup: {e}. "
            "App will continue without cache. Caching will be disabled."
        )

    # Database tables will be created automatically on first use via SQLAlchemy
    # Or you can run migrations separately. This ensures fast startup.
    logger.info("Application startup complete. Database will connect on first use.")

    # Optional: Test database connection in background (non-blocking)
    # This helps identify connection issues early without blocking startup
    async def test_db_connection():
        try:
            from sqlalchemy import text

            async with engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("✅ Database connection verified successfully.")
        except Exception as e:
            logger.error(f"⚠️ Database connection test failed: {e}")
            logger.warning("Database will be retried on first request.")

    # Run database test in background (fire and forget)
    asyncio.create_task(test_db_connection())

    # Start the background scheduler
    try:
        scheduler.start()
        logger.info("✅ Student lifecycle scheduler started.")
        # Run the deactivation job once on startup to catch up
        asyncio.create_task(run_student_lifecycle_job())
    except Exception as e:
        logger.error(f"❌ Failed to start scheduler: {e}")


@app.on_event("shutdown")
async def on_shutdown():
    # Gracefully close Redis connection
    await cache.disconnect()

    # Close Supervisor Recommendation HTTP client
    await supervisor_recommendation_client.close()

    # Close Jury Matching HTTP client
    await jury_matching_client.close()

    # Shutdown scheduler
    scheduler.shutdown()
    logger.info("Student lifecycle scheduler shut down.")

    logger.info("Application shutdown complete.")


if __name__ == "__main__":
    # Local dev
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
