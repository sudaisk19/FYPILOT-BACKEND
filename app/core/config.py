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

    # ─── LLM / GitHub AI Settings ────────────────────────────
    github_openai_token: str | None = Field(
        default=None, validation_alias="GITHUB_OPENAI_TOKEN"
    )
    github_deepseek_token: str | None = Field(
        default=None, validation_alias="GITHUB_DEEPSEEK_TOKEN"
    )
    github_gpto4mini_token: str | None = Field(
        default=None, validation_alias="GITHUB_GPTo4mini_TOKEN"
    )
    github_llama4_token: str | None = Field(
        default=None, validation_alias="GITHUB_LLAMA4_TOKEN"
    )
    github_openai_base_url: str = Field(
        default="https://models.github.ai/inference",
        validation_alias="GITHUB_OPENAI_BASE_URL",
    )

    # ─── MongoDB Settings ────────────────────────────────────
    mongo_uri: str = Field(
        default="mongodb://localhost:27017/", validation_alias="MONGO_URI"
    )
    mongo_db_name: str = Field(default="fypilot", validation_alias="MONGO_DB_NAME")

    # ─── Cache / Infra ───────────────────────────────────────
    redis_url: str = Field(default="redis://localhost:6379/0")  # REDIS_URL

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

    # ─── Email Template Settings ────────────────────────────
    email_logo_url: str | None = Field(
        default=None,
        description="URL to your FYP logo image (e.g., https://yourdomain.com/logo.png or data URI)",
    )  # EMAIL_LOGO_URL
    email_company_name: str = Field(
        default="FYPilot", description="Company/Project name to display in emails"
    )  # EMAIL_COMPANY_NAME

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

    # ─── AI Recommender Service ─────────────────────────────
    ai_recommender_url: str = Field(
        default="http://localhost:8001",
        validation_alias="AI_RECOMMENDER_URL",
        description="URL of the AI Recommender microservice",
    )
    ai_recommender_timeout: float = Field(
        default=30.0,
        validation_alias="AI_RECOMMENDER_TIMEOUT",
        description="HTTP timeout for AI Recommender service calls (seconds)",
    )

    # AI Recommender Middleware Settings
    ai_rate_limit_requests: int = Field(
        default=10,
        validation_alias="AI_RATE_LIMIT_REQUESTS",
        description="Max recommendation requests per user per minute",
    )
    ai_rate_limit_window: int = Field(
        default=60,
        validation_alias="AI_RATE_LIMIT_WINDOW",
        description="Rate limit window in seconds",
    )
    ai_cache_ttl: int = Field(
        default=300,
        validation_alias="AI_CACHE_TTL",
        description="Recommendation cache TTL in seconds (default: 5 minutes)",
    )
    ai_circuit_failure_threshold: int = Field(
        default=5,
        validation_alias="AI_CIRCUIT_FAILURE_THRESHOLD",
        description="Number of failures before opening circuit breaker",
    )
    ai_circuit_recovery_timeout: int = Field(
        default=30,
        validation_alias="AI_CIRCUIT_RECOVERY_TIMEOUT",
        description="Seconds before circuit breaker tries recovery",
    )

    # ─── Bulk Import Settings ───────────────────────────────
    app_encryption_key: str | None = Field(
        default=None, validation_alias="APP_ENCRYPTION_KEY"
    )
    bulk_import_batch_size: int = Field(
        default=50, validation_alias="BULK_IMPORT_BATCH_SIZE"
    )
    temp_password_ttl_hours: int = Field(
        default=24, validation_alias="TEMP_PASSWORD_TTL_HOURS"
    )

    # ─── Storage Upload Timeout ───────────────────────────
    storage_upload_timeout_seconds: float = Field(
        default=60.0,
        validation_alias="STORAGE_UPLOAD_TIMEOUT_SECONDS",
        description="Timeout in seconds for single file upload to Supabase Storage",
    )

    # ─── Collaborative chat (SSE + job workers) ─────────────
    chat_context_message_limit: int = Field(
        default=20,
        validation_alias="CHAT_CONTEXT_MESSAGE_LIMIT",
        description="Max prior messages sent to the LLM per turn",
    )
    chat_rate_limit_per_minute_user: int = Field(
        default=30,
        validation_alias="CHAT_RATE_LIMIT_PER_MINUTE_USER",
    )
    chat_rate_limit_per_minute_room: int = Field(
        default=60,
        validation_alias="CHAT_RATE_LIMIT_PER_MINUTE_ROOM",
    )
    chat_worker_tasks: int = Field(
        default=2,
        validation_alias="CHAT_WORKER_TASKS",
        description="Number of asyncio workers consuming chat LLM jobs",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # <-- ignore any other unexpected keys
        env_prefix="",  # <-- no automatic prefix
        populate_by_name=True,  # <-- allows using field names if no alias env found
    )


settings = Settings()
