"""
conftest-template.py — Memo project conftest with fixture factories.

Place at: backend/tests/conftest.py

Provides:
  - Temporary SQLite database (auto-managed, CI-safe)
  - reset_db fixture (drop_all + create_all before each test)
  - api_client fixture (sync TestClient)
  - Fixture factories: create_master, create_service, create_location,
    create_client, create_activity, create_record

Key differences from generic conftest:
  - Uses sync TestClient, NOT AsyncClient
  - Uses drop_all + create_all, NOT rollback
  - Uses fixture-based factories, NOT factory_boy
  - Uses tempfile for DB, NOT fixed path (parallel-safe)
"""

import asyncio
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

# ─── Test Database ──────────────────────────────────────────────────────────────

# Use a temporary file for SQLite so connections work across event loops.
# In-memory SQLite (`:memory:`) creates a new database per connection, and
# `asyncio.run()` in `reset_db` runs in a different event loop than the
# TestClient's lifespan, causing "no such table" errors.
_db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_db_file.close()
_TEST_DB_URL = f"sqlite+aiosqlite:///{_db_file.name}"

os.environ["DATABASE_URL"] = _TEST_DB_URL
os.environ["ENV_FILE"] = ".env.test"


# ─── Database Reset ─────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_db():
    """Drop and recreate all tables before each test for isolation.

    This ensures zero data leaking between tests — each test starts with a
    clean database. Uses `asyncio.run()` because the shared `db_manager`
    engine is async but the API tests are sync.
    """
    from src.db import db_manager
    from src.db.base import Base
    from src.models import (  # noqa: F401
        Activity, Client, Location, Master, Material,
        Payment, Photo, Record, Service, Tag, Tariff,
        User, Visit, Visitor,
    )

    async def _reset() -> None:
        async with db_manager.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_reset())


# ─── HTTP Client ────────────────────────────────────────────────────────────────

@pytest.fixture
def api_client():
    """Shared TestClient — one per test."""
    from src.main import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c


# ─── Fixture Factories ──────────────────────────────────────────────────────────

@pytest.fixture
def create_master(api_client):
    """Factory: creates a master via API."""
    def factory(**overrides):
        payload = {
            "first_name": "Test",
            "last_name": "Master",
            "color": "#5B8C7A",
            "position": "мастер",
            "specialty": "живопись",
            **overrides,
        }
        resp = api_client.post("/api/v1/masters", json=payload)
        assert resp.status_code == 201, f"create_master failed: {resp.text}"
        return resp.json()
    return factory


@pytest.fixture
def create_service(api_client):
    """Factory: creates a service via API."""
    def factory(**overrides):
        payload = {
            "title": "Test Service",
            "description": "Test",
            "image_url": "https://example.com/test.jpg",
            "specialty": "живопись",
            "min_age": 6,
            "max_age": 99,
            "duration": 90,
            "record_info": "Test info",
            **overrides,
        }
        resp = api_client.post("/api/v1/services", json=payload)
        assert resp.status_code == 201, f"create_service failed: {resp.text}"
        return resp.json()
    return factory


@pytest.fixture
def create_location(api_client):
    """Factory: creates a location via API."""
    def factory(**overrides):
        payload = {
            "name": "Test Studio",
            "address": "Test Address 1",
            "capacity": 20,
            **overrides,
        }
        resp = api_client.post("/api/v1/locations", json=payload)
        assert resp.status_code == 201, f"create_location failed: {resp.text}"
        return resp.json()
    return factory


@pytest.fixture
def create_client(api_client):
    """Factory: creates a client via API. Uses UUID for unique phone."""
    def factory(**overrides):
        import uuid
        payload = {
            "name": f"Client {uuid.uuid4().hex[:6]}",
            "phone": f"+7999{uuid.uuid4().hex[:7]}",
            "email": None,
            "channel": "telegram",
            **overrides,
        }
        resp = api_client.post("/api/v1/clients", json=payload)
        assert resp.status_code == 201, f"create_client failed: {resp.text}"
        return resp.json()
    return factory


@pytest.fixture
def create_activity(api_client, create_master, create_service, create_location):
    """Factory: creates master + service + location + activity."""
    def factory(**overrides):
        from datetime import UTC, datetime, timedelta
        master = create_master()
        service = create_service()
        location = create_location()
        start = overrides.pop("start", datetime.now(UTC) + timedelta(days=1))
        payload = {
            "master_id": master["id"],
            "service_id": service["id"],
            "location_id": location["id"],
            "start": start.isoformat(),
            "duration": 90,
            "capacity": 10,
            "is_private": False,
            **overrides,
        }
        resp = api_client.post("/api/v1/activities", json=payload)
        assert resp.status_code == 201, f"create_activity failed: {resp.text}"
        return resp.json()
    return factory


@pytest.fixture
def create_record(api_client, create_activity, create_client):
    """Factory: creates activity + client + record with 1 visit."""
    def factory(**overrides):
        activity = create_activity()
        client = create_client()
        payload = {
            "activity_id": activity["id"],
            "client_id": client["id"],
            "comment": "Test record",
            "visits": [{"price": 3500, "status": "waiting"}],
            **overrides,
        }
        resp = api_client.post("/api/v1/records", json=payload)
        assert resp.status_code == 201, f"create_record failed: {resp.text}"
        return resp.json()
    return factory


# ─── DB Verification Helper ────────────────────────────────────────────────────

def query_db(sql: str) -> list[dict]:
    """Execute SQL against the test database.

    Usage:
        rows = query_db("SELECT is_active FROM records WHERE id='...'")
        assert rows[0]["is_active"] == 0
    """
    import sqlite3
    conn = sqlite3.connect(_db_file.name)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql).fetchall()
    conn.close()
    return [dict(r) for r in rows]
