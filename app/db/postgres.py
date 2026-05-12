# app/db/postgres.py
import logging
from time import perf_counter

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.orm import (
    declarative_base,
    sessionmaker,
)

from app.core.config import settings
from app.metrics import observe_db_query

logger = logging.getLogger(__name__)

# — SQLAlchemy Async Setup —
original_url = settings.database_url

if not original_url or not original_url.strip():
    raise ValueError("DATABASE_URL is not set.")

# Convert to asyncpg format
if original_url.startswith("postgresql://"):
    database_url = original_url.replace("postgresql://", "postgresql+asyncpg://", 1)
elif original_url.startswith("postgres://"):
    database_url = original_url.replace("postgres://", "postgresql+asyncpg://", 1)
else:
    database_url = original_url

# Configure for Supabase session pooler (disable prepared statements)
if any(x in database_url for x in ["pooler.supabase.com", "db.", ".supabase.co:5432"]):
    if "?" in database_url:
        database_url += "&statement_cache_size=0"
    else:
        database_url += "?statement_cache_size=0"

engine = create_async_engine(
    database_url,
    future=True,
    echo=True,
    connect_args={
        "statement_cache_size": 0,
        "server_settings": {
            "jit": "off",
            "application_name": "fypilot_backend",
        },
        "command_timeout": 30,
    },
    pool_pre_ping=True,
    pool_recycle=180,
    # Parallel browser tabs + endpoints that stack Depends(get_db) can exhaust small pools.
    # Supabase session pooler also caps concurrent clients; use Transaction mode if needed.
    pool_size=15,
    max_overflow=25,
    pool_timeout=45,
)


@event.listens_for(engine.sync_engine, "before_cursor_execute")
def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    context._query_start_time = perf_counter()


@event.listens_for(engine.sync_engine, "after_cursor_execute")
def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    start_time = getattr(context, "_query_start_time", None)
    if start_time is None:
        return
    observe_db_query(statement, perf_counter() - start_time)


AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

Base = declarative_base()


async def get_db():
    """Provides a transactional AsyncSession for each request."""
    async with AsyncSessionLocal() as session:
        yield session


async def test_connection():
    """Test the database connection."""
    try:
        async with engine.begin() as conn:
            await conn.execute("SELECT 1")
        logger.info("Database connection test successful")
        return True
    except Exception as e:
        logger.error(f"Database connection test failed: {e}")
        return False
