# Auction Platform Architecture

## Goal

The platform should aggregate lots from multiple auction marketplaces, normalize them into one domain model, and expose a stable API for a rich datagrid UI with filtering, freshness markers, and lot scoring.

## Layers

1. Source providers
   - One provider per marketplace.
   - Provider contract lives in `backend/app/services/auction_sources.py`.
   - A provider fetches source-specific pages/API responses and returns normalized `AuctionListItem`, `LotDetailResponse`, and `AuctionDetailResponse` objects.

2. Catalog service
   - Source-agnostic orchestration lives in `backend/app/services/auction_catalog.py`.
   - It combines providers, applies filters, prepares datagrid rows, calculates draft ratings, and exposes freshness fields.

3. API layer
   - Stable routes live under `/api/v1/auctions`.
   - `/api/v1/auctions/lots` is the main datagrid endpoint.
   - `/api/v1/auctions/sources` lists available marketplaces.
   - `/{source}/lots/{lot_id}` and `/{source}/{auction_id}` provide source-aware detail pages.

4. Persistence layer, next step
   - Store source snapshots in Postgres.
   - Use a source-specific external key: `source + auction_external_id + lot_external_id`.
   - Keep immutable fetch snapshots for audit/debug and normalized current rows for filters.
   - Compare snapshots to populate `first_seen_at`, `last_seen_at`, `status_changed_at`, and `is_new`.

## Datagrid Contract

The UI should consume `LotDatagridResponse`:

- `columns`: server-owned grid metadata for `affino/datagrid-vue-app`.
- `rows`: normalized lot rows from all enabled sources.
- `filters`: the filters applied by the request.
- `available_sources`: source selector options.
- `total`: count after filtering.

Current filters:

- `source`
- `q`
- `status`
- `min_price`
- `max_price`
- `only_new`
- `min_rating`
- `limit`

## Rating

The current rating is a deterministic draft in `calculate_lot_rating`. It intentionally returns both `score` and `reasons` so the user can understand why a lot is highlighted.

Future rating inputs:

- User preferences: regions, categories, price ranges, excluded terms.
- Lot quality: documents present, photos present, inspection terms, debt/pledge warnings.
- Time pressure: application deadline proximity.
- Market heuristics: discount against comparable market price.
- Risk heuristics: cancelled status, unclear ownership, missing documents.

## Freshness

Freshness is modeled now but requires persistence to become meaningful:

- New lot: not seen in previous snapshot.
- Updated lot: normalized fingerprint changed.
- Status changed: status differs from previous snapshot.

Until the DB snapshot layer is implemented, `is_new` remains `false`.

## Adding A New Marketplace

1. Implement a provider class with the `AuctionSourceProvider` methods.
2. Normalize source-specific data into existing schemas from `backend/app/schemas/auctions.py`.
3. Register the provider in `SOURCE_PROVIDERS`.
4. Add smoke tests for list/detail parsing and at least one fixture page.