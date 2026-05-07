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
