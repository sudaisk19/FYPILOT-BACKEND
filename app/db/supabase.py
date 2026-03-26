from supabase import Client, create_client

from app.core.config import settings

# Initialize Supabase SDK client
supabase: Client = create_client(
    settings.supabase_url,
    settings.supabase_key,
)


def get_supabase_client() -> Client:
    """Dependency for providing the Supabase client."""
    return supabase
