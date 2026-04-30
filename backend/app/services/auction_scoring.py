from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from app.models.auction import AuctionLotDetailCache, AuctionLotRecord, AuctionLotWorkItem
from app.schemas.analysis_config import OwnerScoringProfile, ScoringDimensionWeights
from app.schemas.auctions import AuctionListItem, LotEconomyResponse, LotRating
from app.services.auction_analysis import LegalRiskRules, build_lot_analysis
from app.services.auction_datagrid_payload import validate_datagrid_row_payload
from app.services.auction_values import parse_price


SCORING_VERSION = "deterministic-v2"


@dataclass
class ScoreDimension:
    key: str
    label: str
    score: int = 0
    reasons: list[str] = field(default_factory=list)

    def add(self, points: int, reason: str) -> None:
        self.score += points
        self.reasons.append(reason)


@dataclass
class ScoreCap:
    key: str
    label: str
    max_score: int
    reason: str


@dataclass
class ScoreComputation:
    rating: LotRating
    base_score: int
    raw_score: int
    dimensions: dict[str, ScoreDimension]
    caps: list[ScoreCap]


def calculate_list_lot_rating(item: AuctionListItem, price_value: Decimal | None) -> LotRating:
    scoring_time = datetime.now(UTC)
    base_score = 50
    dimensions = _new_score_dimensions()
    reasons: list[str] = ["Базовая оценка до подключения пользовательской модели рейтинга"]
    status = (item.lot.status or "").lower()

    if "приём" in status or "прием" in status:
        dimensions["urgency"].add(25, "Идет прием заявок")
        reasons.append("Идет прием заявок")
    if "отмен" in status:
        dimensions["risk"].add(-45, "Лот отменен")
        reasons.append("Лот отменен")
    if price_value is not None:
        dimensions["data_quality"].add(10, "Цена распознана и доступна для фильтрации")
        reasons.append("Цена распознана и доступна для фильтрации")
    if item.auction.application_deadline:
        dimensions["urgency"].add(5, "Есть срок окончания приема заявок")
        reasons.append("Есть срок окончания приема заявок")

    raw_score = base_score + _weighted_dimension_total(dimensions, ScoringDimensionWeights())
    caps = _build_list_score_caps(item=item, price_value=price_value)
    score = _apply_score_caps(raw_score, caps)
    reasons.extend(cap.reason for cap in caps)
    if score >= 75:
        level = "high"
    elif score >= 45:
        level = "medium"
    else:
        level = "low"

    input_hash = build_score_input_hash(
        mode="list",
        normalized_item=item.model_dump(mode="json"),
        price_value=price_value,
    )
    breakdown = _build_score_breakdown(
        mode="list",
        score=score,
        level=level,
        reasons=reasons,
        inputs={
            "has_price": price_value is not None,
            "has_application_deadline": bool(item.auction.application_deadline),
            "status": item.lot.status,
        },
        base_score=base_score,
        raw_score=raw_score,
        dimensions=dimensions,
        caps=caps,
        dimension_weights=ScoringDimensionWeights(),
    )
    return LotRating(
        score=score,
        level=level,
        reasons=reasons,
        scoring_version=SCORING_VERSION,
        scored_at=scoring_time,
        input_hash=input_hash,
        breakdown=breakdown,
    )


