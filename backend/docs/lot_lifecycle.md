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

The next step is candidate selection only: a query can list lots with `enrichment_requested_at` set so a future worker can consume them without inventing a new scheduling system. This slice still does not fetch detail data.

Enrichment priority is still query-time logic, not a persisted column. The worker orders requested lots by local evidence only:

- higher `rating_score` first
- nearer deadlines first when scores are equal or missing
- fresher source/list rows first when score and deadline are equal
- then request time and record id for deterministic ties

That keeps the claim path conservative and reviewable while the architecture is still transitioning.

There is now a dry-run execution path that loads those candidates, evaluates local evidence, and returns processing metadata. It still does not fetch external detail data or mutate lots beyond the scheduling marker that was already written at source sync time.

The real execution path now routes through the existing `ensure_lot_detail_cache(...)` service. The worker does not implement its own detail fetcher; it only consumes the existing cache-refresh boundary, keeps the candidate limit small, and clears the request marker only when the refreshed local evidence is sufficient.

There is also a conservative TTL refresh policy for active, high-value lots. If a detail cache is older than the configured TTL and the lot still looks important locally, source sync can mark it for enrichment again using the same `enrichment_requested_at` marker. The policy is intentionally narrow:

- only non-terminal lots
- only when the cached detail is stale
- only when the lot is high-scoring or near its deadline
- no aggressive refresh of low-priority lots

This is still scheduling only. The worker continues to use the same existing detail-cache service when it eventually refreshes the lot.

For operational visibility, the backend also exposes a small pipeline counter snapshot:

- `enrichment_requested`: lots marked for enrichment
- `enrichment_due_now`: requested lots that are eligible to be claimed now
- `enrichment_claimed_active`: lots with an active enrichment lease
- `enrichment_retry_waiting`: requested lots waiting for backoff
- `enrichment_failed_with_error`: lots with a recorded enrichment failure message
- `scoring_stale_or_incomplete`: lots whose persisted score identity is stale or incomplete
- `scored_current`: lots whose persisted score identity is current

These counters are local DB snapshots only. They are meant for lightweight diagnostics and do not change any worker behavior.

Failed or still-incomplete attempts now set a conservative retry schedule on the lot record:

- `last_enrichment_attempt_at`
- `enrichment_attempt_count`
- `next_enrichment_attempt_at`
- `last_enrichment_error`
- `enrichment_claimed_at`
- `enrichment_claimed_by`
- `enrichment_claim_expires_at`

Candidate selection ignores lots whose next retry is still in the future or whose lease is still active, so the worker does not hammer the same lots repeatedly and concurrent workers do not process the same lot at the same time. The lease is intentionally short and bounded; if a worker dies, the claim expires and another worker can reclaim the lot later.
