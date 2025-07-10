# alembic/env.py

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Import your Pydantic settings so we can grab the real DATABASE_URL
from app.core.config import settings


# this is the Alembic Config object, which provides
# access to values within alembic.ini
config = context.config

# ─── Override the URL in alembic.ini with your app's DATABASE_URL ───
# This ensures Alembic uses the same connection string as your FastAPI app
config.set_main_option("sqlalchemy.url", settings.database_url)


# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# If you have model metadata, point target_metadata here
# from app.db import Base
# target_metadata = Base.metadata
target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (no DBAPI needed)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connect via Engine)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


# Decide between offline & online based on context
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
# End of alembic/env.py
# This file is used by Alembic to manage database migrations.
# It configures the connection to the database and runs migrations based on the settings defined in your FastAPI app's configuration.
# The `run_migrations_offline` function is used when running migrations without a live database connection (e.g., generating migration scripts).
# The `run_migrations_online` function is used when running migrations with a live database connection.
# The `target_metadata` variable is set to `None` here, but you can uncomment and set it to your SQLAlchemy