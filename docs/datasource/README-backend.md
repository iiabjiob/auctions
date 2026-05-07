# Affino Grid Backend

Reusable grid backend core for Affino DataGrid.

Affino Grid Backend provides the server-side consistency layer for table-centric applications: revision tracking, dataset versioning, edit and fill commits, stack-based undo/redo, precise invalidation, and change-feed support.

It is designed for apps where the backend owns the canonical data and the frontend grid talks to the server through an HTTP datasource.

## Status

Experimental, `v0.1`.

The package currently targets SQLAlchemy-based backends. The core contract is useful today, but APIs may still change before `v1.0`.

## What It Solves

Most grids solve rendering. Real backend-driven apps also need:

- server-side filtering, sorting, and paging
- optimistic concurrency
- safe bulk edits and fill operations
- undo/redo scoped by user or session
- precise cell, range, row, and dataset invalidation
- dataset versioning
- polling or change-feed support
- deterministic backend-owned state

Affino Grid Backend provides reusable building blocks for those concerns.

## Features

- Monotonic table revisions
- `datasetVersion` contract
- `baseRevision` stale-write checks
- Projection hashing for fill safety
- Boundary tokens for fill commits
- Edit commit helpers
- Fill boundary and fill commit helpers
- Stack-based undo/redo support
- Operation-id replay for diagnostics
- Cell, range, row, and dataset invalidation models
- Change-feed foundation for polling, SSE, or WebSocket transports
- SQLAlchemy-oriented services

## Installation

```bash
pip install affino-grid-backend
```

For local development inside this repository:

```bash
cd backend/packages/affino_grid_backend
uv pip install -e .
```

## Quick Start

Import the package root and build a table definition for your SQLAlchemy model:

```py
from affino_grid_backend import (
    GridColumnDefinition,
    GridRevisionService,
    GridTableDefinition,
)

AUCTION_COLUMNS = {
    "id": GridColumnDefinition(
        id="id",
        model_attr="id",
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
    ),
}

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

revision_service = GridRevisionService(
    AUCTIONS_TABLE,
    workspace_id="workspace-a",
)
```

Use the reusable services to handle revisions, projections, edits, fills, history, and invalidation in your host app.

## Core Concepts

### Revision

`revision` is a monotonic counter for a table scope. It should only change when persisted row state changes.

### Dataset Version

`datasetVersion` is the externally visible version token returned to the frontend. It is typically derived from `revision`.

### Base Revision

`baseRevision` protects edit and fill commits from stale writes. A stale base revision should be rejected with a `stale-revision` error.

### Invalidation

Mutation responses should describe the smallest changed scope possible:

```json
{
  "type": "cell",
  "cells": [
    { "rowId": "row-1", "columnId": "status" }
  ]
}
```

Supported invalidation levels:

- `cell`
- `range`
- `row`
- `dataset`

### History

Normal UX should use stack-based history:

- `POST /api/history/undo`
- `POST /api/history/redo`
- `POST /api/history/status`

History is scoped by `workspace_id`, `table_id`, and `user_id` and/or `session_id`.

### Change Feed

The recommended live-update foundation is transport agnostic:

`GET /api/changes?sinceVersion=123`

Polling, SSE, and WebSocket transports can all use the same change-event contract.

## Recommended Backend Endpoints

A host app usually exposes:

- `POST /pull`
- `POST /histogram`
- `POST /edits`
- `POST /fill-boundary`
- `POST /fill/commit`
- `POST /history/undo`
- `POST /history/redo`
- `POST /history/status`
- `GET /changes?sinceVersion=...`

The package provides reusable services and contracts, not a complete hosted backend by itself.

## Architecture

Typical host app structure:

```text
your_app/
  features/
    auctions/
      models.py
      columns.py
      table.py
      schemas.py
      repository.py
      router.py
```

The host app owns:

- SQLAlchemy row models
- FastAPI routers
- auth and permissions
- tenant or workspace rules
- domain validation
- data import and export

The package provides:

- table definitions
- revision services
- projection helpers
- edit, fill, and history base services
- invalidation contracts
- consistency helpers

## Public API

Stable top-level imports are intentionally limited:

```py
from affino_grid_backend import (
    ApiException,
    GridColumnDefinition,
    GridColumnRegistry,
    GridDataAdapter,
    GridEditServiceBase,
    GridFillServiceBase,
    GridHistoryServiceBase,
    GridInvalidation,
    GridInvalidationService,
    GridProjectionService,
    GridRangeInvalidation,
    GridRevision,
    GridRevisionService,
    GridRowsInvalidation,
    GridTableDefinition,
    MutableGridColumnRegistry,
    build_boundary_token,
    canonical_projection_hash,
)
```

Low-level helpers remain available from their concrete modules, but they are not part of the top-level public API contract.

## Current Limitations

- SQLAlchemy-based backends only
- server-side series fill is not implemented yet
- auth and authorization are owned by the host app
- WebSocket transport is not included yet
- change feed can fall back to dataset invalidation when the event window is incomplete
- APIs may change before `v1.0`

## Deep Dives

- [Quick Start](../../../docs/server-datasource/quick-start.md)
- [HTTP Protocol](../../../docs/server-datasource/protocol.md)
- [Consistency Contract](../../../docs/server-datasource/consistency.md)
- [Integration Playbook](../../../docs/server-datasource/integration-playbook.md)
- [Backend Template](../../../docs/server-datasource/backend-template.md)
- [FastAPI Reference](../../../docs/server-datasource/backend-fastapi.md)

## Development

From the repository root:

```bash
cd backend
python -m compileall app packages/affino_grid_backend
uv run pytest
uv run python scripts/bench_server_demo_grid.py
```

## Benchmarking

The reference server-demo benchmark outputs:

`backend/artifacts/performance/backend-server-demo-grid-benchmark.json`

It measures:

- pull viewport
- edit commit
- fill commit
- history status
- undo/redo cycle
- histogram

Budgets are currently observation-only.

## License

MIT
