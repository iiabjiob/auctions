from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from urllib.parse import urlparse

from sqlalchemy import and_, desc, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auction import AuctionSourceHttpExchange, AuctionSourceState
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


async def get_source_diagnostics(
    session: AsyncSession,
    *,
    range_name: DiagnosticsRange = "day",
    current_time: datetime | None = None,
) -> SourceDiagnosticsResponse:
    current_time = current_time or datetime.now(UTC)
    from_at = _range_start(range_name, current_time)
    filters = _time_filters(from_at=from_at, to_at=current_time)

    totals = await _load_totals(session, filters)
    sources = await _load_source_breakdown(session, filters)
    timeline = await _load_timeline(session, filters, range_name=range_name)
    return SourceDiagnosticsResponse(
        range=range_name,
        generated_at=current_time,
        from_at=from_at,
        to_at=current_time,
        totals=totals,
        sources=sources,
        timeline=timeline,
    )


async def _load_totals(session: AsyncSession, filters) -> SourceDiagnosticsTotals:
    row = (await session.execute(_totals_statement().where(*filters))).one()
    return _totals_from_row(row)


async def _load_source_breakdown(session: AsyncSession, filters) -> list[SourceDiagnosticsSource]:
    statement = (
        select(
            AuctionSourceState.code,
            AuctionSourceState.title,
            AuctionSourceState.website,
            func.count(AuctionSourceHttpExchange.id).label("request_count"),
            func.count(AuctionSourceHttpExchange.id).filter(AuctionSourceHttpExchange.ok.is_(True)).label("success_count"),
            func.count(AuctionSourceHttpExchange.id).filter(AuctionSourceHttpExchange.ok.is_(False)).label("error_count"),
            func.coalesce(func.sum(AuctionSourceHttpExchange.response_bytes), 0).label("inbound_bytes"),
            func.coalesce(func.sum(AuctionSourceHttpExchange.request_bytes), 0).label("outbound_bytes"),
            func.avg(AuctionSourceHttpExchange.duration_ms).label("average_duration_ms"),
        )
        .select_from(AuctionSourceState)
        .outerjoin(
            AuctionSourceHttpExchange,
            and_(AuctionSourceHttpExchange.source_code == AuctionSourceState.code, *filters),
        )
        .group_by(AuctionSourceState.code, AuctionSourceState.title, AuctionSourceState.website)
        .order_by(AuctionSourceState.code.asc())
    )
    rows = (await session.execute(statement)).all()
    return [
        SourceDiagnosticsSource(
            code=row.code,
            title=row.title,
            website=row.website,
            totals=_totals_from_row(row),
            operations=await _load_operations(session, filters, source_code=row.code),
            status_codes=await _load_status_codes(session, filters, source_code=row.code),
            errors=await _load_errors(session, filters, source_code=row.code),
        )
        for row in rows
    ]


async def _load_operations(session: AsyncSession, filters, *, source_code: str) -> list[SourceDiagnosticsOperationBucket]:
    statement = (
        select(
            AuctionSourceHttpExchange.operation,
            func.count(AuctionSourceHttpExchange.id).label("request_count"),
            func.coalesce(func.sum(AuctionSourceHttpExchange.response_bytes), 0).label("inbound_bytes"),
            func.coalesce(func.sum(AuctionSourceHttpExchange.request_bytes), 0).label("outbound_bytes"),
            func.avg(AuctionSourceHttpExchange.duration_ms).label("average_duration_ms"),
        )
        .where(AuctionSourceHttpExchange.source_code == source_code, *filters)
        .group_by(AuctionSourceHttpExchange.operation)
        .order_by(desc("request_count"), AuctionSourceHttpExchange.operation.asc())
    )
    rows = (await session.execute(statement)).all()
    return [
        SourceDiagnosticsOperationBucket(
            operation=row.operation,
            request_count=int(row.request_count or 0),
            inbound_bytes=int(row.inbound_bytes or 0),
            outbound_bytes=int(row.outbound_bytes or 0),
            average_duration_ms=float(row.average_duration_ms) if row.average_duration_ms is not None else None,
        )
        for row in rows
    ]


