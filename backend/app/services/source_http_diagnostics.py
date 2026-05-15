from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from urllib.parse import urlparse

from sqlalchemy import and_, desc, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auction import AuctionSourceHttpExchange, AuctionSourceState
from app.models.procurement import ProcurementSourceHttpExchange, ProcurementSourceState
from app.schemas.source_diagnostics import (
    DiagnosticsRange,
    SourceDiagnosticsBucket,
    SourceDiagnosticsErrorBucket,
    SourceDiagnosticsOperationBucket,
    SourceDiagnosticsResponse,
    SourceDiagnosticsSource,
    SourceDiagnosticsStatusBucket,
    SourceDiagnosticsTotals,
)


DiagnosticsKind = Literal["all", "auction", "procurement"]


@dataclass(slots=True, frozen=True)
class _DiagnosticsDomain:
    kind: Literal["auction", "procurement"]
    state_model: Any
    exchange_model: Any


_DIAGNOSTICS_DOMAINS: tuple[_DiagnosticsDomain, ...] = (
    _DiagnosticsDomain(kind="auction", state_model=AuctionSourceState, exchange_model=AuctionSourceHttpExchange),
    _DiagnosticsDomain(kind="procurement", state_model=ProcurementSourceState, exchange_model=ProcurementSourceHttpExchange),
)


@dataclass(slots=True)
class SourceHttpExchangeEvent:
    source_code: str
    operation: str
    method: str
    url: str
    host: str
    started_at: datetime
    completed_at: datetime
    duration_ms: int
    status_code: int | None
    ok: bool
    request_bytes: int
    response_bytes: int
    error_type: str | None = None
    error_message: str | None = None


_ACTIVE_EVENTS: ContextVar[list[SourceHttpExchangeEvent] | None] = ContextVar("source_http_diagnostics_events", default=None)


def begin_source_http_diagnostics() -> Token[list[SourceHttpExchangeEvent] | None]:
    return _ACTIVE_EVENTS.set([])


def collect_source_http_diagnostics(token: Token[list[SourceHttpExchangeEvent] | None]) -> list[SourceHttpExchangeEvent]:
    events = _ACTIVE_EVENTS.get() or []
    _ACTIVE_EVENTS.reset(token)
    return list(events)


def drain_active_source_http_diagnostics() -> list[SourceHttpExchangeEvent]:
    events = _ACTIVE_EVENTS.get() or []
    _ACTIVE_EVENTS.set(None)
    return list(events)


def record_source_http_exchange(
    *,
    source_code: str,
    operation: str,
    method: str,
    url: str,
    started_at: datetime,
    completed_at: datetime,
    status_code: int | None,
    request_bytes: int,
    response_bytes: int,
    error: BaseException | None = None,
) -> None:
    events = _ACTIVE_EVENTS.get()
    if events is None:
        return
    duration_ms = max(0, int((completed_at - started_at).total_seconds() * 1000))
    events.append(
        SourceHttpExchangeEvent(
            source_code=source_code,
            operation=operation,
            method=method.upper(),
            url=url,
            host=urlparse(url).netloc or "unknown",
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
            status_code=status_code,
            ok=error is None and (status_code is None or status_code < 400),
            request_bytes=max(0, request_bytes),
            response_bytes=max(0, response_bytes),
            error_type=type(error).__name__ if error is not None else None,
            error_message=str(error)[:2000] if error is not None else None,
        )
    )


async def persist_source_http_diagnostics(
    session: AsyncSession,
    events: list[SourceHttpExchangeEvent],
) -> None:
    if not events:
        return
    session.add_all(
        AuctionSourceHttpExchange(
            source_code=event.source_code,
            operation=event.operation,
            method=event.method,
            url=event.url,
            host=event.host,
            started_at=event.started_at,
            completed_at=event.completed_at,
            duration_ms=event.duration_ms,
            status_code=event.status_code,
            ok=event.ok,
            request_bytes=event.request_bytes,
            response_bytes=event.response_bytes,
            error_type=event.error_type,
            error_message=event.error_message,
        )
        for event in events
    )


async def persist_procurement_source_http_diagnostics(
    session: AsyncSession,
    events: list[SourceHttpExchangeEvent],
) -> None:
    if not events:
        return
    session.add_all(
        ProcurementSourceHttpExchange(
            source_code=event.source_code,
            operation=event.operation,
            method=event.method,
            url=event.url,
            host=event.host,
            started_at=event.started_at,
            completed_at=event.completed_at,
            duration_ms=event.duration_ms,
            status_code=event.status_code,
            ok=event.ok,
            request_bytes=event.request_bytes,
            response_bytes=event.response_bytes,
            error_type=event.error_type,
            error_message=event.error_message,
        )
        for event in events
    )


