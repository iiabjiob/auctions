# Auction Scoring Manual Review Workflow

This workflow closes the loop between deterministic scoring, operator judgment, and future scoring changes.

## Review Buckets

Use the same bucket names in exports, notes, and new golden fixtures:

- `true_positive`: highly ranked lot that should stay highly ranked.
- `false_positive`: highly ranked lot that should have been capped, penalized, or excluded.
- `false_negative`: low or medium ranked lot that should have been promoted.
- `needs_more_data`: score is inconclusive because documents, photos, price, or legal inputs are missing.
- `policy_change`: ranking is wrong because the owner profile or business rule changed.

## Weekly Review Loop

1. Export the top 100 rows using `docs/sql/auction-top-rated-score-diagnostics.sql`.
2. Review every row with `rating_score >= 85`, every high-risk row with `rating_score >= 70`, and every row with a cap that still appears in a shortlist.
3. Mark each reviewed row with one review bucket, a short operator note, and the expected action: keep, cap, exclude, promote, or collect data.
4. Convert stable false positives and false negatives into `backend/tests/fixtures/auction_scoring_golden_cases.json`.
5. Run `uv run python -m unittest discover -s tests` before changing weights, caps, owner profile defaults, or analysis rules.
6. If a scoring change intentionally moves ranks, update the fixture `baseline_rank` values in the same change as the scoring code.

## Required Review Fields

- `lot_record_id`
- `reviewed_at`
- `reviewer`
- `review_bucket`
- `expected_action`
- `operator_note`
- `score_at_review`
- `score_breakdown_at_review`
- `accepted_for_fixture`

These fields can start as a spreadsheet/export. When review volume becomes regular, persist them in a dedicated table and use accepted reviews to generate fixture updates.
