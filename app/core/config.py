# app/core/config.py
from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ─── Core DB & Auth Settings ─────────────────────────────
    database_url: str  # DATABASE_URL
    supabase_url: str  # SUPABASE_URL
    supabase_key: str  # SUPABASE_KEY
    jwt_secret: str  # JWT_SECRET
    jwt_algorithm: str = "HS256"
    ENV: str = "development"

    # ─── Mailer Settings ────────────────────────────────────
    mailer_provider: str = "mailtrap"

    # # Ethereal settings (optional - for backward compatibility)
    # ethereal_smtp_host: str | None = None  # ETHEREAL_SMTP_HOST
    # ethereal_smtp_port: int | None = None  # ETHEREAL_SMTP_PORT
    # ethereal_smtp_user: str | None = None  # ETHEREAL_SMTP_USER
    # ethereal_smtp_pass: str | None = None  # ETHEREAL_SMTP_PASS

    # Mailtrap settings
    mailtrap_smtp_host: str = "sandbox.smtp.mailtrap.io"  # MAILTRAP_SMTP_HOST
    mailtrap_smtp_port: int = 2525  # MAILTRAP_SMTP_PORT
    mailtrap_smtp_user: str  # MAILTRAP_SMTP_USER
    mailtrap_smtp_pass: str  # MAILTRAP_SMTP_PASS

    # ─── Frontend / OAuth Settings ──────────────────────────
    frontend_app_url: AnyHttpUrl = "http://localhost:3000"  # Frontend app URL
    oauth_redirect_origin: AnyHttpUrl = (
        "http://127.0.0.1:8000"  # Backend API URL for OAuth callbacks
    )

    # Required by SessionMiddleware (for OAuth state cookies)
    session_secret: str  # SESSION_SECRET

    # Google OAuth2
    google_client_id: str
    google_client_secret: str

    # GitHub OAuth2 (optional)
    github_client_id: str | None = None
    github_client_secret: str | None = None

    # ─── Feature Flags (these caused your error) ────────────
    # If your .env uses lowercase names, these lines are enough.
    # If your .env uses UPPERCASE names, keep the Field(...) aliases below.
    enable_request_id: bool = Field(default=True, validation_alias="ENABLE_REQUEST_ID")
    enable_security_headers: bool = Field(
        default=True, validation_alias="ENABLE_SECURITY_HEADERS"
    )
    enable_sessions: bool = Field(default=False, validation_alias="ENABLE_SESSIONS")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # <-- ignore any other unexpected keys
        env_prefix="",  # <-- no automatic prefix
        populate_by_name=True,  # <-- allows using field names if no alias env found
    )


settings = Settings()
