# Auctions Backend
FastAPI + AsyncPG

### Startup order

Before running any of the commands below in a devcontainer, activate the backend Python environment (e.g. `cd backend && source .venv/bin/activate`) or prefix commands with `uv run` so they reuse the managed virtualenv.

For one-click startup in VS Code, run task `backend: start all` (Terminal → Run Task). It launches all processes below in parallel, each in its own dedicated terminal.


1.1. Migrations:
	```bash
	uv run alembic upgrade head
	```

1.2. Seed default user (optional, explicit):
	```bash
	uv run python -m app.seeds.default_user
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

The worker refreshes enabled auction vendors on `AUCTION_SYNC_INTERVAL_SECONDS`, adds up to `AUCTION_SYNC_INTERVAL_JITTER_SECONDS` of random jitter, writes snapshots to Postgres, and publishes `sync.started`, `sync.progress`, `sync.completed`, and `sync.failed` messages to the Redis Stream configured by `AUCTION_EVENTS_STREAM`. The API exposes those stream messages as SSE at `/api/v1/auctions/events`, so the frontend can refresh its persisted snapshot without manual sync buttons. Production should use a source-friendly interval such as three hours (`10800` seconds), with manual sync or short development intervals used only for controlled runs.

The application no longer creates the default user during API startup or login. If you want the configured default user to exist, create it explicitly with the seed command above.

During each list sync, the worker collects cheap list-card data only. Price schedules are intentionally not loaded during list sync or background detail enrichment; they are loaded through the detail path and cached when a lot workspace is opened. The worker also performs a bounded detail sync when `AUCTION_DETAIL_SYNC_ENABLED=true`, fetching and caching full lot/auction details for up to `AUCTION_DETAIL_SYNC_LIMIT` records per source sync cycle, defaulting to 25, then recalculating the materialized rating from the cached details and work item.

TBankrot is available as source `tbankrot`. It can run anonymously, but authenticated mode unlocks debtor, location, and market-price fields on deeper pages. Configure it with `TBANKROT_LOGIN`, `TBANKROT_PASSWORD`, `TBANKROT_AUTH_ENABLED=true`, and `TBANKROT_PAGES`. Set `TBANKROT_PAGES=0` to crawl all pages advertised by TBankrot pagination. Keep credentials in deployment secrets or local shell environment, not in committed files.

The analysis worker runs independently from scraping. It recalculates the persisted lot signal, keyword category, completeness flags, and rating using cached details plus manual work-item economics, then publishes `analysis.started`, `analysis.completed`, `analysis.failed`, and row-level `lot.row_updated` SSE events for reactive UI updates.
