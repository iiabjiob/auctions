from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis

from app.core.config import get_settings


settings = get_settings()


def get_redis() -> Redis:
    return Redis.from_url(settings.redis_url, decode_responses=True)


async def publish_auction_event(event_type: str, payload: dict[str, Any]) -> str:
    event = {
        "type": event_type,
        "emitted_at": datetime.now(UTC).isoformat(),
        "payload": payload,
    }
    async with get_redis() as redis:
        return await redis.xadd(settings.auction_events_stream, {"event": json.dumps(event, ensure_ascii=False)})


async def read_auction_events(last_id: str = "$", *, block_ms: int = 15_000) -> AsyncIterator[dict[str, Any]]:
    async with get_redis() as redis:
        current_id = last_id
        while True:
            response = await redis.xread({settings.auction_events_stream: current_id}, block=block_ms, count=10)
            if not response:
                yield {"type": "heartbeat", "emitted_at": datetime.now(UTC).isoformat(), "payload": {}}
                continue

            for _stream_name, messages in response:
                for message_id, fields in messages:
                    current_id = message_id
                    raw_event = fields.get("event")
                    if not raw_event:
                        continue
                    event = json.loads(raw_event)
                    event["id"] = message_id
                    yield event