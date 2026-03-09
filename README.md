# Renfu

This repo now carries two stacks in parallel:

- `app.py` + `templates/`: legacy Flask application
- `backend/` + `frontend/`: new split-stack architecture for the long-term product direction

## New Stack Quick Start

```bash
./scripts/run_next_api.sh
cd frontend && npm install && npm run dev
```

Then visit:

- frontend dev: `http://localhost:5173`
- backend API: `http://localhost:9000/api/v1`
- mounted legacy: `http://localhost:9000/legacy`

Default bootstrap admin credentials come from `backend/.env.example` and should be changed before real deployment.
