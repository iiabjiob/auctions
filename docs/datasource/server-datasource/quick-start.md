# Server Datasource Quick Start

This is the golden path for wiring Affino DataGrid to a backend-owned table.

Use `@affino/datagrid-server-adapters` first. It provides the current app-facing datasource factory for the Affino HTTP endpoint shape. Reach for `@affino/datagrid-server-client` only when you need lower-level polling, invalidation, or custom transport helpers.

## Install

Frontend:

```bash
pnpm add @affino/datagrid-vue-app @affino/datagrid-vue @affino/datagrid-server-adapters
```

Backend:

```bash
uv add affino-grid-backend
```

or:

```bash
pip install affino-grid-backend
```

See also:

- [Package installation](./package-installation.md)
- [Backend FastAPI reference](./backend-fastapi.md)
- [Backend template](./backend-template.md)

## Minimal Backend Contract

`createAffinoDatasource({ tableId })` calls endpoints under `/api/{tableId}`.

It also accepts a few optional adapter-level controls:

- `headers` to forward request headers on all adapter requests
- `historyScope` to forward workspace and user/session scope into edit, fill, and history bodies
- `histogram.ignoreSelfFilter` as a default for histogram requests when you want the adapter to exclude the active column unless a call-site override is provided

For a read-only grid, implement:

- `POST /api/{tableId}/pull`

For histogram-backed column filter UI, also implement:

- `POST /api/{tableId}/histogram`

The pull request body is:

```json
{
  "range": { "startRow": 0, "endRow": 50 },
  "sortModel": [{ "colId": "amount", "sort": "desc" }],
  "filterModel": null
}
```

`endRow` is exclusive. Return rows either as raw row objects with `id` and `index`, or as datasource row entries with `rowId`, `index`, and `row`.

Minimal raw-row response:

```json
{
  "rows": [
    { "id": "row-1", "index": 0, "title": "Auction 1", "status": "open", "amount": 1200 }
  ],
  "total": 1,
  "revision": "7",
  "datasetVersion": 7
}
```

Histogram request body:

```json
{
  "columnId": "status",
  "filterModel": null,
  "options": {
    "ignoreSelfFilter": true,
    "search": "op",
    "orderBy": "valueAsc",
    "limit": 25
  }
}
```

Histogram response:

```json
{
  "entries": [
    { "value": "open", "text": "Open", "count": 12 },
    { "value": "closed", "text": "Closed", "count": 4 }
  ]
}
```

The reference backend implementation is in:

- [`backend/app/features/server_demo/router.py`](../../backend/app/features/server_demo/router.py)
- [`backend/app/features/server_demo/repository.py`](../../backend/app/features/server_demo/repository.py)
- [`backend/app/features/server_demo/schemas.py`](../../backend/app/features/server_demo/schemas.py)

## Minimal Frontend Usage

Create the datasource with `createAffinoDatasource`, wrap it in a datasource-backed row model, and pass that row model to `DataGrid`.

```vue
<script setup lang="ts">
import { onBeforeUnmount } from "vue"
import { createDataSourceBackedRowModel } from "@affino/datagrid-vue"
import { DataGrid } from "@affino/datagrid-vue-app"
import { createAffinoDatasource } from "@affino/datagrid-server-adapters"

type AuctionRow = {
  id: string
  index: number
  title: string
  status: string
  amount: number
}

const datasource = createAffinoDatasource<AuctionRow>({
  baseUrl: "http://localhost:8000",
  tableId: "auctions",
})

const rowModel = createDataSourceBackedRowModel<AuctionRow>({
  dataSource: datasource,
  initialTotal: 0,
})

const columns = [
  { key: "title", label: "Title" },
  { key: "status", label: "Status", capabilities: { sortable: true, filterable: true } },
  {
    key: "amount",
    label: "Amount",
    dataType: "number",
    capabilities: { sortable: true, filterable: true },
    presentation: { align: "right", headerAlign: "right" },
  },
]

onBeforeUnmount(() => {
  rowModel.dispose()
})
</script>

<template>
  <DataGrid
    :row-model="rowModel"
    :columns="columns"
    virtualization
  />
</template>
```

With the minimal contract above, the grid can:

- pull viewport rows from the backend
- send sort model changes to `POST /api/{tableId}/pull`
- send filter model changes to `POST /api/{tableId}/pull`
- request histograms through `POST /api/{tableId}/histogram` when the backend supports that endpoint

## Optional Capabilities

`createAffinoDatasource` also wires the current Affino endpoint names for write and history-related operations. These only work when your backend implements the matching endpoints.

When `historyScope` is provided, the adapter forwards it into edit, fill, and history request bodies as `workspace_id`, `user_id`, and `session_id`, while still keeping `table_id` on the table-scoped endpoints.

Optional table-scoped endpoints:

- `POST /api/{tableId}/edits`
- `POST /api/{tableId}/fill-boundary`
- `POST /api/{tableId}/fill/commit`
- `POST /api/{tableId}/operations/{operationId}/undo`
- `POST /api/{tableId}/operations/{operationId}/redo`

Optional shared endpoints:

- `POST /api/history/undo`
- `POST /api/history/redo`
- `POST /api/history/status`
- `GET /api/changes?sinceVersion=...`

Use these when you want:

- edits committed through `DataGridDataSource.commitEdits`
- server-backed fill handle operations
- stack undo/redo backed by the server
- polling-based change feed updates

The `server_demo` backend shows the full shape:

- [Backend FastAPI reference](./backend-fastapi.md)
- [HTTP protocol](./protocol.md)
- [`backend/app/features/server_demo/history_router.py`](../../backend/app/features/server_demo/history_router.py)
- [`backend/app/features/server_demo/changes_router.py`](../../backend/app/features/server_demo/changes_router.py)

## Low-Level Client Package

`@affino/datagrid-server-client` is intentionally lower-level. Use it when the Affino adapter endpoint shape is not enough and you need to build your own datasource adapter around:

- `createServerDatasourceHttpClient`
- `createChangeFeedPoller`
- `normalizeDatasourceInvalidation`
- `normalizeRowSnapshots`
- `normalizeDatasetVersion`

For ordinary Affino HTTP backend integration, start with `@affino/datagrid-server-adapters`.
