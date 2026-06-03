"""
factory-template.py — Memo project fixture-based factories.

Memo uses pytest fixtures that return callables (NOT factory_boy).
Each factory creates an entity via API and returns the response JSON.

Key pattern: factories are composable.
  create_record → create_activity → create_master + create_service + create_location
  create_record → create_client

Pytest resolves the dependency chain automatically.

Usage in tests:
    def test_something(create_record):
        record = create_record()              # default data
        record = create_record(comment="X")   # override fields
"""

import pytest


# ─── Master Factory ─────────────────────────────────────────────────────────────

@pytest.fixture
def create_master(api_client):
    """Factory: creates a master via API.

    Usage:
        master = create_master()
        master = create_master(first_name="Ольга", color="#FF0000")
    """
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


# ─── Service Factory ────────────────────────────────────────────────────────────

@pytest.fixture
def create_service(api_client):
    """Factory: creates a service via API.

    Usage:
        service = create_service()
        service = create_service(title="Картина маслом", duration=150)
    """
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


# ─── Location Factory ───────────────────────────────────────────────────────────

@pytest.fixture
def create_location(api_client):
    """Factory: creates a location via API.

    Usage:
        location = create_location()
        location = create_location(name="Альпика", capacity=30)
    """
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


# ─── Client Factory ─────────────────────────────────────────────────────────────

@pytest.fixture
def create_client(api_client):
    """Factory: creates a client via API. Uses UUID for unique phone.

    Usage:
        client = create_client()
        client = create_client(name="Анна", phone="+79990001122")
    """
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


# ─── Activity Factory (composable) ──────────────────────────────────────────────

@pytest.fixture
def create_activity(api_client, create_master, create_service, create_location):
    """Factory: creates master + service + location + activity.

    This is a COMPOSABLE factory — it depends on create_master, create_service,
    create_location. Pytest resolves the chain automatically.

    Usage:
        activity = create_activity()
        activity = create_activity(capacity=5, is_private=True)

        from datetime import UTC, datetime, timedelta
        past = datetime.now(UTC) - timedelta(days=1)
        activity = create_activity(start=past)
    """
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


# ─── Record Factory (composable) ────────────────────────────────────────────────

@pytest.fixture
def create_record(api_client, create_activity, create_client):
    """Factory: creates activity + client + record with 1 visit.

    This is the TOP-LEVEL composable factory. It creates the full chain:
    master → service → location → activity → client → record → visit.

    Usage:
        record = create_record()
        record = create_record(comment="VIP client")
        record = create_record(visits=[
            {"price": 3500, "status": "waiting"},
            {"price": 2500, "status": "waiting"},
        ])
    """
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


# ─── Usage Examples ─────────────────────────────────────────────────────────────
#
# # Simple test with full chain:
# def test_create_record(create_record):
#     record = create_record()
#     assert record["status"] == "pending"
#     assert record["seats"] == 1
#
# # Test with overrides:
# def test_private_activity(create_activity):
#     activity = create_activity(is_private=True, capacity=5)
#     assert activity["is_private"] is True
#     assert activity["capacity"] == 5
#
# # Test with multiple records:
# def test_multiple_records(create_record):
#     r1 = create_record()
#     r2 = create_record()
#     assert r1["id"] != r2["id"]
#
# # Test with specific client:
# def test_specific_client(create_activity, create_client, api_client):
#     activity = create_activity()
#     client = create_client(name="Анна Иванова", phone="+79990001122")
#     resp = api_client.post("/api/v1/records", json={
#         "activity_id": activity["id"],
#         "client_id": client["id"],
#         "visits": [{"price": 3500}],
#     })
#     assert resp.status_code == 201
