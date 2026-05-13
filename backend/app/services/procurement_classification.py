from __future__ import annotations

import re
from dataclasses import dataclass

from app.schemas.procurements import ProcurementLotItem


KEYWORD_GROUPS: dict[str, tuple[str, ...]] = {
    "Спецодежда": (
        "спецодежда",
        "специальная одежда",
        "рабочая одежда",
        "костюм рабочий",
        "костюм летний",
        "костюм зимний",
        "комбинезон",
        "куртка рабочая",
        "брюки рабочие",
        "жилет сигнальный",
        "форма рабочая",
    ),
    "Медицинская одежда": (
        "медицинская одежда",
        "халат медицинский",
        "костюм медицинский",
        "одежда медицинская",
        "форма медицинская",
        "одежда для медперсонала",
        "брюки медицинские",
        "блуза медицинская",
    ),
    "Спортивная одежда": (
        "спортивная форма",
        "спортивный костюм",
        "форма спортивная",
        "футболка спортивная",
        "шорты спортивные",
        "экипировка спортивная",
        "форма команды",
    ),
    "Униформа": (
        "униформа",
        "форменная одежда",
        "корпоративная одежда",
        "форма охранника",
        "форма персонала",
        "форма для сотрудников",
        "одежда для сотрудников",
    ),
    "Пошив": (
        "пошив",
        "изготовление одежды",
        "поставка одежды",
        "изготовление формы",
        "пошив формы",
        "пошив спецодежды",
    ),
    "Текстиль с пошивом": (
        "постельное белье",
        "полотенца",
        "текстиль",
        "комплекты белья",
        "белье с пошивом",
    ),
}

EXCLUSION_KEYWORDS: tuple[str, ...] = (
    "обувь",
    "сапоги",
    "ботинки",
    "ботинок",
    "перчатки",
    "каски",
    "респираторы",
    "канцтовары",
    "мебель",
    "инвентарь",
    "услуги прачечной",
    "прачечная",
    "химчистка",
    "ремонт одежды",
)


@dataclass(frozen=True, slots=True)
class ProcurementClassification:
    category: str | None
    matched_keywords: list[str]
    excluded_keywords: list[str]
    filter_reason: str | None
    is_relevant: bool


def classify_procurement_lot(item: ProcurementLotItem) -> ProcurementClassification:
    haystack = _classification_text(item)
    excluded = _matched_keywords(haystack, EXCLUSION_KEYWORDS)
    matches_by_category = {
        category: _matched_keywords(haystack, keywords)
        for category, keywords in KEYWORD_GROUPS.items()
    }
    matches_by_category = {category: matches for category, matches in matches_by_category.items() if matches}
    matched_keywords = _dedupe(keyword for matches in matches_by_category.values() for keyword in matches)
    category = _select_category(matches_by_category)

    if excluded:
        return ProcurementClassification(
            category=category,
            matched_keywords=matched_keywords,
            excluded_keywords=excluded,
            filter_reason=f"excluded_keyword:{excluded[0]}",
            is_relevant=False,
        )
    if category:
        return ProcurementClassification(
            category=category,
            matched_keywords=matched_keywords,
            excluded_keywords=[],
            filter_reason=f"matched_category:{category}",
            is_relevant=True,
        )
    return ProcurementClassification(
        category=None,
        matched_keywords=[],
        excluded_keywords=[],
        filter_reason="no_target_keywords",
        is_relevant=False,
    )


def _classification_text(item: ProcurementLotItem) -> str:
    parts = [
        item.title,
        item.procedure_type,
        item.customer_name,
        item.delivery_region,
        item.delivery_address,
        " ".join(item.raw_fields.values()),
    ]
    text = " ".join(part for part in parts if part)
    return _normalize_text(text)


def _matched_keywords(haystack: str, keywords: tuple[str, ...]) -> list[str]:
    return [keyword for keyword in keywords if _contains_keyword(haystack, keyword)]


def _contains_keyword(haystack: str, keyword: str) -> bool:
    normalized_keyword = _normalize_text(keyword)
    if normalized_keyword in haystack:
        return True
    keyword_tokens = _token_stems(normalized_keyword)
    haystack_tokens = _token_stems(haystack)
    if not keyword_tokens or not haystack_tokens:
        return False
    if len(keyword_tokens) > 1:
        return _contains_token_sequence(haystack_tokens, keyword_tokens)
    if len(keyword_tokens[0]) < 4:
        return normalized_keyword in haystack
    return keyword_tokens[0] in haystack_tokens


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("ё", "е").lower()).strip()


def _token_stems(value: str) -> list[str]:
    return [_stem_token(token) for token in re.findall(r"[а-яa-z0-9]+", value)]


def _stem_token(token: str) -> str:
    if re.fullmatch(r"\d+", token):
        return token
    for ending in (
        "иями",
        "ями",
        "ами",
        "ого",
        "ему",
        "ыми",
        "ими",
        "ской",
        "ский",
        "ских",
        "ская",
        "ские",
        "ское",
        "ный",
        "ная",
        "ное",
        "ные",
        "ов",
        "ев",
        "ам",
        "ям",
        "ах",
        "ях",
        "ом",
        "ем",
        "ой",
        "ый",
        "ий",
        "ая",
        "ое",
        "ые",
        "ие",
        "ы",
        "и",
        "а",
        "я",
        "е",
        "у",
        "ю",
    ):
        if len(token) - len(ending) >= 4 and token.endswith(ending):
            return token[: -len(ending)]
    if len(token) >= 5 and token.endswith("ь"):
        return token[:-1]
    return token


def _contains_token_sequence(haystack_tokens: list[str], keyword_tokens: list[str]) -> bool:
    window = len(keyword_tokens)
    return any(haystack_tokens[index : index + window] == keyword_tokens for index in range(len(haystack_tokens) - window + 1))


def _select_category(matches_by_category: dict[str, list[str]]) -> str | None:
    if not matches_by_category:
        return None
    return max(matches_by_category.items(), key=lambda item: (_category_priority(item[0]), len(item[1])))[0]


def _category_priority(category: str) -> int:
    priorities = {
        "Спецодежда": 60,
        "Медицинская одежда": 50,
        "Спортивная одежда": 40,
        "Униформа": 30,
        "Пошив": 20,
        "Текстиль с пошивом": 10,
    }
    return priorities.get(category, 0)


def _dedupe(values) -> list[str]:  # noqa: ANN001
    seen = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
