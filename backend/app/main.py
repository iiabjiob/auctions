import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.api.v1.health.router import router as health_router
from app.api.v1.health.pipeline_router import router as health_pipeline_router
from app.api.v1.health.source_diagnostics_router import router as source_diagnostics_router
from app.api.v1.auth.router import router as auth_router
from app.api.v1.auctions.router import router as auctions_router
from app.api.v1.filter_presets.router import router as filter_presets_router
from app.api.v1.telegram.router import router as telegram_router
from app.api.v1.user_interest_profiles.router import router as user_interest_profiles_router
from app.api.auction_lots_grid_router import router as auction_lots_grid_router
from app.api.grid_changes_router import router as grid_changes_router
from app.api.grid_history_router import router as grid_history_router


from app.infrastructure.db.database import AsyncSessionLocal, engine
from sqlalchemy import text


from app.core.config import get_settings
from app.core.logger import get_logger
from app.services.telegram_webhook_registration import (
    TelegramWebhookRegistrationError,
    telegram_webhook_registrar,
)


settings = get_settings()
logger = get_logger("core")


async def check_database_connection(max_attempts: int = 10, base_delay: float = 1.5):
    """Ping the DB with retries so we can survive slow compose DNS/startup."""

    for attempt in range(1, max_attempts + 1):
        try:
            async with engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
                logger.info("Connected to the database")
                return
        except Exception as e:
            logger.error(
                "Database connection failed (attempt %s/%s): %s",
                attempt,
                max_attempts,
                e,
            )
            if attempt == max_attempts:
                raise
            await asyncio.sleep(base_delay * attempt)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting FastAPI application")

    # Healthchecks
    # await check_database_connection()
    try:
        webhook_result = await telegram_webhook_registrar.ensure_webhook(
            bot_token=settings.telegram_bot_token,
            webhook_url=settings.telegram_webhook_url,
            webhook_secret=settings.telegram_webhook_secret,
            enabled=settings.telegram_webhook_auto_register,
        )
        if webhook_result.registered:
            logger.info("Telegram webhook registered")
        else:
            logger.info("Telegram webhook registration skipped: %s", webhook_result.reason)
    except TelegramWebhookRegistrationError as exc:
        logger.error("Telegram webhook registration failed: %s", exc)

    try:
        yield
    finally:
        logger.info("Shutting down FastAPI application")


app = FastAPI(
    title=settings.app_name,
    description=settings.description,
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
)

allowed_origins = [origin.strip() for origin in settings.cors_allowed_origins.split(",") if origin.strip()]
if allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Routers
logger.info("Registering REST API routers")
app.include_router(health_router)
app.include_router(health_pipeline_router)
app.include_router(source_diagnostics_router)
app.include_router(auth_router)
app.include_router(filter_presets_router)
app.include_router(user_interest_profiles_router)
app.include_router(telegram_router)
app.include_router(auctions_router)
app.include_router(auction_lots_grid_router)
app.include_router(grid_changes_router)
app.include_router(grid_history_router)

logger.info("REST API routers registered")

logger.info("FastAPI application is up and running at version %s", settings.app_version)
