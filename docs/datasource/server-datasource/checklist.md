# Integration Checklist

Use this as a practical checklist for a new table.

## Backend

- [ ] backend package installed
- [ ] model defined
- [ ] columns defined
- [ ] table definition created
- [ ] pull endpoint implemented
- [ ] edit endpoint implemented
- [ ] histogram endpoint implemented
- [ ] fill boundary endpoint implemented
- [ ] fill commit endpoint implemented
- [ ] history undo endpoint wired
- [ ] history redo endpoint wired
- [ ] history status endpoint wired
- [ ] change feed endpoint wired
- [ ] legacy operation-id undo/replay route implemented if needed
- [ ] datasetVersion returned
- [ ] invalidation returned from mutations
- [ ] baseRevision conflict behavior tested
- [ ] workspace header handled
- [ ] consistency metadata preserved
- [ ] legacy `NULL` workspace behavior preserved if needed
- [ ] tests added

## Frontend

- [ ] frontend packages installed
- [ ] HTTP datasource adapter implemented
- [ ] pull mapping implemented
- [ ] histogram mapping implemented
- [ ] edit mapping implemented
- [ ] fill boundary mapping implemented
- [ ] fill commit mapping implemented
- [ ] stack undo mapping implemented
- [ ] stack redo mapping implemented
- [ ] change feed / polling adapter implemented if needed
- [ ] datasetVersion stored
- [ ] invalidation handling implemented
- [ ] warnings surfaced
- [ ] backend errors surfaced

## Validation

- [ ] backend migration applied
- [ ] backend compile check passed
- [ ] backend tests passed
- [ ] browser smoke passed

## Recommended Smoke Path

- [ ] open the grid
- [ ] pull a page of rows
- [ ] edit a cell
- [ ] resolve a fill boundary
- [ ] commit a fill
- [ ] undo the latest operation from stack history
- [ ] redo the latest operation from stack history
- [ ] poll the change feed if push transport is unavailable

## Reference Tests

- `backend/tests/test_server_demo_read.py`
- `backend/tests/test_server_demo_edits.py`
- `backend/tests/test_grid_revision_counter.py`
- `backend/tests/test_grid_revision_workspace.py`
- `packages/datagrid-sandbox/src/serverDatasourceDemo/serverDemoDatasourceHttpAdapter.spec.ts`
- `packages/datagrid-sandbox/src/serverDatasourceDemo/serverDemoDatasourceHttpFillDataSource.spec.ts`
