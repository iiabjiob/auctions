from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AuctionPipelineCounters(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    enrichment_requested: int
    enrichment_due_now: int
    enrichment_claimed_active: int
    enrichment_retry_waiting: int
    enrichment_failed_with_error: int
    enrichment_maxed_out: int
    scoring_stale_or_incomplete: int
    scored_current: int


class AuctionSourceSyncStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    title: str
    enabled: bool
    last_sync_started_at: datetime | None = None
    last_sync_completed_at: datetime | None = None
    next_sync_not_before: datetime | None = None
    next_sync_not_after: datetime | None = None
    last_sync_error: str | None = None


class AuctionPipelineHealthResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    counters: AuctionPipelineCounters
    sources: list[AuctionSourceSyncStatus] = Field(default_factory=list)