async def get_source_diagnostics(
    session: AsyncSession,
    *,
    range_name: DiagnosticsRange = "day",
    kind: DiagnosticsKind = "all",
    source_code: str | None = None,
    current_time: datetime | None = None,
) -> SourceDiagnosticsResponse:
    current_time = current_time or datetime.now(UTC)
    from_at = _range_start(range_name, current_time)
    domains = _selected_domains(kind)

    totals = await _load_totals(session, domains, from_at=from_at, to_at=current_time, source_code=source_code)
    sources = await _load_source_breakdown(session, domains, from_at=from_at, to_at=current_time, source_code=source_code)
    timeline = await _load_timeline(session, domains, from_at=from_at, to_at=current_time, range_name=range_name, source_code=source_code)
    return SourceDiagnosticsResponse(
        range=range_name,
        generated_at=current_time,
        from_at=from_at,
        to_at=current_time,
        totals=totals,
        sources=sources,
        timeline=timeline,
    )


async def _load_totals(
    session: AsyncSession,
    domains: tuple[_DiagnosticsDomain, ...],
    *,
    from_at: datetime | None,
    to_at: datetime,
    source_code: str | None,
) -> SourceDiagnosticsTotals:
    totals = _TotalsAccumulator()
    for domain in domains:
        row = (
            await session.execute(
                _totals_statement(domain.exchange_model).where(
                    *_time_filters(domain.exchange_model, from_at=from_at, to_at=to_at, source_code=source_code)
                )
            )
        ).one()
        totals.add(row)
    return totals.build()


async def _load_source_breakdown(
    session: AsyncSession,
    domains: tuple[_DiagnosticsDomain, ...],
    *,
    from_at: datetime | None,
    to_at: datetime,
    source_code: str | None,
) -> list[SourceDiagnosticsSource]:
    sources: list[SourceDiagnosticsSource] = []
    for domain in domains:
        state_model = domain.state_model
        exchange_model = domain.exchange_model
        statement = select(
            state_model.code,
            state_model.title,
            state_model.website,
            func.count(exchange_model.id).label("request_count"),
            func.count(exchange_model.id).filter(exchange_model.ok.is_(True)).label("success_count"),
            func.count(exchange_model.id).filter(exchange_model.ok.is_(False)).label("error_count"),
            func.coalesce(func.sum(exchange_model.response_bytes), 0).label("inbound_bytes"),
            func.coalesce(func.sum(exchange_model.request_bytes), 0).label("outbound_bytes"),
            func.coalesce(func.sum(exchange_model.duration_ms), 0).label("duration_sum_ms"),
        ).select_from(state_model)
        if source_code is not None:
            statement = statement.where(state_model.code == source_code)
        statement = (
            statement.outerjoin(
                exchange_model,
                and_(
                    exchange_model.source_code == state_model.code,
                    *_time_filters(exchange_model, from_at=from_at, to_at=to_at, source_code=source_code),
                ),
            )
            .group_by(state_model.code, state_model.title, state_model.website)
            .order_by(state_model.code.asc())
        )
        rows = (await session.execute(statement)).all()
        for row in rows:
            sources.append(
                SourceDiagnosticsSource(
                    code=row.code,
                    kind=domain.kind,
                    title=row.title,
                    website=row.website,
                    totals=_totals_from_row(row),
                    operations=await _load_operations(
                        session,
                        exchange_model,
                        from_at=from_at,
                        to_at=to_at,
                        source_code=row.code,
                    ),
                    status_codes=await _load_status_codes(
                        session,
                        exchange_model,
                        from_at=from_at,
                        to_at=to_at,
                        source_code=row.code,
                    ),
                    errors=await _load_errors(
                        session,
                        exchange_model,
                        from_at=from_at,
                        to_at=to_at,
                        source_code=row.code,
                    ),
                )
            )
    return sources


