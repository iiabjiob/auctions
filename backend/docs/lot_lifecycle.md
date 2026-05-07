# Auction Lot Lifecycle

The backend treats local auction lots as moving through a small processing lifecycle:

- `discovered`
- `list_synced`
- `needs_enrichment`
- `enriched`
- `scored`
- `active`
- `stale`
- `archived`

This slice adds the contract and helper predicates only. It does not add a new database column or rewrite worker behavior.

Ownership is split by concern:

- Source ingestion owns discovery and list-sync state.
- Detail enrichment owns evidence completeness.
- Scoring owns score freshness and invalidation.
- The grid only reads local persisted state.
- External sources are ingestion/enrichment dependencies, not part of the user-facing workflow.

`stale` means the persisted score identity is no longer current and the lot needs rescoring.
`archived` is terminal.

The helpers in `app.services.auction_lifecycle` are intentionally conservative and derived from already-persisted local data.

Enrichment is driven by evidence requirements, not by whether the UI detail card was opened. The first-pass scorer only needs a small local evidence set:

- price facts
- location facts
- category facts
- deadline facts

If those are present in persisted local data, the lot does not need enrichment. Optional detail-only facts like documents, media, and description improve ranking quality later, but they are not hard requirements for the first pass.

This slice classifies lots as locally scorable or needing enrichment. When a source sync detects missing first-pass evidence, the backend now writes a lightweight `enrichment_requested_at` marker on the lot record. That marker is only a scheduling hint, not a worker pipeline:

- it is set when the classification says enrichment is needed
- it is cleared when the lot is locally scorable again
- it is not a queue, job table, or background fetcher
- it does not open the UI detail card or call external sources
