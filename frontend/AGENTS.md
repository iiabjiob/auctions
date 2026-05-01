# AGENTS.md

## Project

This project is an scraper of auctions and bankruptcy lots analysis platform.

The goal is to collect public auction/bankruptcy data, normalize it, enrich it, and help users evaluate lots using structured analysis, scoring, filters, risk flags, and investment-style summaries.

## Stack

- Frontend: Vue 3, TypeScript, Tailwind
- Backend: FastAPI, Python, SQLAlchemy 2.x, Alembic
- Database: PostgreSQL
- Deployment: Docker / Docker Compose
- Preferred architecture: clean separation between API, services, repositories, schemas, models, and frontend modules.

## Main product areas

- Auction source ingestion
- Lot parsing and normalization
- Price reduction schedules
- Lot risk analysis
- Region/category filters
- ROI and resale potential estimation
- Legal/status flags
- Smart summaries for each lot
- Admin/import diagnostics

## Coding rules

- Do not rewrite large parts of the app unless needed.
- Prefer small, reviewable commits.
- Keep backend logic out of routes; use services.
- Keep DB access in repository/data-access layer where possible.
- Use typed Pydantic schemas for API contracts.
- Use SQLAlchemy migrations for schema changes.
- In Vue, use Composition API and TypeScript.
- Avoid `any` unless absolutely necessary.
- Keep UI practical, dense, and dashboard-friendly.
- Do not introduce paid external services without asking.
