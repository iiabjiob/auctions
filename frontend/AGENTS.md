# Frontend Agent Instructions

You are working in the `frontend/` app for the auctions platform.

## Stack
- Vue 3 + Vite + TypeScript
- Pinia for local state
- Vue Router for navigation
- Affino datagrid packages for the main grid experience
- API calls go through the backend HTTP client already in the app

## Working style
- Keep changes aligned with the existing Vue component and store patterns.
- Prefer Composition API and typed props/state.
- Avoid `any` unless the integration really cannot be typed cleanly.
- Keep the grid dense and functional rather than decorative.
- Do not introduce new UI patterns if the current ones already solve the task.

## Scope control
- Do not change backend behavior from the frontend unless the task explicitly requires a contract update.
- Keep edits localized to the relevant view, store, router, or API module.
- Preserve datagrid contracts and column keys unless the feature demands a change.
- If a backend contract change is needed, call it out clearly before assuming the frontend shape.

## Validation
- Prefer `pnpm type-check` for logic-only changes.
- Use `pnpm build` when the change touches routing, data loading, or shared components.
- Run `pnpm lint` only when it adds signal for the slice you changed.

## Commit messages
- Use conventional-style subjects with a concrete frontend scope.
- Good scopes here are `frontend`, `grid`, `router`, `store`, or `datagrid`.
- Keep the subject focused on the behavior change.