async def _load_operations(
    session: AsyncSession,
    exchange_model: Any,
    *,
    from_at: datetime | None,
    to_at: datetime,
    source_code: str,
) -> list[SourceDiagnosticsOperationBucket]:
    statement = (
        select(
            exchange_model.operation,
            func.count(exchange_model.id).label("request_count"),
            func.coalesce(func.sum(exchange_model.response_bytes), 0).label("inbound_bytes"),
            func.coalesce(func.sum(exchange_model.request_bytes), 0).label("outbound_bytes"),
            func.coalesce(func.sum(exchange_model.duration_ms), 0).label("duration_sum_ms"),
        )
            .where(
                exchange_model.source_code == source_code,
                *_time_filters(exchange_model, from_at=from_at, to_at=to_at, source_code=None),
            )
        .group_by(exchange_model.operation)
        .order_by(desc("request_count"), exchange_model.operation.asc())
    )
    rows = (await session.execute(statement)).all()
    return [
        SourceDiagnosticsOperationBucket(
            operation=row.operation,
            request_count=int(row.request_count or 0),
            inbound_bytes=int(row.inbound_bytes or 0),
            outbound_bytes=int(row.outbound_bytes or 0),
            average_duration_ms=_average_from_row(row),
        )
        for row in rows
    ]


async def _load_status_codes(
    session: AsyncSession,
    exchange_model: Any,
    *,
    from_at: datetime | None,
    to_at: datetime,
    source_code: str,
) -> list[SourceDiagnosticsStatusBucket]:
    statement = (
        select(exchange_model.status_code, func.count(exchange_model.id).label("count"))
        .where(
            exchange_model.source_code == source_code,
            *_time_filters(exchange_model, from_at=from_at, to_at=to_at, source_code=None),
        )
        .group_by(exchange_model.status_code)
        .order_by(exchange_model.status_code.asc().nulls_last())
    )
    rows = (await session.execute(statement)).all()
    return [SourceDiagnosticsStatusBucket(status_code=row.status_code, count=int(row.count or 0)) for row in rows]


async def _load_errors(
    session: AsyncSession,
    exchange_model: Any,
    *,
    from_at: datetime | None,
    to_at: datetime,
    source_code: str,
) -> list[SourceDiagnosticsErrorBucket]:
    error_type = func.coalesce(exchange_model.error_type, literal_column("'http_error'")).label("error_type")
    statement = (
        select(
            error_type,
            func.count(exchange_model.id).label("count"),
            func.max(exchange_model.error_message).label("last_message"),
        )
        .where(
            exchange_model.source_code == source_code,
            exchange_model.ok.is_(False),
            *_time_filters(exchange_model, from_at=from_at, to_at=to_at, source_code=None),
        )
        .group_by(error_type)
        .order_by(desc("count"))
    )
    rows = (await session.execute(statement)).all()
    return [
        SourceDiagnosticsErrorBucket(error_type=row.error_type, count=int(row.count or 0), last_message=row.last_message)
        for row in rows
    ]


async def _load_timeline(
    session: AsyncSession,
    domains: tuple[_DiagnosticsDomain, ...],
    *,
    from_at: datetime | None,
    to_at: datetime,
    range_name: DiagnosticsRange,
    source_code: str | None,
) -> list[SourceDiagnosticsBucket]:
    bucket = _bucket_interval(range_name)
    totals_by_bucket: dict[datetime, SourceDiagnosticsBucket] = {}
    for domain in domains:
        exchange_model = domain.exchange_model
        statement = (
            select(
                func.date_trunc(bucket, exchange_model.started_at).label("bucket_start"),
                func.count(exchange_model.id).label("request_count"),
                func.coalesce(func.sum(exchange_model.response_bytes), 0).label("inbound_bytes"),
                func.coalesce(func.sum(exchange_model.request_bytes), 0).label("outbound_bytes"),
                func.count(exchange_model.id).filter(exchange_model.ok.is_(False)).label("error_count"),
            )
            .where(*_time_filters(exchange_model, from_at=from_at, to_at=to_at, source_code=source_code))
            .group_by("bucket_start")
            .order_by("bucket_start")
        )
        rows = (await session.execute(statement)).all()
        for row in rows:
            bucket_start = row.bucket_start
            existing = totals_by_bucket.get(bucket_start)
            if existing is None:
                totals_by_bucket[bucket_start] = SourceDiagnosticsBucket(
                    bucket_start=bucket_start,
                    request_count=int(row.request_count or 0),
                    inbound_bytes=int(row.inbound_bytes or 0),
                    outbound_bytes=int(row.outbound_bytes or 0),
                    error_count=int(row.error_count or 0),
                )
            else:
                totals_by_bucket[bucket_start] = SourceDiagnosticsBucket(
                    bucket_start=bucket_start,
                    request_count=existing.request_count + int(row.request_count or 0),
                    inbound_bytes=existing.inbound_bytes + int(row.inbound_bytes or 0),
                    outbound_bytes=existing.outbound_bytes + int(row.outbound_bytes or 0),
                    error_count=existing.error_count + int(row.error_count or 0),
                )
    return [totals_by_bucket[key] for key in sorted(totals_by_bucket)]


