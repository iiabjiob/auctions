from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Mapping, Sequence
import re

from app.models.auction import AuctionLotDetailCache, AuctionLotRecord, AuctionLotWorkItem
from app.schemas.auctions import LotAnalysis, LotDatagridRow, LotEconomyResponse


DEFAULT_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Спецтехника": (
        "экскаватор",
        "погрузчик",
        "фронтальный погрузчик",
        "мини-погрузчик",
        "бульдозер",
        "кран",
        "башенный кран",
        "автокран",
        "манипулятор",
        "самосвал",
        "тягач",
        "трактор",
        "каток",
        "грейдер",
        "буровая установка",
        "автобетононасос",
        "бетономешалка",
    ),
    "Оборудование": (
        "дизельный генератор",
        "дизель-генератор",
        "дгу",
        "электростанция",
        "компрессор",
        "сварочный аппарат",
        "станок",
        "производственная линия",
        "насосная станция",
        "трансформатор",
        "котельная",
    ),
    "Земля и базы": (
        "земельный участок",
        "производственная база",
        "склад",
        "ангар",
        "цех",
        "промышленное помещение",
        "нежилое здание",
        "имущественный комплекс",
    ),
}

DEFAULT_EXCLUSION_KEYWORDS: tuple[str, ...] = (
    "дебиторская задолженность",
    "права требования",
    "право требования",
    "доли в ооо",
    "доля в ооо",
    "акции",
    "товарные знаки",
    "товарный знак",
    "бытовая мебель",
    "одежда",
    "личные вещи",
    "квартира",
    "квартиры",
    "легковой автомобиль",
    "легковые автомобили",
)

@dataclass(frozen=True)
class LegalRiskRules:
    high_keywords: tuple[str, ...]
    medium_keywords: tuple[str, ...]
    medium_categories: tuple[str, ...]


DEFAULT_LEGAL_RISK_RULES = LegalRiskRules(
    high_keywords=(
        "обремен",
        "сервитут",
        "арест",
        "залог",
        "оспарив",
        "право требования",
        "права требования",
        "дебитор",
        "доля в ооо",
        "акции",
        "товарный знак",
        "товарные знаки",
    ),
    medium_keywords=(
        "земельный участок",
        "нежилое здание",
        "имущественный комплекс",
        "аренда",
        "незаверш",
    ),
    medium_categories=("Земля и базы",),
)


