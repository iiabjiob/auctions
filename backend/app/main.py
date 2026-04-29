import asyncio
from fastapi import FastAPI
from contextlib import asynccontextmanager

from app.api.v1.health.router import router as health_router
from app.api.v1.auth.router import router as auth_router
from app.api.v1.auctions.router import router as auctions_router
from app.api.v1.filter_presets.router import router as filter_presets_router


from app.infrastructure.db.database import AsyncSessionLocal, engine
from sqlalchemy import text


from app.core.config import get_settings
from app.core.logger import get_logger


settings = get_settings()
logger = get_logger("core")


async def check_database_connection(max_attempts: int = 10, base_delay: float = 1.5):
    """Ping the DB with retries so we can survive slow compose DNS/startup."""

    for attempt in range(1, max_attempts + 1):
        try:
            async with engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
                logger.info("✅ Connected to the database!")
                return
        except Exception as e:
            logger.error(
                "💥 Database connection failed (attempt %s/%s): %s",
                attempt,
                max_attempts,
                e,
            )
            if attempt == max_attempts:
                raise
            await asyncio.sleep(base_delay * attempt)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting FastAPI application...")

    # Healthchecks
    # await check_database_connection()

    try:
        yield
    finally:
        logger.info("🛑 Shutting down FastAPI application...")


app = FastAPI(
    title=settings.app_name,
    description=settings.description,
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
)

# Routers
logger.info("🔗 Registering REST API routers...")
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(filter_presets_router)
app.include_router(auctions_router)

logger.info("✅ REST API routers registered")

logger.info(f"✅ FastAPI application is up and running at version {settings.app_version}")
