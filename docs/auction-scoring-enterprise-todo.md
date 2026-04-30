# Auction Scoring Enterprise TODO

This document is the implementation checklist for turning lot rating into the core enterprise discovery feature.

Rule for maintaining it: after each implemented and verified item, change `[ ]` to `[x]` and add a short note with the PR/change summary when useful.

## Goal

The platform must calculate a fast, explainable, high-quality rating for every lot whenever the lot is loaded, changed, enriched, or manually edited.

The final score should help the operator quickly answer:

- Is this lot worth attention?
- Why is it rated this way?
- Which risks or missing inputs limit the score?
- What changed since the previous score?
- Is the score current for the active scoring rules?

## Phase 1: Single Source Of Truth

- [x] Create a dedicated backend scoring module, for example `backend/app/services/auction_scoring.py`.
- [x] Move the main rating logic out of `auction_workspace._calculate_workspace_rating`.
- [x] Replace `auction_catalog.calculate_lot_rating` with the same scoring engine in a lightweight/list mode.
- [x] Make `sync_source_lots`, `get_lot_workspace`, `update_lot_work_item`, and `auction_analysis_worker` call the same scoring entry point.
- [x] Keep list-only scoring cheap: it must not force detail fetches, document fetches, or price schedule fetches.
- [x] Add regression tests proving new lot sync, detail refresh, manual work item update, and background worker all use the same scoring version.

Done when:

- There is one canonical scoring entry point.
- No persisted lot receives a score from an obsolete secondary rating function.
- Existing golden rating tests still pass.

## Phase 2: Versioning And Auditability

- [x] Add DB fields to `auction_lot_records`: `scoring_version`, `scored_at`, `score_input_hash`, and `score_breakdown`.
- [x] Add Alembic migration and indexes needed for stale-score selection.
- [x] Include scoring metadata in `datagrid_row.rating` or an adjacent API field without breaking the current frontend.
- [x] Compute `score_input_hash` from normalized lot data, detail cache hash, work item inputs, and scoring config version/hash.
- [x] Recalculate only when the input hash or scoring version changes, unless forced.
- [x] Add unit tests for stale/current scoring decisions.

Done when:

- We can query which lots have stale scores.
- We can explain which scoring version produced a visible score.
- Re-running scoring on unchanged inputs is idempotent.

## Phase 3: Score Dimensions

- [x] Replace the monolithic additive score with explicit dimensions.
- [x] Add `economics` dimension: current price, market value, total expenses, full entry cost, potential profit, ROI, market discount, max purchase price.
- [x] Add `risk` dimension: legal risk, exclusion keywords, source status, cancellation, disputed/pledged/debt/right-claim markers.
- [x] Add `urgency` dimension: application deadline, auction date, stage, time-to-act.
- [x] Add `data_quality` dimension: documents, photos, detail cache freshness, description quality, price parse confidence.
- [x] Add `operational_readiness` dimension: inspection order, delivery/dismantling complexity, known expenses, application/deposit readiness.
- [x] Add `owner_fit` dimension placeholder, initially neutral until owner profile is implemented.
- [x] Add `manual_intent` dimension: reject, watch, calculate, inspection, bid, final decision.
- [x] Store dimension scores and top reasons in `score_breakdown`.
- [x] Show the most useful breakdown in the UI rating tooltip.

Change summary: scoring now records `base_score`, `raw_score`, per-dimension scores/reasons, and cap reasons in `score_breakdown`; the frontend rating tooltip renders the stored dimensions and caps from API payloads.

Done when:

- The final score is reproducible from named dimensions.
- Reasons are grouped enough for a user to trust the rating.
- Top-rated lots can be audited from DB JSON without reading Python code.

## Phase 4: Caps, Gates, And Safety Rules

- [x] Implement hard caps as a separate scoring layer, not mixed into bonuses.
- [x] Cap manually rejected lots to low priority.
- [x] Cap excluded lots to low priority.
- [x] Cap cancelled or completed/non-actionable lots to low priority.
- [x] Cap high legal-risk lots below high rating unless manually approved.
- [x] Cap lots with missing price below high rating.
- [x] Add explicit cap reasons to `score_breakdown`.
- [x] Add regression tests for every cap.

Change summary: scoring now computes raw dimension score first, then applies explicit caps through a separate guardrail layer. Caps cover manual reject, excluded lots, cancelled/non-actionable statuses, high legal risk unless manually approved, and missing price.

Done when:

- A risky or manually rejected lot cannot be promoted by good economics alone.
- The UI can explain not only why a lot scored high, but also why it was limited.

## Phase 5: Owner Interest Profile