def build_lot_analysis(
    record: AuctionLotRecord,
    row: LotDatagridRow,
    detail_cache: AuctionLotDetailCache | None,
    work_item: AuctionLotWorkItem | None,
    economy: LotEconomyResponse,
    *,
    now: datetime | None = None,
    category_keywords: dict[str, tuple[str, ...]] | None = None,
    exclusion_keywords: tuple[str, ...] | None = None,
    legal_risk_rules: LegalRiskRules | None = None,
) -> LotAnalysis:
    analysis_time = now or datetime.now(UTC)
    search_text = _build_search_text(record, detail_cache)
    category_override = (work_item.category_override or "").strip() if work_item and work_item.category_override else None
    category, matched_keyword = _match_category(search_text, category_keywords or DEFAULT_CATEGORY_KEYWORDS)
    if category_override:
        category = category_override
        matched_keyword = None
    exclusion_keyword = _match_keyword(search_text, exclusion_keywords or DEFAULT_EXCLUSION_KEYWORDS)
    if work_item and work_item.exclude_from_analysis:
        exclusion_keyword = (work_item.exclusion_reason or "").strip() or "manual"
    legal_risk = _resolve_legal_risk(search_text, category, legal_risk_rules or DEFAULT_LEGAL_RISK_RULES)
    has_documents = bool(detail_cache and detail_cache.documents)
    has_row_photos = _has_real_row_photos(row)
    has_photos = has_row_photos or any(_is_media_document(document) for document in (detail_cache.documents if detail_cache else []))
    completeness = "complete" if has_documents and has_photos else "partial"
    hours_to_deadline = _hours_to_deadline(row.application_deadline, analysis_time)

    reasons: list[str] = []
    if category:
        reasons.append(f"Категория по ключевым словам: {category}")
    if matched_keyword:
        reasons.append(f"Ключевое слово: {matched_keyword}")
    if work_item and work_item.market_value is not None:
        reasons.append("Есть рыночная стоимость")
    if economy.roi is not None:
        reasons.append(f"ROI: {_format_percent(economy.roi)}")
    if economy.market_discount is not None:
        reasons.append(f"Дисконт к рынку: {_format_percent(economy.market_discount)}")
    if hours_to_deadline is not None and 0 <= hours_to_deadline <= 48:
        reasons.append("До конца заявок меньше 48 часов")
    if not has_documents:
        reasons.append("Нет документов")
    if not has_photos:
        reasons.append("Нет фото")
    if legal_risk == "high":
        reasons.append("Обнаружены маркеры высокого юридического риска")

    if exclusion_keyword:
        status = "excluded"
        color = "gray"
        label = "Исключение"
        reasons.append(f"Исключение по ключевому слову: {exclusion_keyword}")
    elif legal_risk == "high":
        status = "legal_risk"
        color = "red"
        label = "Нужна проверка юриста"
    elif hours_to_deadline is not None and 0 <= hours_to_deadline <= 48:
        status = "urgent"
        color = "orange"
        label = "Срочно"
    elif not has_documents or not has_photos:
        status = "incomplete"
        color = "gray"
        label = "Неполные данные"
    else:
        status, color, label = _classify_by_roi(economy.roi, legal_risk)

    return LotAnalysis(
        status=status,
        color=color,
        label=label,
        category=category,
        matched_keyword=matched_keyword,
        is_excluded=bool(exclusion_keyword),
        exclusion_keyword=exclusion_keyword,
        legal_risk=legal_risk,
        completeness=completeness,
        has_documents=has_documents,
        has_photos=has_photos,
        hours_to_deadline=hours_to_deadline,
        reasons=reasons,
    )


def _build_search_text(record: AuctionLotRecord, detail_cache: AuctionLotDetailCache | None) -> str:
    parts = [
        record.lot_name or "",
        record.status or "",
        record.auction_number or "",
        json_text(record.normalized_item),
    ]
    if detail_cache is not None:
        parts.extend(
            [
                json_text(detail_cache.lot_detail),
                json_text(detail_cache.auction_detail),
                json_text(detail_cache.documents),
            ]
        )
    return " ".join(parts).lower()


def _has_real_row_photos(row: LotDatagridRow) -> bool:
    urls = [row.primary_image_url or "", *(image.url for image in row.images)]
    return any(url and not _is_locked_tbankrot_image_url(url) for url in urls)


def _is_locked_tbankrot_image_url(url: str) -> bool:
    return "/img/blur/" in url.lower() or "/blur_" in url.lower()


