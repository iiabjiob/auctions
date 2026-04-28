from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AnalysisCategoryRule(BaseModel):
    category: str = Field(min_length=1, max_length=160)
    keywords: list[str] = Field(default_factory=list)


class AnalysisLegalRiskRules(BaseModel):
    high_keywords: list[str] = Field(default_factory=list)
    medium_keywords: list[str] = Field(default_factory=list)
    medium_categories: list[str] = Field(default_factory=list)


class AuctionAnalysisConfigResponse(BaseModel):
    id: str
    category_rules: list[AnalysisCategoryRule] = Field(default_factory=list)
    exclusion_keywords: list[str] = Field(default_factory=list)
    legal_risk_rules: AnalysisLegalRiskRules = Field(default_factory=AnalysisLegalRiskRules)
    created_at: datetime
    updated_at: datetime


class AuctionAnalysisConfigUpdate(BaseModel):
    category_rules: list[AnalysisCategoryRule] = Field(default_factory=list)
    exclusion_keywords: list[str] = Field(default_factory=list)
    legal_risk_rules: AnalysisLegalRiskRules = Field(default_factory=AnalysisLegalRiskRules)