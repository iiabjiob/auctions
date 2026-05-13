from __future__ import annotations

from dataclasses import dataclass

from app.models import UserInterestProfileModel
from app.models.auction import AuctionLotDetailCache, AuctionLotRecord, AuctionLotWorkItem
from app.schemas.lot_decision_report import LotDecisionReport
from app.schemas.scoring_profile import LotScoringProfile, build_lot_scoring_profile_hash
from app.schemas.scoring_profile_fit import LotProfileFitEvaluation
from app.services.lot_evidence import build_lot_evidence
from app.services.scoring_profile_fit import evaluate_lot_profile_fit


@dataclass(frozen=True)
class UserInterestMatchResult:
    matches: bool
    reasons: tuple[str, ...]
    blockers: tuple[str, ...]
    profile_hash: str
    profile_fit: LotProfileFitEvaluation


def build_lot_scoring_profile_from_interest(interest_profile: UserInterestProfileModel) -> LotScoringProfile:
    payload = interest_profile.profile_payload if isinstance(interest_profile.profile_payload, dict) else {}
    return LotScoringProfile.model_validate(payload)


def evaluate_user_interest_match(
    record: AuctionLotRecord,
    interest_profile: UserInterestProfileModel,
    *,
    detail_cache: AuctionLotDetailCache | None = None,
    work_item: AuctionLotWorkItem | None = None,
    report: LotDecisionReport | None = None,
    require_telegram_enabled: bool = True,
) -> UserInterestMatchResult:
    del work_item

    scoring_profile = build_lot_scoring_profile_from_interest(interest_profile)
    profile_hash = build_lot_scoring_profile_hash(scoring_profile)
    evidence = build_lot_evidence(record, detail_cache)
    profile_fit = evaluate_lot_profile_fit(evidence, scoring_profile)

    reasons = list(profile_fit.reasons)
    blockers = list(profile_fit.blockers)
    rating_score = int(report.rating_score if report is not None else getattr(record, "rating_score", 0) or 0)
    min_rating = int(getattr(interest_profile, "min_rating", 0) or 0)

    if not getattr(interest_profile, "is_active", False):
        blockers.append("Профиль интересов отключен")
    if require_telegram_enabled and not getattr(interest_profile, "telegram_enabled", False):
        blockers.append("Telegram-уведомления отключены для профиля")
    if rating_score < min_rating:
        blockers.append(f"Рейтинг ниже порога профиля: {rating_score} < {min_rating}")

    if not blockers and not reasons:
        reasons.append("Лот соответствует профилю интересов")

    return UserInterestMatchResult(
        matches=not blockers,
        reasons=tuple(reasons),
        blockers=tuple(blockers),
        profile_hash=profile_hash,
        profile_fit=profile_fit,
    )
