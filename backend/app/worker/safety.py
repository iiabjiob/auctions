from __future__ import annotations

from collections.abc import Callable


DEFAULT_MIN_WORKER_POLL_INTERVAL_SECONDS = 5.0


def safe_worker_sleep_seconds(
    configured_seconds: float | int | None,
    *,
    min_seconds: float = DEFAULT_MIN_WORKER_POLL_INTERVAL_SECONDS,
) -> float:
    try:
        configured = float(configured_seconds or 0)
    except (TypeError, ValueError):
        configured = 0.0
    return max(float(min_seconds), configured)


def safe_worker_jitter_delay(
    interval_seconds: float | int | None,
    jitter_seconds: float | int | None,
    *,
    random_fraction: Callable[[], float],
    min_seconds: float = DEFAULT_MIN_WORKER_POLL_INTERVAL_SECONDS,
) -> float:
    base_delay = safe_worker_sleep_seconds(interval_seconds, min_seconds=min_seconds)
    try:
        jitter = max(0.0, float(jitter_seconds or 0))
    except (TypeError, ValueError):
        jitter = 0.0
    if jitter == 0:
        return base_delay
    offset = ((random_fraction() * 2) - 1) * jitter
    return max(float(min_seconds), base_delay + offset)
