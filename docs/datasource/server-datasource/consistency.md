# Consistency

This page explains the consistency contract in implementation terms.

## Monotonic Revision

`revision` is a monotonic counter for a table scope.

Use it for:

- cache cursors
- stale-write checks
- change detection after pull
- history sequencing

The backend should bump the revision only when the mutation actually changes persisted row state.

## Workspace-Scoped Revision

If the backend is multi-tenant, scope revision by workspace.

Current behavior:

- `X-Workspace-Id` selects the workspace scope
- missing header means legacy default scope
- a given table can have independent revision counters in different workspaces
- `datasetVersion` is the externally visible version token for the scoped dataset

Practical rule:

- do not reuse the global revision counter across workspaces
- do not let a workspace read another workspace's revision row

## `baseRevision` For Edits

`baseRevision` is the optimistic concurrency check for edit commits.

Required behavior:

- if `baseRevision` is present and does not match the current revision, reject with `409 stale-revision`
- if it is omitted, the backend may accept the commit without that specific check

Use it on the frontend when you have a revision token from the last successful pull or write.

## `projectionHash` For Fill

`projectionHash` binds fill commit to the projection that was active when the fill boundary was resolved.

It protects against changes in:

- sort model
- filter model
- group-by state
- group expansion
- tree data
- pivot state
- pagination snapshot

If the hash changes, the backend should reject with `409 projection-mismatch`.

## `boundaryToken` For Fill

`boundaryToken` protects the exact boundary payload.

It should be built from:

- revision
- projection hash
- start row index
- resolved end row index
- resolved end row id

If the boundary token changes, the backend should reject with `409 boundary-mismatch`.

## `X-Workspace-Id`

This header is the current workspace selector.

Current behavior:

- missing header reads the legacy `NULL` workspace
- present header scopes reads and writes to that workspace
- revision, pull, histogram, edits, fill, undo, and redo should all agree on the same workspace scope

Do not derive workspace from the row payload.

## Stale / Mismatch Responses

Use these codes consistently:

- `stale-revision`
- `projection-mismatch`
- `boundary-mismatch`

Frontend behavior should be deterministic:

- stale revision means refresh and retry from a new revision
- projection mismatch means the fill snapshot changed
- boundary mismatch means the user no longer has the same fill boundary

## What The Frontend Must Preserve Between Boundary And Commit

When the user resolves a fill boundary and later commits the fill, the frontend must keep the following fields unchanged unless the user explicitly changes the selection:

- `baseRevision`
- `projectionHash`
- `boundaryToken`
- `sourceRange`
- `targetRange`
- `sourceRowIds`
- `targetRowIds`
- `fillColumns`
- `referenceColumns`
- `mode`
- `projection`

If any of those values drift, the commit should be treated as a new operation rather than a continuation of the old one.

## History Scope

Stack-based undo/redo is resolved by:

- workspace_id
- table_id
- user_id and/or session_id

At least one of `user_id` or `session_id` is required.

Normal UX should use:

- `POST /api/history/undo`
- `POST /api/history/redo`
- `POST /api/history/status`

The frontend should not need to know the latest `operationId` for normal undo/redo.
The legacy `/api/server-demo/operations/{operation_id}/undo|redo` routes remain available for low-level diagnostics/manual replay.

## Fill Idempotency

A fill commit with the same:

- boundaryToken
- projectionHash
- baseRevision

must produce the same result or be rejected.

The backend must not apply the same fill twice if it was already committed.

## Redo Branch Invalidation

When a new operation is committed after one or more undo actions, the redo branch for the same history scope must be discarded.

Example:

A → B → undo B → commit C

Result:

- undo stack: A, C
- redo stack: empty
- B must not be redoable

## Undo And Redo As Mutations

Undo and redo operations are state-changing mutations.

They must:

- update persisted row state
- bump the table `revision`
- update history state
- follow the same scope and consistency rules as edit and fill commits

Undo/redo must produce the same observable effects as applying or reverting the original operation.

## Commit Response History State

Mutation responses should return history state when possible:

- operationId
- canUndo
- canRedo
- latestUndoOperationId
- latestRedoOperationId
- affectedRows / affectedCells

This avoids an immediate `/history/status` probe after every successful commit.
Returned history state must correspond to the same scope as the committed operation.
If history state cannot be determined reliably, the backend should omit it rather than return incorrect values.

## Cell, Range, Row, And Dataset Invalidation

Mutations should describe the smallest affected scope possible:

- cell invalidation
- range invalidation
- row invalidation
- dataset invalidation

Prefer precise invalidation over full refresh.

Invalidation should be:

- minimal (only affected cells/rows/ranges)
- deterministic
- reproducible from the operation

Avoid:

- full dataset invalidation unless strictly necessary

Current mapping:

- edit -> cell invalidation
- fill -> range invalidation
- undo / redo -> invalidation for the original operation
- fallback -> dataset invalidation

## Revision And History Relationship

Each committed operation that changes persisted state must:

- bump the table `revision`
- be recorded in history with the same effective revision ordering

Practical rule:

- history must reflect the same ordering as revision increments
- undo/redo operations must not violate revision monotonicity
- replayed operations should restore state consistent with the revision they represent

## Scope Consistency

All mutation and history operations must use the same scope fields:

- workspace_id
- table_id
- user_id and/or session_id

These fields must be:

- persisted with each operation
- used for history resolution (undo/redo/status)
- consistent across edit, fill, and history APIs

If scope diverges between:

- operation metadata
- affected rows
- history queries

the backend must still be able to resolve and replay the operation safely.

Prefer fallback resolution over hard failure when scope mismatch is detected.

## Dataset Version

`datasetVersion` is the externally visible version token of the table state.

It is typically derived from `revision`.

It must be:

- returned by pull and mutation responses
- used by the frontend for cache validation
- monotonic within the same workspace + table scope

Practical rule:

- if the datasetVersion changes, the frontend must assume that some part of the dataset has changed
- datasetVersion should be included in mutation responses when available

## Change Feed

`GET /api/changes?sinceVersion=...` is the current polling/change-feed path.

Behavior:

- `sinceVersion == current` returns an empty `changes` array
- `sinceVersion > current` returns `400 invalid-since-version`
- `sinceVersion < current` returns matching changes when the window is complete
- if the change window is incomplete or the gap is too large, the backend may return a dataset-level invalidation fallback

The frontend can use this as the fallback path when websocket transport is unavailable.

## Deterministic Replay

History operations must be replayable deterministically.

Given:

- the same operation payload
- the same scope
- a compatible dataset state

The backend should produce the same resulting state.

If exact replay is not possible due to:

- partial materialization
- scope divergence
- missing rows

the backend must:

- attempt a best-effort replay
- prefer consistency over strict failure
- avoid partial or corrupted state

## Current Limitations

- server-side series fill is not implemented yet
- the workspace scope is still demo/env/header driven unless the host app binds it to auth
- the host app must still enforce authorization
- websocket transport is not implemented yet
- operation-id undo/redo remains available as low-level diagnostics/manual replay
- full off-viewport materialization may be bounded
- change feed may return dataset invalidation fallback when the event window is incomplete or the gap is too large
