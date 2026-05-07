from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.grid import GridChangeEventModel, GridRevisionModel
from app.schemas.grid_changes import GridChangeEntry, GridChangeFeedResponse, GridChangeType
from app.services.auction_grid_state import DEFAULT_GRID_WORKSPACE_ID


settings = get_settings()


async def get_grid_changes(
    session: AsyncSession,
    *,
    table_id: str,
    since_version: int,
    workspace_id: str = DEFAULT_GRID_WORKSPACE_ID,
    limit: int | None = None,
) -> GridChangeFeedResponse:
    table_id = _require_scope_value(table_id, "tableId")
    workspace_id = _require_scope_value(workspace_id, "workspace_id")
    resolved_since_version = max(0, int(since_version))
    resolved_limit = _resolve_change_limit(limit)

    latest_version = await session.scalar(
        select(GridRevisionModel.dataset_version).where(
            GridRevisionModel.workspace_id == workspace_id,
            GridRevisionModel.table_id == table_id,
        )
    )
    rows = (
        await session.scalars(
            select(GridChangeEventModel)
            .where(
                GridChangeEventModel.workspace_id == workspace_id,
                GridChangeEventModel.table_id == table_id,
                GridChangeEventModel.dataset_version > resolved_since_version,
            )
            .order_by(GridChangeEventModel.dataset_version.asc(), GridChangeEventModel.id.asc())
            .limit(resolved_limit + 1)
        )
    ).all()

    events = rows[:resolved_limit]
    return GridChangeFeedResponse(
        dataset_version=int(latest_version or 0),
        changes=[
            GridChangeEntry(
                type=_event_type(event.event_type),
                row_id=event.row_id,
                payload=_json_payload(event.payload),
            )
            for event in events
        ],
        has_more=len(rows) > resolved_limit,
    )


def _resolve_change_limit(limit: int | None) -> int:
    configured_limit = max(1, int(settings.grid_change_feed_limit))
    max_limit = max(1, int(settings.grid_change_feed_max_limit))
    requested_limit = configured_limit if limit is None else max(1, int(limit))
    return min(requested_limit, max_limit)


def _event_type(value: str) -> GridChangeType:
    return value if value in {"row_updated", "row_inserted", "row_deleted", "invalidation"} else "invalidation"


def _json_payload(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict(payload or {})


def _require_scope_value(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized
