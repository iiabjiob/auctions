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
