from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.database import Base


class UserInterestProfileModel(Base):
    __tablename__ = "user_interest_profiles"
    __table_args__ = (UniqueConstraint("owner_user_id", "name", name="uq_user_interest_profiles_owner_name"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    profile_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    min_rating: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    notification_priority_threshold: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        default="medium",
        server_default="medium",
    )
    telegram_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
