# Local-First Auction Analysis Architecture Checklist

## Final pipeline

- Source ingestion discovers lots and persists list data locally.
- `LotEvidence` is the local normalized evidence contract for scoring-critical facts.
- Enrichment classification decides whether local evidence is enough or the lot needs enrichment.
- Enrichment scheduling uses persisted markers, retry/backoff, leases, priority ordering, TTL refresh, and max-attempt protection.
- Enrichment execution routes through the existing detail-cache refresh service, not a second fetch implementation.
- Scoring is hash-driven and idempotent on persisted local evidence.
- Scoring can optionally consume the active persisted profile behind an explicit worker flag.
- The presentation grid is read-only against local analytical data by default.
- Live refresh and source fetches remain explicit, user-triggered paths.

## Current hardening checklist

- [ ] Claim heartbeat renewal for enrichment leases
- [ ] Admin view or route for failed-enrichment records
- [ ] Persisted lifecycle state if queryability needs to move from derived state to first-class state
- [ ] Richer source-specific evidence requirements where a source needs tighter classification
- [ ] Full source-matrix scoring regression coverage across major source shapes

## Stability notes

- Default scoring remains unchanged when the active scoring profile flag is off.
- Normal grid browsing does not fetch external source data.
- Normal detail viewing reads cached local workspace state first.
- Worker-controlled enrichment remains bounded, retriable, and claim-guarded.

