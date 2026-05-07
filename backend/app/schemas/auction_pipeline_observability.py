from __future__ import annotations

from pydantic import BaseModel, ConfigDict


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
