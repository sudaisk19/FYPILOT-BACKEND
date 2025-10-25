#!/usr/bin/env python3
"""
Test script for Supabase session pooler connection
"""
import asyncio

import asyncpg
from sqlalchemy.ext.asyncio import create_async_engine


async def test_session_pooler():
    """Test connection to Supabase session pooler"""

    # Your session pooler URL (replace [YOUR-PASSWORD] with actual password)
    database_url = "postgresql://postgres.nnwwlxptgkrrmlvlnrxv:[YOUR-PASSWORD]@aws-0-ap-south-1.pooler.supabase.com:5432/postgres"

    print("Testing Supabase Session Pooler Connection...")
    print(f"URL: {database_url[:50]}...")

    try:
        # Test 1: Direct asyncpg connection
        print("\n1. Testing direct asyncpg connection...")
        parsed_url = database_url.replace("postgresql://", "")
        # Extract components
        auth_part, host_part = parsed_url.split("@")
        user, password = auth_part.split(":")
        host_port, db = host_part.split("/")
        host, port = host_port.split(":")

        conn = await asyncpg.connect(
            host=host,
            port=int(port),
            user=user,
            password=password,
            database=db,
            statement_cache_size=0,  # Disable prepared statements
            server_settings={"jit": "off", "application_name": "test_session_pooler"},
        )

        result = await conn.fetchval("SELECT 1")
        print(f"✅ Direct connection successful: {result}")
        await conn.close()

        # Test 2: SQLAlchemy async engine
        print("\n2. Testing SQLAlchemy async engine...")
        asyncpg_url = database_url.replace("postgresql://", "postgresql+asyncpg://")
        if "?" in asyncpg_url:
            asyncpg_url += "&statement_cache_size=0"
        else:
            asyncpg_url += "?statement_cache_size=0"

        engine = create_async_engine(
            asyncpg_url,
            future=True,
            echo=False,
            connect_args={
                "statement_cache_size": 0,
                "server_settings": {
                    "jit": "off",
                    "application_name": "test_session_pooler",
                },
            },
            pool_pre_ping=True,
            pool_recycle=300,
            pool_size=3,
            max_overflow=5,
        )

        async with engine.begin() as conn:
            result = await conn.execute("SELECT 1")
            print(f"✅ SQLAlchemy engine successful: {result.scalar()}")

        await engine.dispose()
        print("\n🎉 All tests passed! Session pooler is working correctly.")

    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False

    return True


if __name__ == "__main__":
    asyncio.run(test_session_pooler())
