# Integration Playbook

Use this as a mechanical guide for exposing a real backend table through Affino DataGrid.

The example below uses an `Auctions` table with a SQLAlchemy model called `AuctionRowModel`.

Columns:

- `id`
- `index`
- `title`
- `status`
- `category`
- `currentPrice`
- `updatedAt`

Assumption:

- the backend owns the canonical rows
- the frontend talks to the backend through HTTP
- the workspace scope comes from `X-Workspace-Id` unless you later bind it to auth

## Step 1: Define SQLAlchemy Model

Create the row model first. Keep stable row ids and a deterministic ordering key.

```py
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from your_app.infrastructure.db import Base


class AuctionRowModel(Base):
    __tablename__ = "auction_rows"
    __table_args__ = (
        Index("ix_auction_rows_workspace_id", "workspace_id"),
        Index("ix_auction_rows_workspace_id_row_index", "workspace_id", "row_index"),
        Index("ix_auction_rows_row_index", "row_index"),
        Index("ix_auction_rows_status", "status"),
        Index("ix_auction_rows_category", "category"),
        Index("ix_auction_rows_current_price", "current_price"),
        Index("ix_auction_rows_updated_at", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    workspace_id: Mapped[str | None] = mapped_column(String, nullable=True)
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    current_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

Do not invent a second ordering field. Pick one index field and keep it stable.

## Step 2: Define Backend Column Registry

Create a registry that marks each column as editable, sortable, filterable, or histogram-enabled.

```py
from affino_grid_backend import GridColumnDefinition

AUCTION_COLUMNS = {
    "id": GridColumnDefinition(
        id="id",
        model_attr="id",
        readonly=True,
        sortable=True,
        filterable=True,
    ),
    "index": GridColumnDefinition(
        id="index",
        model_attr="row_index",
        readonly=True,
        sortable=True,
        filterable=True,
    ),
    "title": GridColumnDefinition(
        id="title",
        model_attr="title",
        editable=True,
        sortable=True,
        filterable=True,
        histogram=False,
        value_type="string",
    ),
    "status": GridColumnDefinition(
        id="status",
        model_attr="status",
        editable=True,
        sortable=True,
        filterable=True,
        histogram=True,
        value_type="enum",
        enum_values=frozenset({"Draft", "Open", "Closed"}),
    ),
    "category": GridColumnDefinition(
        id="category",
        model_attr="category",
        editable=True,
        sortable=True,
        filterable=True,
        histogram=True,
        value_type="enum",
        enum_values=frozenset({"Art", "Cars", "Collectibles"}),
    ),
    "currentPrice": GridColumnDefinition(
        id="currentPrice",
        model_attr="current_price",
        editable=True,
        sortable=True,
        filterable=True,
        histogram=False,
        value_type="integer",
    ),
    "updatedAt": GridColumnDefinition(
        id="updatedAt",
        model_attr="updated_at",
        readonly=True,
        sortable=True,
        filterable=True,
        value_type="datetime",
    ),
}
```

Keep this registry in the host app unless you are publishing a reusable table package.

## Step 3: Define GridTableDefinition

Wire the model and registry together.

```py
from affino_grid_backend import GridTableDefinition
from your_app.features.auctions.columns import AUCTION_COLUMNS
from your_app.features.auctions.models import AuctionRowModel

AUCTIONS_TABLE = GridTableDefinition(
    table_id="auctions",
    model=AuctionRowModel,
    row_id_attr="id",
    workspace_id_attr="workspace_id",
    row_index_attr="row_index",
    updated_at_attr="updated_at",
    columns=AUCTION_COLUMNS,
    default_sort_column_id="index",
)
```

This definition is the bridge between your ORM model and the reusable grid services.

## Step 4: Define Pydantic DTOs

Define request and response models that match the HTTP protocol exactly.

```py
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AuctionsPullRange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_row: int = Field(ge=0, alias="startRow")
    end_row: int = Field(ge=0, alias="endRow")


class AuctionsPullRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    range: AuctionsPullRange
    sort_model: list[dict[str, Any]] = Field(default_factory=list, alias="sortModel")
    filter_model: dict[str, Any] | None = Field(default=None, alias="filterModel")


