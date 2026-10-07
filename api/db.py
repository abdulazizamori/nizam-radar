"""Database connection. DATABASE_URL comes from .env locally and from the
host's environment variables when deployed (never commit it)."""

from __future__ import annotations

import os

import psycopg
from dotenv import load_dotenv

load_dotenv()


def connect() -> psycopg.Connection:
    url = os.environ.get("DATABASE_URL", "")
    if not url or "user:pass@localhost" in url:
        raise RuntimeError("DATABASE_URL is not set (still the .env.example placeholder).")
    return psycopg.connect(url, connect_timeout=10)


def check() -> dict:
    """Connect, make sure pgvector is enabled, and report versions."""
    with connect() as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        pg = conn.execute("SHOW server_version").fetchone()[0]
        vec = conn.execute(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'").fetchone()[0]
    return {"postgres": pg, "pgvector": vec}
