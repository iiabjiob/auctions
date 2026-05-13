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
        customer_inn=record.customer_inn,
        organizer_name=record.organizer_name,
        procedure_type=record.procedure_type,
        platform_name=record.platform_name,
        region=record.region,
        delivery_region=record.delivery_region,
        delivery_address=record.delivery_address,
        initial_price=record.initial_price,
        initial_price_value=record.initial_price_value,
        currency=record.currency,
        publication_at=record.publication_at,
        application_deadline_at=record.application_deadline_at,
        notice_url=record.notice_url,
        specification_url=record.specification_url,
        documents_url=record.documents_url,
        certificate_requirements=record.certificate_requirements,
        documentation_present=record.documentation_present,
        is_new=record.is_new,
        category=record.category,
        matched_keywords=list(record.matched_keywords or []),
        excluded_keywords=list(record.excluded_keywords or []),
        filter_reason=record.filter_reason,
        attractiveness=ProcurementAttractiveness(
            score=record.attractiveness_score,
            level=record.attractiveness_level,
            reasons=list(record.attractiveness_reasons or []),
        ),
        scoring_version=record.scoring_version,
        scoring_input_hash=record.scoring_input_hash,
        scored_at=record.scored_at,
        workflow_status=record.workflow_status,
        assignee=record.assignee,
        comment=record.comment,
        final_decision=record.final_decision,
        rejection_reason=record.rejection_reason,
        bid_security_amount=record.bid_security_amount,
        contract_security_amount=record.contract_security_amount,
        prepayment_percent=record.prepayment_percent,
        payment_terms=record.payment_terms,
        quantity=record.quantity,
        unit_nmck=record.unit_nmck,
        cost_realistic=record.cost_realistic,
        cost_cautious=record.cost_cautious,
        net_profit=record.net_profit,
        profitability=record.profitability,
        roi=record.roi,
        cash_gap_peak=record.cash_gap_peak,
        calculator_inputs=dict(record.calculator_inputs or {}),
        calculator_scenarios=dict(record.calculator_scenarios or {}),
        first_seen_at=record.first_seen_at,
        last_seen_at=record.last_seen_at,
    )
