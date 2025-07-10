# app/core/config.py

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    supabase_url: str
    supabase_key: str
    jwt_secret: str
    jwt_algorithm: str = "HS256"

    # Pydantic v2 way to load an .env
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


# this will now pull from DATABASE_URL, SUPABASE_URL, etc.
settings = Settings()
# If you need to access the settings in other parts of your app, you can import it like this:
# from app.core.config import settings
