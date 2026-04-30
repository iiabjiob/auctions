# Auction AI Ranking Contract

AI ranking is an enrichment layer. It must never replace deterministic scoring as the source of truth for filtering, caps, or audit.

## Inputs

Only deterministic shortlist candidates are eligible for AI:

- `rating_score >= 85`, or
- manual work status is one of `watch`, `calculate`, `inspection`, `bid`.

Candidate payloads must include deterministic facts:

- deterministic score, level, scoring version, and score breakdown;
- lot identity and source identity;
- analysis status, legal risk, caps, and economy fields;
- work item decision/comment fields when available;
- detail cache/document summary when available.

## Storage

AI results are stored in `auction_lot_ai_analyses`, separately from `auction_lot_records.rating_score`.

Required audit fields:

- `model_version`
- `prompt_version`
- `ai_score`
- `explanation`
- `confidence`
- `input_payload`
- `output_payload`
- `created_at`

Operator feedback fields:

- `operator_feedback_status`: `accepted`, `rejected`, or `needs_review`
- `operator_feedback_comment`
- `operator_feedback_at`
- `operator_feedback_by`

## Evaluation

Evaluation reports compare deterministic rank and AI rank side by side. AI can reprioritize reviewed shortlist candidates, but deterministic caps and exclusions remain auditable and enforceable.
