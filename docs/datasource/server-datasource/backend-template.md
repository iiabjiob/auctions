# Backend Template

This is a minimal, copy-paste-safe backend starter for a single table.

Keep it small:

- implement `pull` and `histogram` first
- add edits, fill, history, and change feed only when you actually need them
- for the full implementation, see the `server_demo` reference in `backend/app/features/server_demo/`

## `columns.py`

```py
from __future__ import annotations

from affino_grid_backend.core.columns import GridColumnDefinition

SERVER_DEMO_COLUMNS = {
    "id": GridColumnDefinition(id="id", model_attr="id", readonly=True, sortable=True, filterable=True),
    "index": GridColumnDefinition(id="index", model_attr="row_index", readonly=True, sortable=True, filterable=True),
    "name": GridColumnDefinition(id="name", model_attr="name", editable=True, sortable=True, filterable=True),
    "segment": GridColumnDefinition(id="segment", model_attr="segment", sortable=True, filterable=True, histogram=True),
    "status": GridColumnDefinition(id="status", model_attr="status", sortable=True, filterable=True, histogram=True),
    "region": GridColumnDefinition(id="region", model_attr="region", sortable=True, filterable=True, histogram=True),
    "value": GridColumnDefinition(id="value", model_attr="value", sortable=True, filterable=True, histogram=True),
    "updatedAt": GridColumnDefinition(id="updatedAt", model_attr="updated_at", readonly=True, sortable=True),
}
```

## `table.py`

```py
from __future__ import annotations

from affino_grid_backend.core.table import GridTableDefinition

from .columns import SERVER_DEMO_COLUMNS
from .models import GridDemoRow

SERVER_DEMO_TABLE = GridTableDefinition(
    table_id="server_demo",
    model=GridDemoRow,
    row_id_attr="id",
    workspace_id_attr="workspace_id",
    row_index_attr="row_index",
    updated_at_attr="updated_at",
    columns=SERVER_DEMO_COLUMNS,
    default_sort_column_id="index",
)
```

## `workspace.py`

```py
from __future__ import annotations

from typing import Any

from affino_grid_backend.core.table import GridTableDefinition


def workspace_scope_condition(table: GridTableDefinition, workspace_id: str | None) -> Any | None:
    if workspace_id is None or table.workspace_id_attr is None:
        return None
    column = getattr(table.model, table.workspace_id_attr)
    return column == workspace_id
```

## `projection.py`

```py
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiException
from affino_grid_backend.core.projection import GridProjectionService
from affino_grid_backend.core.table import GridTableDefinition

from .schemas import ServerDemoHistogramEntry, ServerDemoHistogramResponse
from .workspace import workspace_scope_condition


class ServerDemoProjectionService(GridProjectionService):
    def __init__(
        self,
        table: GridTableDefinition,
        workspace_id: str | None = None,
        *,
        max_histogram_buckets: int = 100,
        max_histogram_source_rows: int | None = None,
    ):
        super().__init__(
            model=table.model,
            columns=table.columns,
            default_sort_column_id=table.default_sort_column_id,
            max_histogram_buckets=max_histogram_buckets,
            max_histogram_source_rows=max_histogram_source_rows,
        )
        self._table = table
        self._workspace_id = workspace_id

    def build_row_query(self, conditions: list[Any]):
        scope_condition = workspace_scope_condition(self._table, self._workspace_id)
        scoped_conditions = [*conditions]
        if scope_condition is not None:
            scoped_conditions.append(scope_condition)
        return super().build_row_query(scoped_conditions)

    async def count_rows(self, session: AsyncSession, conditions: list[Any]) -> int:
        scope_condition = workspace_scope_condition(self._table, self._workspace_id)
        scoped_conditions = [*conditions]
        if scope_condition is not None:
            scoped_conditions.append(scope_condition)
        stmt = select(func.count()).select_from(self._model).where(*scoped_conditions)
        return int(await session.scalar(stmt) or 0)

    async def histogram(
        self,
        session: AsyncSession,
        column_id: str,
        filter_model: dict[str, Any] | None,
    ) -> ServerDemoHistogramResponse:
        definition = self._column_definition(column_id)
        if definition is None or not definition.histogram:
            raise ApiException(
                status_code=400,
                code="unsupported_histogram_column",
                message=f"Histogram is only supported for {self._supported_histogram_columns()}",
            )

        column = getattr(self._model, definition.model_attr)
        conditions = self.build_filter_conditions(filter_model)
        scope_condition = workspace_scope_condition(self._table, self._workspace_id)
        scoped_conditions = [*conditions]
        if scope_condition is not None:
            scoped_conditions.append(scope_condition)

        entries = await self._histogram_entries_for_definition(
            session,
            column_id=column_id,
            definition=definition,
            column=column,
            query_conditions=scoped_conditions,
            matching_row_conditions=conditions,
        )
        return ServerDemoHistogramResponse(
            column_id=column_id,
            entries=[ServerDemoHistogramEntry(value=value, count=count) for value, count in entries],
        )
```

## `schemas.py`

