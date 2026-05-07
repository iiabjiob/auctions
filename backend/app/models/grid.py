from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, Index, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.database import Base


class GridRevisionModel(Base):
    __tablename__ = "grid_revisions"
    __table_args__ = (
        UniqueConstraint("workspace_id", "table_id", name="uq_grid_revisions_workspace_table"),
        Index("ix_grid_revisions_table_id", "table_id"),
        Index("ix_grid_revisions_updated_at", "updated_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False)
    table_id: Mapped[str] = mapped_column(String(128), nullable=False)
    dataset_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default=text("0"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class GridChangeEventModel(Base):
    __tablename__ = "grid_change_events"
    __table_args__ = (
        Index("ix_grid_change_events_workspace_table_version", "workspace_id", "table_id", "dataset_version"),
        Index("ix_grid_change_events_table_version", "table_id", "dataset_version"),
        Index("ix_grid_change_events_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False)
    table_id: Mapped[str] = mapped_column(String(128), nullable=False)
    dataset_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    row_id: Mapped[str | None] = mapped_column(String(255))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class GridOperationModel(Base):
    __tablename__ = "grid_operations"
    __table_args__ = (
        Index(
            "ix_grid_operations_workspace_table_user_session_created",
            "workspace_id",
            "table_id",
            "user_id",
            "session_id",
            "created_at",
        ),
        Index("ix_grid_operations_table_created", "table_id", "created_at"),
        Index("ix_grid_operations_operation_type", "operation_type"),
    )

    id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False)
    table_id: Mapped[str] = mapped_column(String(128), nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(255))
    session_id: Mapped[str | None] = mapped_column(String(255))
    operation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    base_version: Mapped[int | None] = mapped_column(BigInteger)
    resulting_version: Mapped[int | None] = mapped_column(BigInteger)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    undo_payload: Mapped[dict | None] = mapped_column(JSONB)
    redo_payload: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
