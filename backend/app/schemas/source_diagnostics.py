from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


DiagnosticsRange = Literal["day", "week", "month", "3months", "all"]


class SourceDiagnosticsTotals(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    request_count: int
    success_count: int
    error_count: int
    inbound_bytes: int
    outbound_bytes: int
    total_bytes: int
    average_duration_ms: float | None = None


class SourceDiagnosticsBucket(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    bucket_start: datetime
    request_count: int
    inbound_bytes: int
    outbound_bytes: int
    error_count: int


class SourceDiagnosticsStatusBucket(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status_code: int | None = None
    count: int


class SourceDiagnosticsErrorBucket(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    error_type: str
    count: int
    last_message: str | None = None


class SourceDiagnosticsOperationBucket(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    operation: str
    request_count: int
    inbound_bytes: int
    outbound_bytes: int
    average_duration_ms: float | None = None


class SourceDiagnosticsSource(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    kind: Literal["auction", "procurement"]
    title: str
    website: str
    totals: SourceDiagnosticsTotals
    operations: list[SourceDiagnosticsOperationBucket] = Field(default_factory=list)
    status_codes: list[SourceDiagnosticsStatusBucket] = Field(default_factory=list)
    errors: list[SourceDiagnosticsErrorBucket] = Field(default_factory=list)


class SourceDiagnosticsResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    range: DiagnosticsRange
    generated_at: datetime
    from_at: datetime | None = None
    to_at: datetime
    totals: SourceDiagnosticsTotals
    sources: list[SourceDiagnosticsSource] = Field(default_factory=list)
    timeline: list[SourceDiagnosticsBucket] = Field(default_factory=list)
