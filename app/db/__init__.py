# app/db/__init__.py
"""
Database Initialization Module
Exports core database connections (Postgres, MongoDB, Redis, Supabase).
"""

from .mongo import get_mongo_db, mongo_db
from .postgres import AsyncSessionLocal, Base, engine, get_db, test_connection
from .redis import redis_client
from .supabase import get_supabase_client, supabase

__all__ = [
    "Base",
    "engine",
    "AsyncSessionLocal",
    "get_db",
    "test_connection",
    "supabase",
    "get_supabase_client",
    "mongo_db",
    "get_mongo_db",
    "redis_client",
]
