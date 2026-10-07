"""Nizam Radar API, base /api/v1 (spec section 9).

Hello-world version for CP1: /health for deploy checks and /health/db to
prove the deployed API reaches the database. Real routes come by Oct 16.

Run locally:  uvicorn api.main:app --reload --port 8000
"""

from __future__ import annotations

import os

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api import db
from contracts.models import SCHEMA_VERSION

app = FastAPI(title="Nizam Radar API", version=SCHEMA_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
                   if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

v1 = APIRouter(prefix="/api/v1")


@v1.get("/health")
def health():
    return {"status": "ok"}


@v1.get("/health/db")
def health_db():
    try:
        return {"status": "ok", **db.check()}
    except Exception as e:  # report, don't crash: this is a diagnostics route
        # Only the error type and first line, so a connection string can't leak.
        msg = str(e).splitlines()[0][:200] if str(e) else ""
        return JSONResponse(status_code=503, content={
            "error": {"code": "db_unavailable", "message": f"{type(e).__name__}: {msg}"}})


app.include_router(v1)
