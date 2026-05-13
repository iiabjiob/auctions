# Procurement Tender Parser V1 Slices

Source: `.refs/ТЗ на парсинг тендеров.pdf`

Product target: replace the Google Sheets MVP from the spec with the app's existing Affino datagrid stack. The module must work as a decision funnel for apparel-related tenders, not as a raw link list.

## V1 Boundary

V1 must cover:

- EIS `zakupki.gov.ru` as the first production source.
- Extensible source interface for the next 5 key platforms, but not full implementations for all of them in the first pass.
- Keyword and exclusion filtering for apparel tenders: спецодежда, медодежда, спорт, униформа, textile with sewing.
- Tender deduplication by source + procurement number.
- Affino datagrid table instead of Google Sheets.
- Manual workflow fields: status, assignee, comment, decision.
- Cost calculator fields and formulas.
- Primary 0-100 scoring and color/priority.
- Telegram notifications for priority tenders.
- Daily or manual sync in V1, with config for later 1-3 hour sync.

Out of V1:

- Deep AI documentation parsing.
- Customer legal/payment risk intelligence.
- Competitor history.
- CRM integration.
- Production capacity planning.
- Full implementation of every ETP source.

## Architectural Direction

Keep procurements as a separate domain from bankruptcy auctions. Do not overload `AuctionLotRecord`; procurement tenders have different statuses, economics, deadlines, documents, and scoring semantics.

Use these boundaries:

- `backend/app/models/procurement.py`: persistence for procurement lots, sources, workflow/calculation fields.
- `backend/app/services/zakupki_scraper.py`: source-specific parsing.
- `backend/app/services/procurement_sync.py`: source sync and upsert.
- `backend/app/services/procurement_catalog.py`: server-side grid queries.
- `frontend/src/datagrid/*`: procurement server datasource mirroring auction grid patterns.
- `frontend/src/App.vue` or extracted components: tender workspace.

## Slice 1 - Procurement Schema V1

Goal: expand the existing procurement persistence from raw parsed lots into a table-ready decision funnel.

Scope:

- Add workflow fields: `workflow_status`, `assignee`, `comment`, `final_decision`, `rejection_reason`.
- Add tender classification fields: `category`, `matched_keywords`, `excluded_keywords`, `filter_reason`.
- Add customer fields: `customer_inn`, `delivery_region`, `delivery_address`.
- Add document fields: `specification_url`, `documents_url`, `certificate_requirements`, `documentation_present`.
- Add cash-flow and guarantees: `bid_security_amount`, `contract_security_amount`, `prepayment_percent`, `payment_terms`.
- Add calculation fields: `quantity`, `unit_nmck`, `cost_realistic`, `cost_cautious`, `net_profit`, `profitability`, `roi`, `cash_gap_peak`.
- Preserve raw payload and normalized payload.
- Add Alembic migration and model updates together.

Prompt:

```text
Implement Slice 1 from docs/procurement-tender-parser-v1-slices.md.

Read the current procurement model, migration history, and auction grid/work item patterns first. Expand the procurement domain schema for V1 decision workflow and calculation fields. Keep procurements separate from AuctionLotRecord. Add an Alembic migration after the current head, update SQLAlchemy models, and add focused tests that the model/migration metadata compiles.

Do not touch unrelated auction behavior. Do not build frontend in this slice.
Run the smallest relevant backend validation and report remaining migration/runtime risks.
```

## Slice 2 - EIS Parser Coverage

Goal: make `zakupki.gov.ru` ingestion reliable enough for the V1 tender table.

Scope:

- Search list parser for apparel keywords and exclusion terms.
- Pagination with configurable limit/pages.
- Extract from search cards:
  - registry number
  - law type
  - status
  - title
  - customer
  - customer INN when present
  - NMCK
  - publication date
  - application deadline
  - procedure type
  - platform
  - region when present
  - card URL and print URL
- Add detail-page fetch/parser hooks for fields not reliably present on search cards.
- Add fixture tests based on saved HTML snippets and at least one live-gateway smoke command documented in test comments or docs.
- Fix parser diagnostics so structure changes are observable.

Prompt:

```text
Implement Slice 2 from docs/procurement-tender-parser-v1-slices.md.

Read backend/app/services/zakupki_scraper.py and the existing tests. Improve the EIS parser for apparel tender V1 fields and keyword/exclusion search. Add parser functions with fixture-style unit tests for 44-FZ and 223-FZ cards. Use the existing restricted zakupki fetch gateway only for manual smoke checks, not as a test dependency.

Keep parsing source-specific and return normalized ProcurementLotItem objects. Add clear logging/diagnostic signals for cards that cannot be parsed.
Run focused parser tests.
```

## Slice 3 - Filter Dictionary And Classification

Goal: turn the spec's keywords/exclusions into editable backend rules used by sync and grid filters.

Scope:

- Create default keyword groups:
  - спецодежда
  - медицина
  - спорт
  - униформа
  - пошив
  - textile with sewing
