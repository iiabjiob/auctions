from __future__ import annotations

from typing import Literal

from app.models.auction import AuctionLotRecord


ScoreInvalidationReason = Literal[
    "source_content_changed",
    "detail_content_changed",
    "profile_changed",
    "scoring_config_changed",
    "manual_economics_changed",
    "source_status_changed",
    "ttl_expired",
]

SOURCE_CONTENT_CHANGED: ScoreInvalidationReason = "source_content_changed"
DETAIL_CONTENT_CHANGED: ScoreInvalidationReason = "detail_content_changed"
PROFILE_CHANGED: ScoreInvalidationReason = "profile_changed"
SCORING_CONFIG_CHANGED: ScoreInvalidationReason = "scoring_config_changed"
MANUAL_ECONOMICS_CHANGED: ScoreInvalidationReason = "manual_economics_changed"
SOURCE_STATUS_CHANGED: ScoreInvalidationReason = "source_status_changed"
TTL_EXPIRED: ScoreInvalidationReason = "ttl_expired"

ALL_SCORE_INVALIDATION_REASONS: tuple[ScoreInvalidationReason, ...] = (
    SOURCE_CONTENT_CHANGED,
    DETAIL_CONTENT_CHANGED,
    PROFILE_CHANGED,
    SCORING_CONFIG_CHANGED,
    MANUAL_ECONOMICS_CHANGED,
    SOURCE_STATUS_CHANGED,
    TTL_EXPIRED,
)


def invalidate_lot_score(record: AuctionLotRecord, *, reason: ScoreInvalidationReason) -> ScoreInvalidationReason:
    record.score_input_hash = None
    return reason