```py
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ServerDemoSortModelItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    col_id: str | None = Field(default=None, alias="colId")
    key: str | None = None
    sort: str | None = None
    direction: str | None = None


class ServerDemoPullRange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_row: int = Field(ge=0, alias="startRow")
    end_row: int = Field(ge=0, alias="endRow")

    def model_post_init(self, __context: Any) -> None:
        if self.end_row < self.start_row:
            raise ValueError("endRow must be greater than or equal to startRow")


class ServerDemoPullRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    range: ServerDemoPullRange
    sort_model: list[ServerDemoSortModelItem] = Field(default_factory=list, alias="sortModel")
    filter_model: dict[str, Any] | None = Field(default=None, alias="filterModel")


class ServerDemoRow(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    index: int
    name: str
    segment: str
    status: str
    region: str
    value: int | None
    updated_at: datetime = Field(alias="updatedAt")


class ServerDemoPullResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    rows: list[ServerDemoRow] = Field(default_factory=list)
    total: int
    revision: str | None = None
    dataset_version: int = Field(alias="datasetVersion")


class ServerDemoHistogramRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    column_id: str = Field(alias="columnId")
    filter_model: dict[str, Any] | None = Field(default=None, alias="filterModel")


class ServerDemoHistogramEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Any
    count: int = Field(ge=0)


class ServerDemoHistogramResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    column_id: str = Field(alias="columnId")
    entries: list[ServerDemoHistogramEntry] = Field(default_factory=list)
```

## `repository.py`

```py
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from affino_grid_backend.core.revision import GridRevisionService
from .projection import ServerDemoProjectionService
from .models import GridDemoRow
from .schemas import (
    ServerDemoHistogramRequest,
    ServerDemoHistogramResponse,
    ServerDemoPullRequest,
    ServerDemoPullResponse,
    ServerDemoRow,
)
from .table import SERVER_DEMO_TABLE


class ServerDemoRepository:
    def __init__(self, session: AsyncSession, workspace_id: str | None = None):
        self._session = session
        self._projection = ServerDemoProjectionService(SERVER_DEMO_TABLE, workspace_id=workspace_id)
        self._revision = GridRevisionService(SERVER_DEMO_TABLE, workspace_id=workspace_id)

    async def pull(self, request: ServerDemoPullRequest) -> ServerDemoPullResponse:
        conditions = self._projection.build_filter_conditions(request.filter_model)
        stmt = self._projection.build_row_query(conditions)
        stmt = stmt.order_by(*self._projection.build_order_by(request.sort_model))
        stmt = stmt.offset(request.range.start_row).limit(request.range.end_row - request.range.start_row)

        rows = (await self._session.scalars(stmt)).all()
        total = await self._projection.count_rows(self._session, conditions)
        revision = await self._revision.get_revision(self._session)
        return ServerDemoPullResponse(
            rows=[self._to_row(row) for row in rows],
            total=total,
            revision=revision,
            dataset_version=self._dataset_version(revision),
        )

    async def histogram(self, request: ServerDemoHistogramRequest) -> ServerDemoHistogramResponse:
        return await self._projection.histogram(self._session, request.column_id, request.filter_model)

    def _to_row(self, row: GridDemoRow) -> ServerDemoRow:
        return ServerDemoRow(
            id=row.id,
            index=row.row_index,
            name=row.name,
            segment=row.segment,
            status=row.status,
            region=row.region,
            value=row.value,
            updatedAt=row.updated_at,
        )

    @staticmethod
    def _dataset_version(revision: str | None) -> int:
        return int(revision or 0)
```

Optional extensions, when you actually need them:

- `edits.py` for `POST /edits`
- `fill.py` for `POST /fill-boundary` and `POST /fill/commit`
- `history.py` for stack undo/redo and history status
- `changes_router.py` for `GET /changes?sinceVersion=...`

## `router.py`

```py
from __future__ import annotations

from fastapi import APIRouter, Depends, Header

from .repository import ServerDemoRepository
from .schemas import ServerDemoHistogramRequest, ServerDemoHistogramResponse, ServerDemoPullRequest, ServerDemoPullResponse
from your_app.infrastructure.db import get_db

router = APIRouter(prefix="/server-demo", tags=["server-demo"])


def get_server_demo_repository(
    session = Depends(get_db),
    workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
) -> ServerDemoRepository:
    return ServerDemoRepository(session, workspace_id=workspace_id)


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/pull", response_model=ServerDemoPullResponse)
async def pull(
    request: ServerDemoPullRequest,
    repository: ServerDemoRepository = Depends(get_server_demo_repository),
) -> ServerDemoPullResponse:
    return await repository.pull(request)


@router.post("/histogram", response_model=ServerDemoHistogramResponse)
async def histogram(
    request: ServerDemoHistogramRequest,
    repository: ServerDemoRepository = Depends(get_server_demo_repository),
) -> ServerDemoHistogramResponse:
    return await repository.histogram(request)
```

This template keeps the backend contract minimal on purpose:

- `POST /pull`
- `POST /histogram`

Add edits, fill, history, and change-feed routes only when your backend actually supports them.

## Notes

`server_demo` is the canonical reference for full backend behavior, but this template is intentionally smaller so teams can copy it without pulling in extra surface area on day one.

For full implementation, see server_demo reference.
