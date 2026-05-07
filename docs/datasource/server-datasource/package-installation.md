# Package Installation

This page is for teams that want to wire Affino DataGrid into a real backend model.

It separates:

- the reusable grid packages
- the host app code that owns your domain model

## Python Packages

Install the backend package with your preferred workflow.

```bash
uv add affino-grid-backend
```

```bash
pip install affino-grid-backend
```

Editable local install when developing the package itself or vendoring from a path:

```bash
pip install -e ../affino-grid-backend
```

If you are integrating against a local checkout instead of a published wheel, use the editable install form and keep the package import path stable.

## NPM Packages

Install the frontend packages that host the grid runtime, Vue bridge, Vue app shell, and the primary server datasource adapter.

```bash
npm install @affino/datagrid-core @affino/datagrid-vue @affino/datagrid-vue-app @affino/datagrid-server-adapters
```

```bash
pnpm add @affino/datagrid-core @affino/datagrid-vue @affino/datagrid-vue-app @affino/datagrid-server-adapters
```

```bash
yarn add @affino/datagrid-core @affino/datagrid-vue @affino/datagrid-vue-app @affino/datagrid-server-adapters
```

If you need lower-level transport and change-feed helpers, add `@affino/datagrid-server-client` as an advanced dependency.

## Backend Imports

The published Python module should expose the reusable grid primitives.

```py
from affino_grid_backend import (
    GridColumnDefinition,
    GridEditServiceBase,
    GridFillServiceBase,
    GridHistoryServiceBase,
    GridInvalidationService,
    GridProjectionService,
    GridRevisionService,
    GridTableDefinition,
)
```

If your package uses submodules instead of a flat export surface, keep the names the same and adjust the import path only.

## What Belongs Where

### Reusable Package

Put code here when it is generic and table-agnostic:

- `GridTableDefinition`
- `GridColumnDefinition`
- `GridProjectionService`
- `GridEditServiceBase`
- `GridFillServiceBase`
- `GridHistoryServiceBase`
- `GridRevisionService`
- `GridInvalidationService`

This is the code that should be reusable across many projects and many tables.

### Host App

Put code here when it is specific to your domain model:

- the SQLAlchemy row model
- the concrete column registry
- the concrete table definition
- the Pydantic DTOs
- the repository or adapter that talks to your ORM
- the FastAPI router
- the frontend HTTP datasource adapter
- your tests

If you are integrating an `Auctions` table, the reusable package should not know anything about auction titles, statuses, or prices.

## Practical Rule

If a class or function would still make sense for a different table, it belongs in the reusable package.
If it only makes sense for the `Auctions` table, it belongs in the host app.