async def _load_status_codes(session: AsyncSession, filters, *, source_code: str) -> list[SourceDiagnosticsStatusBucket]:
    statement = (
        select(AuctionSourceHttpExchange.status_code, func.count(AuctionSourceHttpExchange.id).label("count"))
        .where(AuctionSourceHttpExchange.source_code == source_code, *filters)
        .group_by(AuctionSourceHttpExchange.status_code)
        .order_by(AuctionSourceHttpExchange.status_code.asc().nulls_last())
    )
    rows = (await session.execute(statement)).all()
    return [SourceDiagnosticsStatusBucket(status_code=row.status_code, count=int(row.count or 0)) for row in rows]


async def _load_errors(session: AsyncSession, filters, *, source_code: str) -> list[SourceDiagnosticsErrorBucket]:
    error_type = func.coalesce(AuctionSourceHttpExchange.error_type, literal_column("'http_error'")).label("error_type")
    statement = (
        select(
            error_type,
            func.count(AuctionSourceHttpExchange.id).label("count"),
            func.max(AuctionSourceHttpExchange.error_message).label("last_message"),
        )
        .where(AuctionSourceHttpExchange.source_code == source_code, AuctionSourceHttpExchange.ok.is_(False), *filters)
        .group_by(error_type)
        .order_by(desc("count"))
    )
    rows = (await session.execute(statement)).all()
    return [
        SourceDiagnosticsErrorBucket(error_type=row.error_type, count=int(row.count or 0), last_message=row.last_message)
        for row in rows
    ]


async def _load_timeline(session: AsyncSession, filters, *, range_name: DiagnosticsRange) -> list[SourceDiagnosticsBucket]:
    bucket = _bucket_interval(range_name)
    statement = (
        select(
            func.date_trunc(bucket, AuctionSourceHttpExchange.started_at).label("bucket_start"),
            func.count(AuctionSourceHttpExchange.id).label("request_count"),
            func.coalesce(func.sum(AuctionSourceHttpExchange.response_bytes), 0).label("inbound_bytes"),
            func.coalesce(func.sum(AuctionSourceHttpExchange.request_bytes), 0).label("outbound_bytes"),
            func.count(AuctionSourceHttpExchange.id).filter(AuctionSourceHttpExchange.ok.is_(False)).label("error_count"),
        )
        .where(*filters)
        .group_by("bucket_start")
        .order_by("bucket_start")
    )
    rows = (await session.execute(statement)).all()
    return [
        SourceDiagnosticsBucket(
            bucket_start=row.bucket_start,
            request_count=int(row.request_count or 0),
            inbound_bytes=int(row.inbound_bytes or 0),
            outbound_bytes=int(row.outbound_bytes or 0),
            error_count=int(row.error_count or 0),
        )
        for row in rows
    ]


def _totals_statement():
    return select(
        func.count(AuctionSourceHttpExchange.id).label("request_count"),
        func.count(AuctionSourceHttpExchange.id).filter(AuctionSourceHttpExchange.ok.is_(True)).label("success_count"),
        func.count(AuctionSourceHttpExchange.id).filter(AuctionSourceHttpExchange.ok.is_(False)).label("error_count"),
        func.coalesce(func.sum(AuctionSourceHttpExchange.response_bytes), 0).label("inbound_bytes"),
        func.coalesce(func.sum(AuctionSourceHttpExchange.request_bytes), 0).label("outbound_bytes"),
        func.avg(AuctionSourceHttpExchange.duration_ms).label("average_duration_ms"),
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
        average_duration_ms=float(row.average_duration_ms) if row.average_duration_ms is not None else None,
    )


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


def _time_filters(*, from_at: datetime | None, to_at: datetime):
    filters = [AuctionSourceHttpExchange.started_at <= to_at]
    if from_at is not None:
        filters.append(AuctionSourceHttpExchange.started_at >= from_at)
    return filters


def _bucket_interval(range_name: DiagnosticsRange) -> Literal["hour", "day", "week"]:
    if range_name == "day":
        return "hour"
    if range_name in {"week", "month"}:
        return "day"
    return "week"
