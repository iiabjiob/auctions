# Scoring Profile Contract

The backend now has a small profile contract for describing user or company scoring preferences.

The contract includes:

- `profile_identifier`
- `target_regions`
- `target_categories`
- `budget_min`
- `budget_max`
- `minimum_roi`
- `minimum_discount`
- `allowed_legal_risks`
- `max_distance_km`
- `stop_words`
- `desired_keywords`
- `strategy`
- `weights`

The profile is normalized deterministically and can be hashed for identity, comparison, or future caching.

### Profile-fit weights

The additive `profile_fit` dimension supports these optional override keys in `weights`:

- `profile_fit.match_bonus`
- `profile_fit.blocker_penalty`
- `profile_fit.neutral`

The service clamps these overrides to a conservative range before they reach the scorer, so extreme values cannot distort the score unexpectedly.

This is still a contract layer for now.
No profile is persisted in the database as part of this slice.

The record score identity path can now include an explicit profile hash when one is provided, so the persisted score input hash can vary by user/company profile without changing score formulas or score values.

Passing a `LotScoringProfile` object or an explicit `profile_hash` still only affects score identity, while the runtime scorer remains backward-compatible with the existing base dimensions.

## Profile-fit preview

There is also a local-only preview helper that evaluates `LotEvidence` against a `LotScoringProfile` and returns profile-fit reasons and blockers for region, category, budget, legal risk, keywords, and distance availability.

It is intentionally read-only and deterministic. The main scoring path now uses it as an additive `profile_fit` dimension, but the base score formula and existing dimensions remain unchanged.
