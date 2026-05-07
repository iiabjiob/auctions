# LotEvidence

`LotEvidence` is the normalized, scoring-critical view of a lot.

Use it for ranking inputs that should come from the local database:
- price facts
- location facts
- category facts
- legal and availability signals
- deadline facts
- freshness metadata

It is not a raw HTML/detail payload and it must not fetch external data.
Builders for this contract should only read already-persisted local lot data.

Future scoring should consume `LotEvidence` instead of using scraped detail payloads directly.

`score_input_hash` should be derived from the deterministic `LotEvidence` hash plus the active scoring version, and optionally a stable profile identifier when one is available. The persistence columns already exist on `auction_lot_records`; this slice only adds the hash builder, not a new scoring flow.

At this stage `LotEvidence` is part of the score input identity, but the scoring engine still uses the existing legacy runtime inputs for the actual score computation.

When the persisted `score_input_hash` matches the freshly computed one and the stored score state is complete, the scorer can skip recomputation safely. This is an idempotency check, not a change to the rating formula.

Use `invalidate_lot_score(...)` to mark a record stale after local evidence changes. The supported reasons are:
- `source_content_changed`
- `detail_content_changed`
- `profile_changed`
- `scoring_config_changed`
- `manual_economics_changed`
- `source_status_changed`
- `ttl_expired`

The first safe wiring point is the detail-cache refresh branch in `ensure_lot_detail_cache(...)`: when the persisted detail `content_hash` changes, call `invalidate_lot_score(record, reason=detail_content_changed)` before the next scoring pass. If the content hash is unchanged, do not invalidate.

The first safe source/list wiring point is the existing `content_changed` branch in `sync_source_lots(...)`: when the persisted list snapshot hash changes, call `invalidate_lot_score(record, reason=source_content_changed)` and keep the previous UI-facing score payload until the next score pass runs. If the source hash is unchanged, do not invalidate.

The intended future wiring points are source sync, detail enrichment, manual economics updates, profile/config edits, and TTL-based freshness checks. For now the helper only clears the persisted score identity so the worker can pick the record up again without dropping the previous UI-facing score payload.
