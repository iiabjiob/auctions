from __future__ import annotations

from datetime import UTC, datetime, timedelta
from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, ConfigDict, Field

from app.models.auction import AuctionLotDetailCache, AuctionLotRecord, AuctionSourceState
from app.schemas.lot_evidence import LotEvidence
from app.services.lot_evidence import build_lot_evidence
from app.services.auction_workspace import ensure_lot_detail_cache


class LotEnrichmentRequirementEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    needs_enrichment: bool
    missing_fields: list[str] = Field(default_factory=list)
    reason_category: str = "ready_for_scoring"


class LotEnrichmentDryRunResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_count: int
    processed_count: int
    needs_enrichment_count: int
    ready_for_scoring_count: int
    candidate_record_ids: list[int] = Field(default_factory=list)
    candidate_row_ids: list[str] = Field(default_factory=list)


class LotEnrichmentExecutionResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_count: int
    processed_count: int
    fetched_count: int
    cleared_count: int
    still_missing_count: int
    skipped_count: int
    candidate_record_ids: list[int] = Field(default_factory=list)


TERMINAL_LOT_STATUS_MARKERS: tuple[str, ...] = (
    "архив",
    "archived",
    "заверш",
    "отмен",
)
DEADLINE_PATTERNS: tuple[str, ...] = (
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%Y-%m-%dT%H:%M:%S",
)
DEFAULT_ENRICHMENT_CANDIDATE_LIMIT = 50
DEFAULT_ENRICHMENT_CLAIM_SECONDS = 15 * 60
ENRICHMENT_BACKOFF_BASE_SECONDS = 30 * 60
ENRICHMENT_BACKOFF_MAX_SECONDS = 24 * 60 * 60
ENRICHMENT_WORKER_ID = "auction-enrichment-worker"


def evaluate_lot_enrichment_requirements(evidence: LotEvidence) -> LotEnrichmentRequirementEvaluation:
    missing_fields: list[str] = []
    if not _has_price_facts(evidence):
        missing_fields.append("price")
    if not _has_location_facts(evidence):
        missing_fields.append("location")
    if not _has_category_facts(evidence):
        missing_fields.append("category")
    if not _has_deadline_facts(evidence):
        missing_fields.append("deadline")

    needs_enrichment = bool(missing_fields)
    return LotEnrichmentRequirementEvaluation(
        needs_enrichment=needs_enrichment,
        missing_fields=missing_fields,
        reason_category="missing_first_pass_evidence" if needs_enrichment else "ready_for_scoring",
    )


def classify_lot_enrichment(
    record: AuctionLotRecord,
    detail_cache: AuctionLotDetailCache | None = None,
) -> LotEnrichmentRequirementEvaluation:
    return evaluate_lot_enrichment_requirements(build_lot_evidence(record, detail_cache))


def build_lot_enrichment_candidate_statement(
    *,
    source_code: str | None = None,
    current_time: datetime | None = None,
    limit: int | None = 50,
):
    current_time = current_time or datetime.now(UTC)
    statement = (
        select(AuctionLotRecord)
        .join(AuctionSourceState, AuctionSourceState.code == AuctionLotRecord.source_code)
        .where(AuctionLotRecord.enrichment_requested_at.is_not(None))
        .where(
            or_(
                AuctionLotRecord.next_enrichment_attempt_at.is_(None),
                AuctionLotRecord.next_enrichment_attempt_at <= current_time,
            )
        )
        .where(
            or_(
                AuctionLotRecord.enrichment_claimed_at.is_(None),
                AuctionLotRecord.enrichment_claim_expires_at.is_(None),
                AuctionLotRecord.enrichment_claim_expires_at <= current_time,
            )
        )
        .where(AuctionSourceState.enabled.is_(True))
        .where(~_terminal_status_predicate())
        .order_by(AuctionLotRecord.enrichment_requested_at.asc(), AuctionLotRecord.id.asc())
    )
    if source_code:
        statement = statement.where(AuctionLotRecord.source_code == source_code)
    if limit is not None:
        statement = statement.limit(max(0, limit))
    return statement


async def list_lot_enrichment_candidates(
    session: AsyncSession,
    *,
    source_code: str | None = None,
    current_time: datetime | None = None,
    limit: int = DEFAULT_ENRICHMENT_CANDIDATE_LIMIT,
) -> list[AuctionLotRecord]:
    current_time = current_time or datetime.now(UTC)
    statement = build_lot_enrichment_candidate_statement(source_code=source_code, current_time=current_time, limit=None)
    records = (await session.scalars(statement)).all()
    return collect_lot_enrichment_candidates(records, current_time=current_time, limit=limit)


