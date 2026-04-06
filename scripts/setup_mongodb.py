import asyncio
import os

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import CollectionInvalid, OperationFailure

# Load environment variables from .env file
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = os.getenv("MONGO_DB_NAME", "fyp_db")


async def _try_coll_mod_validator(db, collection_name: str, validator: dict) -> bool:
    """
    Update collection JSON Schema. Many Atlas database users only have readWrite and
    cannot run collMod — in that case we skip and still create indexes below.
    """
    try:
        await db.command({"collMod": collection_name, "validator": validator})
        return True
    except OperationFailure as e:
        print(
            f"Note: skipped validator update for '{collection_name}' ({e}). "
            "Grant dbAdmin (or use Atlas UI / a user with collMod) if you need schema enforcement."
        )
        return False


async def setup_database():
    print(f"Connecting to MongoDB Atlas at {MONGO_URI[:30]}...")
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]

    # ============================================================
    # 1. document_chat_sessions (WORKSPACE MODEL UPDATE)
    # ============================================================
    session_validator = {
        "$jsonSchema": {
            "bsonType": "object",
            # Removed 'document_id' from required fields
            "required": [
                "_id",
                "group_id",
                "title",
                "created_by",
                "is_active",
                "created_at",
                "updated_at",
            ],
            "properties": {
                "_id": {"bsonType": "string"},
                "group_id": {"bsonType": "string"},
                # CHANGED: Now an array of Postgres document IDs
                "document_ids": {"bsonType": "array", "items": {"bsonType": "string"}},
                "title": {"bsonType": "string"},
                "created_by": {"bsonType": "string"},
                "is_active": {"bsonType": "bool"},
                "tags": {"bsonType": "array", "items": {"bsonType": "string"}},
                "created_at": {"bsonType": "date"},
                "updated_at": {"bsonType": "date"},
            },
        }
    }

    try:
        await db.create_collection(
            "document_chat_sessions", validator=session_validator
        )
        print("Created 'document_chat_sessions' collection.")
    except CollectionInvalid:
        if await _try_coll_mod_validator(
            db, "document_chat_sessions", session_validator
        ):
            print("Updated validator for existing 'document_chat_sessions' collection.")

    # --- Index Management ---

    # Safely drop the old unique index if it exists from previous runs
    try:
        await db.document_chat_sessions.drop_index("document_id_1")
        print("Dropped old UNIQUE index on 'document_id'.")
    except OperationFailure:
        pass  # Index doesn't exist, which is fine

    # Create Updated Indexes
    await db.document_chat_sessions.create_index([("group_id", ASCENDING)])
    await db.document_chat_sessions.create_index(
        [("group_id", ASCENDING), ("is_active", ASCENDING)]
    )
    await db.document_chat_sessions.create_index(
        [("group_id", ASCENDING), ("updated_at", DESCENDING)]
    )

    # NEW: Create a multi-key index on the array to easily find sessions by a specific document
    await db.document_chat_sessions.create_index([("document_ids", ASCENDING)])

    # ============================================================
    # 2. document_chat_messages
    # ============================================================
    message_validator = {
        "$jsonSchema": {
            "bsonType": "object",
            "required": [
                "chat_session_id",
                "sender_id",
                "sender_type",
                "content",
                "is_complete",
                "read_by",
                "created_at",
            ],
            "properties": {
                "chat_session_id": {"bsonType": "string"},
                "sender_id": {"bsonType": "string"},
                "sender_type": {"enum": ["student", "llm", "system"]},
                "content": {"bsonType": "string"},
                "is_complete": {"bsonType": "bool"},
                # doc_context will now hold { "active_document_id": "...", "version_number": ... }
                "doc_context": {"bsonType": ["object", "null"]},
                "read_by": {"bsonType": "array", "items": {"bsonType": "string"}},
                "metadata": {"bsonType": "object"},
                "created_at": {"bsonType": "date"},
                # Collaborative chat / SSE (optional on older documents)
                "sender_name": {"bsonType": "string"},
                "request_id": {"bsonType": "string"},
            },
        }
    }

    try:
        await db.create_collection(
            "document_chat_messages", validator=message_validator
        )
        print("Created 'document_chat_messages' collection.")
    except CollectionInvalid:
        if await _try_coll_mod_validator(
            db, "document_chat_messages", message_validator
        ):
            print("Updated validator for existing 'document_chat_messages' collection.")

    # Create Indexes for Messages
    await db.document_chat_messages.create_index(
        [("chat_session_id", ASCENDING), ("_id", DESCENDING)]
    )
    # Matches ChatSessionRepository.ensure_indexes (cursor history after _id)
    await db.document_chat_messages.create_index(
        [("chat_session_id", ASCENDING), ("_id", ASCENDING)],
        name="idx_chat_messages_session_id",
    )
    await db.document_chat_messages.create_index(
        [("chat_session_id", ASCENDING), ("is_complete", ASCENDING)]
    )

    # Updated to index the new doc_context structure
    await db.document_chat_messages.create_index(
        [("doc_context.active_document_id", ASCENDING)], sparse=True
    )
    await db.document_chat_messages.create_index(
        [("chat_session_id", ASCENDING), ("sender_type", ASCENDING)]
    )

    print(
        "\nDatabase setup complete! Indexes ensured; validators updated only if collMod was allowed."
    )
    client.close()


if __name__ == "__main__":
    asyncio.run(setup_database())
