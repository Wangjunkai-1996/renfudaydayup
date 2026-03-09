# Renfu Next Stack

This repository now contains a second-generation stack alongside the existing Flask app.

## Layout

- `backend/`: FastAPI + SQLAlchemy + Alembic + worker entrypoints
- `frontend/`: Vue 3 + Vite + Pinia + Vue Query + Tailwind + ECharts
- `scripts/run_next_api.sh`: starts the new API
- `scripts/run_next_worker.sh`: starts the new worker stub
- `scripts/migrate_legacy_to_postgres.py`: imports legacy SQLite data into the new schema

## URLs

- New frontend: `/app` when `frontend/dist` is built and the FastAPI server is running
- New REST API: `/api/v1/*`
- New WebSocket: `/ws/v1/stream`
- Legacy Flask app: `/legacy`

## Current Scope

The current implementation establishes the new architecture foundation:

- Cookie-based login and session refresh
- Per-user watchlist, strategy config, paper account, signals, reports, tuning history
- Admin user management endpoints
- Shared market cache + user-isolated signal surfaces
- Legacy mounting for parallel rollout

The worker processes are stubbed but runnable, so the new frontend can already exercise the new API surface while the legacy system remains intact for parity checks.