def collect_lot_enrichment_candidates(
    records: Sequence[AuctionLotRecord],
    *,
    current_time: datetime | None = None,
    limit: int | None = DEFAULT_ENRICHMENT_CANDIDATE_LIMIT,
) -> list[AuctionLotRecord]:
    current_time = current_time or datetime.now(UTC)
    eligible = [record for record in records if _is_enrichment_candidate(record, current_time=current_time)]
    eligible.sort(key=lambda record: build_lot_enrichment_priority_key(record, current_time=current_time))
    if limit is None:
        return eligible
    if limit <= 0:
        return []
    return eligible[:limit]


def schedule_lot_enrichment(
    record: AuctionLotRecord,
    evaluation: LotEnrichmentRequirementEvaluation,
    *,
    requested_at: datetime | None = None,
    force: bool = False,
) -> bool:
    if evaluation.needs_enrichment:
        next_requested_at = requested_at or datetime.now(UTC)
        if not force and record.enrichment_requested_at is not None:
            return False
        record.enrichment_requested_at = next_requested_at
        return True
    if record.enrichment_requested_at is None and record.next_enrichment_attempt_at is None and not record.last_enrichment_error:
        return False
    record.enrichment_requested_at = None
    record.next_enrichment_attempt_at = None
    record.last_enrichment_error = None
    return True


async def dry_run_lot_enrichment_candidates(
    session: AsyncSession,
    *,
    source_code: str | None = None,
    limit: int = DEFAULT_ENRICHMENT_CANDIDATE_LIMIT,
) -> LotEnrichmentDryRunResult:
    now = datetime.now(UTC)
    candidates = await list_lot_enrichment_candidates(session, source_code=source_code, current_time=now, limit=limit)
    evaluations = [classify_lot_enrichment(record) for record in candidates]
    needs_enrichment_count = sum(1 for evaluation in evaluations if evaluation.needs_enrichment)
    candidate_record_ids = [record.id for record in candidates if record.id is not None]
    candidate_row_ids = [record.datagrid_row.get("row_id") for record in candidates if isinstance(record.datagrid_row, dict)]
    return LotEnrichmentDryRunResult(
        candidate_count=len(candidates),
        processed_count=len(candidates),
        needs_enrichment_count=needs_enrichment_count,
        ready_for_scoring_count=len(candidates) - needs_enrichment_count,
        candidate_record_ids=candidate_record_ids,
        candidate_row_ids=[row_id for row_id in candidate_row_ids if isinstance(row_id, str) and row_id],
    )


async def execute_lot_enrichment_candidates(
    session: AsyncSession,
    *,
    source_code: str | None = None,
    limit: int = DEFAULT_ENRICHMENT_CANDIDATE_LIMIT,
) -> LotEnrichmentExecutionResult:
    now = datetime.now(UTC)
    candidates = await claim_lot_enrichment_candidates(
        session,
        source_code=source_code,
        current_time=now,
        limit=limit,
    )
    processed_count = 0
    fetched_count = 0
    cleared_count = 0
    still_missing_count = 0
    skipped_count = 0
    candidate_record_ids: list[int] = []

    for record in candidates:
        processed_count += 1
        if record.id is None:
            skipped_count += 1
            continue
        candidate_record_ids.append(record.id)
        evaluation_before = classify_lot_enrichment(record)
        if not evaluation_before.needs_enrichment:
            if schedule_lot_enrichment(record, evaluation_before):
                cleared_count += 1
            else:
                skipped_count += 1
            _release_lot_enrichment_claim(record)
            continue

        attempt_marked = _mark_enrichment_attempt(record, now=now)
        detail_cache_before = await session.scalar(
            select(AuctionLotDetailCache).where(AuctionLotDetailCache.lot_record_id == record.id)
        )
        fetched_at_before = detail_cache_before.fetched_at if detail_cache_before is not None else None
        detail_cache = await ensure_lot_detail_cache(session, record, refresh=True)
        fetched_count += 1
        evaluation_after = evaluate_lot_enrichment_requirements(build_lot_evidence(record, detail_cache))
        if evaluation_after.needs_enrichment:
            _schedule_lot_retry(
                record,
                now=now,
                reason=_enrichment_failure_reason(evaluation_after, detail_cache, fetched_at_before=fetched_at_before),
            )
            _release_lot_enrichment_claim(record)
            if not attempt_marked:
                skipped_count += 1
            still_missing_count += 1
            continue

        if schedule_lot_enrichment(record, evaluation_after):
            cleared_count += 1
        _release_lot_enrichment_claim(record)

    return LotEnrichmentExecutionResult(
        candidate_count=len(candidates),
        processed_count=processed_count,
        fetched_count=fetched_count,
        cleared_count=cleared_count,
        still_missing_count=still_missing_count,
        skipped_count=skipped_count,
        candidate_record_ids=candidate_record_ids,
    )


