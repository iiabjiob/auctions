from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from affino_grid_backend import ApiException, GridFillServiceBase
from affino_grid_backend.core.mutations import GridHistoryStatus, PendingGridCellEvent
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procurement import ProcurementLotRecord
from app.services.auction_grid_state import AUCTION_LOTS_TABLE_ID
from app.services.grid_backend_edits import AuctionGridEditRow, AuctionGridEditService, GridBackendEditRequest, ProcurementGridEditService
from app.services.grid_backend_history import AuctionGridRevisionService, ProcurementGridRevisionService
from app.services.grid_table_registry import get_grid_table_definition
from app.services.procurement_grid_state import DEFAULT_GRID_WORKSPACE_ID, PROCUREMENT_LOTS_TABLE_ID


class ProcurementGridFillService(GridFillServiceBase):
    def __init__(self, *, workspace_id: str = DEFAULT_GRID_WORKSPACE_ID) -> None:
        self.workspace_id = workspace_id
        self._edit_service = ProcurementGridEditService(workspace_id=workspace_id)
        super().__init__(
            get_grid_table_definition(PROCUREMENT_LOTS_TABLE_ID),
            ProcurementGridRevisionService(workspace_id=workspace_id),  # type: ignore[arg-type]
        )

    def create_fill_operation_id(self) -> str:
        return str(uuid4())

    async def commit_fill(self, session: AsyncSession, request: Any):
        current_revision = await self._revision_service.get_revision(session)
        base_version = getattr(request, "base_version", None)
        if base_version is not None and str(base_version) != current_revision:
            raise ApiException(status_code=409, code="stale-revision", message="Fill commit revision is stale")
        return await super().commit_fill(session, request)

    def normalize_fill_value(self, column_id: str, value: Any) -> Any:
        return self._edit_service.normalize_edit_value(column_id, value)

    def build_projected_query(self, session: AsyncSession, projection: Any) -> Any:
        del session, projection
        raise NotImplementedError("Projected fill boundary queries are not wired for procurement-lots yet")

    async def count_projected_rows(self, session: AsyncSession, projection: Any) -> int:
        del session, projection
        raise NotImplementedError("Projected fill boundary queries are not wired for procurement-lots yet")

    async def fetch_projected_rows(
        self,
        session: AsyncSession,
        projection: Any,
        start_index: int,
        limit: int,
    ) -> list[ProcurementLotRecord]:
        del session, projection, start_index, limit
        raise NotImplementedError("Projected fill boundary queries are not wired for procurement-lots yet")

    async def fetch_projected_row(self, session: AsyncSession, projection: Any, row_index: int) -> ProcurementLotRecord | None:
        del session, projection, row_index
        raise NotImplementedError("Projected fill boundary queries are not wired for procurement-lots yet")

    async def fetch_rows_by_ids(
        self,
        session: AsyncSession,
        row_ids: list[str],
        *,
        with_for_update: bool = False,
    ) -> dict[str, ProcurementLotRecord]:
        return await self._edit_service.fetch_rows_by_ids(session, row_ids, with_for_update=with_for_update)

    async def ensure_operation_id_available(self, session: AsyncSession, operation_id: str) -> None:
        return await self._edit_service.ensure_operation_id_available(session, operation_id)

    async def create_fill_operation(
        self,
        session: AsyncSession,
        operation_id: str,
        metadata: dict[str, Any],
        changed_at: datetime,
        request: Any,
    ) -> None:
        edit_request = GridBackendEditRequest(
            base_revision=str(request.base_version) if getattr(request, "base_version", None) is not None else None,
            base_version=getattr(request, "base_version", None),
            edits=[],
            payload=metadata,
            workspace_id=getattr(request, "workspace_id", self.workspace_id),
            user_id=getattr(request, "user_id", None),
            session_id=getattr(request, "session_id", None),
            operation_type="fill",
        )
        await self._edit_service.create_operation(session, operation_id, changed_at, edit_request)

    async def create_cell_events(
        self,
        session: AsyncSession,
        operation_id: str,
        pending_events: list[PendingGridCellEvent],
        changed_at: datetime,
    ) -> None:
        await self._edit_service.create_cell_events(session, operation_id, pending_events, changed_at)

    def get_row_value(self, row: ProcurementLotRecord, column_id: str) -> Any:
        return self._edit_service.get_row_value(row, column_id)

    def set_row_value(self, row: ProcurementLotRecord, column_id: str, value: Any) -> None:
        self._edit_service.set_row_value(row, column_id, value)

    def set_row_updated_at(self, row: ProcurementLotRecord, changed_at: datetime) -> None:
        self._edit_service.set_row_updated_at(row, changed_at)

    def get_row_id(self, row: ProcurementLotRecord) -> str:
        return self._edit_service.get_row_id(row)

    def get_row_index(self, row: ProcurementLotRecord) -> int:
        return self._edit_service.get_row_index(row)

    async def collect_history_status(
        self,
        session: AsyncSession,
        request: Any,
        *,
        operation_id: str | None,
        affected_row_ids: list[str],
        affected_indexes: list[int],
        affected_cell_count: int,
        warnings: list[str],
        revision: str,
        rows: list[ProcurementLotRecord] | None = None,
    ) -> GridHistoryStatus | None:
        del affected_row_ids, affected_indexes, affected_cell_count, warnings
        edit_request = GridBackendEditRequest(
            base_revision=str(request.base_version) if getattr(request, "base_version", None) is not None else None,
            base_version=getattr(request, "base_version", None),
            edits=_metadata_edits(getattr(request, "metadata", None)),
            payload=getattr(request, "metadata", None),
            workspace_id=getattr(request, "workspace_id", self.workspace_id),
            user_id=getattr(request, "user_id", None),
            session_id=getattr(request, "session_id", None),
            operation_type="fill",
        )
        return await self._edit_service.collect_history_status(
            session,
            edit_request,
            operation_id=operation_id,
            committed=[],
            committed_row_ids=[],
            rejected=[],
            affected_indexes=[],
            revision=revision,
            rows=rows,
        )