- Create default exclusions:
  - обувь, сапоги, ботинки
  - перчатки, каски, респираторы
  - канцтовары, мебель, инвентарь
  - прачечная, химчистка
  - ремонт одежды
- Add classification service:
  - category
  - matched keywords
  - excluded keywords
  - inclusion/exclusion reason
- Decide whether defaults live in code first or a DB table. For V1, code defaults are acceptable if the model leaves room for DB rules later.
- Apply classification during sync.

Prompt:

```text
Implement Slice 3 from docs/procurement-tender-parser-v1-slices.md.

Add a procurement classification service using the keyword and exclusion groups from the spec. Integrate it into procurement sync so each record stores category, matched keywords, excluded keywords, and filter reason. Keep the implementation simple and deterministic; avoid AI or fuzzy matching in this slice beyond lowercase/morphology-friendly substring matching.

Add unit tests for category assignment, exclusion precedence, and neutral unmatched tenders.
```

## Slice 4 - Affino Procurement Datagrid Backend

Goal: replace the Google Sheets table from the spec with a proper server-backed Affino datagrid endpoint.

Scope:

- Create procurement grid table id, row id function, columns and aliases.
- Implement pull endpoint equivalent to `/api/auction-lots/pull`, but for procurements.
- Support server-side:
  - pagination/window pull
  - sorting
  - text search
  - filters by category, law, status, score, price, deadline, workflow status, assignee
  - histogram endpoint if needed by existing datagrid stack
- Return row payloads shaped for frontend grid.
- Include manual fields in row payload.
- Keep routes thin; logic belongs in services.

Prompt:

```text
Implement Slice 4 from docs/procurement-tender-parser-v1-slices.md.

Study backend/app/api/auction_lots_grid_router.py, backend/app/services/auction_grid.py, backend/app/services/auction_catalog.py, and frontend datagrid server adapter expectations. Build a procurement-specific server-backed grid API using the same Affino datagrid protocol shape, but backed by ProcurementLotRecord.

Do not reuse auction row ids or auction table ids. Add focused backend tests for pull, filtering, sorting, and row payload shape.
```

## Slice 5 - Manual Workflow Editing

Goal: allow the team to work the tender funnel inside the datagrid.

Scope:

- Editable columns:
  - workflow status
  - assignee
  - comment
  - final decision
  - rejection reason
  - quantity
  - calculation inputs
  - production confirmation fields
- Add optimistic/concurrent edit handling similar to auction grid edits.
- Add change events if needed for live refresh.
- Required statuses from spec:
  - Новый
  - Быстрый фильтр
  - Считаем
  - Вопросы по ТЗ
  - Проверка цеха
  - На решение
  - Подаем
  - Подано
  - Аукцион
  - Выиграли
  - Проиграли
  - Отказ

Prompt:

```text
Implement Slice 5 from docs/procurement-tender-parser-v1-slices.md.

Read the auction grid edit implementation and build the equivalent minimal edit path for procurement workflow fields. Keep write scope to procurement services/routes and shared grid operation models only if the existing operation system supports another table id cleanly.

Add tests for valid edits, invalid column rejection, conflict behavior, and status persistence. Do not implement calculator formulas in this slice beyond storing manual inputs.
```

## Slice 6 - Cost Calculator V1

Goal: implement the spec's tender economics model so a manager can decide quickly.

Scope:

- Inputs:
  - product type
  - quantity
  - fabric type
  - fabric price
  - fabric consumption per unit
  - accessories cost
  - sewing cost
  - extra operations
  - logistics
  - packaging
  - defect/reserve percent
  - admin/FOT
  - VAT mode
  - profit tax
- Outputs:
  - fabric cost per unit
  - unit cost
  - production cost
  - full cost
  - revenue without VAT
  - gross profit
  - VAT payable
  - profit tax
  - net profit
  - profitability
  - ROI
- Three scenarios:
  - optimistic
  - realistic
  - cautious
- Decision should use cautious scenario by default.

Prompt:

```text
Implement Slice 6 from docs/procurement-tender-parser-v1-slices.md.

Add a deterministic procurement calculator service and persist/store its inputs and outputs on procurement records. Follow the formulas in the spec, using VAT 22% and profit tax 25% defaults. Support optimistic, realistic, and cautious scenarios, with cautious used for decision scoring.

Expose calculation fields through the procurement API/grid row payload. Add unit tests for formulas, null input handling, and scenario selection.
```

## Slice 7 - Tender Scoring V1

Goal: upgrade the initial attractiveness score into the spec's decision score.

Scope:

- Score 0-100:
  - net profitability: 30
  - absolute profit: 15
  - execution deadline realism: 15
  - specification complexity: 15
  - production readiness: 10
  - customer quality/manual flag: 10
  - competition/manual field: 5
- Color/level:
  - 80-100 priority
  - 60-79 watch/calculate
  - 40-59 low priority
  - 0-39 reject/ignore
- Score should degrade for:
  - no documentation
  - excluded category
  - deadline under 2 business days
  - no certificate clarity
  - unrealistic production period
  - cash gap too high

Prompt:

