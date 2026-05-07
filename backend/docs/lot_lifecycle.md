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
