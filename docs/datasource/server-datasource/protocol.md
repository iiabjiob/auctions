# Protocol

This document defines the HTTP contract used by the current server-backed datasource implementation.

The examples below match the current `server_demo` shape. If your table uses different domain fields, keep the transport structure and swap only the row payload.

## Conventions

- All mutation endpoints are `POST`.
- `GET /api/changes?sinceVersion=...` is the current change-feed endpoint.
- Requests and responses are JSON.
- Errors are JSON with at least `code` and `message`.
- `range.endRow` is exclusive.
- `revision` is a monotonic string.
- `datasetVersion` is the externally visible table-version token and is returned by pull and mutation responses.
- `baseRevision` is optional, but recommended for edits and fill commits.
- `projectionHash` and `boundaryToken` are optional on fill commit, but strongly recommended.
- `X-Workspace-Id` is the current workspace scope header.
- Normal undo/redo scope uses `workspace_id`, `table_id`, `user_id`, and/or `session_id`.

## Pull

`POST /api/server-demo/pull`

### Request

```json
{
  "range": { "startRow": 0, "endRow": 50 },
  "sortModel": [
    { "colId": "currentPrice", "sort": "desc" }
  ],
  "filterModel": {
    "status": { "type": "equals", "filter": "Open" }
  }
}
```

### Response

```json
{
  "rows": [
    {
      "id": "srv-000010",
      "index": 10,
      "name": "Account 00010",
      "segment": "Growth",
      "status": "Active",
      "region": "EMEA",
      "value": 970,
      "updatedAt": "2025-01-01T00:10:00Z"
    }
  ],
  "total": 100000,
  "revision": "17",
  "datasetVersion": 17
}
```

Required fields:

- `range.startRow`
- `range.endRow`

Recommended fields:

- `sortModel`
- `filterModel`

Backward compatibility:

- older clients may omit `sortModel` and `filterModel`
- the backend should still return `rows`, `total`, and `revision`

## Histogram

`POST /api/server-demo/histogram`

### Request

```json
{
  "columnId": "region",
  "filterModel": {
    "status": { "type": "equals", "filter": "Active" }
  }
}
```

### Response

```json
{
  "columnId": "region",
  "entries": [
    { "value": "AMER", "count": 25000 },
    { "value": "APAC", "count": 25000 },
    { "value": "EMEA", "count": 25000 },
    { "value": "LATAM", "count": 25000 }
  ]
}
```

Required fields:

- `columnId`

Optional fields:

- `filterModel`

## Commit Edits

`POST /api/server-demo/edits`

### Request

```json
{
  "operationId": "edit-123",
  "baseRevision": "17",
  "edits": [
    {
      "rowId": "srv-000010",
      "columnId": "name",
      "value": "Renamed Account 10",
      "previousValue": "Account 00010"
    }
  ]
}
```

### Response

```json
{
  "operationId": "edit-123",
  "committed": [
    {
      "rowId": "srv-000010",
      "columnId": "name",
      "revision": "2025-05-05T12:00:00Z"
    }
  ],
  "committedRowIds": ["srv-000010"],
  "rejected": [],
  "revision": "18",
  "datasetVersion": 18,
  "affectedRows": 1,
  "affectedCells": 1,
  "invalidation": {
    "type": "cell",
    "cells": [{ "rowId": "srv-000010", "columnId": "name" }],
    "rows": [],
    "range": null
  },
  "canUndo": true,
  "canRedo": false,
  "latestUndoOperationId": "edit-123",
  "latestRedoOperationId": null
}
```

Required fields:

- `edits`

Recommended fields:

- `operationId`
- `baseRevision`

Backward compatibility:

- if all edits are rejected, the backend may still return `200`
- `operationId` may be `null` when nothing was committed

## Fill Boundary

`POST /api/server-demo/fill-boundary`

### Request

```json
{
  "direction": "down",
  "baseRange": { "startRow": 20, "endRow": 20, "startColumn": 0, "endColumn": 0 },
  "fillColumns": ["status"],
  "referenceColumns": ["status"],
  "projection": {
    "sortModel": [],
    "filterModel": null,
    "groupBy": null,
    "groupExpansion": { "expandedByDefault": false, "toggledGroupKeys": [] },
    "treeData": null,
    "pivot": null,
    "pagination": null
  },
  "startRowIndex": 20,
  "startColumnIndex": 0,
  "limit": 3
}
```

### Response

```json
{
  "endRowIndex": 21,
  "endRowId": "srv-000021",
  "boundaryKind": "cache-boundary",
  "scannedRowCount": 3,
  "truncated": true,
  "revision": "18",
  "projectionHash": "c5c7...",
  "boundaryToken": "v1:8f1e..."
}
```

Required fields:

- `direction`
- `baseRange`
- `fillColumns`
- `referenceColumns`
- `projection`
- `startRowIndex`
- `startColumnIndex`

Optional fields:

- `limit`

Consistency fields:

- `revision`
- `projectionHash`
- `boundaryToken`

## Fill Commit

`POST /api/server-demo/fill/commit`

### Request

