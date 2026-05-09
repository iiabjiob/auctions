from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import get_settings

settings = get_settings()

# Асинхронный движок для SQLAlchemy
engine = create_async_engine(settings.database_url, future=True, echo=settings.sqlalchemy_echo)

# Сессия для работы с БД
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()

# Dependency для получения асинхронной сессии
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


def _read_statement_timeout_ms(timeout_ms: int | None = None) -> int:
    configured = settings.db_statement_timeout_ms if timeout_ms is None else timeout_ms
    return max(0, int(configured or 0))


async def apply_read_statement_timeout(session: AsyncSession, timeout_ms: int | None = None) -> None:
    resolved_timeout = _read_statement_timeout_ms(timeout_ms)
    if resolved_timeout <= 0:
        return
    await session.execute(text(f"SET LOCAL statement_timeout = {resolved_timeout}"))


async def get_read_db():
    async with AsyncSessionLocal() as session:
        await apply_read_statement_timeout(session)
        yield session
