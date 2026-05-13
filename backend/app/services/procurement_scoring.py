from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from app.models.procurement import ProcurementLotRecord
from app.schemas.procurements import ProcurementAttractiveness, ProcurementLotItem
from app.services.procurement_values import parse_scraped_datetime


PROCUREMENT_SCORING_VERSION = "procurement-v1"
ACTIVE_STATUS_KEYWORDS = ("подача заявок", "работа комиссии", "определение поставщика")
ATTRACTIVE_TITLE_KEYWORDS = ("спецодеж", "одежд", "форма", "пошив", "текстиль", "поставка")


@dataclass(frozen=True, slots=True)
class ProcurementScoreResult:
    attractiveness: ProcurementAttractiveness
    input_hash: str
    version: str = PROCUREMENT_SCORING_VERSION
    scored_at: datetime | None = None


def apply_procurement_score(
    record: ProcurementLotRecord,
    *,
    current_time: datetime | None = None,
) -> ProcurementScoreResult:
    result = score_procurement_record(record, current_time=current_time)
    record.attractiveness_score = result.attractiveness.score
    record.attractiveness_level = result.attractiveness.level
    record.attractiveness_reasons = result.attractiveness.reasons
    record.scoring_version = result.version
    record.scoring_input_hash = result.input_hash
    record.scored_at = result.scored_at
    return result


def score_procurement_record(
    record: ProcurementLotRecord,
    *,
    current_time: datetime | None = None,
) -> ProcurementScoreResult:
    now = current_time or datetime.now(UTC)
    input_payload = _record_score_input(record)
    reasons: list[str] = []

    score = (
        _score_profitability(record, reasons)
        + _score_absolute_profit(record, reasons)
        + _score_deadline(record.application_deadline_at, now, reasons)
        + _score_specification(record, reasons)
        + _score_production_readiness(record, reasons)
        + _score_customer(record, reasons)
        + _score_competition(record, reasons)
    )
    score = _apply_degradations(record, now, score, reasons)
    score = max(0, min(100, score))
    return ProcurementScoreResult(
        attractiveness=ProcurementAttractiveness(score=score, level=_level_for_score(score), reasons=reasons),
        input_hash=_input_hash(input_payload),
        scored_at=now,
    )


def score_procurement_lot(item: ProcurementLotItem, *, current_time: datetime | None = None) -> ProcurementAttractiveness:
    now = current_time or datetime.now(UTC)
    record = ProcurementLotRecord(
        source_code=item.source,
        external_id=item.external_id,
        registry_number=item.registry_number,
        law=item.law,
        title=item.title,
        status=item.status,
        customer_name=item.customer_name,
        customer_inn=item.customer_inn,
        procedure_type=item.procedure_type,
        platform_name=item.platform_name,
        initial_price_value=item.initial_price_value,
        application_deadline_at=parse_scraped_datetime(item.application_deadline),
        documents_url=item.documents_url,
        specification_url=item.specification_url,
        documentation_present=item.documentation_present,
        matched_keywords=[],
        excluded_keywords=[],
        attractiveness_score=0,
        attractiveness_level="reject",
        attractiveness_reasons=[],
        normalized_item={},
        raw_item={},
    )
    return score_procurement_record(record, current_time=now).attractiveness


def _score_profitability(record: ProcurementLotRecord, reasons: list[str]) -> int:
    profitability = record.profitability
    if profitability is None:
        fallback = 10 if record.category and not record.excluded_keywords else 4
        reasons.append("нет расчета маржинальности, применена первичная эвристика")
        return fallback
    if profitability >= Decimal("0.25"):
        reasons.append("маржинальность выше 25%")
        return 30
    if profitability >= Decimal("0.15"):
        reasons.append("маржинальность выше 15%")
        return 22
    if profitability > 0:
        reasons.append("положительная маржинальность")
        return 12
    reasons.append("отрицательная или нулевая маржинальность")
    return 0


def _score_absolute_profit(record: ProcurementLotRecord, reasons: list[str]) -> int:
    profit = record.net_profit
    if profit is None:
        price = record.initial_price_value or Decimal("0")
        if price >= Decimal("1000000"):
            reasons.append("нет расчета прибыли, НМЦК достаточная для первичного интереса")
            return 8
        return 3 if price > 0 else 0
    if profit >= Decimal("500000"):
        reasons.append("чистая прибыль выше 500k")
        return 15
    if profit >= Decimal("100000"):
        reasons.append("чистая прибыль выше 100k")
        return 10
    if profit > 0:
        reasons.append("чистая прибыль положительная")
        return 5
    reasons.append("чистая прибыль отрицательная или нулевая")
    return 0


def _score_deadline(deadline: datetime | None, now: datetime, reasons: list[str]) -> int:
    if deadline is None:
        reasons.append("дедлайн подачи не найден")
        return 5
    business_days = _business_days_until(now, deadline)
    if business_days < 0:
        reasons.append("дедлайн подачи уже прошел")
        return 0
    if business_days < 2:
        reasons.append("до дедлайна меньше 2 рабочих дней")
        return 0
    if business_days <= 4:
        reasons.append("сжатый, но возможный дедлайн подачи")
        return 8
    reasons.append("дедлайн подачи реалистичный")
    return 15


