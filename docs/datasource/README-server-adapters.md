# @affino/datagrid-server-adapters

Opinionated server datasource adapters for Affino DataGrid.

Use this package when you want the simplest path from a backend-owned table to a working grid datasource.

## When To Use

- use this package for the primary frontend integration path
- use `@affino/datagrid-server-client` only when you need low-level transport or change-feed helpers
- keep sandbox-specific adapter code in the sandbox package, not here

## Install

```bash
pnpm add @affino/datagrid-server-adapters
```

## Minimal Example

```ts
import { createAffinoDatasource } from "@affino/datagrid-server-adapters"

type AuctionRow = {
  id: string
  index: number
  title: string
  status: string
}

const datasource = createAffinoDatasource<AuctionRow>({
  baseUrl: "http://localhost:8000",
  tableId: "auctions",
})
```

`createAffinoDatasource()` returns a `DataGridDataSource<T>`-compatible facade with the additional change-feed and history helpers surfaced on the typed return value.

## Optional Options

- `headers` forwards request headers on adapter-owned requests
- `historyScope` forwards `workspace_id`, `user_id`, and `session_id` into edit, fill, and history bodies
- `histogram.ignoreSelfFilter` sets the default histogram behavior for requests that should ignore the active column filter

## Backend Capabilities

The adapter works best when the backend supports:

- histograms for `POST /api/{tableId}/histogram`
- edits for `POST /api/{tableId}/edits`
- fill for `POST /api/{tableId}/fill-boundary` and `POST /api/{tableId}/fill/commit`
- history for `POST /api/history/undo`, `POST /api/history/redo`, and `POST /api/history/status`

If a backend omits one of these endpoints, keep the feature disabled at the host-app layer.

## Docs

- [Server datasource quick start](../../docs/server-datasource/quick-start.md)
- [Frontend adapter reference](../../docs/server-datasource/frontend-adapter.md)
- [Server client package](../datagrid-server-client/README.md)