def recalculate_record_rating(
    record: AuctionLotRecord,
    detail_cache: AuctionLotDetailCache | None,
    work_item: AuctionLotWorkItem | None = None,
    *,
    category_keywords: dict[str, tuple[str, ...]] | None = None,
    exclusion_keywords: tuple[str, ...] | None = None,
    legal_risk_rules: LegalRiskRules | None = None,
    owner_profile: OwnerScoringProfile | None = None,
    dimension_weights: ScoringDimensionWeights | None = None,
    force: bool = False,
) -> LotRating:
    scoring_time = datetime.now(UTC)
    if detail_cache is not None:
        sync_record_from_detail_cache(record, detail_cache)
    row = validate_datagrid_row_payload(record.datagrid_row)
    input_hash = build_record_score_input_hash(
        record,
        detail_cache,
        work_item,
        category_keywords=category_keywords,
        exclusion_keywords=exclusion_keywords,
        legal_risk_rules=legal_risk_rules,
        owner_profile=owner_profile,
        dimension_weights=dimension_weights,
    )
    if not force and record_score_is_current(record, input_hash=input_hash):
        return row.rating

    economy = calculate_lot_economy(record, work_item) if work_item else LotEconomyResponse(current_price=parse_price(record.initial_price))
    row.analysis = build_lot_analysis(
        record,
        row,
        detail_cache,
        work_item,
        economy,
        category_keywords=category_keywords,
        exclusion_keywords=exclusion_keywords,
        legal_risk_rules=legal_risk_rules,
    )
    row.model_category = row.analysis.category or row.model_category
    row.category = row.category or row.model_category
    row.market_value = work_item.market_value if work_item and work_item.market_value is not None else row.market_value
    row.platform_fee = work_item.platform_fee if work_item else None
    row.delivery_cost = work_item.delivery_cost if work_item else None
    row.dismantling_cost = work_item.dismantling_cost if work_item else None
    row.repair_cost = work_item.repair_cost if work_item else None
    row.storage_cost = work_item.storage_cost if work_item else None
    row.legal_cost = work_item.legal_cost if work_item else None
    row.other_costs = work_item.other_costs if work_item else None
    row.target_profit = work_item.target_profit if work_item else None
    row.total_expenses = economy.total_expenses
    row.full_entry_cost = economy.full_entry_cost
    row.potential_profit = economy.potential_profit
    row.roi = economy.roi
    row.market_discount = economy.market_discount if economy.market_discount is not None else row.market_discount
    row.formula_max_purchase_price = economy.max_purchase_price
    row.exclude_from_analysis = bool(work_item.exclude_from_analysis) if work_item else False
    row.exclusion_reason = work_item.exclusion_reason if work_item else None
    scoring = _calculate_record_rating(
        record,
        row,
        detail_cache,
        work_item,
        economy,
        owner_profile=owner_profile,
        dimension_weights=dimension_weights,
    )
    rating = scoring.rating
    breakdown = _build_score_breakdown(
        mode="record",
        score=rating.score,
        level=rating.level,
        reasons=rating.reasons,
        inputs={
            "has_detail_cache": detail_cache is not None,
            "detail_content_hash": detail_cache.content_hash if detail_cache else None,
            "has_work_item": work_item is not None,
            "has_market_value": work_item is not None and work_item.market_value is not None,
            "analysis_status": row.analysis.status,
            "analysis_legal_risk": row.analysis.legal_risk,
            "analysis_is_excluded": row.analysis.is_excluded,
        },
        base_score=scoring.base_score,
        raw_score=scoring.raw_score,
        dimensions=scoring.dimensions,
        caps=scoring.caps,
        dimension_weights=dimension_weights,
    )
    rating.scoring_version = SCORING_VERSION
    rating.scored_at = scoring_time
    rating.input_hash = input_hash
    rating.breakdown = breakdown
    row.rating = rating
    row.work_decision_status = work_item.decision_status if work_item else None
    record.rating_score = rating.score
    record.rating_level = rating.level
    record.scoring_version = SCORING_VERSION
    record.scored_at = scoring_time
    record.score_input_hash = input_hash
    record.score_breakdown = breakdown
    record.datagrid_row = row.model_dump(mode="json")
    return rating


def build_record_score_input_hash(
    record: AuctionLotRecord,
    detail_cache: AuctionLotDetailCache | None,
    work_item: AuctionLotWorkItem | None = None,
    *,
    category_keywords: dict[str, tuple[str, ...]] | None = None,
    exclusion_keywords: tuple[str, ...] | None = None,
    legal_risk_rules: LegalRiskRules | None = None,
    owner_profile: OwnerScoringProfile | None = None,
    dimension_weights: ScoringDimensionWeights | None = None,
) -> str:
    return build_score_input_hash(
        mode="record",
        normalized_item=record.normalized_item,
        record_status=record.status,
        record_initial_price=record.initial_price,
        record_content_hash=record.content_hash,
        detail_content_hash=detail_cache.content_hash if detail_cache else None,
        work_item=work_item,
        category_keywords=category_keywords,
        exclusion_keywords=exclusion_keywords,
        legal_risk_rules=legal_risk_rules,
        owner_profile=owner_profile,
        dimension_weights=dimension_weights,
    )


