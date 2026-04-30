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
