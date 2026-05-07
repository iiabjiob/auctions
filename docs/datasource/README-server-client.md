# Affino DataGrid Server Client

Framework-agnostic transport utilities for server-backed DataGrid:

- HTTP datasource client factory
- change feed polling
- invalidation normalization
- row snapshot mapping
- dataset version handling

## What It Is

This package contains reusable client-side helpers for talking to a server-backed DataGrid datasource. It sits below a framework adapter and above the raw HTTP contract without depending on Vue, a demo implementation, or a backend runtime.

## What It Is Not

- not a backend package
- not tied to Vue
- not the opinionated datasource adapter

## Installation

```bash
pnpm add @affino/datagrid-server-client
```

## Core Concepts

### Dataset Version

Use `normalizeDatasetVersion()` when the server may return a revision or version in either string or number form. The helper normalizes the value to a non-negative integer or returns `null` when the input is unusable.

### Change Feed Poller

Use `createChangeFeedPoller()` to manage polling lifecycle concerns:

- start and stop polling
- prevent overlapping requests
- abort in-flight requests on stop
- emit lightweight diagnostics
- reset on invalid since-version responses

### Row Snapshots

Use `normalizeRowSnapshots()` to normalize raw row payloads or row-entry payloads into `DataGridDataSourceRowEntry` values.

### Invalidation

Use `normalizeDatasourceInvalidation()` to convert server invalidation payloads into `DataGridDataSourceInvalidation` values.

### HTTP Client Factory

Use `createServerDatasourceHttpClient()` when you want a reusable low-level client for read and change-feed transport:

- viewport `pull`
- column histogram reads
- change-feed polling
- row snapshot application
- diagnostics

Write, fill, and history operations are backend and adapter-level concerns. If you want the full opinionated integration path, start with `@affino/datagrid-server-adapters`.

## Public API

```ts
import {
  createChangeFeedPoller,
  createServerDatasourceHttpClient,
  mapServerChangeEvent,
  normalizeDatasetVersion,
  normalizeDatasourceInvalidation,
  normalizeRowSnapshots,
} from "@affino/datagrid-server-client"
```

Types:

- `ServerDatasourceChangeFeedDiagnostics`
- `ServerDatasourceChangeFeedPoller`
- `ServerDatasourceChangeFeedPollerOptions`
- `ServerRowSnapshotLike`
- `ServerChangeEventLike`
- `ServerChangeMappingResult`
- `ServerDatasourceHttpClientOptions`

## Usage

### 1. Polling change feed

```ts
const poller = createChangeFeedPoller({
  getSinceVersion: () => lastSeenVersion,
  loadSinceVersion: fetchChanges,
  onResponse: handleChanges,
})

poller.start()
```

### 2. Mapping change events

```ts
const result = mapServerChangeEvent(change, normalizeDatasourceInvalidation)

if (result.kind === "upsert") {
  // apply rows
} else {
  // apply invalidation
}
```

### 3. Row snapshot normalization

```ts
const rows = normalizeRowSnapshots(serverRows)
```

### 4. Creating a server datasource client

```ts
const client = createServerDatasourceHttpClient({
  endpoints: {
    pull: "/api/pull",
    histogram: "/api/histogram",
    changesSinceVersion: sinceVersion => `/api/changes?sinceVersion=${sinceVersion}`,
  },
  mapPullResponse: response => ({
    rows: response.rows,
    total: response.total,
    revision: response.revision ?? null,
    datasetVersion: response.datasetVersion ?? null,
  }),
})

client.startChangeFeedPolling()
```

If you need edits, fill, or history, build those in an adapter or host-specific wrapper that composes this client with backend write endpoints.

## Design Principles

- transport-agnostic
- deterministic updates
- no silent partial mutations
- fail-closed behavior

## Status

Experimental, pre-1.0.

## Boundary Notes

- Keep demo-specific filter, fill, edit, and history request shaping in the sandbox adapter.
- Keep HTTP transport helpers internal to the package.
- Use `@affino/datagrid-server-adapters` for the opinionated application entrypoint.
- Use `@affino/datagrid-core` for shared datasource contracts and row-model types.
