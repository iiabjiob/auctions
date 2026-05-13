from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procurement import ProcurementLotRecord
from app.services.grid_state import bump_dataset_version


PROCUREMENT_LOTS_TABLE_ID = "procurement-lots"
DEFAULT_GRID_WORKSPACE_ID = "default"


def procurement_lot_grid_row_id(record: ProcurementLotRecord) -> str:
    return f"{record.source_code}:{record.external_id}"


async def bump_procurement_lot_dataset_version(
    session: AsyncSession,
    record: ProcurementLotRecord | None = None,
    *,
    event_type: str | None = None,
    payload: Mapping[str, Any] | None = None,
    workspace_id: str = DEFAULT_GRID_WORKSPACE_ID,
) -> int:
    return await bump_dataset_version(
        session,
        workspace_id,
        PROCUREMENT_LOTS_TABLE_ID,
        event_type=event_type,
        row_id=procurement_lot_grid_row_id(record) if record is not None else None,
        payload=payload,
    )
