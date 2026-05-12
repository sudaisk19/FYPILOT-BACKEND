# app/main.py

from pathlib import Path

from dotenv import load_dotenv

from app.logging_setup import configure_logging

# Load .env (override any existing OS env vars)
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path, override=True)

configure_logging()

import asyncio
import logging

import uvicorn
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
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
from app.middleware.request_logging import RequestLoggingMiddleware
from app.middleware.whiteboard_patch_size_limit import (
    WhiteboardPatchContentSizeLimitMiddleware,
)
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


def _is_testing_env() -> bool:
    return str(getattr(settings, "ENV", "") or "").lower() in {"testing", "test"}


app = FastAPI(title="FYPilot Backend")
Instrumentator().instrument(app).expose(app)

# Initialize Scheduler
scheduler = create_scheduler()

# CORS origins — include both hostname styles for dev (localhost vs 127.0.0.1).
# Browser Origin must match exactly (e.g. page on localhost:3000 vs API on 127.0.0.1:8000).
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://fypilot-frontend.vercel.app",
    # Add your new production domains below:
    "http://fypilot.tech",
    "https://fypilot.tech",
    "http://www.fypilot.tech",
    "https://www.fypilot.tech",
    "http://168.144.90.160",  # Optional: Helpful if you are testing via direct IP
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # includes GET (required for GET /api/chat/stream SSE)
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

app.add_middleware(WhiteboardPatchContentSizeLimitMiddleware)

# Request logging wraps the app so it can record request metadata and timing.
app.add_middleware(RequestLoggingMiddleware)

# Mount routers
app.include_router(
    auth_router, prefix="/auth"
)  # /auth/login, /auth/signup, /auth/oauth/...
app.include_router(api_router, prefix="/api")  # /api/groups, /api/users, …, /api/health
app.include_router(llm_chat.router, prefix="/llm")

# ── WebSocket routers (no /api prefix — WS uses ?token= for auth) ────────────
from app.api.websocket import chat as ws_chat
from app.api.websocket import document as ws_document

app.include_router(ws_chat.router)
app.include_router(ws_document.router)

# Global exception handlers
register_exception_handlers(app)


@app.on_event("startup")
async def on_startup():
    """Fast startup - don't block on database operations."""
    logger.info("Application starting...")

    # Initialize Redis cache connection (non-blocking with timeout)
    # If Redis fails, app will continue without cache
    redis_ok = False
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

    if redis_ok and not _is_testing_env():
        from app.api.websocket.manager import start_redis_ws_subscriber
        from app.services.chat_sse_hub import start_chat_sse_redis_subscriber

        start_redis_ws_subscriber()
        start_chat_sse_redis_subscriber()

    from app.db.mongo import mongo_db
    from app.repositories.chat_session_repository import chat_session_repo
    from app.services.collaborative_chat_worker import start_chat_workers

    if not _is_testing_env():
        try:
            await chat_session_repo.ensure_indexes(mongo_db)
            logger.info("MongoDB chat message indexes ensured.")
            from app.repositories.document_edit_proposal_repository import (
                document_edit_proposal_repo,
            )

            await document_edit_proposal_repo.ensure_indexes(mongo_db)
            logger.info("MongoDB document_edit_proposals indexes ensured.")
        except Exception as e:
            logger.warning("MongoDB chat index ensure failed (non-fatal): %s", e)

        start_chat_workers()

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

    # Start the background scheduler (skip under pytest / TestClient — shared loop issues)
    if not _is_testing_env():
        try:
            scheduler.start()
            logger.info("✅ Student lifecycle scheduler started.")
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

    # Shutdown scheduler (TestClient teardown can close the loop before this runs)
    try:
        if getattr(scheduler, "running", False):
            scheduler.shutdown()
            logger.info("Student lifecycle scheduler shut down.")
    except RuntimeError:
        logger.debug("Scheduler shutdown skipped (event loop already closed)")

    logger.info("Application shutdown complete.")


if __name__ == "__main__":
    # Local dev
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
