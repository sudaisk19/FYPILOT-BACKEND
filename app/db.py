# app/db.py

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

# — SQLAlchemy Async Setup —
# Uses asyncpg under the hood; your DATABASE_URL must start with "postgresql+asyncpg://"
engine = create_async_engine(
    settings.database_url,
    future=True,  # SQLAlchemy 2.0 style
    echo=True,  # log SQL to console
)

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
