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

The worker refreshes enabled auction vendors on `AUCTION_SYNC_INTERVAL_SECONDS`, adds up to `AUCTION_SYNC_INTERVAL_JITTER_SECONDS` of random jitter, writes snapshots to Postgres, and publishes `sync.started`, `sync.progress`, `sync.completed`, and `sync.failed` messages to the Redis Stream configured by `AUCTION_EVENTS_STREAM`. The default is a polite schedule: every 12 hours with jitter, no sync immediately on worker start, one TBankrot page per run, and no background detail fetches. Use manual sync or short development intervals only for controlled local runs.

The application no longer creates the default user during API startup or login. If you want the configured default user to exist, create it explicitly with the seed command above.

During each list sync, the worker collects cheap list-card data only. Price schedules are intentionally not loaded during list sync, background detail enrichment, or normal workspace open. The worker performs bounded detail sync only when `AUCTION_DETAIL_SYNC_ENABLED=true`; it is disabled by default to avoid pushing source marketplaces.

TBankrot is available as source `tbankrot`. It can run anonymously, but authenticated mode unlocks debtor, location, and market-price fields on deeper pages. Configure it with `TBANKROT_LOGIN`, `TBANKROT_PASSWORD`, `TBANKROT_AUTH_ENABLED=true`, and `TBANKROT_PAGES`. Keep credentials in deployment secrets or local shell environment, not in committed files. The HTTP layer spaces requests with `TBANKROT_REQUEST_MIN_DELAY_SECONDS` / `TBANKROT_REQUEST_MAX_DELAY_SECONDS` and enters a cooldown after 403/429 using `TBANKROT_BLOCKED_COOLDOWN_SECONDS`.

The analysis worker runs independently from scraping. It recalculates the persisted lot signal, keyword category, completeness flags, and rating using cached details plus manual work-item economics, then publishes `analysis.started`, `analysis.completed`, `analysis.failed`, and row-level `lot.row_updated` SSE events for reactive UI updates.
