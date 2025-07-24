# app/main.py

from pathlib import Path

from dotenv import load_dotenv

# Load .env (override any existing OS env vars)
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path, override=True)

import logging

import uvicorn
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.cors import CORSMiddleware

from app.api.http.health import router as health_router
from app.api.http.router import router as api_router  # includes users, groups, etc.
from app.auth.routes import router as auth_router  # your signup/login endpoints
from app.core.exceptions import register_exception_handlers
from app.db import AsyncSessionLocal, Base, engine  # async engine & session

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

# Mount routers
app.include_router(health_router, prefix="")  # GET /health
app.include_router(auth_router, prefix="/auth")  # POST /auth/signup, /auth/login
app.include_router(api_router, prefix="/api")  # e.g. /api/groups, /api/users, etc.

# Global exception handlers
register_exception_handlers(app)


@app.on_event("startup")
async def on_startup():
    # 1) Create all tables if they don’t exist (async)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 2) Quick connectivity check
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        logger.info("Database connected successfully.")
    except SQLAlchemyError as e:
        logger.error(f"Database connection failed: {e}")


if __name__ == "__main__":
    # Local dev
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
