# app/db/supabase.py
from supabase import create_client

from app.core.config import settings

# Initialize Supabase SDK client
supabase = create_client(
    settings.supabase_url,
    settings.supabase_key,
)
