# LotDecisionReport

`LotDecisionReport` is the shared backend output contract for lot decisions.
The same report shape is intended to feed the UI decision report and future
Telegram notification rendering.

This slice is local-only:
- it does not perform scoring
- it does not scrape or fetch external data
- it does not send Telegram messages
- it does not persist decision report snapshots
- it does not change frontend behavior

The contract captures the already-known lot identity, display fields, current
rating, optional profile-fit context, decision level, recommendation, reasons,
risks, next actions, and generation time.

`decision_level` uses this stable vocabulary:
- `ignore`
- `watch`
- `inspect`
- `calculate`
- `bid_candidate`

`recommendation` uses this stable vocabulary:
- `ignore`
- `monitor`
- `request_docs`
- `inspect`
- `calculate_max_bid`
- `prepare_bid`

Future builders should derive `LotDecisionReport` only from local state, such as:
- `LotEvidence`
- score breakdown and rating metadata
- economics and max-buy calculations
- profile fit evaluation
- manual/workspace decision fields

The report is a presentation and delivery contract, not a scoring engine. It
must not change score values or scoring formulas. Telegram should later render
messages from this report or a derivative notification contract, but sending and
deduplication belong to later slices.

Use `lot_decision_report_canonical_json(...)` and
`build_lot_decision_report_hash(...)` when a deterministic serialized payload or
identity for an equivalent report payload is needed.
