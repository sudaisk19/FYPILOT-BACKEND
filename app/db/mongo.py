import os

from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "fypilot")

mongo_client = AsyncIOMotorClient(MONGO_URI)
mongo_db = mongo_client[MONGO_DB_NAME]
