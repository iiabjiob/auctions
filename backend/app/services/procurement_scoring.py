from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.schemas.procurements import ProcurementAttractiveness, ProcurementLotItem
from app.services.procurement_values import parse_scraped_datetime


ACTIVE_STATUS_KEYWORDS = ("подача заявок", "работа комиссии", "определение поставщика")
ATTRACTIVE_TITLE_KEYWORDS = (
    "оборудован",
    "техника",
    "спецодеж",
    "инструмент",
    "запчаст",
    "ремонт",
    "обслуживан",
    "поставка",
)


def score_procurement_lot(item: ProcurementLotItem, *, current_time: datetime | None = None) -> ProcurementAttractiveness:
    now = current_time or datetime.now(UTC)
    score = 0
    reasons: list[str] = []

    status = (item.status or "").lower()
    if any(keyword in status for keyword in ACTIVE_STATUS_KEYWORDS):
        score += 25
        reasons.append("активный этап закупки")

    deadline = parse_scraped_datetime(item.application_deadline)
    if deadline and deadline > now:
        days_left = (deadline - now).days
        if days_left <= 14:
            score += 25
            reasons.append("близкий дедлайн подачи заявок")
        else:
            score += 15
            reasons.append("прием заявок еще открыт")

    price = item.initial_price_value
    if price is not None:
        if Decimal("100000") <= price <= Decimal("50000000"):
            score += 20
            reasons.append("цена в рабочем диапазоне первичного отбора")
        elif price > 0:
            score += 10
            reasons.append("цена указана")

    title = (item.title or "").lower()
    if any(keyword in title for keyword in ATTRACTIVE_TITLE_KEYWORDS):
        score += 15
        reasons.append("предмет закупки похож на коммерчески понятный товар или услугу")

    if item.customer_name:
        score += 5
        reasons.append("заказчик определен")

    if item.law in {"44-ФЗ", "223-ФЗ"}:
        score += 5
        reasons.append(f"понятный режим {item.law}")

    score = min(score, 100)
    if score >= 80:
        level = "high"
    elif score >= 55:
        level = "medium"
    else:
        level = "low"
    return ProcurementAttractiveness(score=score, level=level, reasons=reasons)
