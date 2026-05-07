from __future__ import annotations

from decimal import Decimal, InvalidOperation

from app.schemas.lot_evidence import LotEvidence
from app.schemas.scoring_profile import LotScoringProfile
from app.schemas.scoring_profile_fit import LotProfileFitDimension, LotProfileFitEvaluation


def evaluate_lot_profile_fit(evidence: LotEvidence, profile: LotScoringProfile) -> LotProfileFitEvaluation:
    profile_payload = profile.canonical_payload()
    dimensions: dict[str, LotProfileFitDimension] = {
        "region": LotProfileFitDimension(),
        "category": LotProfileFitDimension(),
        "budget": LotProfileFitDimension(),
        "risk": LotProfileFitDimension(),
        "keywords": LotProfileFitDimension(),
        "distance": LotProfileFitDimension(),
    }
    reasons: list[str] = []
    blockers: list[str] = []

    region_dimension = dimensions["region"]
    target_regions = profile_payload["target_regions"]
    region_text = _text_join(evidence.location.region, evidence.location.city, evidence.location.address)
    if target_regions:
        region_dimension.available = bool(region_text)
        if region_text and _matches_any(region_text, target_regions):
            region_dimension.matched = True
            reason = "Регион соответствует профилю"
            region_dimension.reasons.append(reason)
            reasons.append(reason)
        elif region_text:
            region_dimension.matched = False
            blocker = "Регион вне профиля"
            region_dimension.blockers.append(blocker)
            blockers.append(blocker)
        else:
            blocker = "Регион не указан"
            region_dimension.blockers.append(blocker)
            blockers.append(blocker)

    category_dimension = dimensions["category"]
    target_categories = profile_payload["target_categories"]
    category_text = _text_join(
        evidence.category.category,
        evidence.category.model_category,
        evidence.category.lot_name,
        evidence.category.status,
    )
    if target_categories:
        category_dimension.available = bool(category_text)
        if category_text and _matches_any(category_text, target_categories):
            category_dimension.matched = True
            reason = "Категория соответствует профилю"
            category_dimension.reasons.append(reason)
            reasons.append(reason)
        elif category_text:
            category_dimension.matched = False
            blocker = "Категория вне профиля"
            category_dimension.blockers.append(blocker)
            blockers.append(blocker)
        else:
            blocker = "Категория не указана"
            category_dimension.blockers.append(blocker)
            blockers.append(blocker)

    budget_dimension = dimensions["budget"]
    budget_value = _budget_value(evidence)
    budget_min = _decimal_or_none(profile_payload["budget_min"])
    budget_max = _decimal_or_none(profile_payload["budget_max"])
    if budget_min is not None or budget_max is not None:
        budget_dimension.available = budget_value is not None
        if budget_value is None:
            blocker = "Цена не указана"
            budget_dimension.blockers.append(blocker)
            blockers.append(blocker)
        else:
            lower_ok = budget_min is None or budget_value >= budget_min
            upper_ok = budget_max is None or budget_value <= budget_max
            if lower_ok and upper_ok:
                budget_dimension.matched = True
                reason = "Цена укладывается в бюджет"
                budget_dimension.reasons.append(reason)
                reasons.append(reason)
            else:
                budget_dimension.matched = False
                if budget_min is not None and budget_value < budget_min:
                    blocker = "Цена ниже целевого бюджета"
                else:
                    blocker = "Цена выше целевого бюджета"
                budget_dimension.blockers.append(blocker)
                blockers.append(blocker)

    risk_dimension = dimensions["risk"]
    allowed_risks = profile_payload["allowed_legal_risks"]
    risk_label = _risk_label(evidence)
    if allowed_risks:
        risk_dimension.available = True
        if risk_label in allowed_risks:
            risk_dimension.matched = True
            reason = "Юридический риск соответствует профилю"
            risk_dimension.reasons.append(reason)
            reasons.append(reason)
        else:
            risk_dimension.matched = False
            blocker = "Юридический риск вне профиля"
            risk_dimension.blockers.append(blocker)
            blockers.append(blocker)

    keywords_dimension = dimensions["keywords"]
    search_text = _search_text(evidence)
    stop_words = profile_payload["stop_words"]
    desired_keywords = profile_payload["desired_keywords"]
    keyword_hits = _matches_text_terms(search_text, desired_keywords)
    stop_word_hits = _matches_text_terms(search_text, stop_words)
    if desired_keywords or stop_words:
        keywords_dimension.available = bool(search_text)
    if keyword_hits:
        keywords_dimension.matched = True
        for hit in keyword_hits:
            reason = f"Есть желательное слово: {hit}"
            keywords_dimension.reasons.append(reason)
            reasons.append(reason)
    if stop_word_hits:
        keywords_dimension.matched = False
        for hit in stop_word_hits:
            blocker = f"Профиль исключает слово: {hit}"
            keywords_dimension.blockers.append(blocker)
            blockers.append(blocker)
    elif desired_keywords and not keyword_hits:
        keywords_dimension.matched = None if keywords_dimension.matched is None else keywords_dimension.matched

    distance_dimension = dimensions["distance"]
    max_distance = _decimal_or_none(profile_payload["max_distance_km"])
    if max_distance is not None:
        distance_dimension.available = False
        reason = "Дистанция не оценена без локальной геометрии"
        distance_dimension.reasons.append(reason)
        reasons.append(reason)

    matches_profile = not blockers
    return LotProfileFitEvaluation(
        profile_identifier=profile.profile_identifier,
        matches_profile=matches_profile,
        dimensions=dimensions,
        reasons=reasons,
        blockers=blockers,
    )


def _search_text(evidence: LotEvidence) -> str:
    parts = [
        evidence.location.region,
        evidence.location.city,
        evidence.location.address,
        evidence.category.category,
        evidence.category.model_category,
        evidence.category.lot_name,
        evidence.category.status,
        evidence.legal.legal_risk_signals,
        evidence.legal.exclusion_signals,
        evidence.constraints.inspection_order,
    ]
    return _text_join(*parts)


def _text_join(*values: object) -> str:
    parts: list[str] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            text = value.strip()
            if text:
                parts.append(text.casefold())
            continue
        if isinstance(value, (list, tuple, set)):
            for item in value:
                text = str(item).strip()
                if text:
                    parts.append(text.casefold())
            continue
        text = str(value).strip()
        if text:
            parts.append(text.casefold())
    return " ".join(parts)


def _matches_any(text: str, terms: list[str]) -> bool:
    return any(term.casefold() in text for term in terms if term)


def _matches_text_terms(text: str, terms: list[str]) -> list[str]:
    hits: list[str] = []
    seen: set[str] = set()
    for term in terms:
        normalized = str(term or "").strip().casefold()
        if not normalized or normalized in seen:
            continue
        if normalized in text:
            seen.add(normalized)
            hits.append(normalized)
    return hits


def _budget_value(evidence: LotEvidence) -> Decimal | None:
    return evidence.price.current_price or evidence.price.initial_price or evidence.price.market_value


def _decimal_or_none(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _risk_label(evidence: LotEvidence) -> str:
    if evidence.legal.exclusion_signals:
        return "high"
    if evidence.legal.legal_risk_signals:
        return "medium"
    return "low"
