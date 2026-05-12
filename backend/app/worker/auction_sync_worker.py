from __future__ import annotations

import asyncio
import logging
import random
from datetime import UTC, datetime, timedelta
from collections.abc import Callable
from urllib.error import HTTPError, URLError

from app.core.config import get_settings
from app.infrastructure.db.database import AsyncSessionLocal
from app.infrastructure.redis.streams import publish_auction_event
from app.services.auction_sources import SOURCE_PROVIDERS
from app.services.auction_sync import persist_all_source_sync_windows, persist_source_sync_error, sync_source_lots
from app.worker.safety import safe_worker_jitter_delay


logger = logging.getLogger(__name__)
settings = get_settings()


def calculate_next_sync_delay(
    interval_seconds: int,
    jitter_seconds: int,
    *,
    random_fraction: Callable[[], float] = random.random,
) -> float:
    return safe_worker_jitter_delay(interval_seconds, jitter_seconds, random_fraction=random_fraction)


def calculate_next_sync_window(
    *,
    current_time: datetime | None = None,
    delay_seconds: float | int | None = None,
    jitter_seconds: int | float | None = None,
    interval_seconds: int | float | None = None,
) -> tuple[datetime, datetime]:
    current_time = current_time or datetime.now(UTC)
    if delay_seconds is None:
        delay_seconds = calculate_next_sync_delay(
            int(interval_seconds or settings.auction_sync_interval_seconds),
            int(jitter_seconds or settings.auction_sync_interval_jitter_seconds),
        )
    next_sync_not_before = current_time + timedelta(seconds=float(delay_seconds))
    next_sync_not_after = next_sync_not_before + timedelta(seconds=max(0.0, float(jitter_seconds or 0)))
    return next_sync_not_before, next_sync_not_after


async def persist_next_sync_window(
    *,
    next_sync_not_before: datetime,
    next_sync_not_after: datetime,
) -> int:
    async with AsyncSessionLocal() as session:
        updated_count = await persist_all_source_sync_windows(
            session,
            next_sync_not_before=next_sync_not_before,
            next_sync_not_after=next_sync_not_after,
        )
    return updated_count


async def sync_all_sources() -> None:
    for source_code in SOURCE_PROVIDERS:
        await publish_auction_event("sync.started", {"source": source_code})
        try:
            sync_limit = settings.auction_sync_limit if settings.auction_sync_limit > 0 else None

            async def publish_sync_progress(payload: dict) -> None:
                await publish_auction_event("sync.progress", payload)

            async with AsyncSessionLocal() as session:
                result = await sync_source_lots(
                    session,
                    source=source_code,
                    limit=sync_limit,
                    on_progress=publish_sync_progress,
                )
            await publish_auction_event("sync.completed", result.model_dump(mode="json"))
            logger.info("Synced source %s: %s", source_code, result.model_dump(mode="json"))
        except Exception as error:
            payload = _source_sync_error_payload(source=source_code, error=error)
            async with AsyncSessionLocal() as error_session:
                await persist_source_sync_error(
                    error_session,
                    source_code=source_code,
                    error_message=payload["message"],
                )
            if payload["expected"]:
                logger.warning(
                    "Source sync failed: %s",
                    payload["message"],
                    extra={
                        "source_code": source_code,
                        "error_code": payload["error_code"],
                        "http_status": payload.get("http_status"),
                    },
                )
            else:
                logger.exception("Failed to sync source %s", source_code)
            await publish_auction_event("sync.failed", {key: value for key, value in payload.items() if key != "expected"})


def _source_sync_error_payload(*, source: str, error: Exception) -> dict:
    payload = {
        "source": source,
        "error": str(error),
        "error_code": "unexpected_error",
        "message": "Source sync failed unexpectedly",
        "retryable": False,
        "expected": False,
    }
    if isinstance(error, HTTPError):
        payload["http_status"] = error.code
        payload["expected"] = True
        if error.code == 403:
            payload["error_code"] = "source_forbidden"
            payload["message"] = "Source returned 403 Forbidden"
            payload["retryable"] = False
        elif error.code == 429:
            payload["error_code"] = "source_rate_limited"
            payload["message"] = "Source rate limit reached"
            payload["retryable"] = True
        else:
            payload["error_code"] = "source_http_error"
            payload["message"] = f"Source returned HTTP {error.code}"
            payload["retryable"] = 500 <= error.code < 600
        return payload
    if isinstance(error, TimeoutError):
        payload["error_code"] = "source_timeout"
        payload["message"] = "Source request timed out"
        payload["retryable"] = True
        payload["expected"] = True
        return payload
    if isinstance(error, URLError):
        payload["error_code"] = "source_network_error"
        payload["message"] = str(error.reason) if getattr(error, "reason", None) else "Could not connect to source"
        payload["retryable"] = True
        payload["expected"] = True
        return payload
    if isinstance(error, OSError):
        payload["error_code"] = "source_io_error"
        payload["message"] = str(error) or "Source read failed"
        payload["retryable"] = True
        payload["expected"] = True
        return payload
    payload["message"] = str(error) or payload["message"]
    return payload


async def run_worker(*, run_once: bool = False) -> None:
    logger.info("Auction sync worker started")
    try:
        if not settings.auction_sync_run_on_start:
            initial_delay = calculate_next_sync_delay(
                settings.auction_sync_interval_seconds,
                settings.auction_sync_interval_jitter_seconds,
            )
            next_sync_not_before, next_sync_not_after = calculate_next_sync_window(
                current_time=datetime.now(UTC),
                delay_seconds=initial_delay,
                jitter_seconds=settings.auction_sync_interval_jitter_seconds,
            )
            await persist_next_sync_window(
                next_sync_not_before=next_sync_not_before,
                next_sync_not_after=next_sync_not_after,
            )
            logger.info("Initial auction sync delayed for %.0f seconds", initial_delay)
            await asyncio.sleep(initial_delay)
        while True:
            if not settings.auction_sync_enabled:
                delay = calculate_next_sync_delay(
                    settings.auction_sync_interval_seconds,
                    settings.auction_sync_interval_jitter_seconds,
                )
                next_sync_not_before, next_sync_not_after = calculate_next_sync_window(
                    current_time=datetime.now(UTC),
                    delay_seconds=delay,
                    jitter_seconds=settings.auction_sync_interval_jitter_seconds,
                )
                await persist_next_sync_window(
                    next_sync_not_before=next_sync_not_before,
                    next_sync_not_after=next_sync_not_after,
                )
                logger.info("Auction sync worker disabled; next check in %.0f seconds", delay)
                await asyncio.sleep(delay)
                if run_once:
                    return None
                continue

            await sync_all_sources()
            if run_once:
                return None
            delay = calculate_next_sync_delay(
                settings.auction_sync_interval_seconds,
                settings.auction_sync_interval_jitter_seconds,
            )
            next_sync_not_before, next_sync_not_after = calculate_next_sync_window(
                current_time=datetime.now(UTC),
                delay_seconds=delay,
                jitter_seconds=settings.auction_sync_interval_jitter_seconds,
            )
            await persist_next_sync_window(
                next_sync_not_before=next_sync_not_before,
                next_sync_not_after=next_sync_not_after,
            )
            logger.info("Next auction sync in %.0f seconds", delay)
            await asyncio.sleep(delay)
    except asyncio.CancelledError:
        logger.info("Auction sync worker shutdown requested")
        raise


def main() -> None:
    logging.basicConfig(level=settings.debug_level)
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Auction sync worker stopped by interrupt")


if __name__ == "__main__":
    main()
