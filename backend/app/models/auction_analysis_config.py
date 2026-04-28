from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.database import Base


class AuctionAnalysisConfigModel(Base):
    __tablename__ = "auction_analysis_configs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    category_rules: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    exclusion_keywords: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    legal_risk_rules: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )