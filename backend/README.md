# Renfu Next Backend

FastAPI backend for the new Renfu split-stack architecture.

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 9000
```

## Highlights

- FastAPI + SQLAlchemy 2.x + Alembic
- Cookie-based auth with access + refresh tokens
- PostgreSQL-first schema with per-user isolation
- WebSocket stream under `/ws/v1/stream`
- Optional `legacy` mount for the existing Flask app under `/legacy`

## Commands

- `uvicorn app.main:app --reload --port 9000`
- `alembic upgrade head`
- `pytest backend/tests -q`