def record_score_is_current(record: AuctionLotRecord, *, input_hash: str | None = None) -> bool:
    if record.scoring_version != SCORING_VERSION:
        return False
    if not record.score_input_hash:
        return False
    return record.score_input_hash == input_hash if input_hash is not None else True


def build_score_input_hash(**payload: Any) -> str:
    payload = {"scoring_version": SCORING_VERSION, **payload}
    return hashlib.sha256(
        json.dumps(_normalize_score_payload(payload), sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def calculate_lot_economy(record: AuctionLotRecord, work_item: AuctionLotWorkItem) -> LotEconomyResponse:
    current_price = parse_price(record.initial_price)
    expense_fields = [
        work_item.platform_fee,
        work_item.delivery_cost,
        work_item.dismantling_cost,
        work_item.repair_cost,
        work_item.storage_cost,
        work_item.legal_cost,
        work_item.other_costs,
    ]
    expenses = sum((value or Decimal("0") for value in expense_fields), Decimal("0"))
    full_entry_cost = current_price + expenses if current_price is not None else None
    potential_profit = (
        work_item.market_value - full_entry_cost
        if work_item.market_value is not None and full_entry_cost is not None
        else None
    )
    roi = potential_profit / full_entry_cost if potential_profit is not None and full_entry_cost else None
    market_discount = (
        Decimal("1") - (current_price / work_item.market_value)
        if current_price is not None and work_item.market_value
        else None
    )
    max_purchase_price = (
        work_item.market_value - expenses - (work_item.target_profit or Decimal("0"))
        if work_item.market_value is not None
        else None
    )

    return LotEconomyResponse(
        current_price=current_price,
        market_value=work_item.market_value,
        total_expenses=expenses,
        full_entry_cost=full_entry_cost,
        potential_profit=potential_profit,
        roi=roi,
        market_discount=market_discount,
        target_profit=work_item.target_profit,
        max_purchase_price=max_purchase_price,
    )


def sync_record_from_detail_cache(record: AuctionLotRecord, detail_cache: AuctionLotDetailCache) -> None:
    publication_date = _publication_date_from_detail_cache(detail_cache)
    lot_details = _lot_details_from_detail_cache(detail_cache)
    auction_details = _auction_details_from_detail_cache(detail_cache)

    row = dict(record.datagrid_row or {})
    if publication_date and row.get("publication_date") != publication_date:
        row["publication_date"] = publication_date
    for key, value in auction_details.items():
        if value is not None:
            row[key] = value
    for key, value in lot_details.items():
        if value is not None:
            row[key] = value
    if lot_details.get("initial_price"):
        initial_price_value = parse_price(lot_details["initial_price"])
        row["initial_price_value"] = str(initial_price_value) if initial_price_value is not None else None
    current_price = lot_details.get("current_price") or row.get("current_price") or record.initial_price
    if current_price:
        current_price_value = parse_price(current_price)
        row["current_price"] = current_price
        row["current_price_value"] = str(current_price_value) if current_price_value is not None else None
        record.initial_price = current_price
    minimum_price = lot_details.get("minimum_price") or row.get("minimum_price")
    if minimum_price:
        minimum_price_value = parse_price(minimum_price)
        row["minimum_price"] = minimum_price
        row["minimum_price_value"] = str(minimum_price_value) if minimum_price_value is not None else None
    record.datagrid_row = row

    normalized_item = dict(record.normalized_item or {})
    auction_payload = dict(normalized_item.get("auction") or {})
    if publication_date and auction_payload.get("publication_date") != publication_date:
        auction_payload["publication_date"] = publication_date
    for key, value in auction_details.items():
        if value is not None:
            auction_payload[key] = value
    if auction_payload:
        normalized_item["auction"] = auction_payload
    lot_payload = dict(normalized_item.get("lot") or {})
    for key, value in lot_details.items():
        if value is not None:
            lot_payload[key] = value
    if lot_payload:
        normalized_item["lot"] = lot_payload
    record.normalized_item = normalized_item


def is_media_document(document: dict) -> bool:
    text = " ".join(str(document.get(key) or "") for key in ["name", "document_type", "comment", "url"]).lower()
    return bool(re.search(r"фото|photo|изображ|\.rar|\.zip|\.7z|\.jpe?g|\.png|\.webp", text))


def _new_score_dimensions() -> dict[str, ScoreDimension]:
    return {
        "economics": ScoreDimension("economics", "Экономика"),
        "risk": ScoreDimension("risk", "Риск"),
        "urgency": ScoreDimension("urgency", "Срочность"),
        "data_quality": ScoreDimension("data_quality", "Качество данных"),
        "operational_readiness": ScoreDimension("operational_readiness", "Операционная готовность"),
        "owner_fit": ScoreDimension("owner_fit", "Профиль интереса"),
        "manual_intent": ScoreDimension("manual_intent", "Ручной статус"),
    }


def _calculate_record_rating(
    record: AuctionLotRecord,
    row,
    detail_cache: AuctionLotDetailCache | None,
    work_item: AuctionLotWorkItem | None,
    economy: LotEconomyResponse,
    *,
    owner_profile: OwnerScoringProfile | None,
    dimension_weights: ScoringDimensionWeights | None,
) -> ScoreComputation:
    base_score = 35
    dimensions = _new_score_dimensions()
    reasons = ["Базовая оценка по статусу, данным площадки и ручной экономике"]
    status = (record.status or row.status or "").lower()

    if "приём" in status or "прием" in status:
        dimensions["urgency"].add(20, "Идет прием заявок")
        reasons.append("Идет прием заявок")
    if "публич" in status:
        dimensions["urgency"].add(12, "Публичное предложение")
        reasons.append("Публичное предложение")
    if "отмен" in status:
        dimensions["risk"].add(-50, "Лот отменен")
        reasons.append("Лот отменен")
    if economy.current_price is not None:
        dimensions["data_quality"].add(8, "Цена распознана")
        reasons.append("Цена распознана")

    deadline = _parse_deadline(row.application_deadline)
    if deadline:
        dimensions["urgency"].add(4, "Есть срок окончания заявок")
        remaining_hours = (deadline - datetime.now()).total_seconds() / 3600
        if 0 <= remaining_hours <= 48:
            dimensions["urgency"].add(10, "До окончания заявок меньше 48 часов")
            reasons.append("До окончания заявок меньше 48 часов")

    documents = detail_cache.documents if detail_cache else []
    if documents:
        dimensions["data_quality"].add(6, "Есть документы")
        reasons.append("Есть документы")
    elif detail_cache:
        dimensions["data_quality"].add(-10, "Документы не найдены")
        reasons.append("Документы не найдены")

    media_documents = [document for document in documents if is_media_document(document)]
    if media_documents:
        dimensions["data_quality"].add(6, "Есть фото или фотоархив")
        reasons.append("Есть фото или фотоархив")
    elif detail_cache:
        dimensions["data_quality"].add(-5, "Фото не найдены")
        reasons.append("Фото не найдены")

    if detail_cache:
        lot_detail = detail_cache.lot_detail or {}
        lot = lot_detail.get("lot") or {}
        if lot.get("inspection_order"):
            dimensions["operational_readiness"].add(4, "Есть порядок осмотра")
            reasons.append("Есть порядок осмотра")
        if lot.get("description"):
            dimensions["operational_readiness"].add(3, "Есть подробное описание")
            reasons.append("Есть подробное описание")

    if economy.market_discount is not None:
        if economy.market_discount >= Decimal("0.50"):
            dimensions["economics"].add(25, "Дисконт к рынку 50%+")
            reasons.append("Дисконт к рынку 50%+")
        elif economy.market_discount >= Decimal("0.30"):
            dimensions["economics"].add(18, "Дисконт к рынку 30%+")
            reasons.append("Дисконт к рынку 30%+")
        elif economy.market_discount >= Decimal("0.15"):
            dimensions["economics"].add(10, "Есть дисконт к рынку")
            reasons.append("Есть дисконт к рынку")

    if economy.roi is not None:
        if economy.roi >= Decimal("0.50"):
            dimensions["economics"].add(20, "ROI 50%+")
            reasons.append("ROI 50%+")
        elif economy.roi >= Decimal("0.25"):
            dimensions["economics"].add(12, "ROI 25%+")
            reasons.append("ROI 25%+")
        elif economy.roi > 0:
            dimensions["economics"].add(6, "Положительный ROI")
            reasons.append("Положительный ROI")

    if economy.potential_profit is not None and economy.potential_profit > 0:
        dimensions["economics"].add(5, "Потенциальная прибыль положительная")
        reasons.append("Потенциальная прибыль положительная")

    decision = (work_item.decision_status or "") if work_item else ""
    is_rejected = decision == "reject"
    if decision == "reject":
        dimensions["manual_intent"].add(-60, "Команда отметила отказ")
        reasons.append("Команда отметила отказ")
    elif decision in {"inspection", "bid"}:
        dimensions["manual_intent"].add(8, "Лот взят в работу")
        reasons.append("Лот взят в работу")
    elif decision in {"watch", "calculate"}:
        dimensions["manual_intent"].add(4, "Лот отмечен для проверки")
        reasons.append("Лот отмечен для проверки")

    _apply_owner_profile_dimension(
        record=record,
        row=row,
        detail_cache=detail_cache,
        work_item=work_item,
        economy=economy,
        profile=owner_profile or OwnerScoringProfile(),
        dimensions=dimensions,
    )

    raw_score = base_score + _weighted_dimension_total(dimensions, dimension_weights or ScoringDimensionWeights())
    caps = _build_record_score_caps(row=row, status=status, work_item=work_item, economy=economy)
    score = _apply_score_caps(raw_score, caps)
    reasons.extend(cap.reason for cap in caps if cap.reason not in reasons)
    if score >= 70:
        level = "high"
    elif score >= 45:
        level = "medium"
    else:
        level = "low"
    return ScoreComputation(
        rating=LotRating(score=score, level=level, reasons=reasons),
        base_score=base_score,
        raw_score=raw_score,
        dimensions=dimensions,
        caps=caps,
    )


def _apply_owner_profile_dimension(
    *,
    record: AuctionLotRecord,
    row,
    detail_cache: AuctionLotDetailCache | None,
    work_item: AuctionLotWorkItem | None,
    economy: LotEconomyResponse,
    profile: OwnerScoringProfile,
    dimensions: dict[str, ScoreDimension],
) -> None:
    dimension = dimensions["owner_fit"]
    search_text = _owner_profile_search_text(record, row, detail_cache)
    category = row.analysis.category or row.category or row.model_category
    region = row.location_region or row.location or ""
    budget_value = economy.full_entry_cost or economy.current_price

    if profile.target_regions:
        if _matches_any(region, profile.target_regions):
            dimension.add(8, "Регион соответствует профилю")
        else:
            dimension.add(-8, "Регион вне целевого профиля")

    if profile.target_categories:
        if category and _matches_any(category, profile.target_categories):
            dimension.add(10, "Категория соответствует профилю")
        else:
            dimension.add(-10, "Категория вне целевого профиля")

    if budget_value is not None:
        if profile.min_budget is not None and budget_value < profile.min_budget:
            dimension.add(-4, "Стоимость ниже целевого бюджета")
        if profile.max_budget is not None:
            if budget_value <= profile.max_budget:
                dimension.add(6, "Стоимость укладывается в бюджет")
            else:
                dimension.add(-14, "Стоимость выше бюджета")

    if profile.minimum_roi is not None:
        if economy.roi is not None and economy.roi >= profile.minimum_roi:
            dimension.add(8, "ROI соответствует профилю")
        else:
            dimension.add(-12, "ROI ниже профиля")

    if profile.minimum_market_discount is not None:
        if economy.market_discount is not None and economy.market_discount >= profile.minimum_market_discount:
            dimension.add(8, "Дисконт соответствует профилю")
        else:
            dimension.add(-10, "Дисконт ниже профиля")

    excluded_term = _match_profile_term(search_text, profile.excluded_terms)
    if excluded_term:
        dimension.add(-25, f"Профиль исключает термин: {excluded_term}")

    discouraged_term = _match_profile_term(search_text, profile.discouraged_terms)
    if discouraged_term:
        dimension.add(-8, f"Нежелательный термин по профилю: {discouraged_term}")

    if profile.legal_risk_tolerance == "low" and row.analysis.legal_risk != "low":
        dimension.add(-12, "Юридический риск выше допуска профиля")
    elif profile.legal_risk_tolerance == "medium" and row.analysis.legal_risk == "high":
        dimension.add(-12, "Юридический риск выше допуска профиля")

    if profile.require_documents:
        if row.analysis.has_documents:
            dimension.add(3, "Документы соответствуют профилю")
        else:
            dimension.add(-8, "Профиль требует документы")

    if profile.require_photos:
        if row.analysis.has_photos:
            dimension.add(3, "Фото соответствуют профилю")
        else:
            dimension.add(-8, "Профиль требует фото")

    dismantling_cost = work_item.dismantling_cost if work_item else None
    if not profile.allow_dismantling and ((dismantling_cost or Decimal("0")) > 0 or "демонтаж" in search_text):
        dimension.add(-8, "Профиль не допускает демонтаж")

    if profile.max_delivery_distance_km is not None and row.location_coordinates is None:
        dimension.add(-2, "Дистанция доставки не подтверждена")


def _weighted_dimension_total(
    dimensions: dict[str, ScoreDimension],
    weights: ScoringDimensionWeights,
) -> int:
    payload = weights.model_dump()
    total = Decimal("0")
    for key, dimension in dimensions.items():
        total += Decimal(dimension.score) * Decimal(payload.get(key, Decimal("1.0")))
    return int(total.to_integral_value())


def _owner_profile_search_text(record: AuctionLotRecord, row, detail_cache: AuctionLotDetailCache | None) -> str:
    parts = [
        record.lot_name,
        record.status,
        row.lot_name,
        row.lot_description,
        row.category,
        row.model_category,
        row.location,
        row.location_region,
        row.location_city,
        json.dumps(record.normalized_item or {}, ensure_ascii=False),
    ]
    if detail_cache is not None:
        parts.extend(
            [
                json.dumps(detail_cache.lot_detail or {}, ensure_ascii=False),
                json.dumps(detail_cache.auction_detail or {}, ensure_ascii=False),
                json.dumps(detail_cache.documents or [], ensure_ascii=False),
            ]
        )
    return " ".join(str(part or "") for part in parts).lower()


def _matches_any(value: str, expected_values: list[str]) -> bool:
    normalized_value = value.strip().lower()
    return any(expected.strip().lower() in normalized_value for expected in expected_values if expected.strip())


def _match_profile_term(search_text: str, terms: list[str]) -> str | None:
    for term in terms:
        normalized = term.strip().lower()
        if normalized and normalized in search_text:
            return normalized
    return None


def _build_list_score_caps(*, item: AuctionListItem, price_value: Decimal | None) -> list[ScoreCap]:
    status = (item.lot.status or "").lower()
    caps: list[ScoreCap] = []
    if price_value is None:
        caps.append(ScoreCap("missing_price", "Цена не распознана", 69, "Цена не распознана, рейтинг ограничен ниже высокого"))
    if _is_cancelled_status(status):
        caps.append(ScoreCap("cancelled", "Лот отменен", 20, "Лот отменен"))
    elif _is_non_actionable_status(status):
        caps.append(ScoreCap("non_actionable", "Лот неактивен", 20, "Лот завершен или недоступен для заявки"))
    return caps


def _build_record_score_caps(
    *,
    row,
    status: str,
    work_item: AuctionLotWorkItem | None,
    economy: LotEconomyResponse,
) -> list[ScoreCap]:
    caps: list[ScoreCap] = []
    decision = (work_item.decision_status or "").strip().lower() if work_item else ""
    final_decision = (work_item.final_decision or "").strip().lower() if work_item and work_item.final_decision else ""
    is_manually_approved = decision == "bid" or final_decision in {"approve", "approved", "bid", "go"}

    if economy.current_price is None:
        caps.append(ScoreCap("missing_price", "Цена не распознана", 69, "Цена не распознана, рейтинг ограничен ниже высокого"))
    if row.analysis.legal_risk == "high" and not is_manually_approved:
        caps.append(ScoreCap("high_legal_risk", "Высокий юридический риск", 44, "Высокий юридический риск ограничивает рейтинг"))
    if row.analysis.is_excluded or row.exclude_from_analysis:
        caps.append(ScoreCap("excluded", "Исключение из анализа", 20, "Лот исключен из анализа"))
    if decision == "reject":
        caps.append(ScoreCap("manual_reject", "Ручной отказ", 20, "Команда отметила отказ"))
    if _is_cancelled_status(status):
        caps.append(ScoreCap("cancelled", "Лот отменен", 20, "Лот отменен"))
    elif _is_non_actionable_status(status):
        caps.append(ScoreCap("non_actionable", "Лот неактивен", 20, "Лот завершен или недоступен для заявки"))
    return caps


def _apply_score_caps(raw_score: int, caps: list[ScoreCap]) -> int:
    score = raw_score
    for cap in caps:
        score = min(score, cap.max_score)
    return max(0, min(100, score))


def _is_cancelled_status(status: str) -> bool:
    return "отмен" in status or "снят" in status


def _is_non_actionable_status(status: str) -> bool:
    return any(marker in status for marker in ("заверш", "закончен", "состоял", "состоялись", "подвед", "архив"))


def _publication_date_from_detail_cache(detail_cache: AuctionLotDetailCache | None) -> str | None:
    if detail_cache is None:
        return None
    for payload in (detail_cache.auction_detail or {}, detail_cache.lot_detail or {}):
        auction = payload.get("auction") or {}
        publication_date = auction.get("publication_date")
        if isinstance(publication_date, str) and publication_date.strip():
            return publication_date.strip()
    return None


def _lot_details_from_detail_cache(detail_cache: AuctionLotDetailCache | None) -> dict[str, str | None]:
    if detail_cache is None:
        return {}
    payload = detail_cache.lot_detail or {}
    lot = payload.get("lot") or {}
    raw_fields = payload.get("raw_fields") or []
    cadastral_market_value = _raw_field_value(
        raw_fields,
        "Кадастровая стоимость",
        "Кадастровая стоимость объекта",
        "Кадастровая стоимость имущества",
        "Кадастровая стоимость на дату оценки",
    )
    return {
        "category": _clean_text(lot.get("category")) or _raw_field_value(raw_fields, "Категория площадки", "Категория"),
        "location": _clean_text(lot.get("location")),
        "location_region": _clean_text(lot.get("region")),
        "location_city": _clean_text(lot.get("city")),
        "location_address": _clean_text(lot.get("address")),
        "location_coordinates": _clean_text(lot.get("coordinates")),
        "initial_price": _clean_text(lot.get("initial_price")),
        "current_price": _clean_text(lot.get("current_price")),
        "minimum_price": _clean_text(lot.get("minimum_price")),
        "market_value": _clean_text(lot.get("market_value")) or _clean_text(cadastral_market_value),
    }


def _auction_details_from_detail_cache(detail_cache: AuctionLotDetailCache | None) -> dict[str, str | None]:
    details = {
        "application_start": None,
        "application_deadline": None,
        "auction_date": None,
    }
    if detail_cache is None:
        return details

    for payload in (detail_cache.auction_detail or {}, detail_cache.lot_detail or {}):
        auction = payload.get("auction") or {}
        for key in details:
            details[key] = details[key] or _clean_datetime_text(auction.get(key))

        raw_fields = payload.get("raw_fields") or []
        application_start, application_deadline = _raw_datetime_range(raw_fields, "Прием заявок", "Приём заявок")
        auction_start, _auction_deadline = _raw_datetime_range(raw_fields, "Проведение торгов")
        details["application_start"] = details["application_start"] or application_start
        details["application_deadline"] = details["application_deadline"] or application_deadline
        details["auction_date"] = details["auction_date"] or auction_start

    return details


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _clean_datetime_text(value: object) -> str | None:
    cleaned = _clean_text(value)
    if not cleaned:
        return None
    return re.sub(
        r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b",
        lambda match: f"{int(match.group(1)):02d}.{int(match.group(2)):02d}.{match.group(3)}",
        cleaned,
    )


def _raw_field_value(fields: list[dict], *names: str) -> str | None:
    wanted = {name.lower().rstrip(":") for name in names}
    for field in fields:
        field_name = str(field.get("name") or "").lower().rstrip(":")
        value = field.get("value")
        if field_name in wanted and isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _raw_datetime_range(fields: list[dict], *names: str) -> tuple[str | None, str | None]:
    value = _raw_field_value(fields, *names)
    if not value:
        return None, None
    match = re.search(r"\bс\s+(.+?)\s+до\s+(.+)$", value, re.IGNORECASE)
    if not match:
        return None, _clean_datetime_text(value)
    return _clean_datetime_text(match.group(1)), _clean_datetime_text(match.group(2))


def _build_score_breakdown(
    *,
    mode: str,
    score: int,
    level: str,
    reasons: list[str],
    inputs: dict[str, Any],
    base_score: int | None = None,
    raw_score: int | None = None,
    dimensions: dict[str, ScoreDimension] | None = None,
    caps: list[ScoreCap] | None = None,
    dimension_weights: ScoringDimensionWeights | None = None,
) -> dict[str, Any]:
    weights = dimension_weights or ScoringDimensionWeights()
    return {
        "version": SCORING_VERSION,
        "mode": mode,
        "score": score,
        "level": level,
        "base_score": base_score,
        "raw_score": raw_score,
        "dimensions": _score_dimensions_payload(dimensions, weights),
        "caps": _score_caps_payload(caps),
        "dimension_weights": _normalize_score_payload(weights),
        "reasons": list(reasons),
        "inputs": _normalize_score_payload(inputs),
    }


def _score_dimensions_payload(
    dimensions: dict[str, ScoreDimension] | None,
    weights: ScoringDimensionWeights,
) -> dict[str, dict[str, Any]]:
    if not dimensions:
        return {}
    weight_payload = weights.model_dump()
    return {
        key: {
            "key": dimension.key,
            "label": dimension.label,
            "score": dimension.score,
            "weight": _normalize_score_payload(weight_payload.get(key, Decimal("1.0"))),
            "weighted_score": int((Decimal(dimension.score) * Decimal(weight_payload.get(key, Decimal("1.0")))).to_integral_value()),
            "reasons": list(dimension.reasons),
        }
        for key, dimension in dimensions.items()
    }


def _score_caps_payload(caps: list[ScoreCap] | None) -> list[dict[str, Any]]:
    if not caps:
        return []
    return [
        {
            "key": cap.key,
            "label": cap.label,
            "max_score": cap.max_score,
            "reason": cap.reason,
        }
        for cap in caps
    ]


def _normalize_score_payload(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, AuctionLotWorkItem):
        return {
            "decision_status": value.decision_status,
            "exclude_from_analysis": value.exclude_from_analysis,
            "exclusion_reason": value.exclusion_reason,
            "category_override": value.category_override,
            "max_purchase_price": _normalize_score_payload(value.max_purchase_price),
            "market_value": _normalize_score_payload(value.market_value),
            "platform_fee": _normalize_score_payload(value.platform_fee),
            "delivery_cost": _normalize_score_payload(value.delivery_cost),
            "dismantling_cost": _normalize_score_payload(value.dismantling_cost),
            "repair_cost": _normalize_score_payload(value.repair_cost),
            "storage_cost": _normalize_score_payload(value.storage_cost),
            "legal_cost": _normalize_score_payload(value.legal_cost),
            "other_costs": _normalize_score_payload(value.other_costs),
            "target_profit": _normalize_score_payload(value.target_profit),
            "analogs": _normalize_score_payload(value.analogs or []),
        }
    if is_dataclass(value) and not isinstance(value, type):
        return _normalize_score_payload(asdict(value))
    if isinstance(value, BaseModel):
        return _normalize_score_payload(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {str(key): _normalize_score_payload(item) for key, item in sorted(value.items(), key=lambda entry: str(entry[0]))}
    if isinstance(value, (list, tuple, set)):
        return [_normalize_score_payload(item) for item in value]
    return value


def _parse_deadline(value: str | None) -> datetime | None:
    if not value:
        return None
    for pattern in (
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(value[:19], pattern)
        except ValueError:
            continue
    return None
