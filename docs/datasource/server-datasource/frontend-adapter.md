# Frontend Adapter Reference

This page documents the server datasource split:

- `@affino/datagrid-server-adapters` is the primary app-facing entrypoint
- `@affino/datagrid-server-client` is the lower-level transport package
- the sandbox adapter is only a reference implementation

## What The Adapter Does

Use `@affino/datagrid-server-adapters` when you want a single opinionated factory that returns a `DataGridDataSource<T>`-compatible facade with the current Affino HTTP endpoint shape.

It handles the common server datasource flow:

- viewport pulls
- column histograms
- edit commits
- fill boundary resolution
- fill commits
- undo / redo history
- change-feed transport and normalization

If you only need transport helpers and want to compose your own adapter, use `@affino/datagrid-server-client` directly.

The sandbox implementation in [`packages/datagrid-sandbox/src/serverDatasourceDemo/serverDemoDatasourceHttpAdapter.ts`](../../packages/datagrid-sandbox/src/serverDatasourceDemo/serverDemoDatasourceHttpAdapter.ts) remains useful as a reference, but it is not the recommended integration path.

## Primary Integration Path

Start with [`docs/server-datasource/quick-start.md`](./quick-start.md) and [`packages/datagrid-server-adapters/README.md`](../../packages/datagrid-server-adapters/README.md).

## Reference Notes

- The adapter is intentionally thin and does not reimplement backend logic in the browser.
- The low-level client keeps request shaping and backend-specific behavior out of the package boundary.
- Any sandbox-only demo code should stay in the sandbox package and not be treated as the default integration surface.
