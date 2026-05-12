# Project Agent Instructions

You are working in a monorepo for an auctions platform:
- `backend/`: FastAPI, async SQLAlchemy, Alembic, Redis workers
- `frontend/`: Vue 3, Vite, TypeScript, Pinia, datagrid UI
- `docs/`: product and architecture notes

## Working style
- Read the local code before changing behavior.
- Prefer small, reviewable slices.
- Challenge weak assumptions and hidden coupling.
- Keep changes close to the requested scope.
- Avoid broad refactors unless they unlock the task.
- Use existing patterns in this repo before inventing new ones.

## Scope control
- Do not touch unrelated packages.
- Preserve public API shape unless the task explicitly requires a change.
- For backend behavior changes, keep routes thin and push logic into services.
- For schema changes, use Alembic migrations and update SQLAlchemy models together.
- For frontend work, keep state and server interaction aligned with the existing Vue datagrid stack.

## Validation
- Run the smallest relevant validation first.
- Prefer focused backend tests, frontend type-check/build, or targeted smoke checks over full-suite runs when possible.
- If a validation tool is unavailable in the environment, report that clearly.

## Commit messages
- Use conventional-style subjects with a concrete scope.
- Preferred format: `<type>(<scope>): <what changed>`
- Good scopes here are `backend`, `frontend`, `worker`, `grid`, `lifecycle`, `enrichment`, or `docs`.
- Keep the subject behavior-focused, not implementation-focused.

## Communication
- Keep commentary brief and factual.
- Do not narrate every exploration step.
- Do not dump diffs or long code snippets unless asked.
- When blocked, state the blocker and the next concrete step.

## Delivery
- After implementation, report:
  1. what changed
  2. what validation ran
  3. any remaining risks or missing checks
  4. a suggested commit message
