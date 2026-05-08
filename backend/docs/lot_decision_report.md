# LotDecisionReport

`LotDecisionReport` is the shared backend output contract for lot decisions.
The same report shape is intended to feed the UI decision report and future
Telegram notification rendering.

This slice is local-only:
- it does not perform scoring
- it does not scrape or fetch external data
- it does not send Telegram messages
- it does not call Telegram APIs or any external notification service
- it does not persist decision report snapshots
- it does not change frontend behavior

The contract captures the already-known lot identity, display fields, current
rating, optional profile-fit context, optional economics decision, decision
level, recommendation, reasons, risks, next actions, and generation time.

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

`LotEconomicsDecision` is the local max-buy economics contract attached to a
decision report. It includes:
- current price
- market value
- expected costs
- target ROI
- max buy price
- estimated profit
- confidence
- missing inputs

Use `calculate_lot_economics_decision(...)` to build it from local data. The
helper prefers manual/work-item economics where they exist: work-item market
value overrides scraped/local market value, and work-item fee/cost fields are
summed into expected costs. The helper does not invent market value. If market
value is missing, `max_buy_price` and `estimated_profit` stay empty, confidence
is `low`, and `missing_inputs` includes `market_value`.

The max-buy calculation is conservative and explainable:
`max_buy_price = (market_value - expected_costs) / (1 + target_roi)`.
`target_roi` comes from an explicit helper argument, then profile
`minimum_roi`, then the local default.

`LotNotificationEligibility` is the Telegram-ready local notification contract.
It includes:
- `should_notify`
- `priority`
- `reasons`
- `blockers`
- `dedupe_key`
- `cooldown_key`

Use `evaluate_lot_notification_eligibility(report, profile=None)` to decide
whether a decision report is eligible for future Telegram delivery. The helper
does not send messages and does not integrate with Telegram. It only returns a
local contract that a later outbox/sender slice can consume.

Eligibility is intentionally conservative:
- `ignore` and `watch` reports are blocked
- high risks block notification
- notifiable reports need a high decision level, or an inspect-level report
  with a high score
- a qualifying report must also have a high score, profile-fit signal, or near
  deadline
- `dedupe_key` changes when meaningful report state changes
- `cooldown_key` stays stable for the same lot/profile so a future sender can
  rate-limit repeated alerts

`auction_lot_decision_reports` stores the latest local decision report snapshot
for fast UI and future Telegram reads. It stores:
- `lot_record_id`
- nullable `profile_hash`
- `report_payload`
- `decision_level`
- `recommendation`
- `notification_should_send`
- `report_hash`
- `generated_at`

The table is latest-snapshot only. It has one no-profile snapshot per lot and
one snapshot per lot/profile hash. `upsert_lot_decision_report_snapshot(...)`
updates the existing row or creates it when missing. `report_hash` is computed
from meaningful report content and excludes `generated_at`, so unchanged report
content keeps a stable hash across regeneration.

The report is a presentation and delivery contract, not a scoring engine. It
must not change score values or scoring formulas. Telegram should later render
messages from this report or a derivative notification contract, but sending and
deduplication belong to later slices.

Use `lot_decision_report_canonical_json(...)` and
`build_lot_decision_report_hash(...)` when a deterministic serialized payload or
identity for an equivalent report payload is needed.
