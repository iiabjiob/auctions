# Auction Enterprise Optimization Roadmap

## Product Direction

The system is moving from a scraper-backed table to an enterprise auction intelligence platform. The first stage is reliable collection and display of auction lots. The next stage is optimized discovery: automatically finding the lots most likely to interest the system owner, with deterministic scoring first and AI-assisted ranking later.

## Operating Principles

- Do not overload source marketplaces. Prefer slow, predictable background syncs over aggressive crawling.
- Every visible filter and sort must apply to the full persisted dataset, not only to rows currently loaded in the browser.
- Keep the browser lightweight. Load only the visible slice plus enough metadata for totals, counters, and saved views.
- Treat heavy source requests as explicit work: details, documents, and price schedules should be lazy or queued.
- Keep stale lots out of the active catalog while preserving enough history for audit and analytics.
- Close every application-logic task with golden cases, regression tests, or production diagnostic queries. Component-level benchmarks are useful separately, but the product priority is correct ranking and fast reaction to attractive lots.

## Stage 1: Collection And Display Hardening

### 1. Server-Side Catalog Model

Status: in progress

Goal: make `/api/v1/auctions/lots` query Postgres as the source of truth for filtering, sorting, counts, and pagination.

Work items:

- Done: move quick filters from Python post-processing into SQL `WHERE` clauses.
- Add explicit API parameters for `sort_by` and `sort_direction`.
- Done: apply default sorting and first-column grid sorting in SQL.
- Done: pass full Affino `sortModel` and apply multi-column ordering in SQL.
- Done: connect the frontend through the official Affino `DataSourceBackedRowModel` instead of loading a large client-side page.
- Done: return only the requested viewport range while `total` reflects the full filtered dataset.
- Done: pass Affino `filterModel` to the API and apply supported column predicates, value sets, and advanced expressions in SQL.
- Keep datagrid state compatible with saved filters and future saved views.

Verification:

- Unit tests for SQL filter/sort expression building.
- Regression tests for DataGrid column filters and advanced filter expressions.
- Integration test with a large fixture proving filtered totals and sort order use the full DB dataset.
- Runtime diagnostic for slow catalog queries in production logs.

### 2. Lazy Detail And Price Schedule Loading

Status: in progress

Goal: list sync must collect cheap list-card data only. Details, documents, and price schedules should load when a detail view is opened or when an enrichment job explicitly requests them.

Work items:

- Done: disable price schedule loading during list sync.
- Done: keep price schedule loading in interactive lot detail requests only.
- Add a cache flag or timestamp showing when expensive detail data was fetched.
- Add optional refresh controls for the detail view.

Verification:

- Regression test proving list provider calls the scraper with `include_price_schedule=False`.
- Detail-view test proving `price_schedule` is present when the source returns it.
- Production log sample showing list sync progress without per-lot schedule requests.

### 3. Source-Friendly Sync Cadence

Status: in progress

Goal: reduce source pressure and avoid suspicious traffic patterns.

Work items:

- Done: change default source sync interval to 3 hours for production.
- Done: add jitter to worker sleep windows so requests are not perfectly periodic.
- Add per-source rate limits and request pauses.
- Separate fast list sync from slower detail enrichment.
- Keep manual sync available for operators.

Verification:

- Unit test for worker schedule/jitter bounds.
- Runtime metric or log showing expected next sync time.
- Production diagnostic confirming no duplicate overlapping syncs for the same source.

### 4. Diff-Oriented Crawling

Status: planned

Goal: avoid scanning all 100,000+ lots on every sync when the source does not provide a native delta feed.

Work items:

- Store per-page fingerprints for source listing pages.
- During frequent syncs, scan hot pages first and stop after a configurable number of unchanged pages.
- Use warm/cold tiers: recent pages often, older pages rarely, full crawl on a long interval.
- Detect changed lot cards by content hash and enqueue only changed/new records for enrichment.
- Keep a full backstop crawl for correctness.

Verification:

- Fixture-based test proving unchanged-page stop logic.
- Benchmark comparing source requests for full crawl vs diff crawl.
- Production counters: pages fetched, unchanged pages, new lots, changed lots.

### 5. Active Catalog Lifecycle

Status: planned

Goal: keep inactive lots out of the default working set while preserving history when useful.

Work items:

- Add lifecycle fields such as `is_active`, `archived_at`, `stale_reason`, and `last_seen_at` policy thresholds.
- Mark lots stale when they have not been seen for a configured period.
- Exclude archived/stale lots from the default catalog, with an explicit archived filter.
- Add retention cleanup for observations and old detail snapshots.
- Consider a cold archive table for long-term historical rows.

Verification:

- Migration test for lifecycle fields and indexes.
- Unit test for stale policy decisions.
- SQL diagnostic proving active catalog queries ignore stale rows by default.

### 6. Viewport-Scoped Rating Recalculation

Status: planned

Goal: avoid recalculating ratings for records the operator is not currently seeing unless they are new, changed, or explicitly queued.

Work items:

- Recalculate immediately for opened detail views and edited work items.
- Batch-recalculate records visible in the current server-side page.
- Queue background recalculation for new/changed lots and stale scoring versions.
- Store scoring version on records so old scores can be upgraded gradually.

Verification:

- Unit test for scoring-version eligibility.
- Benchmark comparing full-dataset recalculation vs page-scoped recalculation.
- Event test proving only changed visible rows are pushed to the UI.

## Stage 2: Best-Lot Discovery

### 7. Rating Correctness Foundation

Status: in progress

Goal: make rating deterministic, explainable, and safe for automatic best-lot discovery.

Work items:

- Done: add golden cases for profitable, excluded, rejected, and high legal-risk lots.
- Done: cap ratings for excluded, manually rejected, cancelled, and high legal-risk lots so they cannot be promoted accidentally.
- Split the rating into independent dimensions: economics, urgency, operational readiness, risk, source freshness, and manual intent.
- Store rating/scoring version on records so old scores can be recalculated gradually.
- Keep every high score explainable with reasons suitable for the UI.

Verification:

- Golden-case tests for known good and known bad lots.
- Regression tests for manual overrides and exclusion rules.
- Diagnostic query for top-rated lots with their reasons and risk flags.

### 8. Owner Interest Profile

Status: planned

Goal: encode what is interesting to the system owner before AI ranking is introduced.

Work items:

- Persist target regions, asset classes, budget ranges, minimum discount, excluded risk terms, and operational constraints.
- Build transparent deterministic scoring from those inputs.
- Explain every high score with human-readable reasons.

Verification:

- Unit tests for profile scoring rules.
- Golden fixtures for known good and bad lots.

### 9. AI-Assisted Ranking

Status: planned

Goal: use AI as an enrichment/ranking layer after deterministic filters have reduced the candidate set.

Work items:

- Send only shortlisted candidates to AI analysis.
- Store model version, prompt version, explanation, and confidence.
- Keep deterministic score and AI score separate.
- Add operator feedback to improve future ranking.

Verification:

- Offline evaluation set with accepted/rejected lots.
- Regression report comparing deterministic shortlist vs AI-ranked shortlist.

## Immediate Implementation Order

1. Disable list price schedule loading and prove it with a regression test.
2. Convert `/lots` to SQL-first filtering, sorting, and pagination.
3. Make the 10,000-row cap a safety cap, not a correctness limit.
4. Add active/stale lifecycle fields and cleanup job.
5. Add source-friendly sync cadence, jitter, and diff-page fingerprints.
6. Stabilize deterministic rating with golden cases and scoring-version rules.
7. Move rating recalculation to opened/changed/queued records.
8. Start best-lot discovery with deterministic owner profile scoring.
