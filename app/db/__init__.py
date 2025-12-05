# app/db/__init__.py

import logging

from sqlalchemy.ext.asyncio import (  # Async engine & session
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.orm import (  # Base class & session factory
    declarative_base,
    sessionmaker,
)
from supabase import create_client  # Supabase client

from app.core.config import settings  # loads DATABASE_URL, etc.

# Configure logging
logger = logging.getLogger(__name__)

# — SQLAlchemy Async Setup —
# For Supabase/pgbouncer compatibility, we need to use asyncpg with proper configuration

# Get the original database URL
original_url = settings.database_url

# Validate DATABASE_URL is not empty
if not original_url or not original_url.strip():
    raise ValueError(
        "DATABASE_URL is empty or not set. "
        "Please set DATABASE_URL environment variable."
    )

logger.info(f"Original database URL: {original_url[:50]}...")

# Convert to asyncpg format and add statement cache size parameter
try:
    if original_url.startswith("postgresql://"):
        # Replace with asyncpg driver
        database_url = original_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif original_url.startswith("postgresql+asyncpg://"):
        database_url = original_url
    elif original_url.startswith("postgres://"):
        # Handle postgres:// (alternative format used by some providers)
        database_url = original_url.replace("postgres://", "postgresql+asyncpg://", 1)
    else:
        raise ValueError(
            f"DATABASE_URL must start with postgresql://, postgres://, or postgresql+asyncpg://. "
            f"Got: {original_url[:100]}..."
        )
except Exception as e:
    logger.error(f"Error parsing DATABASE_URL: {e}")
    raise

# Configure for Supabase session pooler
if "pooler.supabase.com" in database_url:
    # Session pooler configuration - use port 5432 and disable prepared statements
    logger.info("Using Supabase session pooler configuration")
    if "?" in database_url:
        database_url += "&statement_cache_size=0"
    else:
        database_url += "?statement_cache_size=0"
elif "db." in database_url and ".supabase.co:5432" in database_url:
    # Direct connection - add statement_cache_size parameter
    if "?" in database_url:
        database_url += "&statement_cache_size=0"
    else:
        database_url += "?statement_cache_size=0"
else:
    # Add statement_cache_size parameter to the URL to disable prepared statements
    if "?" in database_url:
        database_url += "&statement_cache_size=0"
    else:
        database_url += "?statement_cache_size=0"

logger.info(f"Using database URL: {database_url[:50]}...")

# Create engine with asyncpg and session pooler-compatible settings
engine = create_async_engine(
    database_url,
    future=True,  # SQLAlchemy 2.0 style
    echo=True,  # log SQL to console
    connect_args={
        "statement_cache_size": 0,  # Disable prepared statements for session pooler
        "server_settings": {
            "jit": "off",  # Disable JIT compilation
            "application_name": "fypilot_backend",
        },
        "command_timeout": 10,  # 10 second command timeout for asyncpg
    },
    # Session pooler handles connection pooling, so use minimal SQLAlchemy pooling
    pool_pre_ping=True,  # Verify connections before use
    pool_recycle=300,  # Recycle connections every 5 minutes
    pool_size=3,  # Smaller pool size since session pooler handles pooling
    max_overflow=5,  # Reduced overflow for session pooler
    pool_timeout=10,  # 10 second timeout for getting connection from pool
)


# Test the connection to ensure it works with session pooler
async def test_connection():
    """Test the database connection to ensure it works with session pooler"""
    try:
        async with engine.begin() as conn:
            await conn.execute("SELECT 1")
        logger.info("Database connection test successful")
        return True
    except Exception as e:
        logger.error(f"Database connection test failed: {e}")
        return False


AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

Base = declarative_base()

# — Supabase SDK Setup —
supabase = create_client(
    settings.supabase_url,
    settings.supabase_key,
)


# Dependency for FastAPI routes
async def get_db():
    """
    Provide a transactional AsyncSession for each request.
    Use with: Depends(get_db)
    """
    async with AsyncSessionLocal() as session:
        yield session