def _is_enrichment_candidate(record: AuctionLotRecord, *, current_time: datetime | None = None) -> bool:
    current_time = current_time or datetime.now(UTC)
    next_retry = getattr(record, "next_enrichment_attempt_at", None)
    claim_expires_at = getattr(record, "enrichment_claim_expires_at", None)
    return (
        record.enrichment_requested_at is not None
        and (next_retry is None or next_retry <= current_time)
        and (
            getattr(record, "enrichment_claimed_at", None) is None
            or claim_expires_at is None
            or claim_expires_at <= current_time
        )
        and not _is_terminal_status(record.status)
    )


def _candidate_sort_key(record: AuctionLotRecord) -> tuple[object, ...]:
    return build_lot_enrichment_priority_key(record)


def build_lot_enrichment_priority_key(
    record: AuctionLotRecord,
    *,
    current_time: datetime | None = None,
) -> tuple[object, ...]:
    current_time = current_time or datetime.now(UTC)
    rating_score = int(getattr(record, "rating_score", 0) or 0)
    deadline_hours = _candidate_hours_to_deadline(record, current_time=current_time)
    deadline_bucket = 0 if deadline_hours is not None else 1
    deadline_value = deadline_hours if deadline_hours is not None else 0
    freshness_value = _freshness_priority_value(getattr(record, "last_seen_at", None))
    requested_at = getattr(record, "enrichment_requested_at", None) or datetime.min.replace(tzinfo=UTC)
    return (-rating_score, deadline_bucket, deadline_value, freshness_value, requested_at, record.id or 0)


def _terminal_status_predicate():
    status_text = func.lower(func.coalesce(AuctionLotRecord.status, ""))
    return or_(*(status_text.contains(marker) for marker in TERMINAL_LOT_STATUS_MARKERS))


def _is_terminal_status(status: str | None) -> bool:
    if not isinstance(status, str):
        return False
    normalized = status.strip().lower()
    if not normalized:
        return False
    return any(marker in normalized for marker in TERMINAL_LOT_STATUS_MARKERS)


def _mark_enrichment_attempt(record: AuctionLotRecord, *, now: datetime) -> bool:
    record.last_enrichment_attempt_at = now
    record.enrichment_attempt_count = int(getattr(record, "enrichment_attempt_count", 0) or 0) + 1
    return True


def _schedule_lot_retry(record: AuctionLotRecord, *, now: datetime, reason: str | None) -> None:
    attempt_count = int(getattr(record, "enrichment_attempt_count", 0) or 0)
    record.last_enrichment_error = reason
    record.next_enrichment_attempt_at = _next_enrichment_attempt_at(now, attempt_count=attempt_count)
    record.enrichment_requested_at = record.enrichment_requested_at or now


async def claim_lot_enrichment_candidates(
    session: AsyncSession,
    *,
    source_code: str | None = None,
    current_time: datetime | None = None,
    limit: int = DEFAULT_ENRICHMENT_CANDIDATE_LIMIT,
    worker_id: str = ENRICHMENT_WORKER_ID,
    lease_seconds: int = DEFAULT_ENRICHMENT_CLAIM_SECONDS,
) -> list[AuctionLotRecord]:
    current_time = current_time or datetime.now(UTC)
    statement = build_lot_enrichment_candidate_statement(source_code=source_code, current_time=current_time, limit=None)
    statement = statement.with_for_update(skip_locked=True, of=AuctionLotRecord)
    records = (await session.scalars(statement)).all()
    claimed = collect_lot_enrichment_candidates(records, current_time=current_time, limit=limit)
    if not claimed:
        return []
    claim_expires_at = current_time + timedelta(seconds=max(1, lease_seconds))
    for record in claimed:
        record.enrichment_claimed_at = current_time
        record.enrichment_claimed_by = worker_id
        record.enrichment_claim_expires_at = claim_expires_at
    await session.flush()
    return claimed