def _totals_statement(exchange_model: Any):
    return select(
        func.count(exchange_model.id).label("request_count"),
        func.count(exchange_model.id).filter(exchange_model.ok.is_(True)).label("success_count"),
        func.count(exchange_model.id).filter(exchange_model.ok.is_(False)).label("error_count"),
        func.coalesce(func.sum(exchange_model.response_bytes), 0).label("inbound_bytes"),
        func.coalesce(func.sum(exchange_model.request_bytes), 0).label("outbound_bytes"),
        func.coalesce(func.sum(exchange_model.duration_ms), 0).label("duration_sum_ms"),
    )


def _totals_from_row(row) -> SourceDiagnosticsTotals:
    inbound_bytes = int(row.inbound_bytes or 0)
    outbound_bytes = int(row.outbound_bytes or 0)
    return SourceDiagnosticsTotals(
        request_count=int(row.request_count or 0),
        success_count=int(row.success_count or 0),
        error_count=int(row.error_count or 0),
        inbound_bytes=inbound_bytes,
        outbound_bytes=outbound_bytes,
        total_bytes=inbound_bytes + outbound_bytes,
        average_duration_ms=_average_from_row(row),
    )


@dataclass(slots=True)
class _TotalsAccumulator:
    request_count: int = 0
    success_count: int = 0
    error_count: int = 0
    inbound_bytes: int = 0
    outbound_bytes: int = 0
    duration_sum_ms: int = 0

    def add(self, row) -> None:  # noqa: ANN001
        self.request_count += int(row.request_count or 0)
        self.success_count += int(row.success_count or 0)
        self.error_count += int(row.error_count or 0)
        self.inbound_bytes += int(row.inbound_bytes or 0)
        self.outbound_bytes += int(row.outbound_bytes or 0)
        self.duration_sum_ms += int(row.duration_sum_ms or 0)

    def build(self) -> SourceDiagnosticsTotals:
        average_duration_ms = self.duration_sum_ms / self.request_count if self.request_count else None
        return SourceDiagnosticsTotals(
            request_count=self.request_count,
            success_count=self.success_count,
            error_count=self.error_count,
            inbound_bytes=self.inbound_bytes,
            outbound_bytes=self.outbound_bytes,
            total_bytes=self.inbound_bytes + self.outbound_bytes,
            average_duration_ms=average_duration_ms,
        )


def _average_from_row(row) -> float | None:  # noqa: ANN001
    request_count = int(getattr(row, "request_count", 0) or 0)
    duration_sum_ms = int(getattr(row, "duration_sum_ms", 0) or 0)
    if request_count == 0:
        return None
    return duration_sum_ms / request_count


def _selected_domains(kind: DiagnosticsKind) -> tuple[_DiagnosticsDomain, ...]:
    if kind == "auction":
        return (_DIAGNOSTICS_DOMAINS[0],)
    if kind == "procurement":
        return (_DIAGNOSTICS_DOMAINS[1],)
    return _DIAGNOSTICS_DOMAINS


def _range_start(range_name: DiagnosticsRange, current_time: datetime) -> datetime | None:
    ranges: dict[DiagnosticsRange, timedelta | None] = {
        "day": timedelta(days=1),
        "week": timedelta(weeks=1),
        "month": timedelta(days=30),
        "3months": timedelta(days=90),
        "all": None,
    }
    delta = ranges[range_name]
    return None if delta is None else current_time - delta


def _time_filters(exchange_model: Any, *, from_at: datetime | None, to_at: datetime, source_code: str | None):
    filters = [exchange_model.started_at <= to_at]
    if from_at is not None:
        filters.append(exchange_model.started_at >= from_at)
    if source_code is not None:
        filters.append(exchange_model.source_code == source_code)
    return filters


def _bucket_interval(range_name: DiagnosticsRange) -> Literal["hour", "day", "week"]:
    if range_name == "day":
        return "hour"
    if range_name in {"week", "month"}:
        return "day"
    return "week"
