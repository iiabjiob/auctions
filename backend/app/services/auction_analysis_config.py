from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuctionAnalysisConfigModel
from app.schemas.analysis_config import (
    AnalysisCategoryRule,
    AnalysisLegalRiskRules,
    AuctionAnalysisConfigResponse,
    AuctionAnalysisConfigUpdate,
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


DEFAULT_ANALYSIS_CONFIG_ID = "default"


@dataclass(frozen=True)
class AuctionAnalysisRuntimeConfig:
    category_keywords: dict[str, tuple[str, ...]]
    exclusion_keywords: tuple[str, ...]
    legal_risk_rules: LegalRiskRules


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
        config.updated_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(config)
        return AuctionAnalysisConfigResponse.model_validate(config, from_attributes=True)

    async def get_runtime_config(self, session: AsyncSession) -> AuctionAnalysisRuntimeConfig:
        config = await self._get_or_create_model(session)
        return AuctionAnalysisRuntimeConfig(
            category_keywords=build_category_keywords_map(config.category_rules),
            exclusion_keywords=build_exclusion_keywords(config.exclusion_keywords),
            legal_risk_rules=build_legal_risk_rules(config.legal_risk_rules),
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


auction_analysis_config_service = AuctionAnalysisConfigService()