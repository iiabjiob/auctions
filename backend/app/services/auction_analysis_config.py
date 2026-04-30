from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuctionAnalysisConfigModel, AuctionLotRecord
from app.schemas.analysis_config import (
    AnalysisCategoryRule,
    AnalysisLegalRiskRules,
    AuctionAnalysisConfigResponse,
    AuctionAnalysisConfigUpdate,
    OwnerScoringProfile,
    ScoringDimensionWeights,
)
from app.services.auction_analysis import (
    LegalRiskRules,
    build_category_keywords_map,
    build_exclusion_keywords,
    build_legal_risk_rules,
    default_category_rules_payload,
    default_exclusion_keywords_payload,
    default_legal_risk_rules_payload,
)
from app.services.auction_scoring import SCORING_VERSION


DEFAULT_ANALYSIS_CONFIG_ID = "default"


@dataclass(frozen=True)
class AuctionAnalysisRuntimeConfig:
    category_keywords: dict[str, tuple[str, ...]]
    exclusion_keywords: tuple[str, ...]
    legal_risk_rules: LegalRiskRules
    owner_profile: OwnerScoringProfile
    dimension_weights: ScoringDimensionWeights


class AuctionAnalysisConfigService:
    async def get(self, session: AsyncSession) -> AuctionAnalysisConfigResponse:
        config = await self._get_or_create_model(session)
        return AuctionAnalysisConfigResponse.model_validate(config, from_attributes=True)

    async def update(
        self,
        session: AsyncSession,
        payload: AuctionAnalysisConfigUpdate,
    ) -> AuctionAnalysisConfigResponse:
        config = await self._get_or_create_model(session)
        config.category_rules = self._normalize_category_rules(payload.category_rules)
        config.exclusion_keywords = self._normalize_keywords(payload.exclusion_keywords)
        config.legal_risk_rules = self._normalize_legal_risk_rules(payload.legal_risk_rules)
        config.owner_profile = self._normalize_owner_profile(payload.owner_profile)
        config.dimension_weights = self._normalize_dimension_weights(payload.dimension_weights)
        config.updated_at = datetime.now(UTC)
        await self.queue_recalculation(session)
        await session.commit()
        await session.refresh(config)
        return AuctionAnalysisConfigResponse.model_validate(config, from_attributes=True)

    async def get_runtime_config(self, session: AsyncSession) -> AuctionAnalysisRuntimeConfig:
        config = await self._get_or_create_model(session)
        return AuctionAnalysisRuntimeConfig(
            category_keywords=build_category_keywords_map(config.category_rules),
            exclusion_keywords=build_exclusion_keywords(config.exclusion_keywords),
            legal_risk_rules=build_legal_risk_rules(config.legal_risk_rules),
            owner_profile=OwnerScoringProfile.model_validate(config.owner_profile or {}),
            dimension_weights=ScoringDimensionWeights.model_validate(config.dimension_weights or {}),
        )

    async def _get_or_create_model(self, session: AsyncSession) -> AuctionAnalysisConfigModel:
        config = await session.get(AuctionAnalysisConfigModel, DEFAULT_ANALYSIS_CONFIG_ID)
        if config is not None:
            return config

        config = AuctionAnalysisConfigModel(
            id=DEFAULT_ANALYSIS_CONFIG_ID,
            category_rules=default_category_rules_payload(),
            exclusion_keywords=default_exclusion_keywords_payload(),
            legal_risk_rules=default_legal_risk_rules_payload(),
            owner_profile=default_owner_profile_payload(),
            dimension_weights=default_dimension_weights_payload(),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        session.add(config)
        await session.commit()
        await session.refresh(config)
        return config

    def _normalize_category_rules(self, rules: list[AnalysisCategoryRule]) -> list[dict]:
        normalized: list[dict] = []
        for rule in rules:
            category = rule.category.strip()
            if not category:
                continue
            keywords = self._normalize_keywords(rule.keywords)
            normalized.append({"category": category, "keywords": keywords})
        return normalized

    def _normalize_keywords(self, keywords: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for keyword in keywords:
            normalized_keyword = keyword.strip().lower()
            if not normalized_keyword or normalized_keyword in seen:
                continue
            seen.add(normalized_keyword)
            normalized.append(normalized_keyword)
        return normalized

    def _normalize_categories(self, categories: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for category in categories:
            normalized_category = category.strip()
            normalized_key = normalized_category.lower()
            if not normalized_category or normalized_key in seen:
                continue
            seen.add(normalized_key)
            normalized.append(normalized_category)
        return normalized

    def _normalize_legal_risk_rules(self, rules: AnalysisLegalRiskRules) -> dict[str, list[str]]:
        return {
            "high_keywords": self._normalize_keywords(rules.high_keywords),
            "medium_keywords": self._normalize_keywords(rules.medium_keywords),
            "medium_categories": self._normalize_categories(rules.medium_categories),
        }

    def _normalize_owner_profile(self, profile: OwnerScoringProfile) -> dict:
        normalized = profile.model_copy(
            update={
                "target_regions": self._normalize_categories(profile.target_regions),
                "target_categories": self._normalize_categories(profile.target_categories),
                "excluded_terms": self._normalize_keywords(profile.excluded_terms),
                "discouraged_terms": self._normalize_keywords(profile.discouraged_terms),
            }
        )
        return normalized.model_dump(mode="json")

    def _normalize_dimension_weights(self, weights: ScoringDimensionWeights) -> dict:
        return weights.model_dump(mode="json")

    async def queue_recalculation(self, session: AsyncSession) -> int:
        result = await session.execute(
            update(AuctionLotRecord)
            .where(AuctionLotRecord.scoring_version == SCORING_VERSION)
            .values(scoring_version="queued-config-change", score_input_hash=None)
        )
        return int(result.rowcount or 0)


def default_owner_profile_payload() -> dict:
    return OwnerScoringProfile().model_dump(mode="json")


def default_dimension_weights_payload() -> dict:
    return ScoringDimensionWeights().model_dump(mode="json")


auction_analysis_config_service = AuctionAnalysisConfigService()
