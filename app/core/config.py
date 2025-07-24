# app/core/config.py

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ─── Core DB & Auth Settings ─────────────────────────────
    database_url: str  # from DATABASE_URL
    supabase_url: str  # from SUPABASE_URL
    supabase_key: str  # from SUPABASE_KEY
    jwt_secret: str  # from JWT_SECRET
    jwt_algorithm: str = "HS256"  # default or from JWT_ALGORITHM
    ENV: str = "development"  # overrides to "production"

    # ─── Mailer Settings ────────────────────────────────────
    mailer_provider: str = "ethereal"  # either "ethereal" or "sendgrid"

    # Ethereal (dev SMTP)
    ethereal_smtp_host: str  # from ETHEREAL_SMTP_HOST
    ethereal_smtp_port: int  # from ETHEREAL_SMTP_PORT
    ethereal_smtp_user: str  # from ETHEREAL_SMTP_USER
    ethereal_smtp_pass: str  # from ETHEREAL_SMTP_PASS

    # # SendGrid (prod API)
    # sendgrid_api_key: str | None = None # from SENDGRID_API_KEY
    # from_email: str | None = None       # from FROM_EMAIL

    # # ─── Frontend URL ───────────────────────────────────────
    # frontend_url: str                   # from FRONTEND_URL

    # Pydantic v2 way to load an .env
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


# instantiate for import elsewhere
settings = Settings()
