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

This is still a contract layer for now.
Runtime scoring does not use the profile yet, and no profile is persisted in the database as part of this slice.

The record score identity path can now include an explicit profile hash when one is provided, so the persisted score input hash can vary by user/company profile without changing score formulas or score values.

Passing a `LotScoringProfile` object or an explicit `profile_hash` only affects score identity. Runtime scoring still does not consume profile preferences as scoring inputs in this slice.