```text
Implement Slice 7 from docs/procurement-tender-parser-v1-slices.md.

Replace or extend the current procurement attractiveness scoring with the V1 weighted tender score. Use calculated economics when available and fallback to parser-only heuristics when not. Persist score, level, reasons, input hash/version, and scored_at.

Add unit tests for high-profit valid tender, excluded tender, missing-doc tender, urgent-deadline tender, and no-calculation fallback.
```

## Slice 8 - Frontend Affino Datagrid

Goal: replace the temporary `/tenders` table with the same quality of datagrid experience as auctions.

Scope:

- Create procurement datasource adapter.
- Use server-backed Affino datagrid.
- Columns:
  - score/color
  - workflow status
  - source
  - link
  - registry number
  - law
  - customer
  - customer INN
  - region
  - title
  - category
  - NMCK
  - quantity
  - unit NMCK
  - application deadline
  - auction/procedure date if present
  - delivery deadline
  - specification link
  - certificate requirements
  - bid security
  - contract security
  - cost
  - net profit
  - profitability
  - assignee/comment/decision
- Preserve dense operational UI; no marketing layout.

Prompt:

```text
Implement Slice 8 from docs/procurement-tender-parser-v1-slices.md.

Replace the temporary /tenders HTML table in frontend/src/App.vue with an Affino server-backed datagrid. Follow the auction datagrid patterns, but create procurement-specific datasource/types/edit handling. Use the procurement grid backend from Slice 4 and edit backend from Slice 5.

Keep UI dense and operational. Run frontend type-check and build-only.
```

## Slice 9 - Telegram Notifications

Goal: notify only when action is needed.

Scope:

- Events:
  - new priority tender, score > 75
  - projected net profit > 500k
  - profitability > 20%
  - deadline under 48h
  - tender ready for owner decision
- Avoid spam:
  - notification guard by tender + event type
  - do not notify repeatedly on unchanged records
- Reuse existing Telegram sender/outbox patterns if possible, but keep procurement notification state separate enough to avoid auction coupling.

Prompt:

```text
Implement Slice 9 from docs/procurement-tender-parser-v1-slices.md.

Read the existing Telegram outbox/sender code for auction lots and add procurement tender notifications for priority events. Prevent duplicate notifications per tender/event type. Use existing bot configuration and sender worker if the model supports it cleanly; otherwise add a small procurement-specific outbox.

Add tests for notification eligibility and duplicate suppression.
```

## Slice 10 - Source Platform Interface

Goal: prepare V1 for EIS + 5 key platforms without blocking on all parsers.

Scope:

- Define `ProcurementSourceProvider` protocol:
  - `info`
  - `iter_lots`
  - optional `get_lot_detail`
  - optional `get_documents`
- Register EIS provider.
- Add disabled/stub providers for:
  - Сбербанк-АСТ
  - РТС-тендер
  - Росэлторг
  - НЭП
  - ЭТП ГПБ
  - ТЭК-Торг
- Sync worker loops enabled providers only.

Prompt:

```text
Implement Slice 10 from docs/procurement-tender-parser-v1-slices.md.

Create a procurement source provider registry similar in spirit to auction_sources, but dedicated to procurement tenders. Register the EIS provider and add disabled stubs for the next key platforms from the spec. Update sync worker/service to loop enabled procurement providers.

Do not implement the external platform parsers yet. Add tests for provider registry, disabled providers, and unsupported provider errors.
```

## Slice 11 - Operational Diagnostics

Goal: make parser failures and structure drift visible.

Scope:

- Track sync runs per procurement source.
- Track fetched/created/updated/unchanged/error counts.
- Track parser card failures and missing critical fields.
- Expose health endpoint for procurement pipeline.
- Add logs with source, URL, status, parser version.

Prompt:

```text
Implement Slice 11 from docs/procurement-tender-parser-v1-slices.md.

Add procurement pipeline observability similar to auction pipeline health. Track source sync runs, parser failures, missing critical fields, and last successful sync. Expose a read endpoint for the frontend/ops view.

Keep it focused on diagnostics. Do not add frontend charts unless trivial.
```

## Suggested Build Order

1. Slice 1 - Schema V1
2. Slice 2 - EIS parser coverage
3. Slice 3 - Filter dictionary and classification
4. Slice 10 - Source platform interface
5. Slice 4 - Affino procurement datagrid backend
6. Slice 5 - Manual workflow editing
7. Slice 6 - Cost calculator V1
8. Slice 7 - Tender scoring V1
9. Slice 8 - Frontend Affino datagrid
10. Slice 9 - Telegram notifications
11. Slice 11 - Operational diagnostics

## Deployment Notes

- Apply procurement migrations before enabling `procurement-sync-worker`.
- Keep `PROCUREMENT_SYNC_ENABLED=false` until EIS parser and grid backend pass smoke tests.
- First production smoke:
  - run manual sync with `limit=20`
  - verify dedupe
  - verify `/api/v1/procurements/lots`
  - verify `/tenders`
  - check parser logs for missing critical fields
- Turn on worker with a daily interval first; move to 1-3 hours after parser stability is proven.