def json_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(json_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(json_text(item) for item in value)
    return str(value)


def default_category_rules_payload() -> list[dict[str, object]]:
    return [
        {"category": category, "keywords": list(keywords)}
        for category, keywords in DEFAULT_CATEGORY_KEYWORDS.items()
    ]


def default_exclusion_keywords_payload() -> list[str]:
    return list(DEFAULT_EXCLUSION_KEYWORDS)


def default_legal_risk_rules_payload() -> dict[str, list[str]]:
    return {
        "high_keywords": list(DEFAULT_LEGAL_RISK_RULES.high_keywords),
        "medium_keywords": list(DEFAULT_LEGAL_RISK_RULES.medium_keywords),
        "medium_categories": list(DEFAULT_LEGAL_RISK_RULES.medium_categories),
    }


def build_category_keywords_map(
    rules: Sequence[Mapping[str, object]] | None,
) -> dict[str, tuple[str, ...]]:
    if rules is None:
        return DEFAULT_CATEGORY_KEYWORDS

    category_keywords: dict[str, tuple[str, ...]] = {}
    for rule in rules:
        category = str(rule.get("category") or "").strip()
        raw_keywords = rule.get("keywords")
        if not category or not isinstance(raw_keywords, list):
            continue
        normalized_keywords = _normalize_keywords(raw_keywords)
        if normalized_keywords:
            category_keywords[category] = normalized_keywords

    return category_keywords


def build_exclusion_keywords(raw_keywords: Sequence[object] | None) -> tuple[str, ...]:
    if raw_keywords is None:
        return DEFAULT_EXCLUSION_KEYWORDS
    return _normalize_keywords(raw_keywords)


def build_legal_risk_rules(raw_rules: Mapping[str, object] | None) -> LegalRiskRules:
    if raw_rules is None:
        return DEFAULT_LEGAL_RISK_RULES
    return LegalRiskRules(
        high_keywords=_normalize_keywords(raw_rules.get("high_keywords")),
        medium_keywords=_normalize_keywords(raw_rules.get("medium_keywords")),
        medium_categories=_normalize_keywords(raw_rules.get("medium_categories"), lowercase=False),
    )


def _normalize_keywords(raw_keywords: object, *, lowercase: bool = True) -> tuple[str, ...]:
    if not isinstance(raw_keywords, Sequence) or isinstance(raw_keywords, str):
        return ()

    normalized_keywords: list[str] = []
    seen: set[str] = set()
    for keyword in raw_keywords:
        normalized_keyword = str(keyword or "").strip()
        normalized_keyword = normalized_keyword.lower() if lowercase else normalized_keyword
        if not normalized_keyword or normalized_keyword in seen:
            continue
        seen.add(normalized_keyword)
        normalized_keywords.append(normalized_keyword)
    return tuple(normalized_keywords)


def _match_category(
    search_text: str,
    category_keywords: Mapping[str, tuple[str, ...]],
) -> tuple[str | None, str | None]:
    for category, keywords in category_keywords.items():
        keyword = _match_keyword(search_text, keywords)
        if keyword:
            return category, keyword
    return None, None


def _match_keyword(search_text: str, keywords: Sequence[str]) -> str | None:
    for keyword in keywords:
        if keyword in search_text:
            return keyword
    return None


def _resolve_legal_risk(search_text: str, category: str | None, legal_risk_rules: LegalRiskRules) -> str:
    if _match_keyword(search_text, legal_risk_rules.high_keywords):
        return "high"
    if category in legal_risk_rules.medium_categories or _match_keyword(search_text, legal_risk_rules.medium_keywords):
        return "medium"
    return "low"


def _hours_to_deadline(value: str | None, now: datetime) -> int | None:
    if not value:
        return None
    deadline = _parse_deadline(value)
    if deadline is None:
        return None
    remaining_seconds = (deadline - now.replace(tzinfo=None)).total_seconds()
    return int(remaining_seconds // 3600)


def _parse_deadline(value: str) -> datetime | None:
    normalized = value.strip()
    for pattern in (
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(normalized[:19], pattern)
        except ValueError:
            continue
    return None


def _classify_by_roi(roi: Decimal | None, legal_risk: str) -> tuple[str, str, str]:
    if roi is None:
        return "review", "yellow", "Считать детальнее"
    if roi >= Decimal("0.40") and legal_risk in {"low", "medium"}:
        return "interesting", "green", "Интересный лот"
    if roi >= Decimal("0.25"):
        return "review", "yellow", "Считать детальнее"
    return "weak", "red", "Слабый интерес"


def _format_percent(value: Decimal) -> str:
    return f"{(value * Decimal('100')).quantize(Decimal('0.1'))}%"


def _is_media_document(document: dict) -> bool:
    text = " ".join(str(document.get(key) or "") for key in ["name", "document_type", "comment", "url"]).lower()
    return bool(re.search(r"фото|photo|изображ|\.rar|\.zip|\.7z|\.jpe?g|\.png|\.webp", text))
