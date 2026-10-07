# api
FastAPI app, base /api/v1 (owner: Abdulaziz).

- `main.py`: routes. Now `/health` and `/health/db`; the rest of spec section 9 comes by Oct 16.
- `db.py`: Postgres connection from `DATABASE_URL`.

Run: `uvicorn api.main:app --reload --port 8000`. Deploy: see `docs/deploy.md`.
