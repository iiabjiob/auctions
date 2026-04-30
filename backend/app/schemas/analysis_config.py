from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class AnalysisCategoryRule(BaseModel):
    category: str = Field(min_length=1, max_length=160)
    keywords: list[str] = Field(default_factory=list)


class AnalysisLegalRiskRules(BaseModel):
    high_keywords: list[str] = Field(default_factory=list)
    medium_keywords: list[str] = Field(default_factory=list)
    medium_categories: list[str] = Field(default_factory=list)


class OwnerScoringProfile(BaseModel):
    target_regions: list[str] = Field(default_factory=list)
    target_categories: list[str] = Field(default_factory=list)
    min_budget: Decimal | None = None
    max_budget: Decimal | None = None
    minimum_roi: Decimal | None = None
    minimum_market_discount: Decimal | None = None
    excluded_terms: list[str] = Field(default_factory=list)
    discouraged_terms: list[str] = Field(default_factory=list)
    max_delivery_distance_km: Decimal | None = None
    allow_dismantling: bool = True
    legal_risk_tolerance: Literal["low", "medium", "high"] = "medium"
    require_documents: bool = False
    require_photos: bool = False


class ScoringDimensionWeights(BaseModel):
    economics: Decimal = Decimal("1.0")
    risk: Decimal = Decimal("1.0")
    urgency: Decimal = Decimal("1.0")
    data_quality: Decimal = Decimal("1.0")
    operational_readiness: Decimal = Decimal("1.0")
    owner_fit: Decimal = Decimal("1.0")
    manual_intent: Decimal = Decimal("1.0")


class AuctionAnalysisConfigResponse(BaseModel):
    id: str
    category_rules: list[AnalysisCategoryRule] = Field(default_factory=list)
    exclusion_keywords: list[str] = Field(default_factory=list)
    legal_risk_rules: AnalysisLegalRiskRules = Field(default_factory=AnalysisLegalRiskRules)
    owner_profile: OwnerScoringProfile = Field(default_factory=OwnerScoringProfile)
    dimension_weights: ScoringDimensionWeights = Field(default_factory=ScoringDimensionWeights)
    created_at: datetime
    updated_at: datetime


class AuctionAnalysisConfigUpdate(BaseModel):
    category_rules: list[AnalysisCategoryRule] = Field(default_factory=list)
    exclusion_keywords: list[str] = Field(default_factory=list)
    legal_risk_rules: AnalysisLegalRiskRules = Field(default_factory=AnalysisLegalRiskRules)
    owner_profile: OwnerScoringProfile = Field(default_factory=OwnerScoringProfile)
    dimension_weights: ScoringDimensionWeights = Field(default_factory=ScoringDimensionWeights)
