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

This is only a contract layer for now.
Runtime scoring does not use the profile yet, and no profile is persisted in the database as part of this slice.
