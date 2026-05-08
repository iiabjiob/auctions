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

The first local builder is
`app.services.lot_decision_report.build_lot_decision_report(...)`.
It accepts an `AuctionLotRecord`, optional local detail cache, optional work
item, and optional scoring profile. It reads local state only and does not
recalculate or mutate score values.

Current conservative derivation rules:
- low scores, manual rejects, exclusions, and strong blockers become
  `ignore`/`watch`
- good scored lots become `inspect`, or `calculate` when deadline urgency is
  visible in local score metadata
- high scored lots only become `bid_candidate` when a profile match or manual
  bid/approval signal is present
- missing local documents add a `request_docs` next action
- inspect/calculate/bid-candidate reports include practical inspection and
  max-bid actions where applicable

The report is a presentation and delivery contract, not a scoring engine. It
must not change score values or scoring formulas. Telegram should later render
messages from this report or a derivative notification contract, but sending and
deduplication belong to later slices.

Use `lot_decision_report_canonical_json(...)` and
`build_lot_decision_report_hash(...)` when a deterministic serialized payload or
identity for an equivalent report payload is needed.
