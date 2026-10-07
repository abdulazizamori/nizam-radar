"""Offline tests for the hello-world API (no database needed)."""

from fastapi.testclient import TestClient

from api import db
from api.main import app

client = TestClient(app)


def test_health():
    r = client.get("/api/v1/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_health_db_ok(monkeypatch):
    monkeypatch.setattr(db, "check", lambda: {"postgres": "16.4", "pgvector": "0.7.0"})
    r = client.get("/api/v1/health/db")
    assert r.status_code == 200 and r.json()["pgvector"] == "0.7.0"


def test_health_db_down_does_not_leak_url(monkeypatch):
    secret = "postgresql://u:SECRETPW@host/db"

    def boom():
        raise RuntimeError(f"could not connect\nfull url: {secret}")

    monkeypatch.setattr(db, "check", boom)
    r = client.get("/api/v1/health/db")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "db_unavailable"
    assert "SECRETPW" not in r.text


def test_cors_allows_local_web_app():
    r = client.options("/api/v1/health", headers={
        "Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"
