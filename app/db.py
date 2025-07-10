# app/db.py

from sqlalchemy import create_engine  # SQLAlchemy ka engine bananay ke liye import
from sqlalchemy.orm import sessionmaker, declarative_base  # Session factory aur Base class ke liye import
from supabase import create_client  # Supabase client bananay ke liye import
from app.core.config import settings  # .env se settings load karne ke liye import

# --- SQLAlchemy Setup ---
# Engine create karo jo database se connect karega
engine = create_engine(
    settings.database_url,  # settings se database URL fetch hota hai
    future=True,  # SQLAlchemy 2.0 behavior use karne ke liye
)

# SessionLocal ek factory hai jo nayi Session objects banaye gi
SessionLocal = sessionmaker(
    autocommit=False,  # session.commit() explicitly call karna padega
    autoflush=False,  # changes flush nahi honge jab tak commit na karo
    bind=engine,  # kis engine se bind karna hai
)

# Base ek declarative base class hai jise sab ORM models extend karte hain
Base = declarative_base()

# --- Supabase SDK Setup ---
# Supabase client initialize karo, jisse aap CRUD operations aur auth kar sakte ho
supabase = create_client(
    settings.supabase_url,  # env se Supabase project URL
    settings.supabase_key,  # env se Supabase anon/public key
)
