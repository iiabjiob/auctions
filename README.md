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

The production stack includes `db`, `redis`, `migrations`, `backend`, `auction-worker`, and `nginx`.
