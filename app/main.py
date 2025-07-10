# app/main.py
from pathlib import Path

from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path, override=True)  # ← this will replace any existing DATABASE_URL
import logging

import uvicorn
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.db import SessionLocal  # SQLAlchemy session factory

# Configure Python’s built-in logger (uvicorn uses this under the hood)
logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="FYPilot Backend")

# CORS settings: allow your local Next.js dev & deployed frontend
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://fypilot-frontend.vercel.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # permitted origins
    allow_credentials=True,  # allow cookies, Authorization headers
    allow_methods=["*"],  # GET, POST, PUT, DELETE, etc.
    allow_headers=["*"],  # allow all headers
)

# Mount your HTTP routers
app.include_router(health_router, prefix="")  # GET /health


# Mount your WebSocket router (if you have one)
# app.include_router(ws_router, prefix="/ws", tags=["WebSocket"])


@app.on_event("startup")
def check_db_connection():
    """
    Fired once, at application startup.
    Attempts a dummy SELECT 1; logs success or failure.
    """
    try:
        db = SessionLocal()
        # This executes a no-op query just to verify connectivity
        db.execute(text("SELECT 1"))
        logger.info("✅ Database connected successfully.")
    except SQLAlchemyError as e:
        logger.error(f"❌ Database connection failed: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    # For local development:
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

# For production, you can run:
# uvicorn app.main:app --host 0.0.0.0 --port 8000