class AuctionsRow(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    index: int
    title: str
    status: str
    category: str
    current_price: int | None = Field(alias="currentPrice")
    updated_at: datetime = Field(alias="updatedAt")


class AuctionsPullResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[AuctionsRow] = Field(default_factory=list)
    total: int
    revision: str | None = None
    dataset_version: int = Field(alias="datasetVersion")


class AuctionsMutationInvalidationCell(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    row_id: str = Field(alias="rowId")
    column_id: str = Field(alias="columnId")


class AuctionsMutationInvalidationRange(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    start_row: int = Field(alias="startRow")
    end_row: int = Field(alias="endRow")
    start_column: str | None = Field(default=None, alias="startColumn")
    end_column: str | None = Field(default=None, alias="endColumn")


class AuctionsMutationInvalidation(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    type: Literal["cell", "range", "row", "dataset"]
    cells: list[AuctionsMutationInvalidationCell] = Field(default_factory=list)
    rows: list[str] = Field(default_factory=list)
    range: AuctionsMutationInvalidationRange | None = None


class AuctionsCommitResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    operation_id: str | None = Field(default=None, alias="operationId")
    revision: str
    dataset_version: int = Field(alias="datasetVersion")
    affected_rows: int = Field(alias="affectedRows")
    affected_cells: int = Field(alias="affectedCells")
    can_undo: bool = Field(alias="canUndo")
    can_redo: bool = Field(alias="canRedo")
    latest_undo_operation_id: str | None = Field(default=None, alias="latestUndoOperationId")
    latest_redo_operation_id: str | None = Field(default=None, alias="latestRedoOperationId")
    invalidation: AuctionsMutationInvalidation | None = None


class AuctionsHistoryScope(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    workspace_id: str | None = Field(default=None, alias="workspaceId")
    table_id: str | None = Field(default="auctions", alias="tableId")
    user_id: str | None = Field(default=None, alias="userId")
    session_id: str | None = Field(default=None, alias="sessionId")


class AuctionsHistoryStatusResponse(AuctionsHistoryScope):
    can_undo: bool = Field(alias="canUndo")
    can_redo: bool = Field(alias="canRedo")
    latest_undo_operation_id: str | None = Field(default=None, alias="latestUndoOperationId")
    latest_redo_operation_id: str | None = Field(default=None, alias="latestRedoOperationId")
    dataset_version: int = Field(alias="datasetVersion")


class AuctionsChangeFeedChange(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    type: Literal["cell", "range", "row", "dataset"]
    operation_id: str | None = Field(default=None, alias="operationId")
    user_id: str | None = None
    session_id: str | None = None
    invalidation: AuctionsMutationInvalidation


class AuctionsChangeFeedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    dataset_version: int = Field(alias="datasetVersion")
    changes: list[AuctionsChangeFeedChange] = Field(default_factory=list)
```

Add the write DTOs next: edit commit, fill boundary, fill commit, stack history, history status, and change feed responses.

## Step 5: Implement Repository / Adapter

Keep the router thin. Put ORM translation and grid-service orchestration in a repository.

```py
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from affino_grid_backend import GridInvalidationService, GridRevisionService
from your_app.features.auctions.columns import AUCTION_COLUMNS
from your_app.features.auctions.models import AuctionRowModel
from your_app.features.auctions.schemas import AuctionsPullRequest, AuctionsPullResponse, AuctionsRow
from your_app.features.auctions.table import AUCTIONS_TABLE


class AuctionsRepository:
    def __init__(self, session: AsyncSession, workspace_id: str | None = None):
        self._session = session
        self._workspace_id = workspace_id
        self._projection = AuctionsProjectionService(AUCTIONS_TABLE, workspace_id=workspace_id)
        self._revision = GridRevisionService(AUCTIONS_TABLE, workspace_id=workspace_id)
        self._edits = AuctionsEditService(AUCTION_COLUMNS, self._revision, workspace_id=workspace_id)
        self._fill = AuctionsFillService(AUCTION_COLUMNS, self._projection, self._revision, workspace_id=workspace_id)
        self._history = AuctionsHistoryService(AUCTION_COLUMNS, self._revision, workspace_id=workspace_id)
        self._invalidation = GridInvalidationService()

    async def pull(self, request: AuctionsPullRequest) -> AuctionsPullResponse:
        # REQUIRED: translate filters, sort, and offset/limit to SQLAlchemy.
        conditions = self._projection.build_filter_conditions(request.filter_model)
        stmt = self._projection.build_row_query(conditions)
        stmt = stmt.order_by(*self._projection.build_order_by(request.sort_model))
        stmt = stmt.offset(request.range.start_row).limit(request.range.end_row - request.range.start_row)

        rows = (await self._session.scalars(stmt)).all()
        total = await self._projection.count_rows(self._session, conditions)
        revision = await self._revision.get_revision(self._session)
        return AuctionsPullResponse(rows=[self._to_row(row) for row in rows], total=total, revision=revision)

    def _to_row(self, row: AuctionRowModel) -> AuctionsRow:
        return AuctionsRow(
            id=AUCTIONS_TABLE.row_id_value(row),
            index=AUCTIONS_TABLE.row_index_value(row),
            title=row.title,
            status=row.status,
            category=row.category,
            currentPrice=row.current_price,
            updatedAt=AUCTIONS_TABLE.updated_at_value(row),
        )
```

Required methods:

- `pull`
- `histogram`
- `commit_edits`
- `resolve_fill_boundary`
- `commit_fill`
- `undo_operation`
- `redo_operation`
- `undo_latest_operation`
- `redo_latest_operation`
- `history_status`
- `change_feed`

Optional methods:

- `health`
- any table-specific convenience methods

Do not move column coercion into the router.

## Step 6: Wire FastAPI Router

Keep the router declarative.

```py
from fastapi import APIRouter, Depends, Header

from your_app.features.auctions.repository import AuctionsRepository
from your_app.infrastructure.db import get_db

router = APIRouter(prefix="/auctions", tags=["auctions"])


def get_auctions_repository(
    session = Depends(get_db),
    workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
) -> AuctionsRepository:
    return AuctionsRepository(session, workspace_id=workspace_id)
```

Then add route handlers for:

- `GET /health`
- `POST /pull`
- `POST /histogram`
- `POST /edits`
- `POST /fill-boundary`
- `POST /fill/commit`
- `POST /history/undo`
- `POST /history/redo`
- `POST /history/status`
- `POST /operations/{operation_id}/undo`
- `POST /operations/{operation_id}/redo`
- `GET /changes?sinceVersion=...`

## Step 7: Implement Frontend HTTP Datasource Adapter

The adapter should translate DataGrid calls to backend HTTP requests and keep the protocol shape stable.

```ts
type WorkspaceSource = "header" | "auth"

export function createAuctionsDatasourceHttpAdapter(options: {
  baseUrl: string
  workspaceId?: string | null
}) {
  const headers = () =>
    options.workspaceId ? { "X-Workspace-Id": options.workspaceId } : undefined

  return {
    async pull(request: PullRequest) {
      const response = await fetch(`${options.baseUrl}/api/auctions/pull`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers() },
        body: JSON.stringify(request),
      })
      return await readOrThrow(response)
    },
  }
}
```

The adapter should preserve:

- `revision`
- `datasetVersion`
- `baseRevision`
- `projectionHash`
- `boundaryToken`
- mutation invalidation
- stack history scope fields

## Step 8: Mount DataGrid in Vue

Use the Vue app shell package and pass the HTTP datasource through the existing grid API.

```vue
<script setup lang="ts">
import { computed } from "vue"
import { DataGrid } from "@affino/datagrid-vue-app"
import { createAuctionsDatasourceHttpAdapter } from "@/features/auctions/auctionsDatasourceHttpAdapter"

const datasource = createAuctionsDatasourceHttpAdapter({
  baseUrl: import.meta.env.VITE_API_BASE_URL,
  workspaceId: "workspace-a",
})

const gridProps = computed(() => ({
  dataSource: datasource,
  tableId: "auctions",
}))
</script>

<template>
  <DataGrid v-bind="gridProps" />
</template>
```

## Step 9: Add Tests

Test the integration at the boundary you own.

```py
async def test_auctions_pull_scoped_to_workspace(client):
    response = await client.post(
        "/api/auctions/pull",
        json={"range": {"startRow": 0, "endRow": 20}},
        headers={"X-Workspace-Id": "workspace-a"},
    )
    assert response.status_code == 200
```

Test cases to add:

- pull returns only scoped rows
- edit rejects rows from another workspace
- histogram respects active filters
- fill boundary and fill commit preserve consistency tokens
- stack undo/redo only touch scoped rows
- history status is scoped to workspace / user / session
- change feed returns the expected changes or dataset fallback
- legacy `NULL` workspace stays visible when no header is sent

## Step 10: Run Validation

Run the smallest relevant checks first.

```bash
cd backend && uv run alembic upgrade head
cd backend && python -m compileall app
cd backend && uv run pytest
```

If you changed the frontend adapter too, run the frontend type-check and smoke flow for the host app.

## Current Limitations

- server-side series fill is not implemented yet
- stack history is the normal undo/redo path
- operation-id replay remains available for low-level diagnostics/manual replay
- workspace comes from `X-Workspace-Id` unless the host app binds it to auth
- full off-viewport materialization may be bounded by the projection window
- the host app must enforce authorization
- websocket transport is not implemented yet
- polling/change feed is available as the current fallback path