class AuctionGridFillService(GridFillServiceBase):
    def __init__(self, *, workspace_id: str = DEFAULT_GRID_WORKSPACE_ID) -> None:
        self.workspace_id = workspace_id
        self._edit_service = AuctionGridEditService(workspace_id=workspace_id)
        super().__init__(
            get_grid_table_definition(AUCTION_LOTS_TABLE_ID),
            AuctionGridRevisionService(workspace_id=workspace_id),  # type: ignore[arg-type]
        )

    def create_fill_operation_id(self) -> str:
        return str(uuid4())

    async def commit_fill(self, session: AsyncSession, request: Any):
        current_revision = await self._revision_service.get_revision(session)
        base_version = getattr(request, "base_version", None)
        if base_version is not None and str(base_version) != current_revision:
            raise ApiException(status_code=409, code="stale-revision", message="Fill commit revision is stale")
        return await super().commit_fill(session, request)

    def normalize_fill_value(self, column_id: str, value: Any) -> Any:
        return self._edit_service.normalize_edit_value(column_id, value)

    def build_projected_query(self, session: AsyncSession, projection: Any) -> Any:
        del session, projection
        raise NotImplementedError("Projected fill boundary queries are not wired for auction-lots yet")

    async def count_projected_rows(self, session: AsyncSession, projection: Any) -> int:
        del session, projection
        raise NotImplementedError("Projected fill boundary queries are not wired for auction-lots yet")

    async def fetch_projected_rows(
        self,
        session: AsyncSession,
        projection: Any,
        start_index: int,
        limit: int,
    ) -> list[AuctionGridEditRow]:
        del session, projection, start_index, limit
        raise NotImplementedError("Projected fill boundary queries are not wired for auction-lots yet")

    async def fetch_projected_row(self, session: AsyncSession, projection: Any, row_index: int) -> AuctionGridEditRow | None:
        del session, projection, row_index
        raise NotImplementedError("Projected fill boundary queries are not wired for auction-lots yet")

    async def fetch_rows_by_ids(
        self,
        session: AsyncSession,
        row_ids: list[str],
        *,
        with_for_update: bool = False,
    ) -> dict[str, AuctionGridEditRow]:
        return await self._edit_service.fetch_rows_by_ids(session, row_ids, with_for_update=with_for_update)

    async def ensure_operation_id_available(self, session: AsyncSession, operation_id: str) -> None:
        return await self._edit_service.ensure_operation_id_available(session, operation_id)

    async def create_fill_operation(
        self,
        session: AsyncSession,
        operation_id: str,
        metadata: dict[str, Any],
        changed_at: datetime,
        request: Any,
    ) -> None:
        edit_request = GridBackendEditRequest(
            base_revision=str(request.base_version) if getattr(request, "base_version", None) is not None else None,
            base_version=getattr(request, "base_version", None),
            edits=[],
            payload=metadata,
            workspace_id=getattr(request, "workspace_id", self.workspace_id),
            user_id=getattr(request, "user_id", None),
            session_id=getattr(request, "session_id", None),
            operation_type="fill",
        )
        await self._edit_service.create_operation(session, operation_id, changed_at, edit_request)

    async def create_cell_events(
        self,
        session: AsyncSession,
        operation_id: str,
        pending_events: list[PendingGridCellEvent],
        changed_at: datetime,
    ) -> None:
        await self._edit_service.create_cell_events(session, operation_id, pending_events, changed_at)

    def get_row_value(self, row: AuctionGridEditRow, column_id: str) -> Any:
        return self._edit_service.get_row_value(row, column_id)

    def set_row_value(self, row: AuctionGridEditRow, column_id: str, value: Any) -> None:
        self._edit_service.set_row_value(row, column_id, value)

    def set_row_updated_at(self, row: AuctionGridEditRow, changed_at: datetime) -> None:
        self._edit_service.set_row_updated_at(row, changed_at)

    def get_row_id(self, row: AuctionGridEditRow) -> str:
        return self._edit_service.get_row_id(row)

    def get_row_index(self, row: AuctionGridEditRow) -> int:
        return self._edit_service.get_row_index(row)

    async def collect_history_status(
        self,
        session: AsyncSession,
        request: Any,
        *,
        operation_id: str | None,
        affected_row_ids: list[str],
        affected_indexes: list[int],
        affected_cell_count: int,
        warnings: list[str],
        revision: str,
        rows: list[AuctionGridEditRow] | None = None,
    ) -> GridHistoryStatus | None:
        del affected_row_ids, affected_indexes, affected_cell_count, warnings
        edit_request = GridBackendEditRequest(
            base_revision=str(request.base_version) if getattr(request, "base_version", None) is not None else None,
            base_version=getattr(request, "base_version", None),
            edits=_metadata_edits(getattr(request, "metadata", None)),
            payload=getattr(request, "metadata", None),
            workspace_id=getattr(request, "workspace_id", self.workspace_id),
            user_id=getattr(request, "user_id", None),
            session_id=getattr(request, "session_id", None),
            operation_type="fill",
        )
        return await self._edit_service.collect_history_status(
            session,
            edit_request,
            operation_id=operation_id,
            committed=[],
            committed_row_ids=[],
            rejected=[],
            affected_indexes=[],
            revision=revision,
            rows=rows,
        )


def _metadata_edits(metadata: Any) -> list[Any]:
    edits = metadata.get("edits") if isinstance(metadata, dict) else None
    if not isinstance(edits, list):
        return []
    return [
        type("GridBackendFillMetadataEdit", (), {
            "row_id": edit.get("rowId"),
            "column_id": edit.get("columnId"),
        })()
        for edit in edits
        if isinstance(edit, dict)
    ]