```json
{
  "operationId": "fill-123",
  "baseRevision": "18",
  "projectionHash": "c5c7...",
  "boundaryToken": "v1:8f1e...",
  "sourceRange": { "startRow": 20, "endRow": 20, "startColumn": 0, "endColumn": 0 },
  "targetRange": { "startRow": 20, "endRow": 21, "startColumn": 0, "endColumn": 0 },
  "sourceRowIds": ["srv-000020"],
  "targetRowIds": ["srv-000020", "srv-000021"],
  "fillColumns": ["status"],
  "referenceColumns": ["status"],
  "mode": "copy",
  "projection": {
    "sortModel": [],
    "filterModel": null,
    "groupBy": null,
    "groupExpansion": { "expandedByDefault": false, "toggledGroupKeys": [] },
    "treeData": null,
    "pivot": null,
    "pagination": null
  },
  "metadata": {
    "origin": "double-click-fill"
  }
}
```

### Response

```json
{
  "operationId": "fill-123",
  "affectedRowCount": 1,
  "affectedCellCount": 1,
  "revision": "19",
  "datasetVersion": 19,
  "affectedRows": 1,
  "affectedCells": 1,
  "canUndo": true,
  "canRedo": false,
  "latestUndoOperationId": "fill-123",
  "latestRedoOperationId": null,
  "invalidation": {
    "type": "range",
    "cells": [],
    "rows": [],
    "range": { "startRow": 21, "endRow": 21, "startColumn": "status", "endColumn": "status" }
  },
  "warnings": []
}
```

Required fields:

- `sourceRange`
- `targetRange`
- `sourceRowIds`
- `targetRowIds`
- `fillColumns`
- `referenceColumns`
- `mode`
- `projection`

Recommended fields:

- `operationId`
- `baseRevision`
- `projectionHash`
- `boundaryToken`

Backward compatibility:

- if `baseRevision` is omitted, the backend may skip stale-write rejection for that commit
- if `projectionHash` is omitted, the backend may still accept the request when it can safely do so
- if `boundaryToken` is omitted, the backend may still accept the request when it can safely do so
- server-side `series` mode is currently rejected with `400 unsupported-fill-mode`

## History Stack

Normal undo/redo uses stack history.

`POST /api/history/undo`

`POST /api/history/redo`

`POST /api/history/status`

Request body:

```json
{
  "workspaceId": "workspace-a",
  "tableId": "server_demo",
  "userId": "user-a",
  "sessionId": "session-a"
}
```

Required scope:

- `workspace_id`
- `table_id`
- `user_id` and/or `session_id`

### Response

Stack undo/redo return the same mutation shape, plus `action` on the stack route:

```json
{
  "operationId": "edit-123",
  "action": "undo",
  "committed": [
    {
      "rowId": "srv-000010",
      "columnId": "name",
      "revision": "2025-05-05T12:05:00Z"
    }
  ],
  "committedRowIds": ["srv-000010"],
  "rejected": [],
  "revision": "19",
  "datasetVersion": 19,
  "affectedRows": 1,
  "affectedCells": 1,
  "canUndo": true,
  "canRedo": false,
  "latestUndoOperationId": "edit-123",
  "latestRedoOperationId": null,
  "invalidation": {
    "type": "cell",
    "cells": [{ "rowId": "srv-000010", "columnId": "name" }],
    "rows": [],
    "range": null
  }
}
```

## Legacy Operation Replay

`POST /api/server-demo/operations/{operation_id}/undo`

`POST /api/server-demo/operations/{operation_id}/redo`

These routes remain available for low-level diagnostics/manual replay.

If the operation is unknown, the backend returns `404 operation-not-found`.

## History Status

`POST /api/history/status`

### Response

```json
{
  "workspace_id": "workspace-a",
  "table_id": "server_demo",
  "user_id": "user-a",
  "session_id": "session-a",
  "canUndo": true,
  "canRedo": false,
  "latestUndoOperationId": "edit-123",
  "latestRedoOperationId": null,
  "datasetVersion": 19
}
```

## Change Feed

`GET /api/changes?sinceVersion=...`

### Response

```json
{
  "datasetVersion": 19,
  "changes": [
    {
      "type": "cell",
      "operationId": "edit-123",
      "user_id": "user-a",
      "session_id": "session-a",
      "invalidation": {
        "type": "cell",
        "cells": [{ "rowId": "srv-000010", "columnId": "name" }],
        "rows": [],
        "range": null
      }
    }
  ]
}
```

Behavior:

- `sinceVersion == current` returns an empty `changes` array.
- `sinceVersion > current` returns `400 invalid-since-version`.
- `sinceVersion < current` returns matching changes when the gap is complete.
- if the window is incomplete or the gap is too large, the backend may return a dataset invalidation fallback.

## Error Response

```json
{
  "code": "stale-revision",
  "message": "Fill commit revision is stale"
}
```

Common error codes:

- `stale-revision`
- `projection-mismatch`
- `boundary-mismatch`
- `operation-not-found`
- `row-not-found`
- `duplicate-operation-id`
- `unsupported-fill-mode`
- `invalid-since-version`

## Workspace Header

`X-Workspace-Id` is not part of the JSON body, but it is part of the protocol contract because it changes revision scope and row visibility.

Current behavior:

- header missing means legacy default scope
- header present means workspace-scoped row visibility and revision scope
- normal undo/redo scope additionally uses `table_id`, `user_id`, and/or `session_id`

## Current Limitations

- server-side series fill is not implemented yet
- stack history is the normal undo/redo path
- full off-viewport materialization may be bounded
- polling/change feed is available as the current fallback path
- websocket transport is not implemented yet
- operation-id undo/redo remains available as low-level diagnostics/manual replay
- change feed may return dataset invalidation fallback when the event window is incomplete or the gap is too large
- the workspace scope is header-driven, not auth-driven