def _score_specification(record: ProcurementLotRecord, reasons: list[str]) -> int:
    score = 0
    if record.documentation_present or record.documents_url or record.specification_url:
        score += 8
        reasons.append("документация доступна")
    else:
        score += 2
        reasons.append("нет подтвержденной документации")
    if record.certificate_requirements:
        score += 7
        reasons.append("требования к сертификатам понятны")
    else:
        score += 3
        reasons.append("нет ясности по сертификатам")
    return score


def _score_production_readiness(record: ProcurementLotRecord, reasons: list[str]) -> int:
    score = 0
    if record.category and not record.excluded_keywords:
        score += 5
        reasons.append("категория подходит под производство")
    if record.quantity is not None and record.unit_nmck is not None:
        score += 3
        reasons.append("есть количество и цена единицы")
    if _scenario_complete(record):
        score += 2
        reasons.append("калькулятор заполнен")
    return score


def _score_customer(record: ProcurementLotRecord, reasons: list[str]) -> int:
    score = 0
    if record.customer_inn:
        score += 5
        reasons.append("ИНН заказчика определен")
    if record.customer_name:
        score += 3
        reasons.append("заказчик определен")
    if record.law in {"44-ФЗ", "44-FZ", "223-ФЗ", "223-FZ"}:
        score += 2
        reasons.append(f"понятный режим {record.law}")
    return score


def _score_competition(record: ProcurementLotRecord, reasons: list[str]) -> int:
    status = (record.status or "").lower()
    if any(keyword in status for keyword in ACTIVE_STATUS_KEYWORDS):
        reasons.append("активный этап закупки")
        return 4
    if record.platform_name or record.procedure_type:
        reasons.append("тип процедуры или площадка определены")
        return 3
    return 2


def _apply_degradations(record: ProcurementLotRecord, now: datetime, score: int, reasons: list[str]) -> int:
    if record.excluded_keywords:
        reasons.append(f"исключающие ключевые слова: {', '.join(record.excluded_keywords[:3])}")
        score = min(score, 25)
    if record.documentation_present is False and not (record.documents_url or record.specification_url):
        score -= 15
        reasons.append("штраф за отсутствие документации")
    if record.category and not record.certificate_requirements:
        score -= 8
        reasons.append("штраф за неясные сертификаты")
    if record.application_deadline_at is not None and _business_days_until(now, record.application_deadline_at) < 2:
        score -= 20
        reasons.append("штраф за срочный дедлайн")
    if _production_period_unrealistic(record, now):
        score -= 10
        reasons.append("штраф за нереалистичный производственный период")
    if _cash_gap_too_high(record):
        score -= 15
        reasons.append("штраф за высокий кассовый разрыв")
    return score


def _production_period_unrealistic(record: ProcurementLotRecord, now: datetime) -> bool:
    if record.application_deadline_at is None or record.quantity is None:
        return False
    business_days = _business_days_until(now, record.application_deadline_at)
    return business_days < 5 and record.quantity >= Decimal("1000")


def _cash_gap_too_high(record: ProcurementLotRecord) -> bool:
    if record.cash_gap_peak is None:
        return False
    revenue = record.initial_price_value
    if revenue is None and record.quantity is not None and record.unit_nmck is not None:
        revenue = record.quantity * record.unit_nmck
    if revenue is None or revenue <= 0:
        return record.cash_gap_peak > Decimal("500000")
    return record.cash_gap_peak > revenue * Decimal("0.5")


def _scenario_complete(record: ProcurementLotRecord) -> bool:
    scenario = (record.calculator_scenarios or {}).get("cautious")
    return isinstance(scenario, dict) and scenario.get("complete") is True


def _business_days_until(now: datetime, deadline: datetime) -> int:
    if deadline <= now:
        return -1
    day = now.date()
    end = deadline.date()
    count = 0
    while day < end:
        day += timedelta(days=1)
        if day.weekday() < 5:
            count += 1
    return count


def _level_for_score(score: int) -> str:
    if score >= 80:
        return "priority"
    if score >= 60:
        return "watch"
    if score >= 40:
        return "low"
    return "reject"


def _record_score_input(record: ProcurementLotRecord) -> dict[str, Any]:
    return {
        "version": PROCUREMENT_SCORING_VERSION,
        "category": record.category,
        "excluded_keywords": list(record.excluded_keywords or []),
        "documentation_present": record.documentation_present,
        "certificate_requirements": record.certificate_requirements,
        "deadline": record.application_deadline_at.isoformat() if record.application_deadline_at else None,
        "quantity": str(record.quantity) if record.quantity is not None else None,
        "unit_nmck": str(record.unit_nmck) if record.unit_nmck is not None else None,
        "initial_price_value": str(record.initial_price_value) if record.initial_price_value is not None else None,
        "net_profit": str(record.net_profit) if record.net_profit is not None else None,
        "profitability": str(record.profitability) if record.profitability is not None else None,
        "roi": str(record.roi) if record.roi is not None else None,
        "cash_gap_peak": str(record.cash_gap_peak) if record.cash_gap_peak is not None else None,
        "customer_inn": record.customer_inn,
        "customer_name": record.customer_name,
        "law": record.law,
        "status": record.status,
        "platform_name": record.platform_name,
        "procedure_type": record.procedure_type,
        "calculator_scenarios": record.calculator_scenarios or {},
    }


def _input_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()
