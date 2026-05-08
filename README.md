# Vue + FastAPI Starter

Clean monorepo starter for:
- Vue 3 + Vite + Tailwind (frontend)
- FastAPI + async SQLAlchemy + Postgres (backend)
- Redis Stream + background worker for auction vendor updates
- Devcontainer (Docker)
- pnpm + uv

## Production compose

1. Prepare env files:
   `cp backend/.env.prod.example backend/.env.prod`
   `cp backend/.env.db.prod.example backend/.env.db.prod`
   `cp frontend/.env.example frontend/.env.local`

2. Review secrets in `backend/.env.prod` and `backend/.env.db.prod`.
   If the frontend API runs on a different origin, set `VITE_API_BASE_URL` in `frontend/.env.local`.

3. Start the stack:
   `docker compose -f docker-compose.prod.yml up -d --build`

The production stack includes `db`, `redis`, `migrations`, `backend`, auction sync/analysis/enrichment workers, `telegram-sender-worker`, and `nginx`.

Telegram delivery is dry-run by default. To send real messages, set `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and `TELEGRAM_SENDER_DRY_RUN=False`.
To preview one visual test message without touching the outbox, run `uv run python scripts/send_test_telegram_message.py --print-only` from `backend/`.
To send that test message to Telegram, run `uv run python scripts/send_test_telegram_message.py` from `backend/`.
