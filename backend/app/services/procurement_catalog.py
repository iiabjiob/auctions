from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procurement import ProcurementLotRecord
from app.schemas.procurements import ProcurementAttractiveness, ProcurementLotListResponse, ProcurementLotResponse


async def list_procurement_lots(
    session: AsyncSession,
    *,
    source: str | None = "zakupki",
    law: str | None = None,
    status: str | None = None,
    min_price: Decimal | None = None,
    max_price: Decimal | None = None,
    min_score: int | None = None,
    only_new: bool = False,
    search: str | None = None,
    page: int = 1,
    page_size: int = 100,
) -> ProcurementLotListResponse:
    filters = []
    if source:
        filters.append(ProcurementLotRecord.source_code == source)
    if law:
        filters.append(ProcurementLotRecord.law == law)
    if status:
        filters.append(ProcurementLotRecord.status.ilike(f"%{status}%"))
    if min_price is not None:
        filters.append(ProcurementLotRecord.initial_price_value >= min_price)
    if max_price is not None:
        filters.append(ProcurementLotRecord.initial_price_value <= max_price)
    if min_score is not None:
        filters.append(ProcurementLotRecord.attractiveness_score >= min_score)
    if only_new:
        filters.append(ProcurementLotRecord.is_new.is_(True))
    if search:
        pattern = f"%{search}%"
        filters.append(
            or_(
                ProcurementLotRecord.search_text.ilike(pattern),
                ProcurementLotRecord.registry_number.ilike(pattern),
            )
        )

    total_statement = select(func.count()).select_from(ProcurementLotRecord)
    statement = select(ProcurementLotRecord)
    if filters:
        total_statement = total_statement.where(*filters)
        statement = statement.where(*filters)

    total = (await session.execute(total_statement)).scalar_one()
    rows = (
        (
            await session.execute(
                statement.order_by(
                    ProcurementLotRecord.attractiveness_score.desc(),
                    ProcurementLotRecord.publication_at.desc().nulls_last(),
                    ProcurementLotRecord.id.desc(),
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )

    return ProcurementLotListResponse(
        items=[procurement_lot_response(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


def procurement_lot_response(record: ProcurementLotRecord) -> ProcurementLotResponse:
    return ProcurementLotResponse(
        id=record.id,
        source=record.source_code,
        external_id=record.external_id,
        registry_number=record.registry_number,
        law=record.law,
        title=record.title,
        status=record.status,
        customer_name=record.customer_name,
        organizer_name=record.organizer_name,
        procedure_type=record.procedure_type,
        platform_name=record.platform_name,
        region=record.region,
        initial_price=record.initial_price,
        initial_price_value=record.initial_price_value,
        currency=record.currency,
        publication_at=record.publication_at,
        application_deadline_at=record.application_deadline_at,
        notice_url=record.notice_url,
        is_new=record.is_new,
        attractiveness=ProcurementAttractiveness(
            score=record.attractiveness_score,
            level=record.attractiveness_level,
            reasons=list(record.attractiveness_reasons or []),
        ),
        first_seen_at=record.first_seen_at,
        last_seen_at=record.last_seen_at,
    )