def _enrichment_failure_reason(
    evaluation: LotEnrichmentRequirementEvaluation,
    detail_cache: AuctionLotDetailCache | None,
    *,
    fetched_at_before: datetime | None,
) -> str:
    if detail_cache is None:
        return "detail_refresh_failed"
    if fetched_at_before is not None and detail_cache.fetched_at == fetched_at_before:
        return "detail_refresh_failed"
    missing = ",".join(evaluation.missing_fields)
    return f"missing_first_pass_evidence:{missing}" if missing else "missing_first_pass_evidence"


def _next_enrichment_attempt_at(now: datetime, *, attempt_count: int) -> datetime:
    exponent = max(0, attempt_count - 1)
    delay_seconds = min(ENRICHMENT_BACKOFF_BASE_SECONDS * (2**exponent), ENRICHMENT_BACKOFF_MAX_SECONDS)
    return now + timedelta(seconds=delay_seconds)


def _release_lot_enrichment_claim(record: AuctionLotRecord) -> None:
    record.enrichment_claimed_at = None
    record.enrichment_claimed_by = None
    record.enrichment_claim_expires_at = None


def _candidate_hours_to_deadline(record: AuctionLotRecord, *, current_time: datetime) -> int | None:
    deadline_text = _candidate_deadline_text(record)
    if not deadline_text:
        return None
    deadline = _parse_deadline(deadline_text)
    if deadline is None:
        return None
    remaining_seconds = (deadline - current_time.replace(tzinfo=None)).total_seconds()
    return int(remaining_seconds // 3600)


def _candidate_deadline_text(record: AuctionLotRecord) -> str | None:
    row = record.datagrid_row if isinstance(record.datagrid_row, dict) else {}
    normalized_item = record.normalized_item if isinstance(record.normalized_item, dict) else {}
    normalized_auction = normalized_item.get("auction") if isinstance(normalized_item.get("auction"), dict) else {}
    normalized_lot = normalized_item.get("lot") if isinstance(normalized_item.get("lot"), dict) else {}
    return _first_text(
        row.get("application_deadline"),
        row.get("auction_date"),
        normalized_auction.get("application_deadline"),
        normalized_auction.get("auction_date"),
        normalized_lot.get("application_deadline"),
        normalized_lot.get("auction_date"),
    )


def _freshness_priority_value(last_seen_at: datetime | None) -> float:
    if last_seen_at is None:
        return float("inf")
    if last_seen_at.tzinfo is None:
        last_seen_at = last_seen_at.replace(tzinfo=UTC)
    return -last_seen_at.timestamp()


def _first_text(*values: object) -> str | None:
    for value in values:
        if isinstance(value, str):
            normalized = value.strip()
            if normalized:
                return normalized
    return None


def _parse_deadline(value: str) -> datetime | None:
    normalized = value.strip()
    for pattern in DEADLINE_PATTERNS:
        try:
            return datetime.strptime(normalized[:19], pattern)
        except ValueError:
            continue
    return None


def _has_price_facts(evidence: LotEvidence) -> bool:
    return any(
        [
            evidence.price.current_price is not None,
            evidence.price.initial_price is not None,
            evidence.price.minimum_price is not None,
            evidence.price.market_value is not None,
        ]
    )


def _has_location_facts(evidence: LotEvidence) -> bool:
    return any(
        [
            _has_text(evidence.location.region),
            _has_text(evidence.location.city),
            _has_text(evidence.location.address),
            _has_text(evidence.location.coordinates),
        ]
    )


def _has_category_facts(evidence: LotEvidence) -> bool:
    return any(
        [
            _has_text(evidence.category.category),
            _has_text(evidence.category.model_category),
        ]
    )


def _has_deadline_facts(evidence: LotEvidence) -> bool:
    return any(
        [
            _has_text(evidence.deadlines.application_deadline),
            _has_text(evidence.deadlines.auction_date),
            _has_text(evidence.deadlines.application_start),
            evidence.deadlines.hours_to_deadline is not None,
        ]
    )


def _has_text(value: str | None) -> bool:
    return isinstance(value, str) and bool(value.strip())
