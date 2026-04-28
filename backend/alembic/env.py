from logging.config import fileConfig
from alembic import context

from sqlalchemy import create_engine, pool
from app.infrastructure.db.database import Base
import app.models  # noqa
from app.core.config import get_settings

settings = get_settings()
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Async URL from settings (used by application)
async_url = settings.database_url

# Convert asyncpg URL to psycopg3 sync URL for Alembic
# postgresql+asyncpg:// → postgresql+psycopg://
sync_url = async_url.replace("+asyncpg", "+psycopg")

safe_sync_url = sync_url.replace("%", "%%")
config.set_main_option("sqlalchemy.url", safe_sync_url)

target_metadata = Base.metadata

print("ALEMBIC ASYNC URL:", async_url)
print("ALEMBIC  SYNC URL:", sync_url)


def run_migrations_offline():
    context.configure(
        url=safe_sync_url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    engine = create_engine(sync_url, poolclass=pool.NullPool)

    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_schemas=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