- [x] Expand analysis config schema to include owner scoring profile.
- [x] Add target regions.
- [x] Add target asset classes/categories.
- [x] Add budget range.
- [x] Add minimum ROI and minimum market discount.
- [x] Add excluded terms and discouraged terms.
- [x] Add operational constraints: delivery distance, dismantling complexity, legal risk tolerance, document requirements.
- [x] Add dimension weights configurable from backend defaults first, UI later.
- [x] Make `owner_fit` dimension use the profile.
- [x] Add tests for profile matching and mismatching lots.

Change summary: analysis config now stores `owner_profile` and `dimension_weights`; runtime scoring includes them in score input hash and applies them to `owner_fit` and weighted dimension totals. The current frontend analysis-config editor preserves these fields even before dedicated UI controls exist.

Done when:

- The score reflects what the operator actually wants to buy.
- The same lot can score differently after profile changes, with versioned recalculation.

## Phase 6: Recalculation Pipeline

- [x] Recalculate immediately when a lot is created.
- [x] Recalculate immediately when list-card content changes.
- [x] Recalculate immediately when detail cache is loaded or refreshed.
- [x] Recalculate immediately when work item fields change.
- [x] Queue recalculation when analysis/scoring config changes.
- [x] Prioritize opened lot and visible viewport rows.
- [x] Add background stale-score worker using `scoring_version` and `score_input_hash`.
- [x] Publish SSE updates only for rows whose visible score/breakdown changed.
- [x] Add metrics/logs: processed, changed, unchanged, skipped-current, failed.

Change summary: sync now recalculates records immediately on create and list-card changes, opened lots/work-item updates still recalculate synchronously, visible datagrid rows self-heal stale scores, analysis config updates invalidate current scores for worker pickup, and the background worker processes only stale records with explicit metrics and score-payload based SSE publishing.

Done when:

- The catalog score updates quickly for changed/visible lots.
- Full-dataset rescoring can run safely in the background.
- Recalculation does not overload source marketplaces.

## Phase 7: Evaluation And Quality Control

- [x] Build a golden fixture set of real or realistic lots.
- [x] Include known excellent lots.
- [x] Include good-economics/high-risk lots.
- [x] Include excluded categories.
- [x] Include missing-data lots.
- [x] Include urgent lots.
- [x] Include manual reject/watch/bid cases.
- [x] Add a scoring regression report comparing old vs new ranks.
- [x] Add diagnostic SQL for top-rated lots with score breakdown and cap reasons.
- [x] Add a manual review workflow for false positives and false negatives.

Change summary: golden cases live in `backend/tests/fixtures/auction_scoring_golden_cases.json`; `auction_scoring_evaluation` builds a regression report with current rank vs baseline rank and expectation failures; production diagnostics live in `docs/sql/auction-top-rated-score-diagnostics.sql`; manual review workflow lives in `docs/auction-scoring-manual-review-workflow.md`.

Done when:

- A scoring rule change can be evaluated before it reaches production.
- We can tell whether ranking quality improved, not just whether tests passed.

## Phase 8: AI-Assisted Ranking Later

- [x] Keep deterministic score and AI score separate.
- [x] Send only deterministic shortlist candidates to AI.
- [x] Store AI model version, prompt version, explanation, confidence, and created_at.
- [x] Add operator feedback fields for accepted/rejected AI suggestions.
- [x] Compare deterministic rank vs AI rank on the evaluation set.

Change summary: AI ranking is modeled as a separate enrichment layer in `auction_lot_ai_analyses`; `auction_ai_ranking` selects only deterministic shortlist candidates, builds auditable AI payloads, stores model/prompt metadata and feedback, and evaluation reports can compare deterministic rank against AI rank without changing deterministic score.

Done when:

- AI improves prioritization without becoming the only reason a lot is promoted.
- Every AI recommendation remains auditable next to deterministic facts.

## Current Implementation Notes

- Canonical deterministic scoring now lives in `backend/app/services/auction_scoring.py`.
- Shared price parsing lives in `backend/app/services/auction_values.py`.
- Shared datagrid row payload validation lives in `backend/app/services/auction_datagrid_payload.py`.
- Current simple list score is exposed through `calculate_list_lot_rating`.
- Current richer persisted/workspace score is exposed through `recalculate_record_rating`.
- Scoring metadata fields are added by migration `202604280006_add_lot_scoring_metadata.py`.
- Current signal/category/legal-risk analysis lives in `backend/app/services/auction_analysis.py`.
- Current analysis config lives in `backend/app/services/auction_analysis_config.py`.
- Current background recalculation lives in `backend/app/worker/auction_analysis_worker.py`.
- Current golden tests live in `backend/tests/test_auction_rating.py`.
