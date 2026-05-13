from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProcurementPipelineCounters(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    total_lots: int
    priority_lots: int
    decision_pending_lots: int
    missing_documents: int
    missing_critical_fields: int
    scoring_stale_or_incomplete: int
    scored_current: int


class ProcurementSourceSyncStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    title: str
    enabled: bool
    website: str
    parser_version: str | None = None
    last_sync_started_at: datetime | None = None
    last_sync_completed_at: datetime | None = None
    last_successful_sync_at: datetime | None = None
    last_sync_result: str | None = None
    last_sync_error: str | None = None
    last_sync_error_code: str | None = None
    last_sync_fetched: int | None = None
    last_sync_created: int | None = None
    last_sync_updated: int | None = None
    last_sync_unchanged: int | None = None
    last_sync_status_changed: int | None = None
    last_sync_parser_failures: int | None = None
    last_sync_missing_critical_fields: dict[str, int] = Field(default_factory=dict)


class ProcurementPipelineHealthResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    counters: ProcurementPipelineCounters
    sources: list[ProcurementSourceSyncStatus] = Field(default_factory=list)
