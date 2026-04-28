# Auctions Backend
FastAPI + AsyncPG

### Startup order

Before running any of the commands below in a devcontainer, activate the backend Python environment (e.g. `cd backend && source .venv/bin/activate`) or prefix commands with `uv run` so they reuse the managed virtualenv.

For one-click startup in VS Code, run task `backend: start all` (Terminal → Run Task). It launches all processes below in parallel, each in its own dedicated terminal.

1. Infrastructure:
	```bash
	docker compose up -d db redis
	```

1.1. Migrations:
	```bash
	uv run alembic upgrade head
	```

2. FastAPI (REST + SSE events):
	```bash
	uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
	```

3. Auction sync worker:
	```bash
	uv run python -m app.worker.auction_sync_worker
	```

4. Auction analysis worker:
	```bash
	uv run python -m app.worker.auction_analysis_worker
	```

The worker refreshes enabled auction vendors on `AUCTION_SYNC_INTERVAL_SECONDS`, writes snapshots to Postgres, and publishes `sync.started`, `sync.completed`, and `sync.failed` messages to the Redis Stream configured by `AUCTION_EVENTS_STREAM`. The API exposes those stream messages as SSE at `/api/v1/auctions/events`, so the frontend can refresh its persisted snapshot without manual sync buttons.

During each list sync, the worker also performs a bounded detail sync when `AUCTION_DETAIL_SYNC_ENABLED=true`. It fetches and caches full lot/auction details for up to `AUCTION_DETAIL_SYNC_LIMIT` records per source sync cycle, defaulting to 25, then recalculates the materialized rating from the cached details and work item.

The analysis worker runs independently from scraping. It recalculates the persisted lot signal, keyword category, completeness flags, and rating using cached details plus manual work-item economics, then publishes `analysis.started`, `analysis.completed`, `analysis.failed`, and row-level `lot.row_updated` SSE events for reactive UI updates.
