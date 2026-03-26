from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings

MONGO_URI = settings.mongo_uri
MONGO_DB_NAME = settings.mongo_db_name

mongo_client = AsyncIOMotorClient(MONGO_URI)
mongo_db = mongo_client[MONGO_DB_NAME]


async def get_mongo_db() -> AsyncIOMotorDatabase:
    """FastAPI dependency that yields the Motor database instance."""
    yield mongo_db
