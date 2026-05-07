# Codex Integration Prompt

Copy this prompt into Codex in another project.

```text
You are integrating Affino DataGrid server-backed datasource into this project. Read docs/server-datasource/integration-playbook.md and implement a backend datasource for the existing <MODEL_NAME> table. Do not invent a different architecture. Follow the Affino protocol exactly.

Project variables:
- MODEL_NAME = <MODEL_NAME>
- TABLE_ID = <TABLE_ID>
- ROUTE_PREFIX = <ROUTE_PREFIX>
- FRONTEND_ROUTE = <FRONTEND_ROUTE>
- WORKSPACE_SOURCE = <WORKSPACE_SOURCE>
- EDITABLE_COLUMNS = <EDITABLE_COLUMNS>
- HISTOGRAM_COLUMNS = <HISTOGRAM_COLUMNS>
- SORTABLE_COLUMNS = <SORTABLE_COLUMNS>

Instructions:
1. Inspect the existing model and identify the stable row id and ordering key.
2. Create the backend column registry.
3. Create the GridTableDefinition.
4. Define the Pydantic DTOs that match the protocol.
5. Implement the repository / adapter for pull, histogram, edits, fill boundary, fill commit, undo, and redo.
6. Wire the FastAPI router.
7. Implement the frontend HTTP datasource adapter.
8. Mount the grid in Vue on the requested route.
9. Add tests for pull, edit, histogram, fill, undo, redo, workspace scoping, and consistency errors.
10. Run the relevant validation commands and report the files changed.

Constraints:
- Keep workspace handling aligned with the docs.
- Use X-Workspace-Id if the host app has not yet bound workspace to auth.
- Do not add server-side series fill unless the project explicitly needs it.
- Do not change the protocol shape unless the docs say to.
- Preserve warnings and error codes from the backend.
```
